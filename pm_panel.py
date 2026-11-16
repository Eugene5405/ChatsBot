"""Панель управления ботом в личных сообщениях и нижняя клавиатура."""
import html
import json

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

WEBAPP_URL = "https://chatsbot-ve5e.onrender.com/webapp"
ADMIN_RIGHTS = "change_info+delete_messages+restrict_members+invite_users+pin_messages+manage_chat"

FILTER_NAMES = {
    "mat": "🤬 Антимат",
    "stickers": "🎭 Спам стикерами/GIF",
    "links": "🔗 Защита от ссылок",
    "flood": "💬 Антифлуд",
    "inline": "🤖 Инлайн-боты",
}


class EditTextState(StatesGroup):
    waiting_value = State()


def _user_chats_key(user_id: int) -> str:
    return f"owner_chats:{user_id}"


def get_user_chats(user_id: int) -> list[dict]:
    raw = db.get_setting(0, _user_chats_key(user_id))
    if not raw:
        return []
    try:
        return json.loads(raw)
    except Exception:
        return []


def save_user_chat(user_id: int, chat_id: int, title: str):
    chats = get_user_chats(user_id)
    found = False
    for c in chats:
        if c["id"] == chat_id:
            c["title"] = title
            found = True
            break
    if not found:
        chats.append({"id": chat_id, "title": title})
    db.set_setting(0, _user_chats_key(user_id), json.dumps(chats, ensure_ascii=False))


def remove_user_chat(user_id: int, chat_id: int):
    chats = [c for c in get_user_chats(user_id) if c["id"] != chat_id]
    db.set_setting(0, _user_chats_key(user_id), json.dumps(chats, ensure_ascii=False))


def bottom_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Мини-приложение", web_app=WebAppInfo(url=WEBAPP_URL))],
            [
                KeyboardButton(text="➕ Добавить бота в чат"),
                KeyboardButton(text="⚙️ Настроить бота в ЛС"),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


async def _add_bot_url() -> str:
    me = await bot.get_me()
    return f"https://t.me/{me.username}?startgroup=true&admin={ADMIN_RIGHTS}"


def _main_inline_kb(add_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📱 Открыть Мини-приложение", web_app=WebAppInfo(url=WEBAPP_URL))],
            [InlineKeyboardButton(text="➕ Подключить к группе", url=add_url)],
            [InlineKeyboardButton(text="⚙️ Мои чаты (в ЛС)", callback_data="pm:chats")],
        ]
    )


@router.message(F.chat.type == ChatType.PRIVATE, F.text.in_({"/start", "/panel"}))
async def cmd_start_pm(message: Message, state: FSMContext):
    await state.clear()
    add_url = await _add_bot_url()
    text = (
        f"👋 Привет, <b>{html.escape(message.from_user.first_name)}</b>!

"
        f"Я — <b>Хранитель чата</b>. Помогаю следить за порядком, проверять подписку при входе, "
        f"выдавать предупреждения, муты и баны.

"
        f"<b>Как подключить меня в группу:</b>
"
        f"1️⃣ Нажми <b>«➕ Добавить бота в чат»</b> внизу.
"
        f"2️⃣ Выбери нужную группу и выдай права администратора.
"
        f"3️⃣ Я сразу напишу тебе сюда и открою настройки чата."
    )
    await message.answer(text, reply_markup=bottom_keyboard())
    await message.answer("Выбери удобный способ управления:", reply_markup=_main_inline_kb(add_url))


@router.message(F.chat.type == ChatType.PRIVATE, F.text == "➕ Добавить бота в чат")
async def btn_add_bot(message: Message):
    add_url = await _add_bot_url()
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="👉 Выбрать группу в Telegram", url=add_url)]]
    )
    await message.answer(
        "Нажми на кнопку ниже, выбери группу и подтверди назначение администратором:",
        reply_markup=kb,
    )


@router.message(F.chat.type == ChatType.PRIVATE, F.text == "⚙️ Настроить бота в ЛС")
async def btn_settings_pm(message: Message, state: FSMContext):
    await state.clear()
    await _show_chats_list(message, message.from_user.id, edit=False)


async def _show_chats_list(target, user_id: int, edit: bool = True):
    chats = get_user_chats(user_id)
    if not chats:
        add_url = await _add_bot_url()
        text = (
            "📭 У тебя пока нет подключённых чатов.

"
            "Добавь меня администратором в любую группу — она сразу появится здесь!"
        )
        kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="➕ Добавить бота в чат", url=add_url)]]
        )
    else:
        text = "📋 <b>Твои подключённые чаты:</b>
Выбери чат для настройки:"
        rows = [
            [InlineKeyboardButton(text=f"💬 {c['title']}", callback_data=f"pm:chat:{c['id']}")]
            for c in chats
        ]
        kb = InlineKeyboardMarkup(inline_keyboard=rows)

    if edit:
        await target.edit_text(text, reply_markup=kb)
    else:
        await target.answer(text, reply_markup=kb)


@router.callback_query(F.data == "pm:chats")
async def cb_chats_list(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await _show_chats_list(cb.message, cb.from_user.id, edit=True)
    await cb.answer()


def _chat_menu_kb(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📜 Изменить правила", callback_data=f"pm:edit:rules:{chat_id}")],
            [
                InlineKeyboardButton(text="👋 Приветствие", callback_data=f"pm:edit:welcome:{chat_id}"),
                InlineKeyboardButton(text="🚪 Прощание", callback_data=f"pm:edit:goodbye:{chat_id}"),
            ],
            [InlineKeyboardButton(text="🛡 Фильтры защиты", callback_data=f"pm:filters:{chat_id}")],
            [InlineKeyboardButton(text="⬅️ Назад к чатам", callback_data="pm:chats")],
        ]
    )


