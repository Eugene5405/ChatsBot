"""Панель управления ботом в личных сообщениях и нижняя клавиатура."""
import html

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

WEBAPP_URL = "https://chatsbot-ve5e.onrender.com/webapp"


class EditState(StatesGroup):
    waiting_rules = State()
    waiting_welcome = State()
    waiting_goodbye = State()


def _main_reply_kb() -> ReplyKeyboardMarkup:
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


async def _add_chat_url() -> str:
    me = await bot.get_me()
    perms = "change_info+delete_messages+restrict_members+invite_users+pin_messages+manage_chat"
    return f"https://t.me/{me.username}?startgroup=true&admin={perms}"


def _register_chat(chat_id: int, title: str, owner_id: int):
    db.set_setting(chat_id, "chat_title", title)
    if owner_id:
        db.set_setting(chat_id, "owner_id", str(owner_id))
        raw = db.get_setting(0, f"user_chats_{owner_id}") or ""
        ids = [x for x in raw.split(",") if x]
        if str(chat_id) not in ids:
            ids.append(str(chat_id))
            db.set_setting(0, f"user_chats_{owner_id}", ",".join(ids))


def _get_user_chats(user_id: int) -> list[tuple[int, str]]:
    raw = db.get_setting(0, f"user_chats_{user_id}") or ""
    result = []
    for cid_str in raw.split(","):
        if not cid_str:
            continue
        try:
            cid = int(cid_str)
            title = db.get_setting(cid, "chat_title") or f"Чат {cid}"
            result.append((cid, title))
        except ValueError:
            pass
    return result


def _chats_inline_kb(chats: list[tuple[int, str]], add_url: str) -> InlineKeyboardMarkup:
    rows = []
    for cid, title in chats:
        rows.append([InlineKeyboardButton(text=f"💬 {title}", callback_data=f"pmchat:{cid}")])
    rows.append([InlineKeyboardButton(text="➕ Подключить новый чат", url=add_url)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _chat_settings_kb(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📜 Правила", callback_data=f"pmedit:rules:{chat_id}"),
                InlineKeyboardButton(text="👋 Приветствие", callback_data=f"pmedit:welcome:{chat_id}"),
            ],
            [
                InlineKeyboardButton(text="🚪 Прощание", callback_data=f"pmedit:goodbye:{chat_id}"),
                InlineKeyboardButton(text="🛡 Фильтры", callback_data=f"pmfilters:{chat_id}"),
            ],
            [InlineKeyboardButton(text="🔙 К списку чатов", callback_data="pmback:chats")],
        ]
    )


def _filters_kb(chat_id: int) -> InlineKeyboardMarkup:
    labels = {
        "mat": "Антимат",
        "spam": "Антиспам (стикеры/гиф)",
        "links": "Защита от ссылок",
        "flood": "Антифлуд",
        "inline": "Инлайн-боты",
    }
    rows = []
    for key, label in labels.items():
        state = "✅ Вкл" if db.filter_on(chat_id, key) else "❌ Выкл"
        rows.append([InlineKeyboardButton(text=f"{label}: {state}", callback_data=f"pmtog:{key}:{chat_id}")])
    rows.append([InlineKeyboardButton(text="🔙 Назад к чату", callback_data=f"pmchat:{chat_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("start", "panel"), F.chat.type == ChatType.PRIVATE)
async def cmd_start_private(message: Message, state: FSMContext):
    await state.clear()
    add_url = await _add_chat_url()
    name = html.escape(message.from_user.first_name or "друг")
    text = (
        f"👋 Привет, <b>{name}</b>!

"
        f"Я — <b>Хранитель чата</b>. Помогу защитить твои группы от спама, мата и рекламы, "
        f"а также проверю подписку перед вступлением.

"
        f"<b>Как подключить меня к группе:</b>
"
        f"1. Нажми кнопку <b>«➕ Добавить бота в чат»</b> внизу экрана.
"
        f"2. Выбери нужную группу и выдай права администратора.
"
        f"3. Я сразу пришлю тебе сюда уведомление и открою настройки!"
    )
    inline = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📱 Открыть панель (Mini App)", web_app=WebAppInfo(url=WEBAPP_URL))],
            [InlineKeyboardButton(text="➕ Добавить в чат", url=add_url)],
        ]
    )
    await message.answer(text, reply_markup=_main_reply_kb())
    await message.answer("Выбери действие или воспользуйся кнопками внизу 👇", reply_markup=inline)


@router.message(F.text == "➕ Добавить бота в чат", F.chat.type == ChatType.PRIVATE)
async def btn_add_chat(message: Message):
    add_url = await _add_chat_url()
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="➕ Выбрать группу для подключения", url=add_url)]]
    )
    await message.answer(
        "Нажми кнопку ниже, выбери свою группу и подтверди права администратора:",
        reply_markup=kb,
    )


@router.message(F.text == "⚙️ Настроить бота в ЛС", F.chat.type == ChatType.PRIVATE)
async def btn_settings_pm(message: Message, state: FSMContext):
    await state.clear()
    chats = _get_user_chats(message.from_user.id)
    add_url = await _add_chat_url()
    if not chats:
        await message.answer(
            "У тебя пока нет подключённых чатов.
"
            "Добавь меня администратором в группу, и она сразу появится здесь!",
            reply_markup=_chats_inline_kb([], add_url),
        )
        return
    await message.answer(
        "Выбери чат для настройки правил, приветствия и фильтров:",
        reply_markup=_chats_inline_kb(chats, add_url),
    )


