"""Модерация в группе: бан/анбан, мут/анмут, варн/анварн, кик (ответом и по @username, с учётом щитов из магазина)."""
import html
import re
from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import ChatPermissions, Message

import config
import db
from loader import bot

router = Router()

_ADMIN_STATUSES = {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}

_FULL_PERMS = ChatPermissions(
    can_send_messages=True,
    can_send_audios=True,
    can_send_documents=True,
    can_send_photos=True,
    can_send_videos=True,
    can_send_video_notes=True,
    can_send_voice_notes=True,
    can_send_polls=True,
    can_send_other_messages=True,
    can_add_web_page_previews=True,
    can_change_info=True,
    can_invite_users=True,
    can_pin_messages=True,
    can_manage_topics=True,
)

_MUTE_PERMS = ChatPermissions(can_send_messages=False)


def _mention(user) -> str:
    name = html.escape(user.full_name or user.first_name or "Участник")
    return f'<a href="tg://user?id={user.id}">{name}</a>'


async def _is_admin(chat_id: int, user_id: int) -> bool:
    try:
        m = await bot.get_chat_member(chat_id, user_id)
        return m.status in _ADMIN_STATUSES
    except TelegramBadRequest:
        return False


def _parse_duration(arg: str) -> timedelta:
    s = arg.strip().lower()
    m = re.match(r"^(\d+)\s*([мmчhдdнw]?)$", s)
    if not m:
        return timedelta(hours=1)
    num = max(1, int(m.group(1)))
    unit = m.group(2)
    if unit in ("м", "m"):
        return timedelta(minutes=num)
    if unit in ("д", "d"):
        return timedelta(days=num)
    if unit in ("н", "w"):
        return timedelta(weeks=num)
    return timedelta(hours=num)


def _fmt_duration(td: timedelta) -> str:
    mins = int(td.total_seconds() // 60)
    if mins < 60:
        return f"{mins} мин."
    hours = mins // 60
    if hours < 24:
        return f"{hours} ч."
    days = hours // 24
    return f"{days} д."


async def _log_action(text: str):
    if config.LOG_CHAT_ID:
        try:
            await bot.send_message(config.LOG_CHAT_ID, text)
        except TelegramBadRequest:
            pass


async def _resolve_target(msg: Message, arg: str):
    """Определяет цель: из reply_to_message или по @username / ID в аргументах."""
    if msg.reply_to_message and msg.reply_to_message.from_user:
        return msg.reply_to_message.from_user, arg

    tokens = arg.split()
    if not tokens:
        return None, arg

    first = tokens[0]
    rest = " ".join(tokens[1:]).strip()

    if first.startswith("@") or first.isdigit():
        try:
            chat_obj = await bot.get_chat(first if first.startswith("@") else int(first))
            member = await bot.get_chat_member(msg.chat.id, chat_obj.id)
            return member.user, rest
        except Exception:
            return None, arg

    return None, arg
 @router.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}), F.text)
