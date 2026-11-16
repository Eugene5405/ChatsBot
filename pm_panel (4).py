"""Панель управления в ЛС бота: подключение чатов, уведомления о входе/удалении и настройки."""
import html
import logging

from aiogram import F, Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
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

_ACTIVE = {ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}
_ADMIN = {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}
_LEFT = {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED}

# Инициализация таблицы привязки чатов к администраторам в PostgreSQL
db._db.execute("""
CREATE TABLE IF NOT EXISTS managed_chats (
    chat_id BIGINT PRIMARY KEY,
    owner_id BIGINT NOT NULL,
    chat_title TEXT NOT NULL
)
""")


class EditChatState(StatesGroup):
    waiting_rules = State()
    waiting_welcome = State()
    waiting_bye = State()


def register_chat(chat_id: int, owner_id: int, chat_title: str):
    title = chat_title or "Без названия"
    db._db.execute(
        """INSERT INTO managed_chats (chat_id, owner_id, chat_title)
           VALUES (%s, %s, %s)
           ON CONFLICT (chat_id) DO UPDATE SET owner_id = EXCLUDED.owner_id, chat_title = EXCLUDED.chat_title""",
        (chat_id, owner_id, title),
    )


def unregister_chat(chat_id: int) -> tuple[int, str] | None:
    row = db._db.execute(
        "SELECT owner_id, chat_title FROM managed_chats WHERE chat_id=%s",
        (chat_id,),
    ).fetchone()
    db._db.execute("DELETE FROM managed_chats WHERE chat_id=%s", (chat_id,))
    return (row[0], row[1]) if row else None


def get_user_chats(owner_id: int) -> list[tuple[int, str]]:
    rows = db._db.execute(
        "SELECT chat_id, chat_title FROM managed_chats WHERE owner_id=%s ORDER BY chat_title",
        (owner_id,),
    ).fetchall()
    return [(r[0], r[1]) for r in rows]


def _reply_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Мини-приложение")],
            [
                KeyboardButton(text="➕ Добавить бота в чат"),
                KeyboardButton(text="⚙️ Настроить бота в ЛС"),
            ],
        ],
        resize_keyboard=True,
    )


async def _add_to_group_url() -> str:
    me = await bot.get_me()
    perms = "change_info+delete_messages+restrict_members+invite_users+pin_messages+manage_chat"
    return f"https://t.me/{me.username}?startgroup=true&admin={perms}"


def _webapp_url() -> str:
    return "https://chatsbot-ve5e.onrender.com/webapp"


async def _main_inline_kb() -> InlineKeyboardMarkup:
    add_url = await _add_to_group_url()
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📱 Открыть панель управления (Mini App)", web_app=WebAppInfo(url=_webapp_url()))],
            [InlineKeyboardButton(text="➕ Добавить бота в группу", url=add_url)],
            [InlineKeyboardButton(text="⚙️ Мои чаты (настроить в ЛС)", callback_data="pm:my_chats")],
        ]
    )


