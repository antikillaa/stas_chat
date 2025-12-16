import os
import re
import asyncio
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from openai import OpenAI

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

# --- LM Studio / Local ---
client = OpenAI(
    base_url="http://127.0.0.1:1234/v1",
    api_key="lm-studio"  # LM Studio не проверяет ключ
)

# --- Persona ---
with open("persona.txt", "r", encoding="utf-8") as f:
    persona = f.read()

# --- Память чата ---
chat_memory = {}
MAX_HISTORY = 20

def update_history(chat_id: int, role: str, text: str):
    if chat_id not in chat_memory:
        chat_memory[chat_id] = {"history": [], "mode": "stylish"}
    chat_memory[chat_id]["history"].append({"role": role, "content": text})
    chat_memory[chat_id]["history"] = chat_memory[chat_id]["history"][-MAX_HISTORY:]

# --- Генерация ответа ---
async def generate_reply(chat_id: int, user_msg: str) -> str:
    mode = chat_memory.get(chat_id, {}).get("mode", "stylish")

    system_prompt = (
        f"Ты — это я. Общайся в моем стиле.\n"
        f"Мой стиль:\n{persona}\n"
    )
    if mode == "stylish":
        system_prompt += "Отвечай коротко, естественно и как я бы сказал."
    else:
        system_prompt += "Отвечай подробно, развернуто и объясняй все детали."

    messages = [{"role": "system", "content": system_prompt}]

    if chat_id in chat_memory:
        messages.extend(chat_memory[chat_id]["history"])

    messages.append({"role": "user", "content": user_msg})

    response = client.chat.completions.create(
        model="openai/gpt-oss-20b",  # или любое название модели LM Studio
        messages=messages,
    )

    assistant_reply = response.choices[0].message.content
    assistant_reply = re.sub(r"<think>.*?</think>", "", assistant_reply, flags=re.DOTALL).strip()

    update_history(chat_id, "assistant", assistant_reply)
    return assistant_reply

# --- Имя бота ---
bot_names = ["Стасян", "Стасяна", "Стасяну", "Стасяне", "Стасяном", "Стасяне"]

# --- Список похвал ---
import random

PRAISES = [
    "О, брат, молодец 👍",
    "Так держать, красавчик 💪",
    "Красиво получилось 😎",
    "Вот это уровень 👏",
    "Брат, огонь 🔥",
    "Ты прям на стиле 😏",
    "Ну ты загнул, круто 👌",
    "Брат, зачёт 👊",
    "Скиньте фото члена 😏",
]

POSITIVE_KEYWORDS = [
    "сделал", "успех", "готово", "класс", "пофиксил",
    "отлично", "супер", "заработало", "получилось"
]

BASE_CHANCE = 0.5


# --- Команды ---
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
    await msg.answer(f"Режим изменен на '{parts[1]}' ✅")


# --- Обработка сообщений ---
@dp.message()
async def handle_message(msg: types.Message):
    chat_id = msg.chat.id
    text = msg.text or ""
    mentioned = False
    me = await bot.get_me()

    # Автоматическая похвала за медиа
    if msg.photo or msg.video or msg.animation:
        if random.random() < BASE_CHANCE:
            await msg.answer(random.choice(PRAISES))

    # Личные чаты — реагирует всегда
    if msg.chat.type == "private":
        mentioned = True
    else:
        # @упоминание
        if msg.entities:
            for ent in msg.entities:
                if ent.type == "mention":
                    mention_text = text[ent.offset: ent.offset + ent.length]
                    if mention_text.lower() == f"@{me.username.lower()}":
                        text = text.replace(mention_text, "").strip()
                        mentioned = True

        # имя в тексте
        if not mentioned:
            clean = re.sub(r"[^\w\s]", "", text.lower())
            for name in bot_names:
                if name.lower() in clean.split():
                    text = re.sub(name, "", text, flags=re.IGNORECASE).strip()
                    mentioned = True
                    break

        # reply на сообщение бота
        if not mentioned and msg.reply_to_message:
            if msg.reply_to_message.from_user.id == me.id:
                mentioned = True

    if not mentioned:
        return

    update_history(chat_id, "user", text)

    await bot.send_chat_action(chat_id, "typing")
    await asyncio.sleep(1)

    reply = await generate_reply(chat_id, text)
    await msg.answer(reply)


# --- Запуск бота (polling) ---
async def main():
    print("Bot started (polling). LM Studio must be running on port 1234.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())