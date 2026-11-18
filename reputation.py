"""Система репутации: +, +реп, +rep, -, -реп, -rep, /lookrep, /setrep и порог 100 репутации."""
import html
import time

from aiogram import F, Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.filters import Command
from aiogram.types import Message

import db

router = Router()

_ADMINS = {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}
_PLUS_TRIGGERS = {"+", "+реп", "+rep"}
_MINUS_TRIGGERS = {"-", "-реп", "-rep"}

_REP_COOLDOWN: dict[tuple[int, int, int], float] = {}


def _mention(user) -> str:
    name = html.escape(user.full_name or user.first_name or "Участник")
    return f'<a href="tg://user?id={user.id}">{name}</a>'


async def _is_admin(message: Message) -> bool:
    if not message.from_user:
        return False
    member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
    return member.status in _ADMINS


@router.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}), Command("lookrep"))
async def cmd_lookrep(message: Message):
    target = (
        message.reply_to_message.from_user
        if message.reply_to_message and message.reply_to_message.from_user
        else message.from_user
    )
    if not target:
        return
    stats = db.get_user_stats(message.chat.id, target.id)
    rep = stats["reputation"]
    note = "\n🌟 <i>Достигнуто 100+ репутации — доступна подача заявки в администраторы!</i>" if rep >= 100 else ""
    await message.reply(f"🏅 Репутация {_mention(target)}: <b>{rep}</b>{note}")


@router.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}), Command("setrep"))
async def cmd_setrep(message: Message):
    if not await _is_admin(message):
        return
    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.reply("↩️ Ответьте на сообщение участника: <code>/setrep 50</code>")
        return
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.reply("ℹ️ Укажите число: <code>/setrep 50</code>")
        return
    try:
        val = int(parts[1])
    except ValueError:
        await message.reply("⚠️ Значение должно быть целым числом.")
        return

    target = message.reply_to_message.from_user
    new_rep = db.set_reputation(message.chat.id, target.id, val)
    await message.reply(f"✅ Репутация {_mention(target)} установлена на <b>{new_rep}</b>.")


@router.message(
    F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}),
    F.text.func(lambda t: t is not None and t.strip().lower() in (_PLUS_TRIGGERS | _MINUS_TRIGGERS)),
)
async def handle_rep_vote(message: Message):
    if not message.from_user or not message.reply_to_message or not message.reply_to_message.from_user:
        return

    target = message.reply_to_message.from_user
    voter = message.from_user

    if target.id == voter.id or target.is_bot:
        return

    cmd = message.text.strip().lower()

    if cmd in _PLUS_TRIGGERS:
        stats = db.get_user_stats(message.chat.id, voter.id)
        cd = 1800 if stats.get("vip") else 3600
        key = (message.chat.id, voter.id, target.id)
        now = time.time()
        if now - _REP_COOLDOWN.get(key, 0.0) < cd:
            await message.reply("⏳ Повышать репутацию одному и тому же участнику можно раз в час.")
            return
        _REP_COOLDOWN[key] = now

        old_rep = db.get_user_stats(message.chat.id, target.id)["reputation"]
        new_rep = db.add_reputation(message.chat.id, target.id, 1)
        extra = ""
        if old_rep < 100 <= new_rep:
            extra = "\n🎉 <b>Поздравляем!</b> Вы набрали <b>100 репутации</b> и теперь можете подать заявку в админы чата!"
        await message.reply(
            f"⬆️ {_mention(voter)} повысил(а) репутацию {_mention(target)}! Теперь: <b>{new_rep}</b>.{extra}"
        )

    elif cmd in _MINUS_TRIGGERS:
        if not await _is_admin(message):
            return
        new_rep = db.add_reputation(message.chat.id, target.id, -1)
        await message.reply(
            f"⬇️ Администратор {_mention(voter)} понизил(а) репутацию {_mention(target)}. Теперь: <b>{new_rep}</b>."
        )
