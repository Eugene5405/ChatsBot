"""Русская рулетка: запуск по фразе 'русская рулетка', настройка шанса (/change) и мута (/changemute)."""
import html
import random
from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import ChatPermissions, Message

import db

router = Router()

_ADMINS = {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}


def _mention(user) -> str:
    name = html.escape(user.full_name or user.first_name or "Игрок")
    return f'<a href="tg://user?id={user.id}">{name}</a>'


async def _is_admin(message: Message) -> bool:
    if not message.from_user:
        return False
    member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
    return member.status in _ADMINS


@router.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}), Command("enable", "en"))
async def cmd_enable_roulette(message: Message):
    if not await _is_admin(message):
        return
    db.set_setting(message.chat.id, "roulette_enabled", "1")
    await message.reply("🔫 Русская рулетка <b>включена</b>.")


@router.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}), Command("disable", "dis"))
async def cmd_disable_roulette(message: Message):
    if not await _is_admin(message):
        return
    db.set_setting(message.chat.id, "roulette_enabled", "0")
    await message.reply("⛔ Русская рулетка <b>выключена</b>.")


@router.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}), Command("change"))
async def cmd_change_chance(message: Message):
    if not await _is_admin(message):
        return
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit() or int(parts[1]) < 2:
        await message.reply("ℹ️ Укажите число патронов/слотов (от 2): <code>/change 6</code> (шанс 1 к 6)")
        return
    chambers = int(parts[1])
    db.set_setting(message.chat.id, "roulette_chambers", str(chambers))
    await message.reply(f"🎯 Шанс проигрыша в русской рулетке установлен: <b>1 к {chambers}</b>.")


@router.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}), Command("changemute"))
async def cmd_change_mute(message: Message):
    if not await _is_admin(message):
        return
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit() or int(parts[1]) < 1:
        await message.reply("ℹ️ Укажите время мута в минутах: <code>/changemute 5</code>")
        return
    mins = int(parts[1])
    db.set_setting(message.chat.id, "roulette_mute_mins", str(mins))
    await message.reply(f"⏱ Время мута при проигрыше в рулетке установлено: <b>{mins} мин.</b>")


@router.message(
    F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}),
    F.text.func(lambda t: t is not None and t.strip().lower() == "русская рулетка"),
)
async def play_roulette(message: Message):
    if not message.from_user:
        return
    if db.get_setting(message.chat.id, "roulette_enabled") == "0":
        await message.reply("⛔ Русская рулетка сейчас отключена в этом чате.")
        return

    chambers = int(db.get_setting(message.chat.id, "roulette_chambers") or 6)
    mute_mins = int(db.get_setting(message.chat.id, "roulette_mute_mins") or 5)

    shot = random.randint(1, chambers) == 1
    if shot:
        if await _is_admin(message):
            await message.reply(
                f"💥 <b>БАХ!</b> {_mention(message.from_user)} вытянул(а) боевой патрон, но админский иммунитет спас от мута!"
            )
            return
        try:
            until = datetime.now(timezone.utc) + timedelta(minutes=mute_mins)
            await message.bot.restrict_chat_member(
                message.chat.id,
                message.from_user.id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until,
            )
            await message.reply(
                f"💥 <b>БАХ!</b> {_mention(message.from_user)} не повезло (шанс 1 к {chambers}) — мут на <b>{mute_mins} мин.</b>!"
            )
        except TelegramBadRequest:
            await message.reply(f"💥 <b>БАХ!</b> {_mention(message.from_user)} проиграл(а), но у бота нет прав на мут.")
    else:
        stats = db.get_user_stats(message.chat.id, message.from_user.id)
        reward = 13 if stats.get("vip") else 10
        bal = db.add_balance(message.chat.id, message.from_user.id, reward)
        await message.reply(
            f"🔫 <i>Щёлк...</i> Пусто! {_mention(message.from_user)} выживает и получает <b>+{reward} Алиби</b> (баланс: <b>{bal}</b>)."
        )
