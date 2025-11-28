import asyncio
import os
import re
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types
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

# Hugging Face Inference API
client = OpenAI(
    base_url="https://router.huggingface.co/v1",
    api_key=HF_TOKEN,
)

# Загружаем persona (твой стиль)
with open("persona.txt", "r", encoding="utf-8") as f:
    persona = f.read()

# Память чата: {chat_id: {"history": [], "mode": "stylish"}}
chat_memory = {}
MAX_HISTORY = 20

# --- Функции ---
def update_history(chat_id: int, role: str, text: str):
    if chat_id not in chat_memory:
        chat_memory[chat_id] = {"history": [], "mode": "stylish"}
    chat_memory[chat_id]["history"].append({"role": role, "content": text})
    chat_memory[chat_id]["history"] = chat_memory[chat_id]["history"][-MAX_HISTORY:]

def clean_reply(text: str) -> str:
    """Убираем все теги <think>...</think>"""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

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
    assistant_reply = clean_reply(assistant_reply)  # убираем <think>
    update_history(chat_id, "assistant", assistant_reply)
    return assistant_reply

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

    # В группах реагируем только на упоминание имени или @username
    mentioned = False
    if msg.chat.type != "private":
        me = await bot.get_me()
        bot_names = ["Стасян", "Стасяна", "Стасяну", "Стасяне", "Стасяном", "Стасяне"]

        # Проверка @username
        if msg.entities:
            for ent in msg.entities:
                if ent.type == "mention":
                    mention_text = text[ent.offset: ent.offset + ent.length]
                    if mention_text.lower() == f"@{me.username.lower()}":
                        mentioned = True
                        text = text.replace(mention_text, "").strip()
                        break

        # Проверка имени бота
        if not mentioned:
            clean_text = re.sub(r"[^\w\s]", "", text.lower())
            words = clean_text.split()
            for name in bot_names:
                if name.lower() in words:
                    mentioned = True
                    text = re.sub(name, "", text, flags=re.IGNORECASE).strip()
                    break

    if msg.chat.type != "private" and not mentioned:
        return  # игнорируем, если не упомянули

    update_history(chat_id, "user", text)

    # Имитация typing
    await bot.send_chat_action(chat_id, "typing")
    await asyncio.sleep(1)

    # Генерация ответа
    reply = await generate_reply(chat_id, text)
    await asyncio.sleep(0.2)

    await msg.answer(reply)

# --- Запуск ---
async def main():
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())