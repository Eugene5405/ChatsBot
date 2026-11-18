"""Ролеплей-команды в чате, создание/удаление своих РП-команд (/newrp, /delrp) и кулдаун 24ч."""
import html
import time

from aiogram import F, Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.filters import Command
from aiogram.types import Message

import db

router = Router()

_ADMINS = {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}

_DEFAULT_RP = {
    "обнять": "🤗 {a} крепко обнял(а) {b}!",
    "дать леща": "👋 {a} отвесил(а) смачного леща {b}!",
    "поцеловать": "😘 {a} нежно поцеловал(а) {b}!",
    "выкинуть в окно": "🪟 {a} с разбегу выкинул(а) в окно {b}!",
    "укусить": "🧛 {a} больно укусил(а) {b}!",
    "дать пять": "🙌 {a} дал(а) пять {b}!",
    "ударить": "🥊 {a} врезал(а) {b}!",
}

_COOLDOWNS: dict[tuple[int, int, str], float] = {}


def _mention(user) -> str:
    name = html.escape(user.full_name or user.first_name or "Участник")
    return f'<a href="tg://user?id={user.id}">{name}</a>'


async def _is_admin(message: Message) -> bool:
    if not message.from_user:
        return False
    member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
    return member.status in _ADMINS


@router.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}), Command("enablerp", "enrp"))
async def cmd_enable_rp(message: Message):
    if not await _is_admin(message):
        return
    db.set_setting(message.chat.id, "rp_enabled", "1")
    await message.reply("✅ Ролеплей-команды <b>включены</b> в этом чате.")


@router.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}), Command("disablerp", "disrp"))
async def cmd_disable_rp(message: Message):
    if not await _is_admin(message):
        return
    db.set_setting(message.chat.id, "rp_enabled", "0")
    await message.reply("⛔ Ролеплей-команды <b>выключены</b> в этом чате.")


@router.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}), Command("newrp"))
async def cmd_new_rp(message: Message):
    if not await _is_admin(message):
        return
    raw = (message.text or "").split(maxsplit=1)
    if len(raw) < 2 or not raw[1].strip():
        await message.reply(
            "ℹ️ Формат: <code>/newrp напоить чаем</code>\n"
            "Или со своим текстом: <code>/newrp напоить чаем | ☕ {a} напоил(а) горячим чаем {b}</code>"
        )
        return

    body = raw[1].strip()
    if "|" in body:
        trig, tmpl = [p.strip() for p in body.split("|", 1)]
    else:
        trig = body.lower()
        tmpl = f"🎭 {{a}} выполнил(а) действие «{html.escape(trig)}» по отношению к {{b}}!"

    if not trig:
        await message.reply("⚠️ Укажите название команды.")
        return

    db.add_custom_rp(message.chat.id, trig.lower(), tmpl)
    await message.reply(f"✅ Новая РП-команда <b>«{html.escape(trig.lower())}»</b> добавлена!")


@router.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}), Command("delrp"))
async def cmd_del_rp(message: Message):
    if not await _is_admin(message):
        return
    raw = (message.text or "").split(maxsplit=1)
    if len(raw) < 2 or not raw[1].strip():
        await message.reply("ℹ️ Укажите название команды: <code>/delrp напоить чаем</code>")
        return

    trig = raw[1].strip().lower()
    if db.delete_custom_rp(message.chat.id, trig):
        await message.reply(f"🗑 РП-команда <b>«{html.escape(trig)}»</b> удалена.")
    else:
        await message.reply("⚠️ Такой пользовательской РП-команды не найдено.")


@router.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}), F.text)
async def handle_rp_trigger(message: Message):
    if not message.from_user or not message.text:
        return
    if message.text.startswith("/"):
        return

    if db.get_setting(message.chat.id, "rp_enabled") == "0":
        return

    text_clean = message.text.strip().lower()
    all_rps = dict(_DEFAULT_RP)
    all_rps.update(db.get_custom_rps(message.chat.id))

    if text_clean not in all_rps:
        return

    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.reply(f"↩️ Используй команду <b>«{html.escape(text_clean)}»</b> ответом на сообщение участника.")
        return

    target = message.reply_to_message.from_user
    if target.id == message.from_user.id:
        await message.reply("🤔 Нельзя применить РП-действие на самого себя.")
        return

    stats = db.get_user_stats(message.chat.id, message.from_user.id)
    cd_seconds = 12 * 3600 if stats.get("vip") else 24 * 3600
    key = (message.chat.id, message.from_user.id, text_clean)
    now = time.time()
    last = _COOLDOWNS.get(key, 0.0)

    if now - last < cd_seconds:
        left_h = max(1, int((cd_seconds - (now - last)) // 3600))
        await message.reply(f"⏳ Команду <b>«{html.escape(text_clean)}»</b> можно использовать снова через ~{left_h} ч.")
        return

    _COOLDOWNS[key] = now
    template = all_rps[text_clean]
    out = template.format(a=_mention(message.from_user), b=_mention(target))
    await message.answer(out)
