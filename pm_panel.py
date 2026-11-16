"""Панель управления в ЛС бота и уведомления о подключении чатов."""
import html
import json
import os

from aiogram import F, Router
from aiogram.enums import ChatMemberStatus, ChatType
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


class EditChatState(StatesGroup):
    waiting_rules = State()
    waiting_welcome = State()
    waiting_bye = State()


def _get_user_chats(user_id: int) -> dict[str, str]:
    raw = db.get_setting(0, f"owner_chats_{user_id}")
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_user_chat(user_id: int, chat_id: int, title: str):
    chats = _get_user_chats(user_id)
    chats[str(chat_id)] = title or f"Чат {chat_id}"
    db.set_setting(0, f"owner_chats_{user_id}", json.dumps(chats, ensure_ascii=False))
    db.set_setting(chat_id, "owner_id", str(user_id))


def _remove_user_chat(user_id: int, chat_id: int):
    chats = _get_user_chats(user_id)
    if str(chat_id) in chats:
        del chats[str(chat_id)]
        db.set_setting(0, f"owner_chats_{user_id}", json.dumps(chats, ensure_ascii=False))


async def _add_bot_url() -> str:
    me = await bot.get_me()
    rights = "change_info+delete_messages+restrict_members+invite_users+pin_messages+manage_chat"
    return f"https://t.me/{me.username}?startgroup=true&admin={rights}"


def _bottom_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Мини-приложение", web_app=WebAppInfo(url=WEBAPP_URL))],
            [
                KeyboardButton(text="➕ Добавить бота в чат"),
                KeyboardButton(text="⚙️ Настроить бота в ЛС"),
            ],
        ],
        resize_keyboard=True,
    )


async def _main_inline_kb() -> InlineKeyboardMarkup:
    add_url = await _add_bot_url()
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📱 Открыть мини-приложение", web_app=WebAppInfo(url=WEBAPP_URL))],
            [InlineKeyboardButton(text="➕ Добавить бота в чат", url=add_url)],
            [InlineKeyboardButton(text="⚙️ Мои чаты (настроить в ЛС)", callback_data="pm:chats")],
        ]
    )


def _chats_kb(chats: dict[str, str]) -> InlineKeyboardMarkup:
    rows = []
    for cid, title in chats.items():
        rows.append([InlineKeyboardButton(text=f"💬 {title}", callback_data=f"pm:chat:{cid}")])
    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="pm:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _chat_manage_kb(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📜 Правила", callback_data=f"pm:edit:rules:{chat_id}"),
                InlineKeyboardButton(text="👋 Приветствие", callback_data=f"pm:edit:welcome:{chat_id}"),
            ],
            [
                InlineKeyboardButton(text="🚪 Прощание", callback_data=f"pm:edit:bye:{chat_id}"),
                InlineKeyboardButton(text="🛡 Фильтры", callback_data=f"pm:filters:{chat_id}"),
            ],
            [InlineKeyboardButton(text="🔙 К списку чатов", callback_data="pm:chats")],
        ]
    )


def _filters_kb(chat_id: int) -> InlineKeyboardMarkup:
    names = {
        "mat": "Антимат",
        "flood": "Антифлуд",
        "stickers": "Стикеры/GIF",
        "links": "Ссылки/реклама",
        "inline": "Инлайн-боты",
    }
    rows = []
    for key, label in names.items():
        on = db.filter_on(chat_id, key)
        mark = "✅" if on else "❌"
        rows.append([InlineKeyboardButton(text=f"{mark} {label}", callback_data=f"pm:toggle:{key}:{chat_id}")])
    rows.append([InlineKeyboardButton(text="🔙 Назад к чату", callback_data=f"pm:chat:{chat_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.my_chat_member()
async def on_bot_membership(event: ChatMemberUpdated):
    if event.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return
    new_status = event.new_chat_member.status
    actor = event.from_user
    chat_id = event.chat.id
    title = event.chat.title or f"Чат {chat_id}"

    if new_status in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR):
        if actor and not actor.is_bot:
            _save_user_chat(actor.id, chat_id, title)
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="📱 Открыть мини-приложение", web_app=WebAppInfo(url=WEBAPP_URL))],
                    [InlineKeyboardButton(text="⚙️ Настроить в ЛС", callback_data=f"pm:chat:{chat_id}")],
                ]
            )
            try:
                await bot.send_message(
                    actor.id,
                    f"✅ Бот успешно подключён к чату <b>{html.escape(title)}</b>!\n\n"
                    f"Выдай боту права администратора в группе, чтобы работали удаление сообщений, муты, баны и приветствия.",
                    reply_markup=kb,
                )
            except Exception:
                pass
    elif new_status in (ChatMemberStatus.LEFT, ChatMemberStatus.KICKED):
        owner_raw = db.get_setting(chat_id, "owner_id")
        if owner_raw and owner_raw.isdigit():
            _remove_user_chat(int(owner_raw), chat_id)


