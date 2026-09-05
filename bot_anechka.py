import os
import re
import time
import asyncio
import random
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from openai import OpenAI

# =====================
# CONFIG
# =====================
load_dotenv()

TG_TOKEN = os.getenv("TG_TOKEN_ANN")
LM_STUDIO_URL = os.getenv("LM_STUDIO_URL", "http://127.0.0.1:1234/v1")
AI_MODEL = os.getenv("AI_MODEL")

if not TG_TOKEN:
    raise RuntimeError("TG_TOKEN_ANN not found")

bot = Bot(TG_TOKEN)
dp = Dispatcher()

client = OpenAI(
    base_url=LM_STUDIO_URL,
    api_key="lm-studio"
)

# =====================
# PERSONA
# =====================
with open("persona_ann.txt", "r", encoding="utf-8") as f:
    PERSONA = f.read()

# =====================
# MEMORY
# =====================
MAX_HISTORY = 25

chat_memory = {}        # chat_id -> history
stasyan_memory = {}     # chat_id -> list of Stasyan messages
last_ann_init = {}      # chat_id -> timestamp

# =====================
# NAMES
# =====================
ANN_NAMES = ["анечка", "аня"]
STASYAN_NAMES = ["стас", "стасян", "stas", "stanislav"]

# =====================
# MOODS
# =====================
MOODS = ["sweet", "sarcastic", "toxic"]

MOOD_PROMPTS = {
    "sweet": "Ты сегодня милая, но всё равно язвительная.",
    "sarcastic": "Ты саркастичная, подкалываешь, закатываешь глаза.",
    "toxic": "Ты пассивно-агрессивная, язвительная, слегка токсичная."
}

def get_mood():
    return random.choices(
        MOODS,
        weights=[0.2, 0.4, 0.4],
        k=1
    )[0]

# =====================
# HELPERS
# =====================
def clean_text(text: str) -> str:
    return re.sub(r"[^\w\s]", "", text.lower())

def update_history(chat_id, role, text):
    chat_memory.setdefault(chat_id, []).append({
        "role": role,
        "content": text
    })
    chat_memory[chat_id] = chat_memory[chat_id][-MAX_HISTORY:]

def remember_stasyan(chat_id, text):
    stasyan_memory.setdefault(chat_id, []).append(text)
    stasyan_memory[chat_id] = stasyan_memory[chat_id][-10:]

def pick_stasyan_quote(chat_id):
    msgs = stasyan_memory.get(chat_id)
    if not msgs:
        return None
    return random.choice(msgs)

# =====================
# GENERATION
# =====================
async def generate_reply(chat_id, user_text):
    mood = get_mood()
    stas_quote = pick_stasyan_quote(chat_id)

    system_prompt = f"""
Ты — Анечка.

{PERSONA}

Текущее настроение: {mood}.
{MOOD_PROMPTS[mood]}

Правила:
- Отвечай коротко
- С сарказмом и подколами
- Иногда пассивно-агрессивно
- Не объясняй, что ты бот
"""

    if stas_quote and random.random() < 0.4:
        system_prompt += f"\nИногда подкалывай Стасяна за его прошлую фразу: «{stas_quote}»"

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(chat_memory.get(chat_id, []))
    messages.append({"role": "user", "content": user_text})

    response = client.chat.completions.create(
        model=AI_MODEL,
        messages=messages
    )

    reply = response.choices[0].message.content
    reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL).strip()

    update_history(chat_id, "assistant", reply)
    return reply

# =====================
# INIT PHRASES
# =====================
ANN_INIT_PHRASES = [
    "Стасян, ты опять исчез. Классика.",
    "Я тут подумала… а ты всегда такой или только сегодня?",
    "Тишина. Даже неловко.",
    "Стасян, ты когда писал — сам понял, что написал?",
    "Ну что, гений, продолжим или ты устал думать?",
]

INIT_CHANCE = 0.04
INIT_COOLDOWN = 60 * 15

# =====================
# HANDLER
# =====================
@dp.message(Command("addtogroup"))
async def add_to_group(msg: types.Message):
    """Send Telegram's official link for adding this bot to a group."""
    me = await bot.get_me()
    if not me.username:
        await msg.answer("Не удалось создать ссылку: у бота нет username.")
        return
    await msg.answer(
        "Добавить меня в группу может её администратор по ссылке:\n"
        f"https://t.me/{me.username}?startgroup=true"
    )

@dp.message()
async def handle_message(msg: types.Message):
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
    raw_text = msg.text or msg.caption or ""
    text = raw_text.strip()
    now = time.time()

    me = await bot.get_me()
    mentioned = False

    # ---- detect Stasyan
    if msg.from_user:
        name = f"{msg.from_user.first_name or ''} {msg.from_user.username or ''}".lower()
        if any(n in name for n in STASYAN_NAMES):
            remember_stasyan(chat_id, text)

    # ---- private
    if msg.chat.type == "private":
        mentioned = True

    else:
        # @mention
        if msg.entities:
            for ent in msg.entities:
                if ent.type == "mention":
                    m = text[ent.offset: ent.offset + ent.length]
                    if m.lower() == f"@{me.username.lower()}":
                        text = text.replace(m, "").strip()
                        mentioned = True
                        break

        # name mention
        if not mentioned:
            clean = clean_text(text)
            if any(n in clean.split() for n in ANN_NAMES):
                mentioned = True
                text = re.sub("|".join(ANN_NAMES), "", text, flags=re.I).strip()

        # reply
        if not mentioned and msg.reply_to_message:
            if msg.reply_to_message.from_user.id == me.id:
                mentioned = True

    # ---- INITIATIVE
    if not mentioned and msg.chat.type != "private":
        last_init = last_ann_init.get(chat_id, 0)
        if now - last_init > INIT_COOLDOWN:
            if random.random() < INIT_CHANCE:
                last_ann_init[chat_id] = now
                await asyncio.sleep(random.uniform(2, 5))
                await msg.answer(random.choice(ANN_INIT_PHRASES))
        return

    # ---- ANSWER
    update_history(chat_id, "user", text)
    await bot.send_chat_action(chat_id, "typing")
    await asyncio.sleep(random.uniform(0.8, 1.5))

    reply = await generate_reply(chat_id, text)
    await msg.answer(reply)

# =====================
# START
# =====================
async def main():
    print(f"Anechka started with model: {AI_MODEL}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
