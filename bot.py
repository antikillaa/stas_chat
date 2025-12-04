# bot.py
import os
import asyncio
import logging
import random
import re
from typing import Any

import aiohttp
from aiohttp import web
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from openai import OpenAI

# ---------------------------
# config (env)
# ---------------------------
load_dotenv()
TG_TOKEN = os.getenv("TG_TOKEN")
HF_TOKEN = os.getenv("HF_TOKEN")
PUBLIC_URL = os.getenv("PUBLIC_URL")  # https://your-service.onrender.com
PORT = int(os.getenv("PORT", 8000))

# queue/worker tuning
WORKER_COUNT = int(os.getenv("WORKER_COUNT", 2))     # сколько параллельных воркеров
QUEUE_MAXSIZE = int(os.getenv("QUEUE_MAXSIZE", 200)) # max queued updates
WORKER_TIMEOUT = float(os.getenv("WORKER_TIMEOUT", 35))  # сек на обработку одного update

if not TG_TOKEN or not HF_TOKEN or not PUBLIC_URL:
    raise RuntimeError("TG_TOKEN, HF_TOKEN и PUBLIC_URL должны быть заданы в .env")

# ---------------------------
# logging
# ---------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("telegram_bot")

# ---------------------------
# create bot & dispatcher & LLM client
# ---------------------------
bot = Bot(TG_TOKEN)
dp = Dispatcher()

client = OpenAI(base_url="https://router.huggingface.co/v1", api_key=HF_TOKEN)

# ---------------------------
# persona and memory
# ---------------------------
with open("persona.txt", "r", encoding="utf-8") as f:
    persona = f.read()

chat_memory: dict[int, dict] = {}
MAX_HISTORY = 20


def update_history(chat_id: int, role: str, text: str):
    chat_memory.setdefault(chat_id, {"history": [], "mode": "stylish"})
    chat_memory[chat_id]["history"].append({"role": role, "content": text})
    chat_memory[chat_id]["history"] = chat_memory[chat_id]["history"][-MAX_HISTORY:]


# ---------------------------
# LLM generation (unchanged core, but can timeout via worker)
# ---------------------------
def generate_reply_sync(chat_id: int, text: str) -> str:
    """
    Synchronous wrapper around client.chat.completions.create
    We call this inside background worker (not in webhook handler).
    """
    mode = chat_memory.get(chat_id, {}).get("mode", "stylish")
    system_prompt = f"Ты — это я. Общайся в моем стиле.\nМой стиль:\n{persona}\n"
    if mode == "stylish":
        system_prompt += "Отвечай коротко, естественно и как я бы сказал."
    else:
        system_prompt += "Отвечай развернуто и подробно."

    messages = [{"role": "system", "content": system_prompt}]
    if chat_id in chat_memory:
        messages += chat_memory[chat_id]["history"]
    messages.append({"role": "user", "content": text})

    # NOTE: this call may block (network). We run it in background worker.
    response = client.chat.completions.create(
        model="deepseek-ai/DeepSeek-R1",
        messages=messages,
    )
    reply = response.choices[0].message.content
    reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL).strip()
    update_history(chat_id, "assistant", reply)
    return reply


# ---------------------------
# PRAISES and mention helper
# ---------------------------
PRAISES = [
    "О, брат, молодец 👍",
    "Красиво получилось 😎",
    "Ты прям на стиле 😏",
    "Брат, огонь 🔥",
    "Зачёт 👊",
]
POSITIVE_WORDS = [
    "сделал", "готово", "успех", "класс", "получилось", "супер", "отлично", "заработало"
]
BASE_CHANCE = float(os.getenv("BASE_CHANCE", 0.2))
KEYWORD_CHANCE = float(os.getenv("KEYWORD_CHANCE", 0.9))

bot_names = ["Стасян", "Стасяне", "Стасяну", "Стасяном"]


