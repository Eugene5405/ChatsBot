"""Панель управления ботом в ЛС: клавиатура, список чатов, настройки."""
import html
import json
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

import config
import db
import rules
from loader import bot

router = Router()

WEBAPP_URL = os.getenv("WEBAPP_URL", "https://chatsbot-ve5e.onrender.com/webapp").strip()

BTN_MINIAPP = "📱 Мини-приложение"
BTN_ADD_CHAT = "➕ Добавить бота в чат"
BTN_SETTINGS_PM = "⚙️ Настроить бота в ЛС"

_BOT_USERNAME: str | None = None


async def _get_bot_username() -> str:
    global _BOT_USERNAME
    if not _BOT_USERNAME:
        me = await bot.get_me()
        _BOT_USERNAME = me.username or ""
    return _BOT_USERNAME


def _reply_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_MINIAPP, web_app=WebAppInfo(url=WEBAPP_URL))],
            [KeyboardButton(text=BTN_ADD_CHAT), KeyboardButton(text=BTN_SETTINGS_PM)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def register_user_chat(user_id: int, chat_id: int, chat_title: str):
    raw = db.get_setting(user_id, "owned_chats")
    chats = {}
    if raw:
        try:
            chats = json.loads(raw)
        except Exception:
            chats = {}
    chats[str(chat_id)] = chat_title or f"Чат {chat_id}"
    db.set_setting(user_id, "owned_chats", json.dumps(chats, ensure_ascii=False))
    db.set_setting(chat_id, "chat_title", chat_title or f"Чат {chat_id}")


def get_user_chats(user_id: int) -> dict[str, str]:
    raw = db.get_setting(user_id, "owned_chats")
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


class EditSettingState(StatesGroup):
    waiting_value = State()


@router.my_chat_member()
async def on_bot_status_changed(event: ChatMemberUpdated):
    if event.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return
    new_st = event.new_chat_member.status
    actor = event.from_user
    if not actor or actor.is_bot:
        return

    if new_st in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR):
        register_user_chat(actor.id, event.chat.id, event.chat.title or "Без названия")
        title = html.escape(event.chat.title or "Без названия")
        is_admin = new_st == ChatMemberStatus.ADMINISTRATOR
        status_note = (
            "✅ Права администратора выданы — бот полностью готов к работе!"
            if is_admin
            else "⚠️ Выдайте боту права администратора в группе, чтобы работали удаление сообщений, муты и приветствия."
        )
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📱 Открыть Mini App", web_app=WebAppInfo(url=WEBAPP_URL))],
                [InlineKeyboardButton(text="⚙️ Настроить этот чат в ЛС", callback_data=f"pmchat:{event.chat.id}")],
            ]
        )
        try:
            await bot.send_message(
                actor.id,
                f"🎉 <b>Бот подключён к чату «{title}»!</b>\n\n{status_note}",
                reply_markup=kb,
            )
        except Exception:
            pass


@router.message(F.chat.type == ChatType.PRIVATE, Command("start", "panel"))
async def cmd_start_pm(message: Message, state: FSMContext):
    await state.clear()
    username = await _get_bot_username()
    add_url = f"https://t.me/{username}?startgroup=true&admin=change_info+delete_messages+restrict_members+invite_users+pin_messages"
    name = html.escape(message.from_user.first_name or "Администратор")
    text = (
        f"👋 Привет, <b>{name}</b>!\n\n"
        f"Я — <b>Хранитель чата</b>. Помогаю следить за порядком, проверять заявки, чистить спам и мат.\n\n"
        f"<b>Как подключить бота в группу:</b>\n"
        f"1. Нажми кнопку <b>«➕ Добавить бота в чат»</b> ниже.\n"
        f"2. Выбери нужную группу и подтверди права администратора.\n"
        f"3. Я сразу пришлю уведомление сюда и открою настройки чата."
    )
    inline_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📱 Открыть панель управления (Mini App)", web_app=WebAppInfo(url=WEBAPP_URL))],
            [InlineKeyboardButton(text="➕ Добавить бота в группу", url=add_url)],
            [InlineKeyboardButton(text="⚙️ Мои чаты (настроить в ЛС)", callback_data="pm:list")],
        ]
    )
    await message.answer(text, reply_markup=_reply_kb())
    await message.answer("Выбери удобный способ управления ниже:", reply_markup=inline_kb)


@router.message(F.chat.type == ChatType.PRIVATE, F.text == BTN_ADD_CHAT)
async def on_btn_add_chat(message: Message):
    username = await _get_bot_username()
    add_url = f"https://t.me/{username}?startgroup=true&admin=change_info+delete_messages+restrict_members+invite_users+pin_messages"
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="➕ Выбрать чат и выдать права", url=add_url)]]
    )
    await message.answer(
        "Нажми на кнопку ниже, выбери свою группу и разреши боту права администратора:",
        reply_markup=kb,
    )


@router.message(F.chat.type == ChatType.PRIVATE, F.text == BTN_SETTINGS_PM)
async def on_btn_settings_pm(message: Message, state: FSMContext):
    await state.clear()
    await _show_chats_list(message, message.from_user.id, edit=False)


