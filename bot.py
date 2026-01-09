# python
import os
import re
import asyncio
import random
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from openai import OpenAI

AI_MODEL = os.getenv("AI_MODEL", "llama2")
MAX_HISTORY = 20
BASE_CHANCE = 0.2

load_dotenv()
TG_TOKEN = os.getenv("TG_TOKEN")
HF_TOKEN = os.getenv("HF_TOKEN")
if not TG_TOKEN:
    raise RuntimeError("TG_TOKEN не найден в .env")
if not HF_TOKEN:
    raise RuntimeError("HF_TOKEN не найден в .env")

bot = Bot(TG_TOKEN)
dp = Dispatcher()

LM_STUDIO_URL = os.getenv("LM_STUDIO_URL", "http://127.0.0.1:1234/v1")
client = OpenAI(base_url=LM_STUDIO_URL, api_key="lm-studio")

with open("persona.txt", "r", encoding="utf-8") as f:
    persona = f.read()

chat_memory: dict[int, dict] = {}

def update_history(chat_id: int, role: str, text: str):
    mem = chat_memory.setdefault(chat_id, {"history": [], "mode": "stylish"})
    mem["history"].append({"role": role, "content": text})
    mem["history"] = mem["history"][-MAX_HISTORY:]

async def generate_reply(chat_id: int, user_msg: str) -> str:
    mode = chat_memory.get(chat_id, {}).get("mode", "stylish")
    system_prompt = f"Ты — это я. Общайся в моем стиле.\nМой стиль:\n{persona}\n"
    system_prompt += "Отвечай коротко, естественно и как я бы сказал." if mode == "stylish" \
                     else "Отвечай подробно, развернуто и объясняй все детали."

    messages = [{"role": "system", "content": system_prompt}]
    if chat_id in chat_memory:
        messages.extend(chat_memory[chat_id]["history"])
    messages.append({"role": "user", "content": user_msg})

    response = client.chat.completions.create(model=AI_MODEL, messages=messages)
    reply = response.choices[0].message.content
    reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL).strip()
    update_history(chat_id, "assistant", reply)
    return reply

bot_names = ["Стасян", "Стасяна", "Стасяну", "Стасяне", "Стасяном", "Стасяне"]
PRAISES = [
    "О, брат, молодец 👍", "Так держать, красавчик 💪", "Красиво получилось 😎",
    "Вот это уровень 👏", "Брат, огонь 🔥", "Ты прям на стиле 😏",
    "Ну ты загнул, круто 👌", "Брат, зачёт 👊", "Скиньте фото члена 😏",
]

@dp.message(Command("reset"))
async def reset_chat(msg: types.Message):
    chat_memory[msg.chat.id] = {"history": [], "mode": "stylish"}
    await msg.answer("История чата очищена ✅, режим сброшен на 'stylish'.")

@dp.message(Command("mode"))
async def change_mode(msg: types.Message):
    parts = (msg.text or "").split()
    if len(parts) < 2 or parts[1] not in ("stylish", "detailed"):
        await msg.answer("Используй: /mode stylish или /mode detailed")
        return
    chat_memory.setdefault(msg.chat.id, {"history": [], "mode": "stylish"})["mode"] = parts[1]
    await msg.answer(f"Режим изменен на '{parts[1]}' ✅")

def _clean_text_for_name_check(text: str) -> str:
    return re.sub(r"[^\w\s]", "", text.lower())

@dp.message()
async def handle_message(msg: types.Message):
    raw_text = msg.text or msg.caption or ""

    print(
        "FROM:",
        msg.from_user.username,
        "IS_BOT:",
        msg.from_user.is_bot,
        "TEXT:",
        msg.text,
        "ENTITIES:",
        msg.entities,
    )

    print(
        "TYPE:",
        "text" if msg.text else
        "caption" if msg.caption else
        "media_only"
    )

    chat_id = msg.chat.id
    text = raw_text.strip()
    me = await bot.get_me()
    mentioned = False

    # praise for media
    if msg.photo or msg.video or msg.animation:
        if random.random() < BASE_CHANCE:
            await msg.answer(random.choice(PRAISES))

    if msg.chat.type == "private":
        mentioned = True
    else:
        # check @mention entities
        if msg.entities:
            for ent in msg.entities:
                if ent.type == "mention":
                    mention_text = text[ent.offset: ent.offset + ent.length]
                    if mention_text.lower() == f"@{me.username.lower()}":
                        text = text.replace(mention_text, "").strip()
                        mentioned = True
                        break

        # check name tokens
        if not mentioned:
            clean = _clean_text_for_name_check(text)
            for name in bot_names:
                if name.lower() in clean.split():
                    text = re.sub(re.escape(name), "", text, flags=re.IGNORECASE).strip()
                    mentioned = True
                    break

        # check reply to bot
        if not mentioned and msg.reply_to_message:
            if getattr(msg.reply_to_message.from_user, "id", None) == me.id:
                mentioned = True

    if not mentioned:
        return

    update_history(chat_id, "user", text)
    await bot.send_chat_action(chat_id, "typing")
    await asyncio.sleep(1)
    reply = await generate_reply(chat_id, text)
    await msg.answer(reply)

async def main():
    print("Bot started (polling). LM Studio must be running on port 1234.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