async def is_mentioned(msg: types.Message) -> bool:
    me = await bot.get_me()
    # check both text and caption
    text = (msg.text or "") + " " + (msg.caption or "")
    low = text.lower()

    # private chat always considered mention
    if msg.chat.type == "private":
        return True

    # @username mention
    if msg.entities:
        for ent in msg.entities:
            if ent.type == "mention":
                mention = text[ent.offset: ent.offset + ent.length].lower()
                if mention == f"@{me.username.lower()}":
                    return True

    # name substring
    for name in bot_names:
        if name.lower() in low:
            return True

    # reply to bot
    if msg.reply_to_message and msg.reply_to_message.from_user:
        if msg.reply_to_message.from_user.id == (await bot.get_me()).id:
            return True

    return False


async def praise_chance(msg: types.Message) -> bool:
    caption = (msg.caption or "") .lower()
    has_keyword = any(w in caption for w in POSITIVE_WORDS)
    chance = KEYWORD_CHANCE if has_keyword else BASE_CHANCE
    return random.random() < chance


# ---------------------------
# Handlers (these will be executed in background worker via dp.feed_update)
# - keep these minimal: photo/video -> reply with PRAISE (no LLM),
#   text -> call LLM (we placed generate_reply_sync to be used inside handler,
#   but handler must be synchronous in sense of not blocking webhook)
# Note: dp.feed_update runs handlers normally. We run dp.feed_update in background worker.
# ---------------------------

@dp.message(F.photo)
async def handle_photo(msg: types.Message):
    """
    This handler runs in background worker (because dp.feed_update is called from worker).
    It must be quick — we reply with random PRAISE (no LLM calls here).
    """
    try:
        if not await is_mentioned(msg):
            return
        if await praise_chance(msg):
            await asyncio.sleep(random.uniform(0.4, 1.2))
            await msg.answer(random.choice(PRAISES))
            logger.info("Sent praise for photo in chat %s", msg.chat.id)
    except Exception:
        logger.exception("Error in handle_photo")


@dp.message(F.video)
async def handle_video(msg: types.Message):
    try:
        if not await is_mentioned(msg):
            return
        if await praise_chance(msg):
            await asyncio.sleep(random.uniform(0.4, 1.2))
            await msg.answer(random.choice(PRAISES))
            logger.info("Sent praise for video in chat %s", msg.chat.id)
    except Exception:
        logger.exception("Error in handle_video")


@dp.message(F.text)
async def handle_text(msg: types.Message):
    """
    Text handler: only run when mentioned; performs LLM generation.
    This handler will call generate_reply_sync which blocks network.
    It's okay: this handler runs inside background worker.
    """
    try:
        if not await is_mentioned(msg):
            return

        text = msg.text or ""
        update_history(msg.chat.id, "user", text)

        # simulate typing
        await bot.send_chat_action(msg.chat.id, "typing")
        await asyncio.sleep(0.8)

        # Run blocking LLM in threadpool to avoid blocking event loop in case
        loop = asyncio.get_running_loop()
        reply = await loop.run_in_executor(None, generate_reply_sync, msg.chat.id, text)
        await msg.answer(reply)
        logger.info("LLM reply sent to chat %s", msg.chat.id)
    except Exception:
        logger.exception("Error in handle_text")


# Commands
@dp.message(Command("reset"))
async def cmd_reset(msg: types.Message):
    chat_memory[msg.chat.id] = {"history": [], "mode": "stylish"}
    await msg.answer("История очищена.")
    logger.info("Reset history for chat %s", msg.chat.id)


@dp.message(Command("mode"))
async def cmd_mode(msg: types.Message):
    parts = (msg.text or "").split()
    if len(parts) < 2:
        return await msg.answer("Используй: /mode stylish или /mode detailed")
    m = parts[1]
    if m not in ["stylish", "detailed"]:
        return await msg.answer("Некорректный режим.")
    chat_memory.setdefault(msg.chat.id, {"history": [], "mode": "stylish"})["mode"] = m
    await msg.answer(f"Режим установлен: {m}")
    logger.info("Set mode=%s for chat %s", m, msg.chat.id)