async def _show_chats_list(target: Message | CallbackQuery, user_id: int, edit: bool = True):
    chats = get_user_chats(user_id)
    if not chats:
        username = await _get_bot_username()
        add_url = f"https://t.me/{username}?startgroup=true&admin=change_info+delete_messages+restrict_members+invite_users+pin_messages"
        kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="➕ Добавить бота в чат", url=add_url)]]
        )
        msg = (
            "У тебя пока нет привязанных чатов.\n\n"
            "Добавь бота в группу (или сними и заново выдай ему права админа, если он уже там), "
            "и чат сразу появится здесь!"
        )
        if edit and isinstance(target, CallbackQuery):
            await target.message.edit_text(msg, reply_markup=kb)
        elif isinstance(target, Message):
            await target.answer(msg, reply_markup=kb)
        return

    rows = []
    for cid, title in chats.items():
        rows.append([InlineKeyboardButton(text=f"💬 {title}", callback_data=f"pmchat:{cid}")])
    rows.append([InlineKeyboardButton(text="📱 Открыть в Mini App", web_app=WebAppInfo(url=WEBAPP_URL))])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    text = "<b>⚙️ Твои подключённые чаты:</b>\nВыбери чат для настройки правил, приветствия и фильтров:"
    if edit and isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=kb)
    elif isinstance(target, Message):
        await target.answer(text, reply_markup=kb)


@router.callback_query(F.data == "pm:list")
async def cb_pm_list(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await _show_chats_list(cb, cb.from_user.id, edit=True)
    await cb.answer()


@router.callback_query(F.data.startswith("pmchat:"))
async def cb_pm_chat(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    chat_id = int(cb.data.split(":", 1)[1])
    chats = get_user_chats(cb.from_user.id)
    title = html.escape(chats.get(str(chat_id), f"Чат {chat_id}"))

    f_mat = "✅" if db.filter_on(chat_id, "mat") else "❌"
    f_spam = "✅" if db.filter_on(chat_id, "spam") else "❌"
    f_ads = "✅" if db.filter_on(chat_id, "ads") else "❌"

    text = (
        f"<b>⚙️ Настройки чата «{title}»</b>\n\n"
        f"• Антимат: {f_mat}\n"
        f"• Антиспам / флуд: {f_spam}\n"
        f"• Защита от рекламы: {f_ads}\n\n"
        f"Выбери, что хочешь изменить:"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📜 Изменить правила", callback_data=f"pmedit:{chat_id}:rules")],
            [InlineKeyboardButton(text="👋 Изменить приветствие", callback_data=f"pmedit:{chat_id}:welcome")],
            [InlineKeyboardButton(text="🚪 Изменить прощание", callback_data=f"pmedit:{chat_id}:goodbye")],
            [
                InlineKeyboardButton(text=f"Мат {f_mat}", callback_data=f"pmtog:{chat_id}:mat"),
                InlineKeyboardButton(text=f"Спам {f_spam}", callback_data=f"pmtog:{chat_id}:spam"),
                InlineKeyboardButton(text=f"Реклама {f_ads}", callback_data=f"pmtog:{chat_id}:ads"),
            ],
            [InlineKeyboardButton(text="⬅️ Назад к списку чатов", callback_data="pm:list")],
        ]
    )
    await cb.message.edit_text(text, reply_markup=kb)
    await cb.answer()


@router.callback_query(F.data.startswith("pmtog:"))
async def cb_pm_toggle(cb: CallbackQuery, state: FSMContext):
    _, cid_s, kind = cb.data.split(":")
    chat_id = int(cid_s)
    cur = db.filter_on(chat_id, kind)
    db.set_setting(chat_id, "f_" + kind, "0" if cur else "1")
    cb.data = f"pmchat:{chat_id}"
    await cb_pm_chat(cb, state)


@router.callback_query(F.data.startswith("pmedit:"))
async def cb_pm_edit(cb: CallbackQuery, state: FSMContext):
    _, cid_s, field = cb.data.split(":")
    chat_id = int(cid_s)
    await state.set_state(EditSettingState.waiting_value)
    await state.update_data(chat_id=chat_id, field=field)

    prompts = {
        "rules": "📜 <b>Отправь новый текст правил</b> для этого чата одним сообщением (или напиши <code>сброс</code>, чтобы вернуть стандартные):",
        "welcome": (
            "👋 <b>Отправь новый текст приветствия</b>.\n"
            "Можно использовать переменные: <code>{user}</code> — имя новичка, <code>{chat}</code> — название группы.\n"
            "Напиши <code>сброс</code>, чтобы вернуть стандартное приветствие:"
        ),
        "goodbye": (
            "🚪 <b>Отправь новый текст прощания</b> при выходе участника.\n"
            "Переменные: <code>{user}</code> — имя ушедшего, <code>{chat}</code> — название группы.\n"
            "Напиши <code>сброс</code>, чтобы вернуть стандартное:"
        ),
    }
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data=f"pmchat:{chat_id}")]]
    )
    await cb.message.edit_text(prompts[field], reply_markup=kb)
    await cb.answer()


@router.message(F.chat.type == ChatType.PRIVATE, EditSettingState.waiting_value)
async def on_pm_edit_value(message: Message, state: FSMContext):
    data = await state.get_data()
    chat_id = data["chat_id"]
    field = data["field"]
    val = (message.text or "").strip()
    if not val:
        await message.answer("Отправь текстовое сообщение.")
        return

    if val.lower() == "сброс":
        if field == "rules":
            db.set_setting(chat_id, "rules", None)
        elif field == "welcome":
            db.set_setting(chat_id, "welcome_text", None)
        elif field == "goodbye":
            db.set_setting(chat_id, "goodbye_text", None)
        res_text = "✅ Настройка сброшена на стандартную!"
    else:
        safe_val = html.escape(val)
        if field == "rules":
            db.set_setting(chat_id, "rules", safe_val)
        elif field == "welcome":
            db.set_setting(chat_id, "welcome_text", safe_val)
        elif field == "goodbye":
            db.set_setting(chat_id, "goodbye_text", safe_val)
        res_text = "✅ Новое значение успешно сохранено!"

    await state.clear()
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Вернуться к настройкам чата", callback_data=f"pmchat:{chat_id}")]]
    )
    await message.answer(res_text, reply_markup=kb)
