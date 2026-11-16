"""Команды модераторов. Работают и со «/», и словом без «/» — ответом на сообщение нарушителя."""
from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

import config
import db
from loader import bot
from utils import fmt_duration, is_admin, is_admin_msg, log_action, mute, punish, split_duration, unmute

router = Router()
router.message.filter(F.chat.type.in_({"group", "supergroup"}))

SLASH_MAP = {"warn": "пред", "unwarn": "анпред", "mute": "мут", "unmute": "размут",
             "ban": "бан", "unban": "разбан", "kick": "кик"}
TEXT_CMDS = {"бан", "разбан", "мут", "размут", "пред", "варн", "кик"}
PUNISHING = {"бан", "мут", "пред", "кик"}


def parse_text_cmd(text: str):
    t = (text or "").strip()
    low = t.lower()
    for prefix in ("снять пред", "снять варн"):
        if low.startswith(prefix):
            return "анпред", t[len(prefix):].strip()
    parts = t.split(None, 1)
    if not parts:
        return None
    word = parts[0].lower().strip(".,!:;")
    if word in TEXT_CMDS:
        return ("пред" if word == "варн" else word), (parts[1].strip() if len(parts) > 1 else "")
    return None


async def run(m: Message, cmd: str, rest: str):
    target = m.reply_to_message.from_user if m.reply_to_message else None
    if target is None:
        await m.reply("📝 Нет информации о пользователе. Ответь командой на его сообщение.")
        return
    chat_id = m.chat.id
    mod = m.from_user
    if cmd in PUNISHING and (target.is_bot or await is_admin(chat_id, target.id)):
        await m.reply("📝 Эту цель наказывать нельзя (бот или админ).")
        return

    try:
        if cmd == "бан":
            await bot.ban_chat_member(chat_id, target.id)
            text = f"🔴 {target.mention_html()} получает бан навсегда"
            if rest:
                text += f"\nПричина: {rest}"
            text += f"\n👮 Модератор: {mod.mention_html()}"
            await m.answer(text)
            await log_action(text)

        elif cmd == "разбан":
            await bot.unban_chat_member(chat_id, target.id, only_if_banned=True)
            await m.answer(f"✅ Пользователь {target.mention_html()} разбанен. Теперь его можно добавить в чат.")

        elif cmd == "кик":
            await bot.ban_chat_member(chat_id, target.id)
            await bot.unban_chat_member(chat_id, target.id)
            text = f"👢 {target.mention_html()} исключён из чата.\n👮 Модератор: {mod.mention_html()}"
            await m.answer(text)
            await log_action(text)

        elif cmd == "мут":
            secs, reason = split_duration(rest)
            secs = secs or config.DEFAULT_MUTE_SECONDS
            await mute(chat_id, target.id, secs)
            text = f"🔇 {target.mention_html()} получает мут на {fmt_duration(secs)}"
            if reason:
                text += f"\nПричина: {reason}"
            text += f"\n👮 Модератор: {mod.mention_html()}"
            await m.answer(text)
            await log_action(text)

        elif cmd == "размут":
            await unmute(chat_id, target.id)
            await m.answer(f"🔊 С {target.mention_html()} снят мут.")

        elif cmd == "пред":
            await punish(chat_id, target, rest or "нарушение правил", moderator=mod)

        elif cmd == "анпред":
            left = db.remove_last_warn(chat_id, target.id)
            await m.answer(f"✅ Последнее предупреждение у {target.mention_html()} снято. Осталось: {left}/3")
    except TelegramBadRequest as e:
        await m.reply(f"❌ Не получилось: {e.message}\nПроверь, что у бота есть права банить и ограничивать участников.")


@router.message(Command(*SLASH_MAP))
async def slash_cmd(m: Message, command: CommandObject):
    if not await is_admin_msg(m):
        return
    await run(m, SLASH_MAP[command.command.lower()], command.args or "")


@router.message(F.reply_to_message, F.text.func(lambda t: parse_text_cmd(t) is not None))
async def text_cmd(m: Message):
    if not await is_admin_msg(m):
        raise SkipHandler
    cmd, rest = parse_text_cmd(m.text)
    await run(m, cmd, rest)
