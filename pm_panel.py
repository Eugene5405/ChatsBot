"""Меню в личных сообщениях с ботом, нижняя клавиатура и открытие админ-панели."""
import html
import os

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

import db

router = Router()
router.message.filter(F.chat.type == ChatType.PRIVATE)


def _get_webapp_url() -> str:
    base = os.getenv("RENDER_EXTERNAL_URL", "https://onrender.com").rstrip("/")
    return f"{base}/webapp"


def _bottom_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🛡 Админ-панель", web_app=WebAppInfo(url=_get_webapp_url())),
                KeyboardButton(text="➕ Добавить в чат"),
            ],
            [
                KeyboardButton(text="📋 Мои чаты"),
                KeyboardButton(text="❓ Помощь"),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def _inline_start_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🛡 Открыть админ-панель",
                    web_app=WebAppInfo(url=_get_webapp_url()),
                )
            ],
            [
                InlineKeyboardButton(
                    text="➕ Добавить бота в группу",
                    url="https://t.me",
                )
            ],
        ]
    )


@router.message(CommandStart())
async def cmd_start_pm(message: Message):
    await message.answer(
        "👋 Привет! Я <b>Хранитель чата</b>.\n\n"
        "Я защищаю группы от мата, спама и рекламы, управляю репортами, репутацией, экономикой «Алиби», магазином и ролеплеем.\n\n"
        "1. Нажми <b>«➕ Добавить бота в группу»</b> и выдай права администратора.\n"
        "2. Напиши в группе <code>/status</code> для проверки прав.\n"
        "3. Управляй всеми чатами через <b>админ-панель</b>:",
        reply_markup=_inline_start_kb(),
    )
    await message.answer("⌨️ Быстрое меню управления активировано:", reply_markup=_bottom_menu())


@router.message(Command("help"))
@router.message(F.text.func(lambda t: t is not None and "помощ" in t.lower()))
async def cmd_help_pm(message: Message):
    await message.answer(
        "❓ <b>Справка по Хранителю чата</b>\n\n"
        "<b>Команды для участников:</b>\n"
        "• <code>репорт причина</code> (ответом) — жалоба админам в ЛС со ссылкой\n"
        "• <code>мешок</code> / <code>/bag</code> — баланс «Алиби» и инвентарь\n"
        "• <code>дать 50</code> / <code>/give 50</code> — перевести «Алиби»\n"
        "• <code>магазин</code> / <code>/shop</code> — магазин на 13 товаров\n"
        "• <code>+реп</code> / <code>/lookrep</code> — репутация\n"
        "• <code>русская рулетка</code> — игра на удачу\n"
        "• <code>обнять</code>, <code>дать леща</code>, <code>поцеловать</code> — РП-действия\n\n"
        "<b>Команды для админов:</b>\n"
        "• <code>-чат</code> / <code>+чат</code> — закрыть / открыть чат для участников\n"
        "• <code>варн</code>, <code>мут</code>, <code>бан</code>, <code>кик</code> — модерация (ответом или по <code>@username</code>)\n"
        "• <code>/settings</code>, <code>/status</code>, <code>/setrules</code>, <code>/newrp</code>, <code>/change</code>",
        reply_markup=_bottom_menu(),
    )


@router.message(F.text.func(lambda t: t is not None and "добавить" in t.lower()))
async def btn_add_chat(message: Message):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Выбрать группу для добавления",
                    url="https://t.me",
                )
            ]
        ]
    )
    await message.answer(
        "Нажми кнопку ниже, выбери свою группу и подтверди права администратора:",
        reply_markup=kb,
    )


@router.message(F.text.func(lambda t: t is not None and "чат" in t.lower()))
async def btn_my_chats(message: Message):
    chats = db.get_chats()
    if not chats:
        await message.answer(
            "📭 Подключённых чатов пока нет.\n"
            "Добавь бота в группу и напиши там любое сообщение или <code>/status</code>.",
            reply_markup=_bottom_menu(),
        )
        return

    lines = ["📋 <b>Подключённые чаты:</b>\n"]
    for idx, ch in enumerate(chats, start=1):
        lines.append(f"{idx}. <b>{html.escape(ch['title'])}</b> (<code>{ch['chat_id']}</code>)")

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🛡 Управлять в админ-панели",
                    web_app=WebAppInfo(url=_get_webapp_url()),
                )
            ]
        ]
    )
    await message.answer("\n".join(lines), reply_markup=kb)