@router.message(F.chat.type == ChatType.PRIVATE, F.text.in_({"/start", "/panel"}))
async def cmd_pm_start(message: Message, state: FSMContext):
    await state.clear()
    name = html.escape(message.from_user.first_name or "друг")
    text = (
        f"👋 Привет, <b>{name}</b>!\n\n"
        f"Я — <b>Хранитель чата</b>. Помогаю следить за порядком, выдавать предупреждения, "
        f"фильтровать мат и спам, а также встречать новичков.\n\n"
        f"<b>Как подключить меня в группу:</b>\n"
        f"1. Нажми кнопку <b>«➕ Добавить бота в чат»</b> ниже.\n"
        f"2. Выбери нужную группу и выдай права администратора.\n"
        f"3. Управляй правилами, приветствием и фильтрами через <b>Мини-приложение</b> или прямо здесь в ЛС."
    )
    await message.answer(text, reply_markup=_bottom_keyboard())
    await message.answer("Выбери действие:", reply_markup=await _main_inline_kb())


@router.message(F.chat.type == ChatType.PRIVATE, F.text == "➕ Добавить бота в чат")
async def btn_add_to_chat(message: Message):
    add_url = await _add_bot_url()
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="➕ Выбрать чат и добавить", url=add_url)]]
    )
    await message.answer(
        "Нажми на кнопку ниже, чтобы выбрать группу и назначить бота администратором:",
        reply_markup=kb,
    )


@router.message(F.chat.type == ChatType.PRIVATE, F.text == "⚙️ Настроить бота в ЛС")
async def btn_settings_pm(message: Message, state: FSMContext):
    await state.clear()
    chats = _get_user_chats(message.from_user.id)
    if not chats:
        await message.answer(
            "У тебя пока нет подключённых чатов.\n\n"
            "Нажми <b>«➕ Добавить бота в чат»</b>, добавь меня в группу (или передобавь, если я уже там) — и чат появится здесь!",
            reply_markup=await _main_inline_kb(),
        )
        return
    await message.answer("Выбери чат для настройки:", reply_markup=_chats_kb(chats))


