"""Меню в личных сообщениях с ботом и кнопка открытия админ-панели."""
import os
from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

router = Router()


def _get_webapp_url() -> str:
    base = os.getenv("RENDER_EXTERNAL_URL", "https://chatsbot-ve5e.onrender.com").rstrip("/")
    return f"{base}/webapp"


@router.message(CommandStart())
async def cmd_start_pm(message: Message):
    if message.chat.type != "private":
        return

    kb = InlineKeyboardMarkup(
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

    await message.answer(
        "👋 Привет! Я <b>Хранитель чата</b>.\n\n"
        "Я помогаю защищать группы от спама, мата и рекламы, проверяю подписку на канал при входе и слежу за порядком.\n\n"
        "1. Нажмите <b>«Добавить бота в группу»</b> и выдайте права администратора.\n"
        "2. Напишите в группе команду <b>/status</b> для синхронизации.\n"
        "3. Управляйте всеми фильтрами через <b>админ-панель</b> ниже:",
        reply_markup=kb,
    )
