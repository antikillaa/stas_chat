# bot.py
import os
import asyncio
import logging
import random
import re
from typing import Any, Dict
from concurrent.futures import ThreadPoolExecutor

import aiohttp
from aiohttp import web
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from openai import OpenAI

# ----------------------------
# Config (env)
# ----------------------------
load_dotenv()
TG_TOKEN = os.getenv("TG_TOKEN")
HF_TOKEN = os.getenv("HF_TOKEN")
PUBLIC_URL = os.getenv("PUBLIC_URL")  # e.g. https://your-service.onrender.com
PORT = int(os.getenv("PORT", 8000))

# tuning
WORKER_COUNT = int(os.getenv("WORKER_COUNT", 2))      # workers for dp.feed_update
LLM_WORKERS = int(os.getenv("LLM_WORKERS", 2))        # workers for LLM queue
QUEUE_MAXSIZE = int(os.getenv("QUEUE_MAXSIZE", 500))
LLM_QUEUE_MAXSIZE = int(os.getenv("LLM_QUEUE_MAXSIZE", 200))
WORKER_TIMEOUT = float(os.getenv("WORKER_TIMEOUT", 40))  # seconds for dp.feed_update timeout
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", 60))     # seconds to wait for LLM call
LLM_RETRIES = int(os.getenv("LLM_RETRIES", 2))

BASE_CHANCE = float(os.getenv("BASE_CHANCE", 0.2))
KEYWORD_CHANCE = float(os.getenv("KEYWORD_CHANCE", 0.9))

if not TG_TOKEN or not HF_TOKEN or not PUBLIC_URL:
    raise RuntimeError("Please set TG_TOKEN, HF_TOKEN and PUBLIC_URL in environment")

# ----------------------------
# Logging
# ----------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("sta_bot")

# ----------------------------
# Bot, Dispatcher, LLM client
# ----------------------------
bot = Bot(token=TG_TOKEN)
dp = Dispatcher()

client = OpenAI(base_url="https://router.huggingface.co/v1", api_key=HF_TOKEN)

# ----------------------------
# Persona & memory
# ----------------------------
with open("persona.txt", "r", encoding="utf-8") as f:
    persona = f.read()

chat_memory: Dict[int, Dict[str, Any]] = {}
MAX_HISTORY = 20


def update_history(chat_id: int, role: str, text: str):
    chat_memory.setdefault(chat_id, {"history": [], "mode": "stylish"})
    chat_memory[chat_id]["history"].append({"role": role, "content": text})
    chat_memory[chat_id]["history"] = chat_memory[chat_id]["history"][-MAX_HISTORY:]


# ----------------------------
# PRAISES and mention helper
# ----------------------------
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

bot_names = ["Стасян", "Стасяне", "Стасяну", "Стасяном"]


async def is_mentioned(msg: types.Message) -> bool:
    me = await bot.get_me()
    text = (msg.text or "") + " " + (msg.caption or "")
    low = text.lower()

    # private chat -> always mention
    if msg.chat.type == "private":
        return True

    # @username mention
    if msg.entities:
        for ent in msg.entities:
            if ent.type == "mention":
                try:
                    mention = text[ent.offset:ent.offset + ent.length].lower()
                except Exception:
                    mention = ""
                if mention == f"@{me.username.lower()}":
                    return True

    # name substring
    for name in bot_names:
        if name.lower() in low:
            return True

    # reply to bot
    if msg.reply_to_message and msg.reply_to_message.from_user:
        if msg.reply_to_message.from_user.id == me.id:
            return True

    return False


def praise_chance_sync(caption: str) -> bool:
    caption_low = (caption or "").lower()
    has_keyword = any(w in caption_low for w in POSITIVE_WORDS)
    chance = KEYWORD_CHANCE if has_keyword else BASE_CHANCE
    return random.random() < chance