@router.my_chat_member()
async def on_bot_membership_update(event: ChatMemberUpdated):
    if event.chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
        return

    old_st = event.old_chat_member.status
    new_st = event.new_chat_member.status
    actor = event.from_user
    title = html.escape(event.chat.title or "Группа")

    # Бота добавили в чат или выдали ему права администратора
    if new_st in _ACTIVE:
        if actor and not actor.is_bot:
            register_chat(event.chat.id, actor.id, event.chat.title or "Группа")
            if old_st in _LEFT or new_st in _ADMIN:
                is_admin = new_st in _ADMIN
                status_line = (
                    "✅ <b>Права администратора выданы</b> — бот полностью готов к работе!"
                    if is_admin
                    else "⚠️ <b>Выдай боту права администратора</b> в настройках группы, чтобы он мог удалять спам, банить и приветствовать новичков."
                )
                kb = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="📱 Открыть Mini App", web_app=WebAppInfo(url=_webapp_url()))],
                        [InlineKeyboardButton(text="⚙️ Настроить этот чат в ЛС", callback_data=f"pm:chat:{event.chat.id}")],
                    ]
                )
                try:
                    await bot.send_message(
                        actor.id,
                        f"🎉 <b>Бот подключён к чату «{title}»!</b>\n\n{status_line}",
                        reply_markup=kb,
                    )
                except (TelegramForbiddenError, TelegramBadRequest) as e:
                    logging.warning("Не удалось отправить уведомление о подключении в ЛС: %s", e)

    # Бота удалили / кикнули из чата
    elif old_st in _ACTIVE and new_st in _LEFT:
        saved = unregister_chat(event.chat.id)
        notify_ids = set()
        if saved:
            notify_ids.add(saved[0])
        if actor and not actor.is_bot:
            notify_ids.add(actor.id)

        for uid in notify_ids:
            try:
                await bot.send_message(
                    uid,
                    f"❌ <b>Бот был удалён из чата «{title}»</b> и отключён от управления.\n"
                    f"Чат автоматически убран из списка в Mini App и ЛС.",
                )
            except (TelegramForbiddenError, TelegramBadRequest):
                pass


@router.message(F.chat.type == ChatType.PRIVATE, Command("start", "panel"))
async def cmd_start_pm(msg: Message, state: FSMContext):
    await state.clear()
    name = html.escape(msg.from_user.first_name or "друг")
    text = (
        f"👋 <b>Привет, {name}!</b>\n\n"
        f"Я — <b>Хранитель чата</b>. Слежу за порядком, проверяю заявки на вступление, "
        f"чищу спам и мат.\n\n"
        f"<b>Как подключить бота в группу:</b>\n"
        f"1. Нажми кнопку <b>«➕ Добавить бота в чат»</b> ниже.\n"
        f"2. Выбери нужную группу и подтверди права администратора.\n"
        f"3. Я сразу пришлю уведомление сюда и открою настройки чата."
    )
    await msg.answer(text, reply_markup=_reply_menu_kb())
    await msg.answer("Выбери удобный способ управления:", reply_markup=await _main_inline_kb())


@router.message(F.chat.type == ChatType.PRIVATE, F.text == "📱 Мини-приложение")
async def btn_open_miniapp(msg: Message):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📱 Запустить Mini App", web_app=WebAppInfo(url=_webapp_url()))]
        ]
    )
    await msg.answer("Нажми на кнопку ниже, чтобы открыть панель управления:", reply_markup=kb)


@router.message(F.chat.type == ChatType.PRIVATE, F.text == "➕ Добавить бота в чат")
async def btn_add_to_chat(msg: Message):
    add_url = await _add_to_group_url()
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="➕ Выбрать чат и выдать права", url=add_url)]]
    )
    await msg.answer(
        "Нажми кнопку ниже, выбери свою группу и разреши права администратора:",
        reply_markup=kb,
    )


@router.message(F.chat.type == ChatType.PRIVATE, F.text == "⚙️ Настроить бота в ЛС")
async def btn_settings_pm(msg: Message, state: FSMContext):
    await state.clear()
    await _show_chats_list(msg, msg.from_user.id, edit=False)


async def _show_chats_list(target: Message | CallbackQuery, user_id: int, edit: bool = True):
    chats = get_user_chats(user_id)
    if not chats:
        add_url = await _add_to_group_url()
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="➕ Добавить бота в группу", url=add_url)],
                [InlineKeyboardButton(text="📱 Открыть Mini App", web_app=WebAppInfo(url=_webapp_url()))],
            ]
        )
        text = (
            "У тебя пока нет подключённых чатов.\n\n"
            "Добавь бота администратором в свою группу — он сразу появится здесь."
        )
    else:
        rows = [
            [InlineKeyboardButton(text=f"💬 {title}", callback_data=f"pm:chat:{cid}")]
            for cid, title in chats
        ]
        rows.append([InlineKeyboardButton(text="📱 Открыть в Mini App", web_app=WebAppInfo(url=_webapp_url()))])
        kb = InlineKeyboardMarkup(inline_keyboard=rows)
        text = "<b>⚙️ Твои подключённые чаты:</b>\nВыбери группу, чтобы изменить её настройки:"

    if edit and isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=kb)
        await target.answer()
    else:
        m = target.message if isinstance(target, CallbackQuery) else target
        await m.answer(text, reply_markup=kb)


