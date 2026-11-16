"""Информационные команды: /start, /help, /rules и «Правила», «кто админ», /warns."""
import time
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

import config
import db
from loader import bot
from utils import get_rules

router = Router()

RULES_WORDS = {"правила", "правила чата", "rules"}
ADMIN_WORDS = {"кто админ", "кто админы", "админы", "кто администратор"}


def _norm(t) -> str:
    return (t or "").strip().lower().strip("?!.,: ")


@router.message(Command("start"), F.chat.type == "private")
async def cmd_start(m: Message):
    await m.answer(f"Привет! Я «{config.CHAT_NAME}». Слежу за порядком, принимаю заявки и напоминаю правила. "
                   "Напиши /rules, чтобы увидеть правила.")


@router.message(Command("help"))
async def cmd_help(m: Message):
    await m.answer(
        "<b>Для всех:</b>\n"
        "/rules или «Правила» — правила чата\n"
        "«кто админ» — список админов\n"
        "/warns — сколько у тебя предупреждений (или ответом на чужое сообщение)\n\n"
        "<b>Для админов</b> (ответом на сообщение нарушителя, можно без «/»):\n"
        "Бан / Разбан / Кик\n"
        "Мут 1д (30м, 12ч, 1н) / Размут\n"
        "Пред — предупреждение, Снять пред — снять последнее\n"
        "Причину пиши на второй строке.\n\n"
        "<b>Настройка (админы):</b>\n"
        "/settings — включить/выключить фильтры\n"
        "/setrules — ответом на сообщение: новый текст правил\n"
        "/resetrules — вернуть стандартные правила\n"
        "/pinrules — отправить и закрепить правила\n"
        "/status — проверка прав бота"
    )


@router.message(Command("rules"))
@router.message(F.text.func(lambda t: _norm(t) in RULES_WORDS))
async def cmd_rules(m: Message):
    await m.reply(get_rules(m.chat.id))


@router.message(F.text.func(lambda t: _norm(t) in ADMIN_WORDS), F.chat.type.in_({"group", "supergroup"}))
async def who_admin(m: Message):
    admins = await bot.get_chat_administrators(m.chat.id)
    lines = [f"• {a.user.mention_html()}" for a in admins if not a.user.is_bot]
    await m.reply("👮 <b>Админы:</b>\n" + "\n".join(lines))


@router.message(Command("warns"), F.chat.type.in_({"group", "supergroup"}))
async def cmd_warns(m: Message):
    target = m.reply_to_message.from_user if m.reply_to_message and m.reply_to_message.from_user else m.from_user
    rows = db.list_warns(m.chat.id, target.id)
    text = f"{target.mention_html()}: предупреждений {len(rows)}/3"
    for ts, reason in rows:
        left = max(0, int((ts + db.TTL - time.time()) // 86400))
        text += f"\n• {datetime.fromtimestamp(ts):%d.%m} — {reason or 'без причины'} (сгорит через {left} дн.)"
    await m.reply(text)
