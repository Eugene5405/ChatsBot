"""Заявки на вступление, приветствие (вход/добавление) и прощание при выходе."""
import html
import logging

from aiogram import F, Router
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import CallbackQuery, ChatJoinRequest, ChatMemberUpdated, InlineKeyboardButton, InlineKeyboardMarkup

import config
import db
import rules
import webapp
from loader import bot

router = Router()

_ACTIVE = {ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}
_LEFT = {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED}


def _mention(user) -> str:
    name = html.escape(user.full_name or user.first_name or "Участник")
    return f'<a href="tg://user?id={user.id}">{name}</a>'


async def _is_subscribed(user_id: int) -> bool:
    if not config.CHANNEL_ID:
        return True
    try:
        m = await bot.get_chat_member(config.CHANNEL_ID, user_id)
        return m.status in _ACTIVE
    except TelegramBadRequest as e:
        logging.warning("Проверка подписки не удалась (%s) — пропускаю", e)
        return True


async def _channel_url() -> str | None:
    if config.CHANNEL_URL:
        return config.CHANNEL_URL
    if not config.CHANNEL_ID:
        return None
    chat = await bot.get_chat(config.CHANNEL_ID)
    return f"https://t.me/{chat.username}" if chat.username else chat.invite_link


def _ask_sub_kb(chat_id: int, url: str | None) -> InlineKeyboardMarkup:
    rows = []
    if url:
        rows.append([InlineKeyboardButton(text="📢 Открыть канал", url=url)])
    rows.append([InlineKeyboardButton(text="✅ Я подписался", callback_data=f"chksub:{chat_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _send_welcome(chat_id: int, chat_title: str, user):
    title = html.escape(chat_title or config.CHAT_TITLE)
    custom = db.get_setting(chat_id, "welcome_text")
    if custom:
        rendered = html.escape(custom).replace("{user}", _mention(user)).replace("{chat}", title)
        text = f"{rendered}\n\n<blockquote expandable>{rules.get_rules(chat_id)}</blockquote>"
    else:
        text = (
            f"👋 Добро пожаловать в <b>{title}</b>, {_mention(user)}!\n\n"
            f"Ознакомься с правилами, чтобы не словить мут или бан:\n"
            f"<blockquote expandable>{rules.get_rules(chat_id)}</blockquote>"
        )
    await bot.send_message(chat_id, text)


@router.chat_join_request()
async def on_join_request(req: ChatJoinRequest):
    if await _is_subscribed(req.from_user.id):
        await req.approve()
        return

    try:
        await bot.send_message(
            req.from_user.id,
            f"Чтобы вступить в <b>{html.escape(req.chat.title or config.CHAT_TITLE)}</b>, "
            f"сначала подпишись на наш канал, затем нажми кнопку ниже:",
            reply_markup=_ask_sub_kb(req.chat.id, await _channel_url()),
        )
    except (TelegramForbiddenError, TelegramBadRequest):
        pass


@router.callback_query(F.data.startswith("chksub:"))
async def on_check_sub(cb: CallbackQuery):
    chat_id = int(cb.data.split(":", 1)[1])
    if not await _is_subscribed(cb.from_user.id):
        await cb.answer("Подписка пока не видна. Подпишись на канал и нажми снова.", show_alert=True)
        return
    try:
        await bot.approve_chat_join_request(chat_id, cb.from_user.id)
        await cb.message.edit_text("✅ Отлично, заявка одобрена! Добро пожаловать в чат.")
    except TelegramBadRequest as e:
        await cb.message.edit_text(f"Не удалось принять заявку (возможно, она уже неактуальна): {e.message}")
    await cb.answer()


@router.chat_member()
async def on_chat_member_update(event: ChatMemberUpdated):
    old_status = event.old_chat_member.status
    new_status = event.new_chat_member.status
    user = event.new_chat_member.user

    if user.is_bot:
        return

    if new_status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR):
        webapp.register_user_chat(user.id, event.chat.id)

    if old_status in _LEFT and new_status in _ACTIVE:
        await _send_welcome(event.chat.id, event.chat.title, user)

    elif old_status in _ACTIVE and new_status == ChatMemberStatus.LEFT:
        custom_bye = db.get_setting(event.chat.id, "goodbye_text")
        if custom_bye:
            msg = html.escape(custom_bye).replace("{user}", _mention(user))
        else:
            msg = f"👋 {_mention(user)} покинул(а) чат. Удачи и всего хорошего!"
        await bot.send_message(event.chat.id, msg)