@router.callback_query(F.data == "pm:my_chats")
async def cb_my_chats(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await _show_chats_list(cb, cb.from_user.id, edit=True)


def _chat_settings_kb(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📜 Правила", callback_data=f"pm:edit_rules:{chat_id}"),
                InlineKeyboardButton(text="👋 Приветствие", callback_data=f"pm:edit_welcome:{chat_id}"),
            ],
            [
                InlineKeyboardButton(text="🚪 Прощание", callback_data=f"pm:edit_bye:{chat_id}"),
                InlineKeyboardButton(text="🛡 Фильтры", callback_data=f"pm:filters:{chat_id}"),
            ],
            [InlineKeyboardButton(text="⬅️ К списку чатов", callback_data="pm:my_chats")],
        ]
    )


@router.callback_query(F.data.startswith("pm:chat:"))
async def cb_open_chat(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    chat_id = int(cb.data.split(":")[2])
    row = db._db.execute("SELECT chat_title FROM managed_chats WHERE chat_id=%s", (chat_id,)).fetchone()
    title = html.escape(row[0] if row else "Чат")
    await cb.message.edit_text(
        f"⚙️ <b>Настройки чата «{title}»</b>\n\nВыбери, что хочешь изменить:",
        reply_markup=_chat_settings_kb(chat_id),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("pm:filters:"))
async def cb_filters(cb: CallbackQuery):
    chat_id = int(cb.data.split(":")[2])
    kinds = [
        ("mat", "🤬 Фильтр мата"),
        ("flood", "🌊 Антифлуд"),
        ("links", "🔗 Блок ссылок"),
        ("media", "🎭 Стикеры/гифки 3+"),
        ("inline", "🤖 Инлайн-боты"),
    ]
    rows = []
    for kind, label in kinds:
        on = db.filter_on(chat_id, kind)
        mark = "✅ ВКЛ" if on else "❌ ВЫКЛ"
        rows.append([InlineKeyboardButton(text=f"{label}: {mark}", callback_data=f"pm:toggle:{chat_id}:{kind}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад к чату", callback_data=f"pm:chat:{chat_id}")])
    await cb.message.edit_text(
        "<b>🛡 Фильтры автомодерации</b>\nНажми на фильтр, чтобы переключить:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("pm:toggle:"))
async def cb_toggle_filter(cb: CallbackQuery):
    _, _, cid_s, kind = cb.data.split(":")
    chat_id = int(cid_s)
    cur = db.filter_on(chat_id, kind)
    db.set_setting(chat_id, "f_" + kind, "0" if cur else "1")
    await cb_filters(cb)


@router.callback_query(F.data.startswith("pm:edit_rules:"))
async def cb_edit_rules(cb: CallbackQuery, state: FSMContext):
    chat_id = int(cb.data.split(":")[2])
    await state.set_state(EditChatState.waiting_rules)
    await state.update_data(chat_id=chat_id)
    cur = rules.get_rules(chat_id)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data=f"pm:chat:{chat_id}")]]
    )
    await cb.message.edit_text(
        f"<b>📜 Текущие правила чата:</b>\n<blockquote expandable>{cur}</blockquote>\n\n"
        f"Отправь новым сообщением текст новых правил:",
        reply_markup=kb,
    )
    await cb.answer()