@router.callback_query(F.data.startswith("pm:chat:"))
async def cb_chat_menu(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    chat_id = int(cb.data.split(":")[2])
    chats = {c["id"]: c["title"] for c in get_user_chats(cb.from_user.id)}
    title = html.escape(chats.get(chat_id, f"Чат {chat_id}"))
    await cb.message.edit_text(
        f"⚙️ <b>Управление чатом:</b> {title}

Выбери, что хочешь изменить:",
        reply_markup=_chat_menu_kb(chat_id),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("pm:filters:"))
async def cb_chat_filters(cb: CallbackQuery):
    chat_id = int(cb.data.split(":")[2])
    rows = []
    for kind, label in FILTER_NAMES.items():
        status = "✅ ВКЛ" if db.filter_on(chat_id, kind) else "❌ ВЫКЛ"
        rows.append([InlineKeyboardButton(text=f"{label}: {status}", callback_data=f"pm:tog:{kind}:{chat_id}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"pm:chat:{chat_id}")])
    await cb.message.edit_text(
        "🛡 <b>Фильтры автомодерации:</b>
Нажми на фильтр, чтобы переключить:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("pm:tog:"))
async def cb_toggle_filter(cb: CallbackQuery):
    _, _, kind, chat_id_str = cb.data.split(":")
    chat_id = int(chat_id_str)
    new_val = "0" if db.filter_on(chat_id, kind) else "1"
    db.set_setting(chat_id, "f_" + kind, new_val)
    await cb_chat_filters(cb)


@router.callback_query(F.data.startswith("pm:edit:"))
async def cb_start_edit(cb: CallbackQuery, state: FSMContext):
    _, _, field, chat_id_str = cb.data.split(":")
    chat_id = int(chat_id_str)
    await state.set_state(EditTextState.waiting_value)
    await state.update_data(chat_id=chat_id, field=field)

    hints = {
        "rules": (
            "📜 <b>Отправь новый текст правил чата</b> одним сообщением.

"
            f"Текущие правила:
<blockquote expandable>{rules.get_rules(chat_id)}</blockquote>"
        ),
        "welcome": (
            "👋 <b>Отправь новый текст приветствия</b>.
"
            "Можно использовать переменные: <code>{user}</code> (имя новичка) и <code>{chat}</code> (название чата).
"
            "Чтобы вернуть стандартное приветствие, отправь слово <code>сброс</code>."
        ),
        "goodbye": (
            "🚪 <b>Отправь новый текст прощания</b> при выходе участника.
"
            "Можно использовать переменные: <code>{user}</code> и <code>{chat}</code>.
"
            "Чтобы вернуть стандартное, отправь слово <code>сброс</code>."
        ),
    }
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data=f"pm:chat:{chat_id}")]]
    )
    await cb.message.edit_text(hints[field], reply_markup=kb)
    await cb.answer()


@router.message(EditTextState.waiting_value, F.chat.type == ChatType.PRIVATE, F.text)
async def msg_save_edit(message: Message, state: FSMContext):
    data = await state.get_data()
    chat_id = data["chat_id"]
    field = data["field"]
    val = message.text.strip()
    await state.clear()

    if field == "rules":
        if val.lower() == "сброс":
            db.set_setting(chat_id, "rules", None)
        else:
            db.set_setting(chat_id, "rules", html.escape(val))
        done_text = "✅ Правила чата обновлены!"
    elif field == "welcome":
        db.set_setting(chat_id, "welcome_text", None if val.lower() == "сброс" else html.escape(val))
        done_text = "✅ Текст приветствия обновлён!"
    else:
        db.set_setting(chat_id, "goodbye_text", None if val.lower() == "сброс" else html.escape(val))
        done_text = "✅ Текст прощания обновлён!"

    await message.answer(done_text, reply_markup=_chat_menu_kb(chat_id))


@router.my_chat_member()
async def on_bot_membership_update(event: ChatMemberUpdated):
    if event.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return

    new_status = event.new_chat_member.status
    actor = event.from_user
    chat_id = event.chat.id
    title = event.chat.title or f"Чат {chat_id}"

    if new_status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.MEMBER):
        save_user_chat(actor.id, chat_id, title)
        try:
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="📱 Открыть в Mini App", web_app=WebAppInfo(url=WEBAPP_URL))],
                    [InlineKeyboardButton(text="⚙️ Настроить этот чат", callback_data=f"pm:chat:{chat_id}")],
                ]
            )
            admin_note = ""
            if new_status != ChatMemberStatus.ADMINISTRATOR:
                admin_note = "

⚠️ <i>Не забудь выдать мне права администратора в группе, чтобы я мог удалять спам и выдавать муты!</i>"

            await bot.send_message(
                actor.id,
                f"✅ Бот успешно подключён к чату <b>{html.escape(title)}</b>!{admin_note}",
                reply_markup=kb,
            )
        except Exception:
            pass

    elif new_status in (ChatMemberStatus.LEFT, ChatMemberStatus.KICKED):
        remove_user_chat(actor.id, chat_id)
