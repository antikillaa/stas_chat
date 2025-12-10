import aiohttp
import asyncio
import os

PUBLIC_URL = os.environ.get("PUBLIC_URL")  # твой URL Render

async def keep_alive(bot, webhook_url):
    if not PUBLIC_URL:
        print("PUBLIC_URL не задан, Keep-Alive не работает")
        return

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(PUBLIC_URL) as resp:
                    print(f"Keep-Alive ping: {resp.status}")
                # await bot.set_webhook(webhook_url)
            except Exception as e:
                print(f"Keep-Alive ошибка: {e}")
            await asyncio.sleep(30)  # каждые 30 секунд