@router.callback_query(F.data.startswith("pm:edit_welcome:"))
async def cb_edit_welcome(cb: CallbackQuery, state: FSMContext):
    chat_id = int(cb.data.split(":")[2])
    await state.set_state(EditChatState.waiting_welcome)
    await state.update_data(chat_id=chat_id)
    cur = db.get_setting(chat_id, "custom_welcome") or "Стандартное приветствие с правилами"
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Сбросить на стандарт", callback_data=f"pm:reset_welcome:{chat_id}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data=f"pm:chat:{chat_id}")],
        ]
    )
    await cb.message.edit_text(
        f"<b>👋 Текущее приветствие:</b>\n<code>{html.escape(cur)}</code>\n\n"
        f"Отправь новый текст приветствия. Можно использовать переменные:\n"
        f"<code>{{user}}</code> — имя новичка\n"
        f"<code>{{chat}}</code> — название чата",
        reply_markup=kb,
    )
    await cb.answer()


@router.callback_query(F.data.startswith("pm:reset_welcome:"))
async def cb_reset_welcome(cb: CallbackQuery):
    chat_id = int(cb.data.split(":")[2])
    db.set_setting(chat_id, "custom_welcome", None)
    await cb.answer("Приветствие сброшено на стандартное!", show_alert=True)
    await cb_open_chat(cb, None)


@router.callback_query(F.data.startswith("pm:edit_bye:"))
async def cb_edit_bye(cb: CallbackQuery, state: FSMContext):
    chat_id = int(cb.data.split(":")[2])
    await state.set_state(EditChatState.waiting_bye)
    await state.update_data(chat_id=chat_id)
    cur = db.get_setting(chat_id, "custom_bye") or "👋 {user} покинул(а) чат. Удачи и всего хорошего!"
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Сбросить на стандарт", callback_data=f"pm:reset_bye:{chat_id}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data=f"pm:chat:{chat_id}")],
        ]
    )
    await cb.message.edit_text(
        f"<b>🚪 Текущее прощание:</b>\n<code>{html.escape(cur)}</code>\n\n"
        f"Отправь новый текст прощания. Переменные:\n"
        f"<code>{{user}}</code> — имя ушедшего\n"
        f"<code>{{chat}}</code> — название чата",
        reply_markup=kb,
    )
    await cb.answer()


@router.callback_query(F.data.startswith("pm:reset_bye:"))
async def cb_reset_bye(cb: CallbackQuery):
    chat_id = int(cb.data.split(":")[2])
    db.set_setting(chat_id, "custom_bye", None)
    await cb.answer("Прощание сброшено на стандартное!", show_alert=True)
    await cb_open_chat(cb, None)


@router.message(F.chat.type == ChatType.PRIVATE, EditChatState.waiting_rules)
async def save_rules_msg(msg: Message, state: FSMContext):
    data = await state.get_data()
    chat_id = data["chat_id"]
    db.set_setting(chat_id, "rules", html.escape(msg.text or ""))
    await state.clear()
    await msg.answer("✅ <b>Новые правила сохранены!</b>", reply_markup=_chat_settings_kb(chat_id))


@router.message(F.chat.type == ChatType.PRIVATE, EditChatState.waiting_welcome)
async def save_welcome_msg(msg: Message, state: FSMContext):
    data = await state.get_data()
    chat_id = data["chat_id"]
    db.set_setting(chat_id, "custom_welcome", msg.text or "")
    await state.clear()
    await msg.answer("✅ <b>Новое приветствие сохранено!</b>", reply_markup=_chat_settings_kb(chat_id))


@router.message(F.chat.type == ChatType.PRIVATE, EditChatState.waiting_bye)
async def save_bye_msg(msg: Message, state: FSMContext):
    data = await state.get_data()
    chat_id = data["chat_id"]
    db.set_setting(chat_id, "custom_bye", msg.text or "")
    await state.clear()
    await msg.answer("✅ <b>Новое прощание сохранено!</b>", reply_markup=_chat_settings_kb(chat_id))
