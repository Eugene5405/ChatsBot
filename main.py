import asyncio
import logging
import os

from aiohttp import web
from aiogram import Dispatcher

import admin
import automod
import chat_lock
import db
import info
import moderation
import pm_panel
import webapp
import welcome
from loader import bot

logging.basicConfig(level=logging.INFO)


async def _health_root(request: web.Request) -> web.Response:
    return web.Response(text="Bot is alive!")


async def start_web_server():
    app = web.Application()
    app.router.add_get("/", _health_root)
    webapp.setup_routes(app)

    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info("Веб-сервер запущен на порту %s", port)


async def main():
    if hasattr(db, "init_db"):
        await db.init_db()

    dp = Dispatcher()

    # Подключаем ВСЕ модули бота в правильном порядке приоритета
    dp.include_router(pm_panel.router)
    dp.include_router(chat_lock.router)
    dp.include_router(admin.router)
    dp.include_router(moderation.router)
    dp.include_router(info.router)
    dp.include_router(welcome.router)
    dp.include_router(automod.router)

    await start_web_server()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
