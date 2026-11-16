"""Общие функции: проверка админа/подписки, мут, наказание, разбор сроков, логи."""
import re
import time
from datetime import timedelta

from aiogram.enums import ChatMemberStatus
from aiogram.types import ChatPermissions, Message

import config
import db
from loader import bot
from rules import RULES

_admin_cache: dict[int, tuple[float, set[int]]] = {}


async def get_admin_ids(chat_id: int) -> set[int]:
    now = time.time()
    cached = _admin_cache.get(chat_id)
    if cached and now - cached[0] < 60:
        return cached[1]
    ids = {a.user.id for a in await bot.get_chat_administrators(chat_id)}
    _admin_cache[chat_id] = (now, ids)
    return ids


async def is_admin(chat_id: int, user_id: int) -> bool:
    return user_id in await get_admin_ids(chat_id)


async def is_admin_msg(m: Message) -> bool:
    if m.sender_chat and m.sender_chat.id == m.chat.id:
        return True
    return bool(m.from_user) and await is_admin(m.chat.id, m.from_user.id)


async def is_subscribed(user_id: int) -> bool:
    if not config.CHANNEL_ID:
        return True
    try:
        m = await bot.get_chat_member(config.CHANNEL_ID, user_id)
        return m.status in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR)
    except Exception:
        return False


_DUR_RE = re.compile(r"^\s*(\d+)\s*([a-zа-яё]+)?", re.I)
_UNITS = (
    (r"м|мин|минут[аыу]?|m|min", 60),
    (r"ч|час|часа|часов|h|hr", 3600),
    (r"д|дн|дня|дней|день|d", 86400),
    (r"н|нед|неделя|недели|недель|неделю|w", 604800),
    (r"мес|месяц|месяца|месяцев", 30 * 86400),
)


def split_duration(text: str) -> tuple[int | None, str]:
    mt = _DUR_RE.match(text)
    if not mt:
        return None, text.strip()
    n, word = int(mt.group(1)), (mt.group(2) or "").lower()
    for pattern, mult in _UNITS:
        if re.fullmatch(pattern, word):
            return n * mult, text[mt.end():].strip()
    return n * 3600, (text[mt.start(2):].strip() if word else "")


def fmt_duration(secs: int) -> str:
    d, rem = divmod(int(secs), 86400)
    h, rem = divmod(rem, 3600)
    mnt = rem // 60
    parts = [f"{d} д." if d else "", f"{h} ч." if h else "", f"{mnt} мин." if mnt and not d else ""]
    return " ".join(p for p in parts if p) or "1 мин."


async def log_action(text: str):
    if config.LOG_CHAT_ID:
        try:
            await bot.send_message(config.LOG_CHAT_ID, text)
        except Exception:
            pass


async def mute(chat_id: int, user_id: int, seconds: int):
    await bot.restrict_chat_member(chat_id, user_id, ChatPermissions(can_send_messages=False),
                                   until_date=timedelta(seconds=max(seconds, 60)))


async def unmute(chat_id: int, user_id: int):
    chat = await bot.get_chat(chat_id)
    perms = chat.permissions or ChatPermissions(
        can_send_messages=True, can_send_other_messages=True, can_send_polls=True,
        can_add_web_page_previews=True)
    await bot.restrict_chat_member(chat_id, user_id, perms)


async def punish(chat_id: int, user, reason: str, mute_seconds: int = 0, warn: bool = True, moderator=None):
    lines = [f"⚠️ {user.mention_html()}: {reason}"]
    if mute_seconds:
        await mute(chat_id, user.id, mute_seconds)
        lines.append(f"🔇 Мут на {fmt_duration(mute_seconds)}")
    if warn:
        count, bans = db.add_warn(chat_id, user.id, reason, moderator.id if moderator else 0)
        if count == 0:
            if bans == 1:
                await bot.ban_chat_member(chat_id, user.id, until_date=timedelta(days=3))
                lines.append("⛔ 3 предупреждения — бан на 3 дня.")
            else:
                await bot.ban_chat_member(chat_id, user.id)
                lines.append("⛔ 3 предупреждения — бан навсегда.")
        else:
            lines.append(f"Предупреждений: {count}/3 (каждое сгорает через {config.WARN_TTL_DAYS} дн.)")
    if moderator:
        lines.append(f"👮 Модератор: {moderator.mention_html()}")
    text = "\n".join(lines)
    await bot.send_message(chat_id, text)
    await log_action(text)


def get_rules(chat_id: int) -> str:
    return db.get_setting(chat_id, "rules") or RULES
