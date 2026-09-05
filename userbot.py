"""Optional Telegram client that can reply from the account owner's name."""
import asyncio
import json
import os
import random
import re
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from telethon import TelegramClient, events
from personas import PERSONA_FILES, load_persona


load_dotenv()

API_ID = os.getenv("TELEGRAM_API_ID")
API_HASH = os.getenv("TELEGRAM_API_HASH")
LM_STUDIO_URL = os.getenv("LM_STUDIO_URL", "http://127.0.0.1:1234/v1")
AI_MODEL = os.getenv("AI_MODEL")
SESSION_NAME = os.getenv("USERBOT_SESSION", ".userbot")
STATE_FILE = Path(os.getenv("USERBOT_STATE_FILE", "userbot-state.json"))
MAX_HISTORY = 100
GROUP_REPLY_CHANCE = float(os.getenv("GROUP_REPLY_CHANCE", "0.01"))
OWNER_NAME_RE = re.compile(
    r"(?<!\w)(?:стас\s*п|стасян(?:а|у|ом|е)?|сасян(?:а|у|ом|е)?|стас(?:а|у|ом|е)?|stas)(?!\w)",
    re.IGNORECASE,
)
owner_username = ""
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

if not API_ID or not API_HASH:
    raise RuntimeError("TELEGRAM_API_ID and TELEGRAM_API_HASH must be set in .env")
if not 0 <= GROUP_REPLY_CHANCE <= 1:
    raise RuntimeError("GROUP_REPLY_CHANCE must be a number between 0 and 1")

telegram = TelegramClient(SESSION_NAME, int(API_ID), API_HASH)
llm = OpenAI(base_url=LM_STUDIO_URL, api_key="lm-studio")
history: dict[int, list[dict[str, str]]] = {}


def load_state() -> tuple[set[int], dict[int, str], dict[int, str]]:
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        active_chats = {int(chat_id) for chat_id in data.get("active_chat_ids", [])}
        tones = {
            int(chat_id): tone
            for chat_id, tone in data.get("chat_tones", {}).items()
            if tone in TONE_PROMPTS
        }
        personas = {
            int(chat_id): persona
            for chat_id, persona in data.get("chat_personas", {}).items()
            if persona in PERSONA_FILES
        }
        return active_chats, tones, personas
    except (FileNotFoundError, json.JSONDecodeError, OSError, TypeError, ValueError):
        return set(), {}, {}


active_chat_ids, chat_tones, chat_personas = load_state()