@router.my_chat_member()
async def on_bot_added_or_updated(event: ChatMemberUpdated):
    if event.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return
    new_status = event.new_chat_member.status
    actor = event.from_user
    if new_status in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR):
        _register_chat(event.chat.id, event.chat.title or "Группа", actor.id)
        try:
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="⚙️ Настроить чат в ЛС", callback_data=f"pmchat:{event.chat.id}")],
                    [InlineKeyboardButton(text="📱 Открыть Mini App", web_app=WebAppInfo(url=WEBAPP_URL))],
                ]
            )
            role_note = (
                "Все права администратора выданы — защита активна!"
                if new_status == ChatMemberStatus.ADMINISTRATOR
                else "⚠️ Выдай мне права администратора в группе, чтобы я мог удалять спам и выдавать муты."
            )
            await bot.send_message(
                actor.id,
                f"✅ Бот подключён к чату <b>{html.escape(event.chat.title or 'Группа')}</b>!

{role_note}",
                reply_markup=kb,
            )
        except Exception:
            pass


@router.callback_query(F.data == "pmback:chats")
async def cb_back_chats(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    chats = _get_user_chats(cb.from_user.id)
    add_url = await _add_chat_url()
    await cb.message.edit_text(
        "Выбери чат для настройки:",
        reply_markup=_chats_inline_kb(chats, add_url),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("pmchat:"))
async def cb_open_chat(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    chat_id = int(cb.data.split(":", 1)[1])
    title = db.get_setting(chat_id, "chat_title") or f"Чат {chat_id}"
    await cb.message.edit_text(
        f"⚙️ Настройки чата <b>{html.escape(title)}</b>

"
        f"Выбери, что хочешь изменить:",
        reply_markup=_chat_settings_kb(chat_id),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("pmfilters:"))
async def cb_open_filters(cb: CallbackQuery):
    chat_id = int(cb.data.split(":", 1)[1])
    title = db.get_setting(chat_id, "chat_title") or f"Чат {chat_id}"
    await cb.message.edit_text(
        f"🛡 Фильтры модерации для чата <b>{html.escape(title)}</b>:",
        reply_markup=_filters_kb(chat_id),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("pmtog:"))
async def cb_toggle_filter(cb: CallbackQuery):
    _, kind, cid_str = cb.data.split(":", 2)
    chat_id = int(cid_str)
    cur = db.filter_on(chat_id, kind)
    db.set_setting(chat_id, f"f_{kind}", "0" if cur else "1")
    await cb.message.edit_reply_markup(reply_markup=_filters_kb(chat_id))
    await cb.answer("Сохранено")


@router.callback_query(F.data.startswith("pmedit:"))
async def cb_start_edit(cb: CallbackQuery, state: FSMContext):
    _, field, cid_str = cb.data.split(":", 2)
    chat_id = int(cid_str)
    await state.update_data(edit_chat_id=chat_id, edit_field=field)
    if field == "rules":
        await state.set_state(EditState.waiting_rules)
        cur = rules.get_rules(chat_id)
        hint = f"Отправь новый текст правил для чата.

Текущие правила:
<blockquote expandable>{cur}</blockquote>"
    elif field == "welcome":
        await state.set_state(EditState.waiting_welcome)
        hint = (
            "Отправь новый текст приветствия (или слово <code>сброс</code> для стандартного).
"
            "Можно использовать переменные: <code>{user}</code> — имя участника, <code>{chat}</code> — название чата."
        )
    else:
        await state.set_state(EditState.waiting_goodbye)
        hint = (
            "Отправь новый текст прощания при выходе (или слово <code>сброс</code> для стандартного).
"
            "Доступны переменные: <code>{user}</code> и <code>{chat}</code>."
        )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data=f"pmchat:{chat_id}")]]
    )
    await cb.message.edit_text(hint, reply_markup=kb)
    await cb.answer()


@router.message(EditState.waiting_rules, F.chat.type == ChatType.PRIVATE)
async def save_rules_pm(message: Message, state: FSMContext):
    data = await state.get_data()
    chat_id = data["edit_chat_id"]
    if message.text and message.text.strip().lower() == "сброс":
        db.set_setting(chat_id, "rules", None)
    else:
        db.set_setting(chat_id, "rules", message.html_text)
    await state.clear()
    await message.answer("✅ Правила чата обновлены!", reply_markup=_chat_settings_kb(chat_id))


@router.message(EditState.waiting_welcome, F.chat.type == ChatType.PRIVATE)
async def save_welcome_pm(message: Message, state: FSMContext):
    data = await state.get_data()
    chat_id = data["edit_chat_id"]
    if message.text and message.text.strip().lower() == "сброс":
        db.set_setting(chat_id, "welcome_text", None)
    else:
        db.set_setting(chat_id, "welcome_text", message.html_text)
    await state.clear()
    await message.answer("✅ Приветствие обновлено!", reply_markup=_chat_settings_kb(chat_id))


@router.message(EditState.waiting_goodbye, F.chat.type == ChatType.PRIVATE)
async def save_goodbye_pm(message: Message, state: FSMContext):
    data = await state.get_data()
    chat_id = data["edit_chat_id"]
    if message.text and message.text.strip().lower() == "сброс":
        db.set_setting(chat_id, "goodbye_text", None)
    else:
        db.set_setting(chat_id, "goodbye_text", message.html_text)
    await state.clear()
    await message.answer("✅ Сообщение при выходе обновлено!", reply_markup=_chat_settings_kb(chat_id))
