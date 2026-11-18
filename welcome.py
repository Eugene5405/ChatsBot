"""Заявки на вступление, приветствие/прощание участников и регистрация добавления самого бота."""
import html
import logging

from aiogram import F, Router
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import (
    CallbackQuery,
    ChatJoinRequest,
    ChatMemberUpdated,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

import config
import db
import rules
from loader import bot

router = Router()

_ACTIVE = {ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}
_LEFT = {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED}


def mention(user) -> str:
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
    settings = db.get_chat_settings(chat_id)
    if not settings.get("welcome", True):
        return
    title = html.escape(chat_title or config.CHAT_TITLE)
    text = (
        f"👋 Добро пожаловать в <b>{title}</b>, {mention(user)}!

"
        f"Ознакомься с правилами, чтобы не словить мут или бан:
"
        f"<blockquote expandable>{rules.get_rules(chat_id)}</blockquote>"
    )
    await bot.send_message(chat_id, text)


@router.my_chat_member()
async def on_bot_membership_update(event: ChatMemberUpdated):
    """Срабатывает, когда самого бота добавили в группу, выдали админку или удалили из чата."""
    old_status = event.old_chat_member.status
    new_status = event.new_chat_member.status
    chat = event.chat
    actor = event.from_user

    if old_status in _LEFT and new_status in _ACTIVE:
        db.register_chat(chat.id, chat.title)
        title = html.escape(chat.title or "Чат")
        try:
            await bot.send_message(
                chat.id,
                f"👋 Привет! Я <b>Хранитель чата</b> — подключился к группе <b>{title}</b>.

"
                f"Чтобы включить защиту от спама, мата и команду <code>-чат</code>, "
                f"выдайте мне права администратора (удаление сообщений и блокировка участников) и напишите <code>/status</code>.",
            )
        except TelegramBadRequest:
            pass

        if actor and not actor.is_bot:
            try:
                await bot.send_message(
                    actor.id,
                    f"✅ Бот успешно добавлен в чат <b>{title}</b> (<code>{chat.id}</code>) и зарегистрирован в админ-панели!",
                )
            except (TelegramForbiddenError, TelegramBadRequest):
                pass

    elif old_status in _ACTIVE and new_status in _LEFT:
        db.delete_chat(chat.id)
        title = html.escape(chat.title or "Чат")
        if actor and not actor.is_bot:
            try:
                await bot.send_message(
                    actor.id,
                    f"🗑 Бот был удалён из чата <b>{title}</b> (<code>{chat.id}</code>). Чат убран из админ-панели.",
                )
            except (TelegramForbiddenError, TelegramBadRequest):
                pass


@router.chat_join_request()
async def on_join_request(req: ChatJoinRequest):
    db.register_chat(req.chat.id, req.chat.title)
    settings = db.get_chat_settings(req.chat.id)
    if not settings.get("subcheck", True) or await _is_subscribed(req.from_user.id):
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

    db.register_chat(event.chat.id, event.chat.title)

    if old_status in _LEFT and new_status in _ACTIVE:
        await _send_welcome(event.chat.id, event.chat.title, user)

    elif old_status in _ACTIVE and new_status == ChatMemberStatus.LEFT:
        await bot.send_message(
            event.chat.id,
            f"👋 {mention(user)} покинул(а) чат. Удачи и всего хорошего!",
        )
