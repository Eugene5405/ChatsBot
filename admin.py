"""Настройка бота прямо из Telegram: /settings, /setrules, /resetrules, /pinrules, /status."""
from aiogram import F, Router
from aiogram.enums import ChatMemberStatus
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import config
import db
from loader import bot
from utils import get_rules, is_admin, is_admin_msg

router = Router()
router.message.filter(F.chat.type.in_({"group", "supergroup"}))


def settings_kb(chat_id: int) -> InlineKeyboardMarkup:
    rows = []
    for kind, label in config.FILTER_LABELS.items():
        mark = "✅" if db.filter_on(chat_id, kind) else "❌"
        rows.append([InlineKeyboardButton(text=f"{mark} {label}", callback_data=f"st:{kind}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("settings"))
async def cmd_settings(m: Message):
    if not await is_admin_msg(m):
        return
    await m.answer("⚙️ <b>Автомодерация</b>\nНажми на пункт, чтобы включить или выключить:",
                   reply_markup=settings_kb(m.chat.id))


@router.callback_query(F.data.startswith("st:"))
async def on_toggle(cb: CallbackQuery):
    chat_id = cb.message.chat.id
    if not await is_admin(chat_id, cb.from_user.id):
        await cb.answer("Только для админов.", show_alert=True)
        return
    kind = cb.data.split(":", 1)[1]
    if kind in config.FILTER_LABELS:
        db.set_setting(chat_id, "f_" + kind, "0" if db.filter_on(chat_id, kind) else "1")
    await cb.message.edit_reply_markup(reply_markup=settings_kb(chat_id))
    await cb.answer("Готово")


@router.message(Command("setrules"))
async def cmd_setrules(m: Message):
    if not await is_admin_msg(m):
        return
    src = m.reply_to_message
    if not src or not (src.text or src.caption):
        await m.reply("Напиши новый текст правил отдельным сообщением, а потом ответь на него командой /setrules.")
        return
    html = src.html_text
    if "<blockquote" not in html:
        html = f"<blockquote expandable>{html}</blockquote>"
    if len(html) > 3500:
        await m.reply("❌ Текст слишком длинный (лимит Telegram). Сократи правила.")
        return
    db.set_setting(m.chat.id, "rules", html)
    await m.reply("✅ Правила обновлены. Проверь: /rules")


@router.message(Command("resetrules"))
async def cmd_resetrules(m: Message):
    if not await is_admin_msg(m):
        return
    db.set_setting(m.chat.id, "rules", None)
    await m.reply("✅ Возвращены стандартные правила.")


@router.message(Command("pinrules"))
async def cmd_pinrules(m: Message):
    if not await is_admin_msg(m):
        return
    sent = await m.answer("❗️ <b>Правила чата</b>\n\n" + get_rules(m.chat.id))
    try:
        await bot.pin_chat_message(m.chat.id, sent.message_id, disable_notification=True)
    except Exception:
        await m.reply("❌ Не смог закрепить. Дай боту право закреплять сообщения.")


@router.message(Command("status"))
async def cmd_status(m: Message):
    if not await is_admin_msg(m):
        return
    me = await bot.get_me()
    cm = await bot.get_chat_member(m.chat.id, me.id)
    ok = lambda v: "✅" if v else "❌"
    lines = ["🔎 <b>Проверка бота</b>"]
    if cm.status != ChatMemberStatus.ADMINISTRATOR:
        lines.append("❌ Бот не админ в этой группе — сделай его админом.")
    else:
        lines += [f"{ok(cm.can_delete_messages)} удалять сообщения",
                  f"{ok(cm.can_restrict_members)} ограничивать и банить",
                  f"{ok(cm.can_invite_users)} приглашать (нужно для заявок)",
                  f"{ok(cm.can_pin_messages)} закреплять сообщения"]
    if config.CHANNEL_ID:
        try:
            ch = await bot.get_chat_member(config.CHANNEL_ID, me.id)
            good = ch.status == ChatMemberStatus.ADMINISTRATOR
            lines.append(f"{ok(good)} бот — админ в канале (нужно для проверки подписки)")
        except Exception:
            lines.append("❌ канал недоступен: проверь CHANNEL_ID и добавь бота в канал админом")
    else:
        lines.append("ℹ️ Проверка подписки выключена (CHANNEL_ID не задан)")
    lines.append("\n<b>Фильтры:</b> " + ", ".join(
        f"{label.split(' (')[0]} {ok(db.filter_on(m.chat.id, k))}" for k, label in config.FILTER_LABELS.items()))
    await m.reply("\n".join(lines))
