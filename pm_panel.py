"""Панель управления в ЛС бота: постоянные кнопки внизу, уведомления о подключении и настройка чатов."""
import html
import os

from aiogram import F, Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.exceptions import TelegramForbiddenError
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


class EditChatState(StatesGroup):
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


async def _add_to_chat_inline_kb() -> InlineKeyboardMarkup:
    me = await bot.get_me()
    url = f"https://t.me/{me.username}?startgroup=true&admin=change_info+delete_messages+restrict_members+invite_users+pin_messages"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Выбрать чат и выдать права", url=url)],
            [InlineKeyboardButton(text="📱 Открыть панель управления", web_app=WebAppInfo(url=WEBAPP_URL))],
        ]
    )


def _get_owned_chats(user_id: int) -> list[tuple[int, str]]:
    rows = db._db.execute(
        "SELECT chat_id, key, value FROM settings WHERE key LIKE 'owner_%' OR key = 'chat_title'"
    ).fetchall()
    titles = {}
    owned = set()
    for cid, k, v in rows:
        if k == "chat_title":
            titles[cid] = v
        elif k == f"owner_{user_id}" and v == "1":
            owned.add(cid)
    return [(cid, titles.get(cid, f"Чат {cid}")) for cid in sorted(owned)]


@router.my_chat_member()
async def on_bot_added_or_updated(event: ChatMemberUpdated):
    if event.chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
        return
    new_status = event.new_chat_member.status
    actor = event.from_user

    if new_status in {ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR}:
        db.set_setting(event.chat.id, "chat_title", event.chat.title or "Группа")
        db.set_setting(event.chat.id, f"owner_{actor.id}", "1")

        is_admin = new_status == ChatMemberStatus.ADMINISTRATOR
        status_note = (
            "✅ Права администратора получены, защита активна!"
            if is_admin
            else "⚠️ Выдайте боту <b>права администратора</b> в настройках группы, иначе он не сможет удалять спам и выдавать муты."
        )
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⚙️ Настроить этот чат в ЛС", callback_data=f"pm_chat:{event.chat.id}")],
                [InlineKeyboardButton(text="📱 Открыть мини-приложение", web_app=WebAppInfo(url=WEBAPP_URL))],
            ]
        )
        try:
            await bot.send_message(
                actor.id,
                f"🎉 Бот подключён к чату <b>{html.escape(event.chat.title or 'Группа')}</b>!

{status_note}",
                reply_markup=kb,
            )
        except TelegramForbiddenError:
            pass


@router.message(Command("start", "panel"), F.chat.type == ChatType.PRIVATE)
async def cmd_start_pm(msg: Message, state: FSMContext):
    await state.clear()
    text = (
        "🛡️ <b>Чат-менеджер — твой надёжный модератор 24/7</b>

"
        "<b>Как подключить бота:</b>
"
        "1. Нажми <b>«➕ Добавить бота в чат»</b> внизу экрана.
"
        "2. Выбери нужную группу и выдай боту права администратора.
"
        "3. Управляй правилами, приветствиями и фильтрами через <b>Мини-приложение</b> или прямо здесь в ЛС."
    )
    await msg.answer(text, reply_markup=_main_reply_kb())


@router.message(F.text == "➕ Добавить бота в чат", F.chat.type == ChatType.PRIVATE)
async def btn_add_bot(msg: Message):
    await msg.answer(
        "Нажмите кнопку ниже, выберите группу и подтвердите выдачу прав администратора:",
        reply_markup=await _add_to_chat_inline_kb(),
    )


@router.message(F.text == "⚙️ Настроить бота в ЛС", F.chat.type == ChatType.PRIVATE)
async def btn_settings_pm(msg: Message, state: FSMContext):
    await state.clear()
    chats = _get_owned_chats(msg.from_user.id)
    if not chats:
        await msg.answer(
            "У вас пока нет подключённых чатов.
"
            "Нажмите <b>«➕ Добавить бота в чат»</b>, чтобы подключить первую группу!",
            reply_markup=await _add_to_chat_inline_kb(),
        )
        return
    rows = [[InlineKeyboardButton(text=f"💬 {title}", callback_data=f"pm_chat:{cid}")] for cid, title in chats]
    await msg.answer("Выберите чат для настройки:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


def _chat_manage_kb(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📜 Изменить правила", callback_data=f"pm_edit:rules:{chat_id}")],
            [InlineKeyboardButton(text="👋 Изменить приветствие", callback_data=f"pm_edit:welcome:{chat_id}")],
            [InlineKeyboardButton(text="🚪 Изменить прощание", callback_data=f"pm_edit:goodbye:{chat_id}")],
            [InlineKeyboardButton(text="🛡️ Фильтры защиты", callback_data=f"pm_filters:{chat_id}")],
            [InlineKeyboardButton(text="← К списку чатов", callback_data="pm_back_list")],
        ]
    )


