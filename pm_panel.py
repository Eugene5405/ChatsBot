"""Личный кабинет бота: рабочее нижнее меню кнопок, Помощь и запуск Web App."""
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


def _get_webapp_url() -> str:
    base = os.getenv("RENDER_EXTERNAL_URL", "https://chatsbot-ve5e.onrender.com").rstrip("/")
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


def _inline_panel() -> InlineKeyboardMarkup:
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
                    url="https://t.me/chat_custodian_bot?startgroup=true&admin=change_info+delete_messages+restrict_members+invite_users+pin_messages",
                )
            ],
        ]
    )


@router.message(F.chat.type == ChatType.PRIVATE, CommandStart())
async def cmd_start_pm(message: Message):
    await message.answer(
        "👋 Привет! Я <b>Хранитель чата</b>.\n\n"
        "Используй нижнее меню или кнопки ниже для управления чатами и настройками:",
        reply_markup=_bottom_menu(),
    )
    await message.answer(
        "⚙️ Быстрый доступ к панели управления:",
        reply_markup=_inline_panel(),
    )


@router.message(F.chat.type == ChatType.PRIVATE, Command("help"))
@router.message(F.chat.type == ChatType.PRIVATE, F.text.func(lambda t: t and "помощ" in t.lower()))
async def btn_help(message: Message):
    await message.answer(
        "❓ <b>Помощь по боту:</b>\n\n"
        "1. Нажми <b>«➕ Добавить в чат»</b> и выбери свою группу.\n"
        "2. Назначь бота <b>администратором</b> со всеми правами.\n"
        "3. Напиши в группе <b>/status</b>, чтобы группа появилась в админ-панели.\n\n"
        "<b>Команды в чате для админов:</b>\n"
        "• <code>-чат</code> — закрыть чат (писать могут только админы)\n"
        "• <code>+чат</code> — открыть чат для всех\n"
        "• <code>/status</code> — проверить права бота\n"
        "• <code>/settings</code> — настройки защиты\n"
        "• <code>/setrules</code> — задать правила ответом на сообщение",
        reply_markup=_bottom_menu(),
    )


@router.message(F.chat.type == ChatType.PRIVATE, F.text.func(lambda t: t and "добавить" in t.lower()))
async def btn_add_chat(message: Message):
    await message.answer(
        "Нажми на кнопку ниже, чтобы выбрать группу и добавить туда бота с нужными правами:",
        reply_markup=_inline_panel(),
    )


@router.message(F.chat.type == ChatType.PRIVATE, F.text.func(lambda t: t and "чат" in t.lower()))
async def btn_my_chats(message: Message):
    chats = db.get_chats()
    if not chats:
        await message.answer(
            "📋 Пока нет привязанных чатов.\n\n"
            "Добавь бота администратором в группу и напиши там команду <b>/status</b>.",
            reply_markup=_inline_panel(),
        )
        return
    lines = ["📋 <b>Подключённые чаты:</b>\n"]
    for c in chats:
        lines.append(f"• <b>{c['title']}</b> (<code>{c['chat_id']}</code>)")
    lines.append("\nУправлять фильтрами можно через <b>🛡 Админ-панель</b>.")
    await message.answer("\n".join(lines), reply_markup=_inline_panel())


@router.message(F.chat.type == ChatType.PRIVATE)
async def fallback_pm(message: Message):
    await message.answer(
        "Выбери нужный раздел в нижнем меню или открой админ-панель:",
        reply_markup=_bottom_menu(),
    )
