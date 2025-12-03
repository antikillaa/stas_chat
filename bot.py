import os
import random
import re
import asyncio
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiohttp import web
from openai import OpenAI

from keep_alive import keep_alive

# ------------------------------
# ENV
# ------------------------------
load_dotenv()
TG_TOKEN = os.getenv("TG_TOKEN")
HF_TOKEN = os.getenv("HF_TOKEN")
PUBLIC_URL = os.getenv("PUBLIC_URL")

if not TG_TOKEN:
    raise RuntimeError("TG_TOKEN missing")
if not HF_TOKEN:
    raise RuntimeError("HF_TOKEN missing")
if not PUBLIC_URL:
    raise RuntimeError("PUBLIC_URL missing")

bot = Bot(TG_TOKEN)
dp = Dispatcher()

# ------------------------------
# HuggingFace
# ------------------------------
client = OpenAI(
    base_url="https://router.huggingface.co/v1",
    api_key=HF_TOKEN,
)

# ------------------------------
# Persona
# ------------------------------
with open("persona.txt", "r", encoding="utf-8") as f:
    persona = f.read()

# ------------------------------
# Memory
# ------------------------------
chat_memory = {}  # {chat_id: {"history": [], "mode": "stylish"}}
MAX_HISTORY = 20


def update_history(chat_id: int, role: str, text: str):
    chat_memory.setdefault(chat_id, {"history": [], "mode": "stylish"})
    chat_memory[chat_id]["history"].append({"role": role, "content": text})
    chat_memory[chat_id]["history"] = chat_memory[chat_id]["history"][-MAX_HISTORY:]


# ------------------------------
# LLM Generation
# ------------------------------
async def generate_reply(chat_id: int, text: str) -> str:
    mode = chat_memory.get(chat_id, {}).get("mode", "stylish")

    system_prompt = (
        f"Ты — это я. Общайся в моем стиле.\n"
        f"Мой стиль:\n{persona}\n"
    )

    if mode == "stylish":
        system_prompt += "Отвечай коротко, естественно и как я бы сказал."
    else:
        system_prompt += "Отвечай развернуто и подробно."

    messages = [{"role": "system", "content": system_prompt}]

    if chat_id in chat_memory:
        messages += chat_memory[chat_id]["history"]

    messages.append({"role": "user", "content": text})

    response = client.chat.completions.create(
        model="deepseek-ai/DeepSeek-R1",
        messages=messages
    )

    reply = response.choices[0].message.content
    reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL).strip()

    update_history(chat_id, "assistant", reply)
    return reply


# ------------------------------
# Praise auto-reactions
# ------------------------------
PRAISES = [
    "О, брат, молодец 👍",
    "Красиво получилось 😎",
    "Ты прям на стиле 😏",
    "Брат, огонь 🔥",
    "Зачёт 👊",
]

POSITIVE_WORDS = [
    "сделал", "готово", "успех", "класс", "получилось", "супер", "отлично", "заработало"
]

BASE_CHANCE = 0.2
KEYWORD_CHANCE = 0.9

@dp.message(F.text)
async def auto_praise(msg: types.Message):
    me = await bot.get_me()

    # ignore bot messages
    if msg.from_user.id == me.id:
        return

    text = msg.text.lower()

    has_keyword = any(w in text for w in POSITIVE_WORDS)
    chance = KEYWORD_CHANCE if has_keyword else BASE_CHANCE

    # only in groups
    if msg.chat.type == "private":
        return

    if random.random() < chance:
        await asyncio.sleep(0.5)
        await msg.answer(random.choice(PRAISES))


# ------------------------------
# Handle text messages (bot mentions)
# ------------------------------
bot_names = ["Стасян", "Стасяне", "Стасяну", "Стасяном"]