def save_active_chats() -> None:
    STATE_FILE.write_text(
        json.dumps(
            {
                "active_chat_ids": sorted(active_chat_ids),
                "chat_tones": {str(chat_id): tone for chat_id, tone in chat_tones.items()},
                "chat_personas": {str(chat_id): persona for chat_id, persona in chat_personas.items()},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def update_history(chat_id: int, role: str, text: str) -> None:
    messages = history.setdefault(chat_id, [])
    if messages and messages[-1]["role"] == role:
        messages[-1]["content"] = text
    else:
        messages.append({"role": role, "content": text})
    history[chat_id] = messages[-MAX_HISTORY:]


def normalized_history(chat_id: int) -> list[dict[str, str]]:
    """Return a prompt history that starts with a user message and alternates roles."""
    normalized: list[dict[str, str]] = []
    expected_role = "user"
    for message in history.get(chat_id, []):
        if message["role"] != expected_role:
            continue
        normalized.append(message)
        expected_role = "assistant" if expected_role == "user" else "user"
    return normalized


def is_owner_mentioned(text: str) -> bool:
    if OWNER_NAME_RE.search(text):
        return True
    return bool(owner_username and f"@{owner_username}" in text.lower())


def create_reply(chat_id: int) -> str:
    tone = chat_tones.get(chat_id, DEFAULT_TONE)
    persona_name = chat_personas.get(chat_id, DEFAULT_PERSONA)
    system_prompt = (
        "Ты — это я. Отвечай от моего имени, в моём стиле. "
        "Не говори, что ты бот или автоответчик. Ответ короткий и естественный.\n\n"
        f"Текущий тон: {TONE_PROMPTS[tone]}\n\n"
        f"Моя персона:\n{load_persona(persona_name)}"
    )
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(normalized_history(chat_id))
    response = llm.chat.completions.create(model=AI_MODEL, messages=messages)
    reply = response.choices[0].message.content or ""
    return re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL).strip()


COMMAND_RE = re.compile(r"^/autorespond(?:@\w+)?\s+(on|off|status)\s*$", re.IGNORECASE)
TONE_COMMAND_RE = re.compile(
    r"^/tone(?:@\w+)?\s+(natural|calm|warm|professional|concise|playful|status)\s*$",
    re.IGNORECASE,
)
PERSONA_COMMAND_RE = re.compile(r"^/persona(?:@\w+)?\s+(classic|personal|status)\s*$", re.IGNORECASE)


def is_control_command(text: str) -> bool:
    return bool(COMMAND_RE.match(text) or TONE_COMMAND_RE.match(text) or PERSONA_COMMAND_RE.match(text))


@telegram.on(events.NewMessage(outgoing=True))
async def control_autorespond(event: events.NewMessage.Event) -> None:
    """Toggle auto-replies for the chat where the owner sends the command."""
    text = (event.raw_text or "").strip()
    match = COMMAND_RE.match(text)
    if not match:
        return

    action = match.group(1).lower()
    chat_id = event.chat_id
    if chat_id is None:
        return

    if action == "on":
        active_chat_ids.add(chat_id)
        save_active_chats()
        result = "Автоответ включён"
    elif action == "off":
        active_chat_ids.discard(chat_id)
        history.pop(chat_id, None)
        save_active_chats()
        result = "Автоответ выключен"
    else:
        result = "Автоответ включён" if chat_id in active_chat_ids else "Автоответ выключен"

    await event.delete()
    await telegram.send_message("me", f"{result} для чата {chat_id}.")


@telegram.on(events.NewMessage(outgoing=True))
async def control_tone(event: events.NewMessage.Event) -> None:
    """Set the reply tone for the chat where the owner sends the command."""
    text = (event.raw_text or "").strip()
    match = TONE_COMMAND_RE.match(text)
    if not match or event.chat_id is None:
        return

    tone = match.group(1).lower()
    if tone == "status":
        result = f"Current tone: {chat_tones.get(event.chat_id, DEFAULT_TONE)}"
    else:
        chat_tones[event.chat_id] = tone
        save_active_chats()
        result = f"Tone set to: {tone}"

    await event.delete()
    await telegram.send_message("me", f"{result} for chat {event.chat_id}.")


@telegram.on(events.NewMessage(outgoing=True))
async def control_persona(event: events.NewMessage.Event) -> None:
    text = (event.raw_text or "").strip()
    match = PERSONA_COMMAND_RE.match(text)
    if not match or event.chat_id is None:
        return
    persona = match.group(1).lower()
    if persona == "status":
        result = f"Current persona: {chat_personas.get(event.chat_id, DEFAULT_PERSONA)}"
    else:
        chat_personas[event.chat_id] = persona
        save_active_chats()
        result = f"Persona set to: {persona}"
    await event.delete()
    await telegram.send_message("me", f"{result} for chat {event.chat_id}.")


@telegram.on(events.NewMessage(outgoing=True))
async def remember_owner_messages(event: events.NewMessage.Event) -> None:
    """Keep genuine outgoing messages as conversation context."""
    if event.chat_id not in active_chat_ids:
        return
    text = (event.raw_text or "").strip()
    if text and not is_control_command(text):
        update_history(event.chat_id, "assistant", text)


@telegram.on(events.NewMessage(incoming=True))
async def respond_as_owner(event: events.NewMessage.Event) -> None:
    chat_id = event.chat_id
    text = (event.raw_text or "").strip()
    if chat_id not in active_chat_ids or not text:
        return

    sender = await event.get_sender()
    if getattr(sender, "bot", False):
        return

    # A direct mention always gets a reply; other group messages reply occasionally.
    if event.is_group and not is_owner_mentioned(text) and random.random() >= GROUP_REPLY_CHANCE:
        return

    update_history(chat_id, "user", text)
    try:
        reply = await asyncio.to_thread(create_reply, chat_id)
    except Exception as error:
        await telegram.send_message("me", f"Не удалось сгенерировать автоответ: {error}")
        return

    if reply:
        update_history(chat_id, "assistant", reply)
        await event.respond(reply)


async def main() -> None:
    global owner_username
    await telegram.start()
    owner = await telegram.get_me()
    owner_username = (owner.username or "").lower()
    print(f"Userbot started with model: {AI_MODEL}. Use /autorespond on or /autorespond off in a chat.")
    await telegram.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
