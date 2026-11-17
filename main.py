"""Точка входа бота: подключение всех роутеров, умного антимата и веб-сервера."""
import asyncio
import logging
import os

from aiohttp import web
from aiogram import Dispatcher, F, Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import Message

import chat_lock
import db
import pm_panel
import profanity_filter
import webapp
import welcome
from loader import bot

logging.basicConfig(level=logging.INFO)

core_router = Router()
_ADMINS = {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}


async def _is_admin(message: Message) -> bool:
    if not message.from_user:
        return False
    if message.sender_chat and message.sender_chat.id == message.chat.id:
        return True
    member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    return member.status in _ADMINS


@core_router.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}), Command("status"))
async def cmd_status(message: Message):
    db.register_chat(message.chat.id, message.chat.title)
    me = await bot.get_me()
    member = await bot.get_chat_member(message.chat.id, me.id)
    is_adm = member.status in _ADMINS
    await message.answer(
        f"✅ <b>Чат синхронизирован с базой!</b>\n"
        f"• Группа: <b>{message.chat.title}</b>\n"
        f"• ID: <code>{message.chat.id}</code>\n"
        f"• Статус бота: {'Администратор 🛡' if is_adm else 'Обычный участник ⚠️ (выдайте права админа)'}"
    )


@core_router.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def group_guard(message: Message):
    db.register_chat(message.chat.id, message.chat.title)
    if await _is_admin(message):
        return

    settings = db.get_chat_settings(message.chat.id)
    text = message.text or message.caption or ""

    if settings.get("profanity", True) and profanity_filter.contains_profanity(text):
        try:
            await message.delete()
            await message.answer(f"🚫 {message.from_user.mention_html()}, мат в чате запрещён!")
        except TelegramBadRequest:
            pass
        return

    if settings.get("antilink", True) and any(x in text.lower() for x in ("http://", "https://", "t.me/", "@")):
        try:
            await message.delete()
            await message.answer(f"🔗 {message.from_user.mention_html()}, ссылки в чате запрещены!")
        except TelegramBadRequest:
            pass


async def _root_health(request: web.Request) -> web.Response:
    return web.Response(text="Bot is alive!")


async def start_web_server() -> None:
    app = web.Application()
    app.router.add_get("/", _root_health)
    webapp.setup_routes(app)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "10000"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()


async def main() -> None:
    db.init_db()
    dp = Dispatcher()

    # Подключаем роутеры в строгом порядке приоритета
    dp.include_router(pm_panel.router)
    dp.include_router(chat_lock.router)
    dp.include_router(welcome.router)
    dp.include_router(core_router)

    await start_web_server()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
