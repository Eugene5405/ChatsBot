"""Панель управления ботом в личных сообщениях и уведомления о подключении чата."""
import html
import os

from aiogram import F, Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    ChatMemberUpdated,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

import db
import rules
import webapp
from loader import bot

router = Router()

WEBAPP_URL = os.getenv("WEBAPP_URL", "https://chatsbot-ve5e.onrender.com/webapp").strip()
BOT_USERNAME = os.getenv("BOT_USERNAME", "chat_custodian_bot").strip().lstrip("@")

BTN_MINIAPP = "📱 Мини-приложение"
BTN_ADD_CHAT = "➕ Добавить бота в чат"
BTN_SETTINGS = "⚙️ Настроить бота в ЛС"

_ACTIVE = {ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}
_INACTIVE = {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED}


class EditChatState(StatesGroup):
    waiting_rules = State()
    waiting_welcome = State()
    waiting_farewell = State()


def _reply_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_MINIAPP)],
            [KeyboardButton(text=BTN_ADD_CHAT), KeyboardButton(text=BTN_SETTINGS)],
        ],
        resize_keyboard=True,
    )


def _add_group_url() -> str:
    return (
        f"https://t.me/{BOT_USERNAME}?startgroup=true"
        "&admin=delete_messages+restrict_members+invite_users+pin_messages"
    )


def _start_inline_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📱 Открыть панель управления (Mini App)", web_app=WebAppInfo(url=WEBAPP_URL))],
            [InlineKeyboardButton(text="➕ Добавить бота в группу", url=_add_group_url())],
            [InlineKeyboardButton(text="⚙️ Мои чаты (настроить в ЛС)", callback_data="pm:chats")],
        ]
    )


def _chats_kb(user_id: int) -> InlineKeyboardMarkup:
    chats = webapp.get_user_chats(user_id)
    rows = [[InlineKeyboardButton(text=f"💬 {c['title']}", callback_data=f"pm:chat:{c['chat_id']}")] for c in chats]
    rows.append([InlineKeyboardButton(text="➕ Добавить бота в группу", url=_add_group_url())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _chat_manage_kb(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📜 Правила", callback_data=f"pm:edit:rules:{chat_id}"),
                InlineKeyboardButton(text="👋 Приветствие", callback_data=f"pm:edit:welcome:{chat_id}"),
            ],
            [
                InlineKeyboardButton(text="🚪 Прощание", callback_data=f"pm:edit:farewell:{chat_id}"),
                InlineKeyboardButton(text="🛡️ Фильтры", callback_data=f"pm:filters:{chat_id}"),
            ],
            [InlineKeyboardButton(text="📱 Открыть в Mini App", web_app=WebAppInfo(url=WEBAPP_URL))],
            [InlineKeyboardButton(text="← К списку чатов", callback_data="pm:chats")],
        ]
    )


def _filters_kb(chat_id: int) -> InlineKeyboardMarkup:
    items = [
        ("mat", "🤬 Антимат"),
        ("links", "🔗 Ссылки"),
        ("flood", "🌊 Антифлуд"),
        ("stickers", "🎭 Стикеры/GIF"),
    ]
    rows = []
    for kind, label in items:
        state_icon = "✅" if db.filter_on(chat_id, kind) else "❌"
        rows.append([InlineKeyboardButton(text=f"{state_icon} {label}", callback_data=f"pm:tog:{kind}:{chat_id}")])
    rows.append([InlineKeyboardButton(text="← Назад к чату", callback_data=f"pm:chat:{chat_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("start", "panel"), F.chat.type == ChatType.PRIVATE)
async def cmd_start_private(message: Message, state: FSMContext):
    await state.clear()
    name = html.escape(message.from_user.first_name or "друг")
    text = (
        f"👋 Привет, <b>{name}</b>!\n\n"
        "Я — <b>Хранитель чата</b>. Помогаю следить за порядком, проверять заявки, чистить спам и мат.\n\n"
        "<b>Как подключить бота в группу:</b>\n"
        "1. Нажми кнопку <b>«➕ Добавить бота в чат»</b>.\n"
        "2. Выбери нужную группу и подтверди права администратора.\n"
        "3. Я сразу пришлю уведомление сюда и открою настройки чата."
    )
    await message.answer(text, reply_markup=_reply_kb())
    await message.answer("Выбери удобный способ управления ниже:", reply_markup=_start_inline_kb())


@router.message(F.text == BTN_MINIAPP, F.chat.type == ChatType.PRIVATE)
async def on_btn_miniapp(message: Message):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Запустить Mini App", web_app=WebAppInfo(url=WEBAPP_URL))]
        ]
    )
    await message.answer("Нажми на кнопку ниже, чтобы открыть панель управления:", reply_markup=kb)


@router.message(F.text == BTN_ADD_CHAT, F.chat.type == ChatType.PRIVATE)
async def on_btn_add_chat(message: Message):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Выбрать группу в Telegram", url=_add_group_url())]
        ]
    )
    await message.answer(
        "Нажми на кнопку ниже, выбери свою группу и выдай боту права администратора:",
        reply_markup=kb,
    )


@router.message(F.text == BTN_SETTINGS, F.chat.type == ChatType.PRIVATE)
async def on_btn_settings(message: Message, state: FSMContext):
    await state.clear()
    chats = webapp.get_user_chats(message.from_user.id)
    if not chats:
        await message.answer(
            "У тебя пока нет подключённых чатов. Добавь бота администратором в группу!",
            reply_markup=_chats_kb(message.from_user.id),
        )
        return
    await message.answer("Выбери чат для настройки:", reply_markup=_chats_kb(message.from_user.id))


