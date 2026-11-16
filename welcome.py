"""Заявки в группу, проверка подписки на канал, приветствие с правилами."""
from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, ChatJoinRequest, InlineKeyboardButton, InlineKeyboardMarkup, Message

import config
from loader import bot
from utils import get_rules, is_subscribed

router = Router()


async def _channel_link() -> str:
    if config.CHANNEL_LINK:
        return config.CHANNEL_LINK
    try:
        chat = await bot.get_chat(config.CHANNEL_ID)
        return f"https://t.me/{chat.username}" if chat.username else ""
    except Exception:
        return ""


@router.chat_join_request()
async def on_join_request(req: ChatJoinRequest):
    user = req.from_user
    if await is_subscribed(user.id):
        await bot.approve_chat_join_request(req.chat.id, user.id)
        if config.CHANNEL_ID:
            await bot.send_message(req.chat.id, f"✅ Пользователь {user.mention_html()} присутствует в канале.")
        return
    rows = []
    link = await _channel_link()
    if link:
        rows.append([InlineKeyboardButton(text="📢 Открыть канал", url=link)])
    rows.append([InlineKeyboardButton(text="✅ Я подписался", callback_data=f"sub:{req.chat.id}")])
    try:
        await bot.send_message(
            req.user_chat_id,
            "Чтобы вступить в чат, нужно подписаться на наш канал.\nПодпишись и нажми «Я подписался».",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("sub:"))
async def on_check_sub(cb: CallbackQuery):
    chat_id = int(cb.data.split(":", 1)[1])
    if not await is_subscribed(cb.from_user.id):
        await cb.answer("Подписка пока не найдена. Подпишись на канал и нажми ещё раз.", show_alert=True)
        return
    try:
        await bot.approve_chat_join_request(chat_id, cb.from_user.id)
    except TelegramBadRequest:
        await cb.answer("Заявка уже обработана или устарела. Подай её заново.", show_alert=True)
        return
    await cb.message.edit_text("✅ Подписка найдена, ты принят(а) в группу!")
    await bot.send_message(chat_id, f"✅ Пользователь {cb.from_user.mention_html()} присутствует в канале.")
    await cb.answer()


@router.message(F.new_chat_members)
async def greet(m: Message):
    for u in m.new_chat_members:
        if u.is_bot:
            continue
        await m.answer(
            f"Добро пожаловать в {config.CHAT_NAME}, {u.mention_html()}! 👋\n"
            "Перед тем как начать общаться, ознакомься с правилами:\n\n" + get_rules(m.chat.id)
        )