# ----------------------------
# LLM generation (sync wrapper to run in executor)
# ----------------------------
def generate_reply_sync(chat_id: int, text: str) -> str:
    """
    Blocking call to LLM (runs in threadpool). Returns generated reply (string).
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

    try:
        logger.info("LLM call: chat_id=%s text_preview=%s", chat_id, text[:200])
        response = client.chat.completions.create(
            model="deepseek-ai/DeepSeek-R1",
            messages=messages,
        )
        reply = response.choices[0].message.content
        # strip internal <think> tags
        reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL).strip()
        update_history(chat_id, "assistant", reply)
        logger.info("LLM success: chat_id=%s reply_preview=%s", chat_id, reply[:200])
        return reply
    except Exception as e:
        logger.exception("LLM call failed: %s", e)
        raise


# ----------------------------
# Lightweight handlers (these run when dp.feed_update is executed by update workers)
# - TEXT: only enqueue LLM job to llm_queue
# - PHOTO/VIDEO: send praise (no LLM), but still quick
# ----------------------------

# We'll refer to llm_queue inside handlers; define below before start


@dp.message(F.photo)
async def _photo_handler(msg: types.Message):
    try:
        if not await is_mentioned(msg):
            logger.debug("Photo ignored (not mentioned). chat=%s", msg.chat.id)
            return

        # chance decision (sync)
        if praise_chance_sync(msg.caption or ""):
            await asyncio.sleep(random.uniform(0.4, 1.1))
            await msg.answer(random.choice(PRAISES))
            logger.info("Sent praise for photo in chat %s", msg.chat.id)
        else:
            logger.debug("Photo mention, but chance skipped. chat=%s", msg.chat.id)
    except Exception:
        logger.exception("Error in photo handler")


@dp.message(F.video)
async def _video_handler(msg: types.Message):
    try:
        if not await is_mentioned(msg):
            logger.debug("Video ignored (not mentioned). chat=%s", msg.chat.id)
            return

        if praise_chance_sync(msg.caption or ""):
            await asyncio.sleep(random.uniform(0.4, 1.1))
            await msg.answer(random.choice(PRAISES))
            logger.info("Sent praise for video in chat %s", msg.chat.id)
        else:
            logger.debug("Video mention, but chance skipped. chat=%s", msg.chat.id)
    except Exception:
        logger.exception("Error in video handler")


@dp.message(F.text)
async def _text_handler(msg: types.Message):
    """
    Lightweight: if mentioned, push an LLM job to llm_queue (do not call LLM here).
    """
    try:
        if not await is_mentioned(msg):
            logger.debug("Text ignored (not mentioned). chat=%s", msg.chat.id)
            return

        text = msg.text or ""
        update_history(msg.chat.id, "user", text)

        # build job
        job = {
            "type": "llm",
            "chat_id": msg.chat.id,
            "text": text,
            "from_id": msg.from_user.id,
            "msg_id": msg.message_id,
        }

        # try to enqueue (non-blocking)
        try:
            llm_queue.put_nowait(job)
            logger.info("Enqueued LLM job for chat %s (msg %s)", msg.chat.id, msg.message_id)
        except asyncio.QueueFull:
            logger.warning("LLM queue full, dropping LLM job for chat %s", msg.chat.id)
            # optionally: inform user that bot is busy
            try:
                await msg.reply("Сорян, сейчас перегруз — попробуй чуть позже.")
            except Exception:
                pass

    except Exception:
        logger.exception("Error in text handler")


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


# ----------------------------
# Queues and workers
# ----------------------------
update_queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_MAXSIZE)
llm_queue: asyncio.Queue = asyncio.Queue(maxsize=LLM_QUEUE_MAXSIZE)

update_workers: list[asyncio.Task] = []
llm_workers: list[asyncio.Task] = []

# use a threadpool for blocking LLM network calls
executor = ThreadPoolExecutor(max_workers=LLM_WORKERS * 2)


async def update_worker(worker_id: int):
    logger.info("Update worker %s started", worker_id)
    while True:
        data = await update_queue.get()
        try:
            # quick validation
            try:
                update = types.Update.model_validate(data)
            except Exception:
                logger.exception("Invalid update received (skipping)")
                continue

            # execute dp.feed_update with timeout to avoid stuck
            try:
                await asyncio.wait_for(dp.feed_update(bot, update), timeout=WORKER_TIMEOUT)
            except asyncio.TimeoutError:
                logger.error("dp.feed_update timeout in worker %s", worker_id)
            except Exception:
                logger.exception("Error while processing update in worker %s", worker_id)

        finally:
            update_queue.task_done()


async def llm_worker(worker_id: int):
    logger.info("LLM worker %s started", worker_id)
    while True:
        job = await llm_queue.get()
        try:
            chat_id = job.get("chat_id")
            text = job.get("text")
            msg_id = job.get("msg_id")
            from_id = job.get("from_id")

            attempt = 0
            reply_text = None
            # run LLM in executor with timeout and retry
            while attempt <= LLM_RETRIES:
                attempt += 1
                try:
                    loop = asyncio.get_running_loop()
                    # run blocking LLM in threadpool
                    coro = loop.run_in_executor(executor, generate_reply_sync, chat_id, text)
                    reply_text = await asyncio.wait_for(coro, timeout=LLM_TIMEOUT)
                    break
                except asyncio.TimeoutError:
                    logger.error("LLM attempt %s timed out for chat %s", attempt, chat_id)
                except Exception as e:
                    logger.exception("LLM attempt %s failed for chat %s: %s", attempt, chat_id, e)

            if reply_text is None:
                # final failure
                try:
                    await bot.send_message(chat_id, "Сорян, не могу ответить сейчас — попробуй позже.")
                    logger.error("LLM ultimately failed for chat %s", chat_id)
                except Exception:
                    logger.exception("Failed to send failure message to chat %s", chat_id)
            else:
                try:
                    await bot.send_message(chat_id, reply_text, reply_to_message_id=msg_id)
                    logger.info("Sent LLM reply to chat %s", chat_id)
                except Exception:
                    logger.exception("Failed to send LLM reply to chat %s", chat_id)

        finally:
            llm_queue.task_done()


# ----------------------------
# Webhook & health handlers
# ----------------------------
async def webhook_handler(request: web.Request):
    """
    Fast: accepts request, parses JSON, logs some info, enqueues to update_queue and returns 200 immediately.
    """
    try:
        data = await request.json()
    except Exception:
        logger.exception("Bad JSON received at webhook")
        return web.Response(status=400, text="bad json")

    logger.debug("Webhook received update_id=%s", data.get("update_id"))
    # schedule enqueue in background to keep handler fast
    try:
        update_queue.put_nowait(data)
    except asyncio.QueueFull:
        logger.warning("Update queue full, dropping update id=%s", data.get("update_id"))
    return web.Response(text="OK")


async def health_handler(request: web.Request):
    return web.Response(text="OK")


# ----------------------------
# Keep-alive pinger
# ----------------------------
async def keep_alive_task():
    url = f"{PUBLIC_URL}/health"
    logger.info("keep_alive pinging %s every 60s", url)
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(url, timeout=10) as resp:
                    logger.debug("keep_alive status=%s", resp.status)
            except Exception as e:
                logger.warning("keep_alive error: %s", e)
            await asyncio.sleep(60)


# ----------------------------
# Startup / Shutdown
# ----------------------------
async def on_startup(app: web.Application):
    logger.info("App startup: creating workers and setting webhook")

    # spawn update workers
    for i in range(WORKER_COUNT):
        t = asyncio.create_task(update_worker(i + 1))
        update_workers.append(t)

    # spawn llm workers
    for i in range(LLM_WORKERS):
        t = asyncio.create_task(llm_worker(i + 1))
        llm_workers.append(t)

    # spawn keep_alive
    asyncio.create_task(keep_alive_task())

    # set webhook: delete old then set
    url = f"{PUBLIC_URL}/webhook/{TG_TOKEN}"
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception:
        logger.exception("Error deleting previous webhook (ignored)")

    await bot.set_webhook(url)
    logger.info("Webhook set to %s", url)


async def on_shutdown(app: web.Application):
    logger.info("Shutdown: deleting webhook and cancelling workers")
    try:
        await bot.delete_webhook()
    except Exception:
        logger.exception("Error deleting webhook on shutdown (ignored)")

    # cancel tasks
    for t in update_workers + llm_workers:
        t.cancel()
    try:
        await bot.session.close()
    except Exception:
        pass

    # shutdown executor
    executor.shutdown(wait=False)


# ----------------------------
# App routes and run
# ----------------------------
app = web.Application()
app.router.add_post(f"/webhook/{TG_TOKEN}", webhook_handler)
app.router.add_get("/health", health_handler)
app.router.add_get("/", health_handler)

app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)

if __name__ == "__main__":
    logger.info("Starting web app on port %s", PORT)
    web.run_app(app, host="0.0.0.0", port=PORT)