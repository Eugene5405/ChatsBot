"""Система репортов (как в Ирисе): жалоба ответом на сообщение + уведомление админам в ЛС со ссылкой."""
import html
import logging
from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import (
    CallbackQuery,
    ChatPermissions,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

router = Router()

_ADMINS = {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}
_TRIGGERS = ("репорт", "!репорт", "/report", "!report")


def _mention(user) -> str:
    name = html.escape(user.full_name or user.first_name or "Пользователь")
    return f'<a href="tg://user?id={user.id}">{name}</a>'


def _msg_link(chat, message_id: int) -> str | None:
    if chat.username:
        return f"https://t.me/{chat.username}/{message_id}"
    cid = str(chat.id)
    if cid.startswith("-100"):
        return f"https://t.me/c/{cid[4:]}/{message_id}"
    return None


@router.message(
    F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}),
    F.text.func(
        lambda t: t is not None
        and any(t.strip().lower() == tr or t.strip().lower().startswith(tr + " ") for tr in _TRIGGERS)
    ),
)
async def on_report(message: Message):
    if not message.from_user:
        return

    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.reply("ℹ️ Чтобы отправить жалобу, ответьте на сообщение нарушителя: <code>репорт причина</code>")
        return

    target = message.reply_to_message.from_user
    reporter = message.from_user

    if target.id == reporter.id:
        await message.reply("🤔 Нельзя отправить репорт на самого себя.")
        return

    if target.is_bot:
        await message.reply("🤖 На ботов жалобы не принимаются.")
        return

    parts = message.text.strip().split(maxsplit=1)
    reason = html.escape(parts[1].strip()) if len(parts) > 1 else "Не указана"

    # 1. Публикуем уведомление в чате
    await message.answer(
        f"🚨 <b>Репорт отправлен администраторам!</b>
"
        f"👤 От: {_mention(reporter)}
"
        f"🎯 На: {_mention(target)}
"
        f"📝 Причина: <i>{reason}</i>"
    )

    # 2. Отправляем карточку жалобы в ЛС всем админам со ссылкой на сообщение
    reported_msg = message.reply_to_message
    snippet = html.escape((reported_msg.text or reported_msg.caption or "[Медиа / вложение]")[:300])
    chat_title = html.escape(message.chat.title or "Чат")
    link = _msg_link(message.chat, reported_msg.message_id)

    admin_text = (
        f"🚨 <b>Новый репорт в чате «{chat_title}»</b>

"
        f"👤 <b>Отправил:</b> {_mention(reporter)} (<code>{reporter.id}</code>)
"
        f"🎯 <b>Нарушитель:</b> {_mention(target)} (<code>{target.id}</code>)
"
        f"📝 <b>Причина:</b> {reason}
"
        f"💬 <b>Сообщение:</b> <blockquote>{snippet}</blockquote>"
    )

    rows = []
    if link:
        rows.append([InlineKeyboardButton(text="🔗 Перейти к сообщению", url=link)])

    cid = message.chat.id
    mid = reported_msg.message_id
    uid = target.id

    rows.append([
        InlineKeyboardButton(text="🗑 Удалить", callback_data=f"rep:del:{cid}:{mid}:{uid}"),
        InlineKeyboardButton(text="🔇 Мут 1ч", callback_data=f"rep:mute:{cid}:{mid}:{uid}"),
    ])
    rows.append([
        InlineKeyboardButton(text="🚫 Бан", callback_data=f"rep:ban:{cid}:{mid}:{uid}"),
        InlineKeyboardButton(text="✅ Отклонить", callback_data=f"rep:skip:{cid}:{mid}:{uid}"),
    ])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)

    try:
        admins = await message.bot.get_chat_administrators(message.chat.id)
        for adm in admins:
            if adm.user.is_bot:
                continue
            try:
                await message.bot.send_message(adm.user.id, admin_text, reply_markup=kb)
            except (TelegramForbiddenError, TelegramBadRequest):
                pass
    except TelegramBadRequest as e:
        logging.warning("Не удалось получить список админов для репорта: %s", e)


@router.callback_query(F.data.startswith("rep:"))
async def on_report_action(cb: CallbackQuery):
    _, action, cid_s, mid_s, uid_s = cb.data.split(":")
    chat_id, msg_id, target_id = int(cid_s), int(mid_s), int(uid_s)

    try:
        member = await cb.bot.get_chat_member(chat_id, cb.from_user.id)
        if member.status not in _ADMINS:
            await cb.answer("Вы больше не администратор этого чата.", show_alert=True)
            return
    except TelegramBadRequest:
        await cb.answer("Не удалось проверить права.", show_alert=True)
        return

    try:
        if action == "del":
            await cb.bot.delete_message(chat_id, msg_id)
            status_line = f"🗑 Сообщение удалено админом {_mention(cb.from_user)}."
        elif action == "mute":
            await cb.bot.delete_message(chat_id, msg_id)
            until = datetime.now(timezone.utc) + timedelta(hours=1)
            await cb.bot.restrict_chat_member(
                chat_id,
                target_id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until,
            )
            status_line = f"🔇 Выдан мут на 1 час и удалено сообщение ({_mention(cb.from_user)})."
        elif action == "ban":
            await cb.bot.delete_message(chat_id, msg_id)
            await cb.bot.ban_chat_member(chat_id, target_id)
            status_line = f"🚫 Пользователь забанен админом {_mention(cb.from_user)}."
        else:
            status_line = f"✅ Репорт закрыт без наказания ({_mention(cb.from_user)})."

        await cb.message.edit_text(f"{cb.message.html_text}\n\n<b>Итог:</b> {status_line}", reply_markup=None)
        await cb.answer("Выполнено!")
    except TelegramBadRequest as e:
        await cb.answer(f"Ошибка Telegram: {e.message}", show_alert=True)