@router.callback_query(F.data == "pm_back_list")
async def cb_back_list(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    chats = _get_owned_chats(cb.from_user.id)
    rows = [[InlineKeyboardButton(text=f"💬 {title}", callback_data=f"pm_chat:{cid}")] for cid, title in chats]
    await cb.message.edit_text("Выберите чат для настройки:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await cb.answer()


@router.callback_query(F.data.startswith("pm_chat:"))
async def cb_manage_chat(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    chat_id = int(cb.data.split(":", 1)[1])
    if db.get_setting(chat_id, f"owner_{cb.from_user.id}") != "1":
        await cb.answer("Нет доступа к этому чату.", show_alert=True)
        return
    title = html.escape(db.get_setting(chat_id, "chat_title") or f"Чат {chat_id}")
    await cb.message.edit_text(
        f"⚙️ Настройка чата <b>{title}</b>

Выберите раздел:",
        reply_markup=_chat_manage_kb(chat_id),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("pm_filters:"))
async def cb_pm_filters(cb: CallbackQuery):
    chat_id = int(cb.data.split(":", 1)[1])
    if db.get_setting(chat_id, f"owner_{cb.from_user.id}") != "1":
        await cb.answer("Нет доступа.", show_alert=True)
        return
    labels = [("mat", "🤬 Антимат"), ("ads", "🔗 Антиреклама"), ("flood", "⚡ Антифлуд"), ("media", "🎭 Стикер-спам")]
    rows = []
    for k, name in labels:
        st = "✅ ВКЛ" if db.filter_on(chat_id, k) else "❌ ВЫКЛ"
        rows.append([InlineKeyboardButton(text=f"{name}: {st}", callback_data=f"pm_tog:{k}:{chat_id}")])
    rows.append([InlineKeyboardButton(text="← Назад", callback_data=f"pm_chat:{chat_id}")])
    await cb.message.edit_text("Нажмите на фильтр, чтобы переключить:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await cb.answer()


@router.callback_query(F.data.startswith("pm_tog:"))
async def cb_pm_toggle(cb: CallbackQuery):
    _, kind, cid_s = cb.data.split(":")
    chat_id = int(cid_s)
    if db.get_setting(chat_id, f"owner_{cb.from_user.id}") != "1":
        await cb.answer("Нет доступа.", show_alert=True)
        return
    db.set_setting(chat_id, "f_" + kind, "0" if db.filter_on(chat_id, kind) else "1")
    await cb_pm_filters(cb)


@router.callback_query(F.data.startswith("pm_edit:"))
async def cb_pm_edit_prompt(cb: CallbackQuery, state: FSMContext):
    _, field, cid_s = cb.data.split(":")
    chat_id = int(cid_s)
    if db.get_setting(chat_id, f"owner_{cb.from_user.id}") != "1":
        await cb.answer("Нет доступа.", show_alert=True)
        return
    await state.update_data(edit_chat_id=chat_id)
    prompts = {
        "rules": ("📜 Отправьте новый текст <b>правил</b> для этого чата:", EditChatState.waiting_rules),
        "welcome": (
            "👋 Отправьте новый текст <b>приветствия</b>.
"
            "Можно использовать <code>{user}</code> (имя новичка) и <code>{chat}</code> (название группы).
"
            "Отправьте <code>-</code> чтобы вернуть стандартное.",
            EditChatState.waiting_welcome,
        ),
        "goodbye": (
            "🚪 Отправьте новый текст <b>прощания</b> при выходе участника.
"
            "Можно использовать <code>{user}</code> и <code>{chat}</code>.
"
            "Отправьте <code>-</code> чтобы вернуть стандартное.",
            EditChatState.waiting_goodbye,
        ),
    }
    text, st = prompts[field]
    await state.set_state(st)
    await cb.message.answer(text)
    await cb.answer()


@router.message(EditChatState.waiting_rules, F.chat.type == ChatType.PRIVATE)
async def save_pm_rules(msg: Message, state: FSMContext):
    data = await state.get_data()
    chat_id = data["edit_chat_id"]
    db.set_setting(chat_id, "rules", (msg.text or "").strip() or None)
    await state.clear()
    await msg.answer("✅ Правила обновлены!", reply_markup=_chat_manage_kb(chat_id))


@router.message(EditChatState.waiting_welcome, F.chat.type == ChatType.PRIVATE)
async def save_pm_welcome(msg: Message, state: FSMContext):
    data = await state.get_data()
    chat_id = data["edit_chat_id"]
    val = (msg.text or "").strip()
    db.set_setting(chat_id, "welcome_text", None if val == "-" else val)
    await state.clear()
    await msg.answer("✅ Приветствие обновлено!", reply_markup=_chat_manage_kb(chat_id))


@router.message(EditChatState.waiting_goodbye, F.chat.type == ChatType.PRIVATE)
async def save_pm_goodbye(msg: Message, state: FSMContext):
    data = await state.get_data()
    chat_id = data["edit_chat_id"]
    val = (msg.text or "").strip()
    db.set_setting(chat_id, "goodbye_text", None if val == "-" else val)
    await state.clear()
    await msg.answer("✅ Прощание обновлено!", reply_markup=_chat_manage_kb(chat_id))
