import asyncio
import inspect
import logging
import os

from aiohttp import web
from aiogram import BaseMiddleware, Dispatcher
from aiogram.types import Message

import admin
import automod
import chat_lock
import db
import economy_shop
import info
import moderation
import pm_panel
import report
import reputation
import roulette
import rp
import webapp
import welcome
from loader import bot

logging.basicConfig(level=logging.INFO)


class AutoRegisterChatMiddleware(BaseMiddleware):
    """Автоматически регистрирует группу в базе Neon при любом сообщении."""

    async def __call__(self, handler, event, data):
        if isinstance(event, Message) and event.chat.type in ("group", "supergroup"):
            try:
                db.register_chat(event.chat.id, event.chat.title)
            except Exception as e:
                logging.warning("Ошибка авторегистрации чата: %s", e)
        return await handler(event, data)


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
        res = db.init_db()
        if inspect.isawaitable(res):
            await res

    dp = Dispatcher()
    dp.message.outer_middleware(AutoRegisterChatMiddleware())

    # Подключаем все модули бота
    dp.include_router(pm_panel.router)
    dp.include_router(chat_lock.router)
    dp.include_router(report.router)
    dp.include_router(economy_shop.router)
    dp.include_router(reputation.router)
    dp.include_router(roulette.router)
    dp.include_router(rp.router)
    dp.include_router(admin.router)
    dp.include_router(moderation.router)
    dp.include_router(info.router)
    dp.include_router(welcome.router)
    dp.include_router(automod.router)

    await start_web_server()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(
        bot,
        allowed_updates=[
            "message",
            "edited_message",
            "callback_query",
            "chat_member",
            "my_chat_member",
            "chat_join_request",
        ],
    )


if __name__ == "__main__":
    asyncio.run(main())
