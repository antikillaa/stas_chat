# python
import os
import re
import asyncio
import random
import base64
import io
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from openai import OpenAI
from PIL import Image
import requests
from personas import PERSONA_FILES, available_personas, load_persona

load_dotenv()

AI_MODEL = os.getenv("AI_MODEL", "google/gemma-4-26b-a4b")
MAX_HISTORY = 20
BASE_CHANCE = 0.1
DEFAULT_TONE = "natural"
DEFAULT_PERSONA = "personal"
TONE_PROMPTS = {
    "natural": "Говори естественно, прямо и доброжелательно.",
    "calm": "Говори спокойно, взвешенно и поддерживающе.",
    "warm": "Говори тепло, по-человечески и с лёгкой эмпатией.",
    "professional": "Говори профессионально, структурированно и без лишней неформальности.",
    "concise": "Отвечай максимально коротко и по существу.",
    "playful": "Допускай лёгкий уместный юмор, но оставайся уважительным.",
}

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

chat_memory: dict[int, dict] = {}

def update_history(chat_id: int, role: str, text: str):
    mem = chat_memory.setdefault(chat_id, {"history": [], "mode": "stylish", "tone": DEFAULT_TONE, "persona": DEFAULT_PERSONA})
    
    # Проверяем последнюю роль, чтобы избежать дублирования
    if mem["history"] and mem["history"][-1]["role"] == role:
        # Если последняя роль такая же, заменяем сообщение
        mem["history"][-1]["content"] = text
    else:
        # Добавляем новое сообщение
        mem["history"].append({"role": role, "content": text})
    
    # Обрезаем историю
    mem["history"] = mem["history"][-MAX_HISTORY:]

async def analyze_image(image_url: str, user_msg: str = "") -> str:
    """Анализ изображения через vision модель"""
    try:
        # Скачиваем изображение
        response = requests.get(image_url)
        image = Image.open(io.BytesIO(response.content))
        
        # Конвертируем в base64
        buffered = io.BytesIO()
        image.save(buffered, format="JPEG")
        img_base64 = base64.b64encode(buffered.getvalue()).decode()
        
        # Отправляем на анализ (если модель поддерживает vision)
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"Опиши изображение в моем стиле: {load_persona(DEFAULT_PERSONA)[:200]}... {user_msg}"},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"}}
                ]
            }
        ]
        
        response = client.chat.completions.create(
            model=AI_MODEL,
            messages=messages,
            max_tokens=300
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Брат, не могу разобрать картинку: {str(e)}"

async def generate_reply(chat_id: int, user_msg: str) -> str:
    try:
        mode = chat_memory.get(chat_id, {}).get("mode", "stylish")
        tone = chat_memory.get(chat_id, {}).get("tone", DEFAULT_TONE)
        persona_name = chat_memory.get(chat_id, {}).get("persona", DEFAULT_PERSONA)
        system_prompt = (
            f"Ты — это я. Общайся в моем стиле.\n"
            f"Текущий тон: {TONE_PROMPTS[tone]}\n\nМой стиль:\n{load_persona(persona_name)}\n"
        )
        system_prompt += "Отвечай коротко, естественно и как я бы сказал." if mode == "stylish" \
                         else "Отвечай подробно, развернуто и объясняй все детали."

        messages = [{"role": "system", "content": system_prompt}]
        
        # Добавляем историю с проверкой чередования ролей
        if chat_id in chat_memory:
            history = chat_memory[chat_id]["history"]
            # Проверяем чередование ролей
            filtered_history = []
            last_role = None
            for msg in history:
                if msg["role"] != last_role:
                    filtered_history.append(msg)
                    last_role = msg["role"]
            messages.extend(filtered_history)
        
        messages.append({"role": "user", "content": user_msg})

        response = client.chat.completions.create(model=AI_MODEL, messages=messages)
        reply = response.choices[0].message.content
        
        if not reply or not reply.strip():
            return "Наверное Леша опять ерунду написал 🙄"
        
        reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL).strip()
        
        if not reply:
            reply = "Леша опять рыгнул, как обычно 😒"
        
        update_history(chat_id, "assistant", reply)
        return reply
    except Exception as e:
        return f"Леша опять намудрил: {str(e)}"

BOT_NAME_RE = re.compile(
    r"(?<!\w)(?:стас\s*п|стасян(?:а|у|ом|е)?|сасян(?:а|у|ом|е)?|стас(?:а|у|ом|е)?)(?!\w)",
    re.IGNORECASE,
)
PRAISES = [
    "О, брат, молодец 👍", "Так держать, красавчик 💪", "Красиво получилось 😎",
    "Вот это уровень 👏", "Брат, огонь 🔥", "Ты прям на стиле 😏",
    "Ну ты загнул, круто 👌", "Брат, зачёт 👊", "Скиньте фото члена 😏",
]