@dp.message(F.text)
async def handle_text(msg: types.Message):
    me = await bot.get_me()
    text = msg.text or ""
    mentioned = False

    # private chat — always answer
    if msg.chat.type == "private":
        mentioned = True

    # @username mention
    elif msg.entities:
        for ent in msg.entities:
            if ent.type == "mention":
                mention = text[ent.offset:ent.offset+ent.length]
                if mention.lower() == f"@{me.username.lower()}":
                    mentioned = True
                    text = text.replace(mention, "").strip()

    # name mention
    if not mentioned:
        clean = re.sub(r"[^\w\s]", "", text.lower())
        for name in bot_names:
            if name.lower() in clean.split():
                mentioned = True

    # reply to bot
    if not mentioned and msg.reply_to_message:
        if msg.reply_to_message.from_user.id == me.id:
            mentioned = True

    if not mentioned:
        return

    update_history(msg.chat.id, "user", text)

    await bot.send_chat_action(msg.chat.id, "typing")
    await asyncio.sleep(1)

    reply = await generate_reply(msg.chat.id, text)
    await msg.answer(reply)


# ------------------------------
# PHOTO HANDLER
# ------------------------------
@dp.message(F.photo)
async def handle_photo(msg: types.Message):
    me = await bot.get_me()
    caption = msg.caption or ""
    mentioned = False

    if msg.chat.type == "private":
        mentioned = True
    elif caption and f"@{me.username.lower()}" in caption.lower():
        mentioned = True
    elif msg.reply_to_message and msg.reply_to_message.from_user.id == me.id:
        mentioned = True

    if not mentioned:
        return

    file_id = msg.photo[-1].file_id
    file = await bot.get_file(file_id)
    file_url = f"https://api.telegram.org/file/bot{TG_TOKEN}/{file.file_path}"

    update_history(msg.chat.id, "user", f"[Фото] {caption}")

    await bot.send_chat_action(msg.chat.id, "typing")
    await asyncio.sleep(1)

    reply = await generate_reply(
        msg.chat.id,
        f"Пользователь отправил фото: {file_url}\nОписание: {caption}"
    )
    await msg.answer(reply)


# ------------------------------
# VIDEO
# ------------------------------
@dp.message(F.video)
async def handle_video(msg: types.Message):
    me = await bot.get_me()
    caption = msg.caption or ""
    mentioned = False

    if msg.chat.type == "private":
        mentioned = True
    elif caption and f"@{me.username.lower()}" in caption.lower():
        mentioned = True
    elif msg.reply_to_message and msg.reply_to_message.from_user.id == me.id:
        mentioned = True

    if not mentioned:
        return

    file = await bot.get_file(msg.video.file_id)
    file_url = f"https://api.telegram.org/file/bot{TG_TOKEN}/{file.file_path}"

    update_history(msg.chat.id, "user", f"[Видео] {caption}")

    await bot.send_chat_action(msg.chat.id, "typing")
    await asyncio.sleep(1)

    reply = await generate_reply(
        msg.chat.id,
        f"Пользователь отправил видео: {file_url}\nОписание: {caption}"
    )
    await msg.answer(reply)


# ------------------------------
# Commands
# ------------------------------
@dp.message(Command("reset"))
async def reset(msg: types.Message):
    chat_memory[msg.chat.id] = {"history": [], "mode": "stylish"}
    await msg.answer("История очищена.")


@dp.message(Command("mode"))
async def mode(msg: types.Message):
    parts = msg.text.split()
    if len(parts) < 2:
        return await msg.answer("Используй: /mode stylish или /mode detailed")
    m = parts[1]
    if m not in ["stylish", "detailed"]:
        return await msg.answer("Некорректный режим.")
    chat_memory.setdefault(msg.chat.id, {"history": [], "mode": "stylish"})["mode"] = m
    await msg.answer(f"Режим установлен: {m}")


# ------------------------------
# Webhook application
# ------------------------------
app = web.Application()


async def webhook(request):
    data = await request.json()
    update = types.Update.model_validate(data)
    await dp.feed_update(bot, update)
    return web.Response(text="OK")


async def health(request):
    return web.Response(text="OK")


app.router.add_post(f"/webhook/{TG_TOKEN}", webhook)
app.router.add_get("/", health)
app.router.add_get("/health", health)


async def on_startup(app):
    asyncio.create_task(keep_alive())  # ping every minute
    url = f"{PUBLIC_URL}/webhook/{TG_TOKEN}"
    await bot.set_webhook(url)
    print("Webhook set:", url)


async def on_shutdown(app):
    await bot.delete_webhook()


app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)


if __name__ == "__main__":
    PORT = int(os.getenv("PORT", 8000))
    web.run_app(app, host="0.0.0.0", port=PORT)