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


load_dotenv()

API_ID = os.getenv("TELEGRAM_API_ID")
API_HASH = os.getenv("TELEGRAM_API_HASH")
LM_STUDIO_URL = os.getenv("LM_STUDIO_URL", "http://127.0.0.1:1234/v1")
AI_MODEL = os.getenv("AI_MODEL", "google/gemma-3-12b")
SESSION_NAME = os.getenv("USERBOT_SESSION", ".userbot")
STATE_FILE = Path(os.getenv("USERBOT_STATE_FILE", "userbot-state.json"))
MAX_HISTORY = 20
GROUP_REPLY_CHANCE = float(os.getenv("GROUP_REPLY_CHANCE", "0.01"))
OWNER_NAME_RE = re.compile(
    r"(?<!\w)(?:стас\s*п|стасян(?:а|у|ом|е)?|сасян(?:а|у|ом|е)?|стас(?:а|у|ом|е)?|stas)(?!\w)",
    re.IGNORECASE,
)
owner_username = ""

if not API_ID or not API_HASH:
    raise RuntimeError("TELEGRAM_API_ID and TELEGRAM_API_HASH must be set in .env")
if not 0 <= GROUP_REPLY_CHANCE <= 1:
    raise RuntimeError("GROUP_REPLY_CHANCE must be a number between 0 and 1")

with Path(__file__).with_name("persona.txt").open(encoding="utf-8") as file:
    PERSONA = file.read()

telegram = TelegramClient(SESSION_NAME, int(API_ID), API_HASH)
llm = OpenAI(base_url=LM_STUDIO_URL, api_key="lm-studio")
history: dict[int, list[dict[str, str]]] = {}


def load_active_chats() -> set[int]:
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return {int(chat_id) for chat_id in data.get("active_chat_ids", [])}
    except (FileNotFoundError, json.JSONDecodeError, OSError, TypeError, ValueError):
        return set()


active_chat_ids = load_active_chats()


def save_active_chats() -> None:
    STATE_FILE.write_text(
        json.dumps({"active_chat_ids": sorted(active_chat_ids)}, ensure_ascii=False),
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
    system_prompt = (
        "Ты — это я. Отвечай от моего имени, в моём стиле. "
        "Не говори, что ты бот или автоответчик. Ответ короткий и естественный.\n\n"
        f"Мой стиль:\n{PERSONA}"
    )
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(normalized_history(chat_id))
    response = llm.chat.completions.create(model=AI_MODEL, messages=messages)
    reply = response.choices[0].message.content or ""
    return re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL).strip()


COMMAND_RE = re.compile(r"^/autorespond(?:@\w+)?\s+(on|off|status)\s*$", re.IGNORECASE)


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
async def remember_owner_messages(event: events.NewMessage.Event) -> None:
    """Keep genuine outgoing messages as conversation context."""
    if event.chat_id not in active_chat_ids:
        return
    text = (event.raw_text or "").strip()
    if text and not COMMAND_RE.match(text):
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
    print("Userbot started. Use /autorespond on or /autorespond off in a chat.")
    await telegram.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