# ---------------------------
# Queue + Workers for safe background processing
# ---------------------------
update_queue: "asyncio.Queue[dict[str, Any]]" = asyncio.Queue(maxsize=QUEUE_MAXSIZE)
workers_tasks: list[asyncio.Task] = []


async def process_update_worker(worker_id: int):
    logger.info("Worker %d started", worker_id)
    while True:
        data = await update_queue.get()
        try:
            # validate update quickly (avoid blocking)
            try:
                update = types.Update.model_validate(data)
            except Exception as e:
                logger.exception("Invalid update data: %s", e)
                continue

            # feed update with timeout to avoid stuck workers
            try:
                await asyncio.wait_for(dp.feed_update(bot, update), timeout=WORKER_TIMEOUT)
            except asyncio.TimeoutError:
                logger.error("Worker %d: processing update timed out", worker_id)
            except Exception:
                logger.exception("Worker %d: error while feeding update", worker_id)

        finally:
            update_queue.task_done()


# safe enqueue with backpressure
async def enqueue_update_safe(data: dict):
    try:
        update_queue.put_nowait(data)
    except asyncio.QueueFull:
        # queue full -> drop oldest or skip; we drop the new update to avoid memory pressure
        logger.warning("Update queue full — dropping update")
        # alternative strategies: await put, or pop one and put new


# ---------------------------
# Webhook + health handlers
# ---------------------------
async def webhook_handler(request: web.Request):
    """
    Very fast: accept JSON and queue it for background processing.
    Return 200 OK immediately.
    """
    try:
        data = await request.json()
    except Exception:
        logger.exception("Bad JSON in webhook")
        return web.Response(status=400, text="bad json")

    # quick log
    logger.debug("Received webhook update id=%s", data.get("update_id"))

    # schedule for background processing
    asyncio.create_task(enqueue_update_safe(data))

    # respond fast
    return web.Response(text="OK")


async def health_handler(request: web.Request):
    return web.Response(text="OK")


# ---------------------------
# keep_alive pinger (background)
# ---------------------------
async def keep_alive_task():
    url = f"{PUBLIC_URL}/health"
    logger.info("Keep-alive will ping %s every 60s", url)
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(url, timeout=10) as resp:
                    logger.debug("Keep-alive ping status: %s", resp.status)
            except Exception as e:
                logger.warning("Keep-alive error: %s", e)
            await asyncio.sleep(60)


# ---------------------------
# startup/shutdown
# ---------------------------
async def on_startup(app: web.Application):
    logger.info("App starting, creating workers and setting webhook")

    # create workers
    for i in range(WORKER_COUNT):
        t = asyncio.create_task(process_update_worker(i + 1))
        workers_tasks.append(t)

    # schedule keep_alive
    asyncio.create_task(keep_alive_task())

    # set webhook with Telegram (ensure previous webhook removed)
    url = f"{PUBLIC_URL}/webhook/{TG_TOKEN}"
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception:
        logger.exception("Error deleting previous webhook (ignored)")

    await bot.set_webhook(url)
    logger.info("Webhook set to %s", url)


async def on_shutdown(app: web.Application):
    logger.info("App shutting down: deleting webhook and cancelling workers")
    try:
        await bot.delete_webhook()
    except Exception:
        logger.exception("Error deleting webhook on shutdown")

    # cancel worker tasks
    for t in workers_tasks:
        t.cancel()
    await bot.session.close()


# ---------------------------
# app routes
# ---------------------------
app = web.Application()
app.router.add_post(f"/webhook/{TG_TOKEN}", webhook_handler)
app.router.add_get("/health", health_handler)
app.router.add_get("/", health_handler)

app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)


# ---------------------------
# run
# ---------------------------
if __name__ == "__main__":
    logger.info("Starting web app on port %s", PORT)
    web.run_app(app, host="0.0.0.0", port=PORT)