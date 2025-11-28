import os
import asyncio
import re
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from openai import OpenAI
from dotenv import load_dotenv

# --- Настройка ---
load_dotenv()
TG_TOKEN = os.getenv("TG_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # твой публичный URL + /webhook
HF_TOKEN = os.getenv("HF_TOKEN")

if not TG_TOKEN or not WEBHOOK_URL or not HF_TOKEN:
    raise RuntimeError("TG_TOKEN, WEBHOOK_URL или HF_TOKEN не найдены в .env")

bot = Bot(TG_TOKEN, parse_mode="HTML")
dp = Dispatcher()

# Hugging Face client
client = OpenAI(
    base_url="https://router.huggingface.co/v1",
    api_key=HF_TOKEN,
)

# Загружаем persona
with open("persona.txt", "r", encoding="utf-8") as f:
    persona = f.read()

# Память чата
chat_memory = {}
MAX_HISTORY = 20

def update_history(chat_id: int, role: str, text: str):
    if chat_id not in chat_memory:
        chat_memory[chat_id] = {"history": [], "mode": "stylish"}
    chat_memory[chat_id]["history"].append({"role": role, "content": text})
    chat_memory[chat_id]["history"] = chat_memory[chat_id]["history"][-MAX_HISTORY:]

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

    # Обработка тегов <think> от deepsick
    assistant_reply = response.choices[0].message.content
    assistant_reply = re.sub(r"<think>.*?</think>", "", assistant_reply, flags=re.DOTALL).strip()

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

    # Проверка упоминания имени бота
    me = await bot.get_me()
    bot_names = ["Стасян", "Стасяна", "Стасяну", "Стасяне", "Стасяном", "Стасяне"]
    mentioned = False

    if msg.chat.type != "private":
        clean_text = re.sub(r"[^\w\s]", "", text.lower())
        words = clean_text.split()
        if f"@{me.username.lower()}" in text.lower():
            mentioned = True
            text = text.replace(f"@{me.username}", "").strip()
        else:
            for name in bot_names:
                if name.lower() in words:
                    mentioned = True
                    text = re.sub(name, "", text, flags=re.IGNORECASE).strip()
                    break

    if msg.chat.type != "private" and not mentioned:
        return  # игнорируем сообщения без упоминания

    update_history(chat_id, "user", text)
    await msg.answer("⌛ Думаю...")  # имитация typing
    reply = await generate_reply(chat_id, text)
    await msg.answer(reply)

# --- FastAPI Webhook ---
app = FastAPI()

@app.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = types.Update(**data)
    await dp.feed_update(bot, update)
    return JSONResponse(content={"ok": True})

# --- Установка webhook ---
async def set_webhook():
    await bot.delete_webhook()
    await bot.set_webhook(WEBHOOK_URL)

# --- Запуск ---
if __name__ == "__main__":
    import uvicorn
    asyncio.run(set_webhook())
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))