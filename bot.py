import os
import re
import asyncio
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from openai import OpenAI
from aiohttp import web

# --- Настройка ---
load_dotenv()
TG_TOKEN = os.getenv("TG_TOKEN")
HF_TOKEN = os.getenv("HF_TOKEN")

if not TG_TOKEN:
    raise RuntimeError("TG_TOKEN не найден в .env")
if not HF_TOKEN:
    raise RuntimeError("HF_TOKEN не найден в .env")

bot = Bot(TG_TOKEN)
dp = Dispatcher()

# Hugging Face Inference API
client = OpenAI(
    base_url="https://router.huggingface.co/v1",
    api_key=HF_TOKEN,
)

# --- Persona ---
with open("persona.txt", "r", encoding="utf-8") as f:
    persona = f.read()

# --- Память чата ---
chat_memory = {}  # {chat_id: {"history": [], "mode": "stylish"}}
MAX_HISTORY = 20

def update_history(chat_id: int, role: str, text: str):
    if chat_id not in chat_memory:
        chat_memory[chat_id] = {"history": [], "mode": "stylish"}
    chat_memory[chat_id]["history"].append({"role": role, "content": text})
    chat_memory[chat_id]["history"] = chat_memory[chat_id]["history"][-MAX_HISTORY:]

# --- Генерация ответа ---
async def generate_reply(chat_id: int, user_msg: str) -> str:
    mode = chat_memory.get(chat_id, {}).get("mode", "stylish")
    system_prompt = f"Ты — это я. Общайся в моем стиле.\nМой стиль:\n{persona}\n"
    if mode == "stylish":
        system_prompt += "Отвечай коротко, естественно и как я бы сказал."
    elif mode == "detailed":
        system_prompt += "Отвечай подробно, развернуто и объясняй все детали."

    messages = [{"role": "system", "content": system_prompt}]
    if chat_id in chat_memory:
        messages.extend(chat_memory[chat_id]["history"])
    messages.append({"role": "user", "content": user_msg})

    response = client.chat.completions.create(
        model="deepseek-ai/DeepSeek-R1",
        messages=messages
    )

    assistant_reply = response.choices[0].message.content

    # Убираем теги <think>
    assistant_reply = re.sub(r"<think>.*?</think>", "", assistant_reply, flags=re.DOTALL).strip()

    update_history(chat_id, "assistant", assistant_reply)
    return assistant_reply

# --- Имя бота ---
bot_names = ["Стасян", "Стасяна", "Стасяну", "Стасяне", "Стасяном", "Стасяне"]

# --- Обработчики ---
@dp.message(Command("reset"))
async def reset_chat(msg: types.Message):
    chat_id = msg.chat.id
    chat_memory[chat_id] = {"history": [], "mode": "stylish"}
    await msg.answer("История чата очищена ✅, режим сброшен на 'stylish'.")

@dp.message(Command("mode"))
async def change_mode(msg: types.Message):
    chat_id = msg.chat.id
    parts = msg.text.split()
    if len(parts) < 2 or parts[1] not in ["stylish", "detailed"]:
        await msg.answer("Используй: /mode stylish или /mode detailed")
        return
    chat_memory.setdefault(chat_id, {"history": [], "mode": "stylish"})["mode"] = parts[1]
    await msg.answer(f"Режим ответа изменен на '{parts[1]}' ✅")

@dp.message()
async def handle_message(msg: types.Message):
    chat_id = msg.chat.id
    text = msg.text or ""
    mentioned = False
    me = await bot.get_me()

    # Личные чаты всегда упоминание
    if msg.chat.type == "private":
        mentioned = True
    else:
        # 1️⃣ Проверка @username
        if msg.entities:
            for ent in msg.entities:
                if ent.type == "mention":
                    mention_text = text[ent.offset: ent.offset + ent.length]
                    if mention_text.lower() == f"@{me.username.lower()}":
                        mentioned = True
                        text = text.replace(mention_text, "").strip()
                        break

        # 2️⃣ Проверка имени бота
        if not mentioned:
            clean_text = re.sub(r"[^\w\s]", "", text.lower())
            words = clean_text.split()
            for name in bot_names:
                if name.lower() in words:
                    mentioned = True
                    text = re.sub(name, "", text, flags=re.IGNORECASE).strip()
                    break

        # 3️⃣ Проверка reply_to_message
        if not mentioned and msg.reply_to_message:
            if msg.reply_to_message.from_user.id == me.id:
                mentioned = True

    if not mentioned:
        return  # игнорируем сообщение в группе, если не упомянуты и не reply

    # --- Обновляем историю ---
    update_history(chat_id, "user", text)

    # --- Симуляция typing ---
    await bot.send_chat_action(chat_id, "typing")
    await asyncio.sleep(1)

    # --- Генерация ответа ---
    reply = await generate_reply(chat_id, text)
    await asyncio.sleep(0.2)
    await msg.answer(reply)


# --- Webhook ---
WEBHOOK_PATH = f"/webhook/{TG_TOKEN}"
PORT = int(os.environ.get("PORT", 8000))
PUBLIC_URL = os.environ.get("PUBLIC_URL")


async def telegram_webhook(request):
    data = await request.json()
    update = types.Update.model_validate(data)
    await dp.feed_update(bot, update)
    return web.Response(text="OK")


async def health(request):
    return web.Response(text="OK")


app = web.Application()
app.router.add_post(WEBHOOK_PATH, telegram_webhook)
app.router.add_get("/", health)
app.router.add_get("/health", health)


async def on_startup(app):
    if not PUBLIC_URL:
        raise RuntimeError("PUBLIC_URL не указан в настройках Render!")

    webhook_url = f"{PUBLIC_URL}{WEBHOOK_PATH}"
    await bot.set_webhook(webhook_url)

    print("Webhook установлен:", webhook_url)


async def on_shutdown(app):
    await bot.delete_webhook()


if __name__ == "__main__":
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    web.run_app(app, host="0.0.0.0", port=PORT)