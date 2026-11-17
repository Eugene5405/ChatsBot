"""Меню в личных сообщениях с ботом, нижняя клавиатура и админ-панель."""
import os
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

router = Router()


def _get_webapp_url() -> str:
    base = os.getenv("RENDER_EXTERNAL_URL", "https://chatsbot-ve5e.onrender.com").rstrip("/")
    return f"{base}/webapp"


def _add_group_url() -> str:
    return (
        "https://t.me/chat_custodian_bot"
        "?startgroup=true"
        "&admin=change_info+delete_messages+restrict_members+invite_users+pin_messages"
    )


def _main_reply_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="🛡 Админ-панель",
                    web_app=WebAppInfo(url=_get_webapp_url()),
                ),
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
                    url=_add_group_url(),
                )
            ],
        ]
    )


@router.message(CommandStart(), F.chat.type == "private")
async def cmd_start_pm(message: Message):
    await message.answer(
        "👋 Привет! Я <b>Хранитель чата</b>.\n\n"
        "Я защищаю группы от спама, мата и рекламы, проверяю подписку на канал при входе и слежу за порядком.\n\n"
        "Пользуйтесь кнопками в меню внизу или откройте панель управления прямо сейчас:",
        reply_markup=_main_reply_kb(),
    )


@router.message(F.chat.type == "private", F.text.lower().contains("добавить"))
async def btn_add_chat(message: Message):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Выбрать группу для бота", url=_add_group_url())]
        ]
    )
    await message.answer(
        "Нажмите кнопку ниже, выберите вашу группу и выдайте боту <b>права администратора</b>.\n\n"
        "После добавления напишите в группе команду <b>/status</b>, чтобы бот активировал защиту и синхронизировал чат.",
        reply_markup=kb,
    )


@router.message(F.chat.type == "private", F.text.lower().contains("чат"))
async def btn_my_chats(message: Message):
    await message.answer(
        "📋 <b>Управление вашими группами</b>\n\n"
        "Откройте админ-панель, чтобы выбрать подключённый чат и настроить фильтры (антимат, антиспам, ссылки, приветствие).\n\n"
        "<i>Если группа ещё не появилась в списке — убедитесь, что бот назначен в ней администратором, и отправьте в чат команду /status.</i>",
        reply_markup=_inline_panel_kb(),
    )


@router.message(Command("help"), F.chat.type == "private")
@router.message(F.chat.type == "private", F.text.lower().contains("помощ"))
async def btn_help(message: Message):
    await message.answer(
        "❓ <b>Помощь и основные команды</b>\n\n"
        "<b>Как подключить группу:</b>\n"
        "1. Нажмите <b>«➕ Добавить в чат»</b> и выберите группу.\n"
        "2. Выдайте боту права администратора (удаление, бан, приглашение, закрепление).\n"
        "3. Напишите в чате команду <b>/status</b>.\n\n"
        "<b>Команды в группе (для админов):</b>\n"
        "• <code>/status</code> — проверить права бота и синхронизировать чат\n"
        "• <code>/settings</code> — быстрые настройки фильтров в чате\n"
        "• <code>/setrules</code> — задать правила чата (ответом на сообщение)\n"
        "• <code>/warn</code> / <code>/unwarn</code> — выдать или снять предупреждение\n"
        "• <code>/mute</code> / <code>/ban</code> — замутить или забанить нарушителя",
        reply_markup=_inline_panel_kb(),
    )


@router.message(F.chat.type == "private")
async def fallback_pm_buttons(message: Message):
    await message.answer(
        "Выберите нужное действие в меню внизу или откройте <b>Админ-панель</b>:",
        reply_markup=_main_reply_kb(),
    )
