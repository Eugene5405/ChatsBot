"""Точка входа: python main.py"""
import asyncio
import logging
import os

from aiohttp import web
from aiogram.types import BotCommand, BotCommandScopeAllChatAdministrators, BotCommandScopeDefault

import admin
import automod
import info
import moderation
import welcome
from loader import bot, dp

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

dp.include_routers(welcome.router, moderation.router, admin.router, info.router, automod.router)


@dp.error()
async def on_error(event):
    logging.exception("Ошибка в обработчике: %s", event.exception)
    return True


async def health_check(request):
    return web.Response(text="Bot is alive!")


async def start_web_server():
    app = web.Application()
    app.router.add_get("/", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()


async def main():
    await start_web_server()
    user_cmds = [BotCommand(command="rules", description="Правила чата"),
                 BotCommand(command="warns", description="Мои предупреждения"),
                 BotCommand(command="help", description="Помощь")]
    admin_cmds = user_cmds + [BotCommand(command="warn", description="Предупреждение (ответом)"),
                              BotCommand(command="mute", description="Мут: /mute 1д"),
                              BotCommand(command="ban", description="Бан (ответом)"),
                              BotCommand(command="settings", description="Фильтры вкл/выкл"),
                              BotCommand(command="setrules", description="Новые правила (ответом)"),
                              BotCommand(command="pinrules", description="Закрепить правила"),
                              BotCommand(command="status", description="Проверка прав бота")]
    await bot.set_my_commands(user_cmds, scope=BotCommandScopeDefault())
    await bot.set_my_commands(admin_cmds, scope=BotCommandScopeAllChatAdministrators())
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