async def handle_mod_commands(msg: Message):
    raw = (msg.text or "").strip()
    if not raw or not msg.from_user:
        return

    lines = raw.splitlines()
    first_line = lines[0].strip()
    reason = "\n".join(lines[1:]).strip()

    cmd_line = first_line[1:] if first_line.startswith("/") else first_line
    parts = cmd_line.split(maxsplit=1)
    cmd = parts[0].split("@")[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    warn_cmds = {"warn", "варн", "пред"}
    unwarn_cmds = {"unwarn", "анварн", "снятьпред", "снять_пред"}
    mute_cmds = {"mute", "мут"}
    unmute_cmds = {"unmute", "анмут", "размут"}
    ban_cmds = {"ban", "бан"}
    unban_cmds = {"unban", "анбан", "разбан"}
    kick_cmds = {"kick", "кик"}

    if cmd == "снять" and arg.lower().startswith("пред"):
        cmd = "снятьпред"
        arg = arg[4:].strip()

    all_cmds = warn_cmds | unwarn_cmds | mute_cmds | unmute_cmds | ban_cmds | unban_cmds | kick_cmds
    if cmd not in all_cmds:
        return

    target, remaining_arg = await _resolve_target(msg, arg)

    if not first_line.startswith("/") and not target:
        return

    if not await _is_admin(msg.chat.id, msg.from_user.id):
        if first_line.startswith("/"):
            await msg.reply("⛔ Эта команда доступна только администраторам чата.")
        return

    if not target:
        await msg.reply("↩️ Используй команду <b>ответом на сообщение</b> или укажи <code>@username</code>.")
        return

    if target.id == msg.from_user.id:
        await msg.reply("Нельзя применить эту команду к самому себе.")
        return

    if target.is_bot:
        await msg.reply("Нельзя применить эту команду к боту.")
        return

    if await _is_admin(msg.chat.id, target.id):
        await msg.reply("⛔ Нельзя применить команду к администратору чата.")
        return

    reason_text = f"\n📝 Причина: <i>{html.escape(reason)}</i>" if reason else ""

    try:
        # ---------- ВАРН / ПРЕД ----------
        if cmd in warn_cmds:
            if db.consume_item(msg.chat.id, target.id, "shield_warn"):
                await msg.reply(f"🛡 У {_mention(target)} сработал <b>Щит от преда</b>! Предупреждение заблокировано.")
                return
            final_reason = reason or remaining_arg or "Нарушение правил"
            count, bans = db.add_warn(msg.chat.id, target.id, final_reason, msg.from_user.id)
            if count == 0:
                if bans == 1:
                    until = datetime.now(timezone.utc) + timedelta(days=3)
                    await bot.ban_chat_member(msg.chat.id, target.id, until_date=until)
                    out = f"🔨 {_mention(target)} получил 3/3 предупреждений и отправлен в <b>бан на 3 дня</b>."
                else:
                    await bot.ban_chat_member(msg.chat.id, target.id)
                    out = f"⛔ {_mention(target)} повторно набрал 3/3 предупреждений и <b>забанен навсегда</b>."
            else:
                out = (
                    f"⚠️ {_mention(target)} получил предупреждение (<b>{count}/3</b>)."
                    f"\n📝 Причина: <i>{html.escape(final_reason)}</i>"
                )
            await msg.reply(out)
            await _log_action(f"[{html.escape(msg.chat.title or '')}] {out}")

        # ---------- АНВАРН / СНЯТЬ ПРЕД ----------
        elif cmd in unwarn_cmds:
            left = db.remove_last_warn(msg.chat.id, target.id)
            out = f"✅ С {_mention(target)} снято одно предупреждение. Осталось: <b>{left}/3</b>.{reason_text}"
            await msg.reply(out)
            await _log_action(f"[{html.escape(msg.chat.title or '')}] {out}")

        # ---------- МУТ ----------
        elif cmd in mute_cmds:
            if db.consume_item(msg.chat.id, target.id, "shield_mute"):
                await msg.reply(f"🛡 У {_mention(target)} сработал <b>Щит от мута</b>! Мут отменён.")
                return
            arg_parts = remaining_arg.split(maxsplit=1)
            dur_str = arg_parts[0] if arg_parts else ""
            inline_reason = arg_parts[1] if len(arg_parts) > 1 else ""
            if inline_reason and not reason:
                reason_text = f"\n📝 Причина: <i>{html.escape(inline_reason)}</i>"
            td = _parse_duration(dur_str) if dur_str else timedelta(hours=1)
            until = datetime.now(timezone.utc) + td
            await bot.restrict_chat_member(msg.chat.id, target.id, permissions=_MUTE_PERMS, until_date=until)
            out = f"🔇 {_mention(target)} получил мут на <b>{_fmt_duration(td)}</b>.{reason_text}"
            await msg.reply(out)
            await _log_action(f"[{html.escape(msg.chat.title or '')}] {out}")

        # ---------- АНМУТ / РАЗМУТ ----------
        elif cmd in unmute_cmds:
            await bot.restrict_chat_member(msg.chat.id, target.id, permissions=_FULL_PERMS)
            out = f"🔊 С {_mention(target)} снят мут (анмут).{reason_text}"
            await msg.reply(out)
            await _log_action(f"[{html.escape(msg.chat.title or '')}] {out}")

        # ---------- БАН ----------
        elif cmd in ban_cmds:
            if db.consume_item(msg.chat.id, target.id, "shield_ban"):
                await msg.reply(f"🛡 У {_mention(target)} сработал <b>Щит от бана</b>! Блокировка отменена.")
                return
            await bot.ban_chat_member(msg.chat.id, target.id)
            out = f"⛔ {_mention(target)} забанен.{reason_text}"
            await msg.reply(out)
            await _log_action(f"[{html.escape(msg.chat.title or '')}] {out}")

        # ---------- АНБАН / РАЗБАН ----------
        elif cmd in unban_cmds:
            await bot.unban_chat_member(msg.chat.id, target.id, only_if_banned=True)
            out = f"🕊 {_mention(target)} разбанен (анбан).{reason_text}"
            await msg.reply(out)
            await _log_action(f"[{html.escape(msg.chat.title or '')}] {out}")

        # ---------- КИК ----------
        elif cmd in kick_cmds:
            await bot.ban_chat_member(msg.chat.id, target.id)
            await bot.unban_chat_member(msg.chat.id, target.id)
            out = f"👢 {_mention(target)} исключён из чата.{reason_text}"
            await msg.reply(out)
            await _log_action(f"[{html.escape(msg.chat.title or '')}] {out}")

    except TelegramBadRequest as e:
        await msg.reply(f"⚠️ Не удалось выполнить действие: <code>{html.escape(e.message)}</code>")