@router.callback_query(F.data == "pm:chats")
async def cb_list_chats(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    chats = webapp.get_user_chats(cb.from_user.id)
    if not chats:
        await cb.message.edit_text(
            "У тебя пока нет подключённых чатов. Добавь бота администратором в группу!",
            reply_markup=_chats_kb(cb.from_user.id),
        )
    else:
        await cb.message.edit_text("Выбери чат для настройки:", reply_markup=_chats_kb(cb.from_user.id))
    await cb.answer()


@router.callback_query(F.data.startswith("pm:chat:"))
async def cb_open_chat(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    chat_id = int(cb.data.split(":")[2])
    chats = {c["chat_id"]: c["title"] for c in webapp.get_user_chats(cb.from_user.id)}
    if chat_id not in chats:
        await cb.answer("Нет доступа к этому чату", show_alert=True)
        return
    title = html.escape(chats[chat_id])
    await cb.message.edit_text(
        f"⚙️ Управление чатом <b>{title}</b>\n\nВыбери, что хочешь изменить:",
        reply_markup=_chat_manage_kb(chat_id),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("pm:filters:"))
async def cb_filters(cb: CallbackQuery):
    chat_id = int(cb.data.split(":")[2])
    await cb.message.edit_text("🛡️ Настройка фильтров автомодерации:", reply_markup=_filters_kb(chat_id))
    await cb.answer()


@router.callback_query(F.data.startswith("pm:tog:"))
async def cb_toggle_filter(cb: CallbackQuery):
    _, _, kind, chat_id_str = cb.data.split(":")
    chat_id = int(chat_id_str)
    cur = db.filter_on(chat_id, kind)
    db.set_setting(chat_id, "f_" + kind, "0" if cur else "1")
    await cb.message.edit_reply_markup(reply_markup=_filters_kb(chat_id))
    await cb.answer("Сохранено")


@router.callback_query(F.data.startswith("pm:edit:"))
async def cb_edit_field(cb: CallbackQuery, state: FSMContext):
    _, _, field, chat_id_str = cb.data.split(":")
    chat_id = int(chat_id_str)
    await state.update_data(chat_id=chat_id)
    if field == "rules":
        await state.set_state(EditChatState.waiting_rules)
        cur = db.get_setting(chat_id, "rules") or rules.DEFAULT_RULES
        await cb.message.answer(f"📜 Отправь новый текст правил ответом на это сообщение.\n\nТекущие правила:\n{cur}")
    elif field == "welcome":
        await state.set_state(EditChatState.waiting_welcome)
        await cb.message.answer(
            "👋 Отправь новый текст приветствия (можно использовать {user} и {chat}).\n"
            "Чтобы вернуть стандартное приветствие, отправь символ <code>-</code>"
        )
    elif field == "farewell":
        await state.set_state(EditChatState.waiting_farewell)
        await cb.message.answer(
            "🚪 Отправь новый текст прощания при выходе (можно использовать {user} и {chat}).\n"
            "Чтобы вернуть стандартное прощание, отправь символ <code>-</code>"
        )
    await cb.answer()


@router.message(EditChatState.waiting_rules, F.chat.type == ChatType.PRIVATE)
async def save_new_rules(message: Message, state: FSMContext):
    data = await state.get_data()
    chat_id = data["chat_id"]
    val = (message.html_text or message.text or "").strip()
    db.set_setting(chat_id, "rules", None if val == "-" else val)
    await state.clear()
    await message.answer("✅ Правила обновлены!", reply_markup=_chat_manage_kb(chat_id))


@router.message(EditChatState.waiting_welcome, F.chat.type == ChatType.PRIVATE)
async def save_new_welcome(message: Message, state: FSMContext):
    data = await state.get_data()
    chat_id = data["chat_id"]
    val = (message.html_text or message.text or "").strip()
    db.set_setting(chat_id, "custom_welcome", None if val == "-" else val)
    await state.clear()
    await message.answer("✅ Приветствие обновлено!", reply_markup=_chat_manage_kb(chat_id))


@router.message(EditChatState.waiting_farewell, F.chat.type == ChatType.PRIVATE)
async def save_new_farewell(message: Message, state: FSMContext):
    data = await state.get_data()
    chat_id = data["chat_id"]
    val = (message.html_text or message.text or "").strip()
    db.set_setting(chat_id, "custom_farewell", None if val == "-" else val)
    await state.clear()
    await message.answer("✅ Текст прощания обновлён!", reply_markup=_chat_manage_kb(chat_id))


@router.my_chat_member()
async def on_bot_added_or_updated(event: ChatMemberUpdated):
    if event.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return
    old_st = event.old_chat_member.status
    new_st = event.new_chat_member.status
    user = event.from_user

    if new_st in _ACTIVE and user and not user.is_bot:
        webapp.register_chat(user.id, event.chat.id, event.chat.title or "Группа")
        title = html.escape(event.chat.title or "Группа")
        if old_st in _INACTIVE or new_st == ChatMemberStatus.ADMINISTRATOR:
            status_line = (
                "✅ Права администратора выданы — бот полностью готов к работе!"
                if new_st == ChatMemberStatus.ADMINISTRATOR
                else "⚠️ Выдай боту права администратора в группе, чтобы он мог удалять спам и приветствовать новичков."
            )
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="📱 Открыть Mini App", web_app=WebAppInfo(url=WEBAPP_URL))],
                    [InlineKeyboardButton(text="⚙️ Настроить этот чат в ЛС", callback_data=f"pm:chat:{event.chat.id}")],
                ]
            )
            try:
                await bot.send_message(
                    user.id,
                    f"🎉 Бот подключён к чату <b>«{title}»</b>!\n\n{status_line}",
                    reply_markup=kb,
                )
            except Exception:
                pass