@dp.message(Command("reset"))
async def reset_chat(msg: types.Message):
    chat_memory[msg.chat.id] = {"history": [], "mode": "stylish", "tone": DEFAULT_TONE, "persona": DEFAULT_PERSONA}
    await msg.answer("История чата очищена ✅, режим сброшен на 'stylish'.")

@dp.message(Command("mode"))
async def change_mode(msg: types.Message):
    parts = (msg.text or "").split()
    if len(parts) < 2 or parts[1] not in ("stylish", "detailed"):
        await msg.answer("Используй: /mode stylish или /mode detailed")
        return
    chat_memory.setdefault(msg.chat.id, {"history": [], "mode": "stylish", "tone": DEFAULT_TONE, "persona": DEFAULT_PERSONA})["mode"] = parts[1]
    await msg.answer(f"Режим изменен на '{parts[1]}' ✅")

@dp.message(Command("tone"))
async def change_tone(msg: types.Message):
    parts = (msg.text or "").split()
    available_tones = ", ".join(TONE_PROMPTS)
    memory = chat_memory.setdefault(
        msg.chat.id, {"history": [], "mode": "stylish", "tone": DEFAULT_TONE, "persona": DEFAULT_PERSONA}
    )
    if len(parts) < 2 or parts[1] == "status":
        await msg.answer(f"Текущий тон: {memory.get('tone', DEFAULT_TONE)}. Доступно: {available_tones}")
        return
    tone = parts[1].lower()
    if tone not in TONE_PROMPTS:
        await msg.answer(f"Используй: /tone {available_tones} или /tone status")
        return
    memory["tone"] = tone
    await msg.answer(f"Тон изменен на '{tone}' ✅")

@dp.message(Command("persona"))
async def change_persona(msg: types.Message):
    parts = (msg.text or "").split()
    memory = chat_memory.setdefault(
        msg.chat.id, {"history": [], "mode": "stylish", "tone": DEFAULT_TONE, "persona": DEFAULT_PERSONA}
    )
    if len(parts) < 2 or parts[1] == "status":
        await msg.answer(f"Текущая персона: {memory.get('persona', DEFAULT_PERSONA)}. Доступно: {available_personas()}")
        return
    persona_name = parts[1].lower()
    if persona_name not in PERSONA_FILES:
        await msg.answer(f"Используй: /persona {available_personas()} или /persona status")
        return
    memory["persona"] = persona_name
    await msg.answer(f"Персона изменена на '{persona_name}' ✅")

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

        # Check common forms of the owner's name.
        if not mentioned:
            name_mention = BOT_NAME_RE.search(text)
            if name_mention:
                text = (text[:name_mention.start()] + text[name_mention.end():]).strip()
                mentioned = True

        # check reply to bot
        if not mentioned and msg.reply_to_message:
            if getattr(msg.reply_to_message.from_user, "id", None) == me.id:
                mentioned = True

    # обработка изображений
    if msg.photo and mentioned:
        # Получаем URL изображения
        photo = msg.photo[-1]  # берем самое большое разрешение
        file_info = await bot.get_file(photo.file_id)
        image_url = f"https://api.telegram.org/file/bot{bot.token}/{file_info.file_path}"
        
        await bot.send_chat_action(chat_id, "typing")
        reply = await analyze_image(image_url, text)
        await msg.answer(reply)
        return

    # обработка изображений без текста (media_only) - только в приватных чатах или при упоминании
    if msg.photo and not text.strip() and (msg.chat.type == "private" or mentioned):
        # Получаем URL изображения
        photo = msg.photo[-1]  # берем самое большое разрешение
        file_info = await bot.get_file(photo.file_id)
        image_url = f"https://api.telegram.org/file/bot{bot.token}/{file_info.file_path}"
        
        await bot.send_chat_action(chat_id, "typing")
        reply = await analyze_image(image_url, "")
        await msg.answer(reply)
        return

    if not mentioned:
        return

    # Проверяем, есть ли текст для обработки
    if not text or not text.strip():
        return

    update_history(chat_id, "user", text)
    await bot.send_chat_action(chat_id, "typing")
    await asyncio.sleep(1)
    
    # Обычный ответ
    reply = await generate_reply(chat_id, text)
    if reply and reply.strip():
        await msg.answer(reply)
    else:
        await msg.answer("Наверное Леша опять ерунду написал 🙄")

async def main():
    print(f"Bot started (polling) with model: {AI_MODEL}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
