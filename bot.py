import os
import random
import re
import asyncio
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from openai import OpenAI

# --- Настройка ---
load_dotenv()
TG_TOKEN = os.getenv("TG_TOKEN")
HF_TOKEN = os.getenv("HF_TOKEN")

if not TG_TOKEN or not HF_TOKEN:
    raise RuntimeError("TG_TOKEN или HF_TOKEN не найден!")

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
    system_prompt = f"Ты — это я. Общайся в моем стиле.\nМой стиль:\n{persona}\n"
    system_prompt += "Отвечай коротко, естественно и как я бы сказал." if mode == "stylish" else "Отвечай подробно, развернуто и объясняй все детали."

    messages = [{"role": "system", "content": system_prompt}]
    if chat_id in chat_memory:
        messages.extend(chat_memory[chat_id]["history"])
    messages.append({"role": "user", "content": user_msg})

    response = client.chat.completions.create(
        model="deepseek-ai/DeepSeek-R1",
        messages=messages
    )

    assistant_reply = response.choices[0].message.content
    assistant_reply = re.sub(r"<think>.*?</think>", "", assistant_reply, flags=re.DOTALL).strip()
    update_history(chat_id, "assistant", assistant_reply)
    return assistant_reply

# --- Имя бота ---
bot_names = ["Стасян", "Стасяна", "Стасяну", "Стасяне", "Стасяном", "Стасяне"]

# --- Авто-похвалы ---
PRAISES = [
    "О, брат, молодец 👍",
    "Так держать, красавчик 💪",
    "Красиво получилось 😎",
    "Вот это уровень 👏",
    "Брат, огонь 🔥",
    "Ты прям на стиле 😏",
    "Ну ты загнул, круто 👌",
    "Брат, зачёт 👊",
]

BASE_CHANCE = 0.5  # 50% шанс

@dp.message()
async def auto_praise(msg: types.Message):
    me = await bot.get_me()
    if msg.from_user.id == me.id:
        return  # игнорируем свои сообщения
    if msg.photo or msg.video or msg.animation:
        if random.random() < BASE_CHANCE:
            praise = random.choice(PRAISES)
            await bot.send_chat_action(msg.chat.id, "typing")
            await asyncio.sleep(random.uniform(0.5, 1.5))
            await msg.reply(praise)

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
    await msg.answer(f"Режим ответа изменен на '{parts[1]}' ✅")

# --- Ответ на текстовые сообщения ---
@dp.message()
async def handle_text(msg: types.Message):
    chat_id = msg.chat.id
    text = msg.text or ""
    me = await bot.get_me()
    mentioned = msg.chat.type == "private" or (msg.reply_to_message and msg.reply_to_message.from_user.id == me.id)

    if not mentioned:
        return

    update_history(chat_id, "user", text)
    await bot.send_chat_action(chat_id, "typing")
    await asyncio.sleep(1)
    reply = await generate_reply(chat_id, text)
    await asyncio.sleep(0.2)
    await msg.answer(reply)

# --- Keep-alive ---
async def keep_alive():
    while True:
        try:
            await bot.get_me()
        except Exception:
            pass
        await asyncio.sleep(300)

# --- Запуск ---
async def main():
    print("Бот запущен на long polling...")
    asyncio.create_task(keep_alive())
    await dp.start_polling(bot)
    asyncio.create_task(keep_alive())

if __name__ == "__main__":
    asyncio.run(main())