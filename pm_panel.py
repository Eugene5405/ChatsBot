"""Личный кабинет, нижнее меню кнопок, список чатов и кнопка админ-панели."""
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


def _get_webapp_url() -> str:
    base = os.getenv("RENDER_EXTERNAL_URL", "https://chatsbot-ve5e.onrender.com").rstrip("/")
    return f"{base}/webapp"


def _main_reply_kb() -> ReplyKeyboardMarkup:
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
    )


def _inline_panel_kb() -> InlineKeyboardMarkup:
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
        "Я защищаю группы от мата, спама и рекламы, проверяю подписку на канал при входе "
        "и помогаю управлять порядком.\n\n"
        "Используйте кнопки меню внизу или откройте <b>админ-панель</b>:",
        reply_markup=_main_reply_kb(),
    )
    await message.answer("Быстрый доступ к панели управления:", reply_markup=_inline_panel_kb())


@router.message(F.chat.type == ChatType.PRIVATE, Command("help"))
@router.message(F.chat.type == ChatType.PRIVATE, F.text.lower().contains("помощ"))
async def cmd_help_pm(message: Message):
    await message.answer(
        "📖 <b>Справка по работе с ботом</b>\n\n"
        "<b>1. Подключение чата:</b>\n"
        "• Нажмите <b>«➕ Добавить в чат»</b> и выберите нужную группу.\n"
        "• Выдайте боту права администратора (удаление, блокировка, закрепление).\n"
        "• Напишите в группе <code>/status</code> для синхронизации.\n\n"
        "<b>2. Команды в группе (для админов):</b>\n"
        "• <code>-чат</code> — закрыть чат (писать могут только админы)\n"
        "• <code>+чат</code> — открыть чат для всех участников\n"
        "• <code>/status</code> — проверить права бота\n"
        "• <code>/settings</code> — настройки фильтров\n"
        "• <code>/warn</code>, <code>/mute</code>, <code>/ban</code> — модерация нарушителей",
        reply_markup=_main_reply_kb(),
    )


@router.message(F.chat.type == ChatType.PRIVATE, F.text.lower().contains("добавить"))
async def btn_add_chat(message: Message):
    await message.answer(
        "Нажмите на кнопку ниже, чтобы выбрать группу и добавить туда бота администратором:",
        reply_markup=_inline_panel_kb(),
    )


@router.message(F.chat.type == ChatType.PRIVATE, F.text.lower().contains("чат"))
async def btn_my_chats(message: Message):
    chats = []
    if hasattr(db, "get_all_chats"):
        try:
            chats = await db.get_all_chats()
        except Exception:
            chats = []

    if not chats:
        await message.answer(
            "📭 <b>Список подключённых чатов пока пуст.</b>\n\n"
            "Добавьте бота в любую группу (или напишите в уже подключённой группе <code>/status</code>) — "
            "чат сразу появится здесь и в админ-панели!",
            reply_markup=_inline_panel_kb(),
        )
        return

    lines = ["📋 <b>Ваши подключённые чаты:</b>\n"]
    for c in chats:
        title = html.escape(str(c.get("title") or "Без названия"))
        cid = c.get("chat_id")
        lines.append(f"• <b>{title}</b> (<code>{cid}</code>)")

    await message.answer("\n".join(lines), reply_markup=_inline_panel_kb())
