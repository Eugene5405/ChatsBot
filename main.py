import asyncio
import html
import logging
import os

from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatMemberStatus, ParseMode
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    ChatJoinRequest,
    ChatMemberUpdated,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)
from dotenv import load_dotenv

import db
import webapp

load_dotenv()
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0") or 0)
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "https://chatsbot-ve5e.onrender.com").rstrip("/")

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

_ACTIVE = {ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}
_LEFT = {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED}


def mention(user) -> str:
    name = html.escape(user.full_name or "Участник")
    return f'<a href="tg://user?id={user.id}">{name}</a>'


@dp.message(Command("start"))
async def cmd_start(message: Message):
    if message.chat.type == "private":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛡 Открыть админ-панель", web_app=WebAppInfo(url=f"{RENDER_URL}/webapp"))],
            [InlineKeyboardButton(text="➕ Добавить бота в группу", url="https://t.me/chat_custodian_bot?startgroup=true&admin=change_info+delete_messages+restrict_members+invite_users+pin_messages")]
        ])
        await message.answer(
            "👋 Привет! Я <b>Хранитель чата</b>.\n\n"
            "Добавь меня администратором в группу и напиши там <b>/status</b>, чтобы группа появилась в админ-панели.",
            reply_markup=kb
        )
    else:
        db.register_chat(message.chat.id, message.chat.title or "Группа")
        await message.answer("✅ Бот активен в этом чате! Используйте /status для проверки прав.")


@dp.message(Command("status"))
async def cmd_status(message: Message):
    if message.chat.type == "private":
        await cmd_start(message)
        return
    db.register_chat(message.chat.id, message.chat.title or "Группа")
    me = await bot.get_chat_member(message.chat.id, bot.id)
    is_admin = me.status in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}
    s = db.get_chat_settings(message.chat.id)
    await message.answer(
        f"🛡 <b>Статус чата:</b> {html.escape(message.chat.title or '')}\n"
        f"• Права администратора: {'✅ Есть' if is_admin else '❌ Нет (выдайте права!)'}\n"
        f"• Синхронизация с панелью: ✅ Готово\n"
        f"• Приветствие/прощание: {'✅' if s['welcome'] else '❌'}\n"
        f"• Проверка подписки: {'✅' if s['subcheck'] else '❌'}"
    )


@dp.my_chat_member()
async def on_bot_added(event: ChatMemberUpdated):
    if event.chat.type in {"group", "supergroup"} and event.new_chat_member.status in _ACTIVE:
        db.register_chat(event.chat.id, event.chat.title or "Группа")
        try:
            await bot.send_message(
                event.chat.id,
                f"🛡 <b>Хранитель чата</b> подключен к <b>{html.escape(event.chat.title or '')}</b>!\n"
                "Чат добавлен в админ-панель. Выдайте мне права администратора для полноценной работы."
            )
        except Exception:
            pass


@dp.chat_member()
async def on_member_update(event: ChatMemberUpdated):
    user = event.new_chat_member.user
    if user.is_bot:
        return
    db.register_chat(event.chat.id, event.chat.title or "Группа")
    settings = db.get_chat_settings(event.chat.id)
    if not settings.get("welcome", True):
        return

    old_st = event.old_chat_member.status
    new_st = event.new_chat_member.status
    title = html.escape(event.chat.title or "чат")

    if old_st in _LEFT and new_st in _ACTIVE:
        rules_text = html.escape(settings.get("rules_text", ""))
        await bot.send_message(
            event.chat.id,
            f"👋 Добро пожаловать в <b>{title}</b>, {mention(user)}!\n\n"
            f"Правила чата:\n<blockquote expandable>{rules_text}</blockquote>"
        )
    elif old_st in _ACTIVE and new_st == ChatMemberStatus.LEFT:
        await bot.send_message(
            event.chat.id,
            f"👋 {mention(user)} покинул(а) чат. Удачи и всего хорошего!"
        )


@dp.chat_join_request()
async def on_join_request(req: ChatJoinRequest):
    db.register_chat(req.chat.id, req.chat.title or "Группа")
    settings = db.get_chat_settings(req.chat.id)
    if not settings.get("subcheck", True) or not CHANNEL_ID:
        await req.approve()
        return

    try:
        member = await bot.get_chat_member(CHANNEL_ID, req.from_user.id)
        if member.status in _ACTIVE:
            await req.approve()
            return
    except Exception:
        await req.approve()
        return

    try:
        ch = await bot.get_chat(CHANNEL_ID)
        url = f"https://t.me/{ch.username}" if ch.username else ch.invite_link
        rows = []
        if url:
            rows.append([InlineKeyboardButton(text="📢 Открыть канал", url=url)])
        rows.append([InlineKeyboardButton(text="✅ Я подписался", callback_data=f"chksub:{req.chat.id}")])
        await bot.send_message(
            req.from_user.id,
            f"Чтобы вступить в <b>{html.escape(req.chat.title or '')}</b>, подпишитесь на канал и нажмите кнопку ниже:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
        )
    except Exception:
        pass


@dp.callback_query(F.data.startswith("chksub:"))
async def on_chksub(cb: CallbackQuery):
    chat_id = int(cb.data.split(":", 1)[1])
    try:
        member = await bot.get_chat_member(CHANNEL_ID, cb.from_user.id)
        if member.status not in _ACTIVE:
            await cb.answer("Вы еще не подписались на канал!", show_alert=True)
            return
        await bot.approve_chat_join_request(chat_id, cb.from_user.id)
        await cb.message.edit_text("✅ Подписка подтверждена! Заявка одобрена.")
    except Exception as e:
        await cb.message.edit_text(f"Не удалось одобрить заявку: {e}")
    await cb.answer()


@dp.message(F.chat.type.in_({"group", "supergroup"}))
async def on_group_message(message: Message):
    db.register_chat(message.chat.id, message.chat.title or "Группа")


async def index_root(request: web.Request) -> web.Response:
    return web.Response(text="Bot is alive!")


async def main():
    db.init_db()
    app = web.Application()
    app.router.add_get("/", index_root)
    webapp.setup_routes(app)

    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "10000"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