@router.callback_query(F.data == "pm:home")
async def cb_pm_home(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("Главное меню управления ботом:", reply_markup=await _main_inline_kb())
    await cb.answer()


@router.callback_query(F.data == "pm:chats")
async def cb_pm_chats(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    chats = _get_user_chats(cb.from_user.id)
    if not chats:
        await cb.message.edit_text(
            "У тебя пока нет подключённых чатов.\nДобавь бота в группу, и она появится в этом списке.",
            reply_markup=await _main_inline_kb(),
        )
        await cb.answer()
        return
    await cb.message.edit_text("Выбери чат для настройки:", reply_markup=_chats_kb(chats))
    await cb.answer()


@router.callback_query(F.data.startswith("pm:chat:"))
async def cb_pm_chat_menu(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    chat_id = int(cb.data.split(":")[2])
    chats = _get_user_chats(cb.from_user.id)
    title = html.escape(chats.get(str(chat_id), f"Чат {chat_id}"))
    await cb.message.edit_text(
        f"⚙️ Настройка чата <b>{title}</b>\n\nВыбери, что хочешь изменить:",
        reply_markup=_chat_manage_kb(chat_id),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("pm:filters:"))
async def cb_pm_filters(cb: CallbackQuery):
    chat_id = int(cb.data.split(":")[2])
    await cb.message.edit_text(
        "🛡 Включение и отключение фильтров защиты:",
        reply_markup=_filters_kb(chat_id),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("pm:toggle:"))
async def cb_pm_toggle(cb: CallbackQuery):
    parts = cb.data.split(":")
    kind = parts[2]
    chat_id = int(parts[3])
    current = db.filter_on(chat_id, kind)
    db.set_setting(chat_id, "f_" + kind, "0" if current else "1")
    await cb.message.edit_reply_markup(reply_markup=_filters_kb(chat_id))
    await cb.answer("Сохранено")


@router.callback_query(F.data.startswith("pm:edit:"))
async def cb_pm_edit_prompt(cb: CallbackQuery, state: FSMContext):
    parts = cb.data.split(":")
    field = parts[2]
    chat_id = int(parts[3])
    await state.update_data(chat_id=chat_id)
    cancel_kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data=f"pm:chat:{chat_id}")]]
    )
    if field == "rules":
        await state.set_state(EditChatState.waiting_rules)
        current = rules.get_rules(chat_id)
        await cb.message.edit_text(
            f"📜 <b>Текущие правила:</b>\n<blockquote>{current}</blockquote>\n\n"
            f"Отправь новый текст правил ответным сообщением:",
            reply_markup=cancel_kb,
        )
    elif field == "welcome":
        await state.set_state(EditChatState.waiting_welcome)
        current = db.get_setting(chat_id, "welcome_text") or "Стандартное приветствие с правилами"
        await cb.message.edit_text(
            f"👋 <b>Текущее приветствие:</b>\n{html.escape(current)}\n\n"
            f"Отправь новый текст приветствия (можно использовать <code>{{user}}</code> для имени и <code>{{chat}}</code> для названия чата). "
            f"Чтобы вернуть стандартное — отправь <code>сброс</code>:",
            reply_markup=cancel_kb,
        )
    elif field == "bye":
        await state.set_state(EditChatState.waiting_bye)
        current = db.get_setting(chat_id, "bye_text") or "Стандартное прощание"
        await cb.message.edit_text(
            f"🚪 <b>Текущее прощание:</b>\n{html.escape(current)}\n\n"
            f"Отправь новый текст прощания (можно использовать <code>{{user}}</code> и <code>{{chat}}</code>). "
            f"Чтобы вернуть стандартное — отправь <code>сброс</code>:",
            reply_markup=cancel_kb,
        )
    await cb.answer()


@router.message(EditChatState.waiting_rules)
async def save_pm_rules(message: Message, state: FSMContext):
    data = await state.get_data()
    chat_id = data["chat_id"]
    if message.text and message.text.strip().lower() == "сброс":
        db.set_setting(chat_id, "rules", None)
    else:
        db.set_setting(chat_id, "rules", html.escape(message.text or ""))
    await state.clear()
    await message.answer("✅ Правила чата обновлены!", reply_markup=_chat_manage_kb(chat_id))


@router.message(EditChatState.waiting_welcome)
async def save_pm_welcome(message: Message, state: FSMContext):
    data = await state.get_data()
    chat_id = data["chat_id"]
    txt = (message.text or "").strip()
    if txt.lower() == "сброс":
        db.set_setting(chat_id, "welcome_text", None)
    else:
        db.set_setting(chat_id, "welcome_text", txt)
    await state.clear()
    await message.answer("✅ Приветствие обновлено!", reply_markup=_chat_manage_kb(chat_id))


@router.message(EditChatState.waiting_bye)
async def save_pm_bye(message: Message, state: FSMContext):
    data = await state.get_data()
    chat_id = data["chat_id"]
    txt = (message.text or "").strip()
    if txt.lower() == "сброс":
        db.set_setting(chat_id, "bye_text", None)
    else:
        db.set_setting(chat_id, "bye_text", txt)
    await state.clear()
    await message.answer("✅ Текст прощания обновлён!", reply_markup=_chat_manage_kb(chat_id))
