"""Панель управления в ЛС бота (как в Iris) + кнопка Mini App."""
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
    Message,
    WebAppInfo,
)

import db
import rules
import webapp
from loader import bot

router = Router()


class EditChatState(StatesGroup):
    waiting_rules = State()
    waiting_welcome = State()
    waiting_goodbye = State()


def _webapp_url() -> str:
    base = os.getenv("RENDER_EXTERNAL_URL", "https://chatsbot-ve5e.onrender.com").rstrip("/")
    return f"{base}/webapp"


async def _main_menu_kb() -> InlineKeyboardMarkup:
    me = await bot.get_me()
    add_url = (
        f"https://t.me/{me.username}?startgroup=true"
        "&admin=change_info+delete_messages+restrict_members+invite_users+pin_messages"
    )
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Открыть панель управления (Mini App)", web_app=WebAppInfo(url=_webapp_url()))],
        [InlineKeyboardButton(text="➕ Добавить бота в чат", url=add_url)],
        [InlineKeyboardButton(text="⚙️ Мои чаты (настройка в ЛС)", callback_data="pm:my_chats")],
    ])


@router.message(F.chat.type == ChatType.PRIVATE, Command("start", "panel"))
async def pm_start(message: Message, state: FSMContext):
    await state.clear()
    text = (
        "🛡 <b>Добро пожаловать в панель управления Чат-ботом!</b>\n\n"
        "<b>Как подключить бота к группе:</b>\n"
        "1. Нажмите кнопку <b>«➕ Добавить бота в чат»</b> ниже.\n"
        "2. Выберите вашу группу и выдайте права администратора.\n"
        "3. Бот сразу пришлёт сюда уведомление, и вы сможете настроить правила, приветствие и фильтры.\n\n"
        "Управлять всеми чатами можно через удобное всплывающее окно <b>Mini App</b> или прямо здесь в сообщениях:"
    )
    await message.answer(text, reply_markup=await _main_menu_kb())


@router.my_chat_member()
async def on_bot_added_or_removed(event: ChatMemberUpdated):
    if event.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return
    new_status = event.new_chat_member.status
    actor = event.from_user

    if new_status in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR):
        webapp.register_user_chat(actor.id, event.chat.id)
        title = html.escape(event.chat.title or "Без названия")
        is_admin = new_status == ChatMemberStatus.ADMINISTRATOR
        admin_note = (
            "✅ Права администратора выданы — бот полностью готов к работе!"
            if is_admin else
            "⚠️ <b>Важно:</b> назначьте бота администратором в группе, чтобы он мог удалять спам, банить нарушителей и приветствовать новичков."
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📱 Настроить в Mini App", web_app=WebAppInfo(url=_webapp_url()))],
            [InlineKeyboardButton(text="⚙️ Настроить этот чат в ЛС", callback_data=f"pm:chat:{event.chat.id}")],
        ])
        try:
            await bot.send_message(
                actor.id,
                f"🎉 <b>Бот подключён к чату «{title}»!</b>\n\n{admin_note}",
                reply_markup=kb,
            )
        except Exception:
            pass


@router.callback_query(F.data == "pm:home")
async def cb_pm_home(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text(
        "🛡 <b>Главное меню управления</b>\nВыберите действие:",
        reply_markup=await _main_menu_kb(),
    )
    await cb.answer()


@router.callback_query(F.data == "pm:my_chats")
async def cb_my_chats(cb: CallbackQuery):
    chat_ids = webapp._get_user_chats(cb.from_user.id)
    rows = []
    for cid in chat_ids:
        try:
            chat = await bot.get_chat(cid)
            member = await bot.get_chat_member(cid, cb.from_user.id)
            if member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR):
                rows.append([InlineKeyboardButton(text=f"💬 {chat.title}", callback_data=f"pm:chat:{cid}")])
        except Exception:
            continue

    rows.append([InlineKeyboardButton(text="← Назад", callback_data="pm:home")])
    text = (
        "⚙️ <b>Ваши подключённые чаты:</b>\nВыберите группу для настройки:"
        if rows[:-1] else
        "У вас пока нет подключённых чатов. Добавьте бота в группу, и она появится здесь!"
    )
    await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await cb.answer()


def _chat_manage_kb(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📜 Изменить правила", callback_data=f"pm:edit_rules:{chat_id}")],
        [InlineKeyboardButton(text="👋 Изменить приветствие", callback_data=f"pm:edit_welcome:{chat_id}")],
        [InlineKeyboardButton(text="🚪 Изменить прощание", callback_data=f"pm:edit_goodbye:{chat_id}")],
        [InlineKeyboardButton(text="← К списку чатов", callback_data="pm:my_chats")],
    ])


@router.callback_query(F.data.startswith("pm:chat:"))
async def cb_manage_chat(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    chat_id = int(cb.data.split(":")[2])
    chat = await bot.get_chat(chat_id)
    title = html.escape(chat.title or str(chat_id))
    cur_welcome = db.get_setting(chat_id, "welcome_text") or "Стандартное"
    cur_goodbye = db.get_setting(chat_id, "goodbye_text") or "Стандартное"

    text = (
        f"⚙️ <b>Управление чатом «{title}»</b>\n\n"
        f"• <b>Приветствие:</b> {html.escape(cur_welcome[:60])}...\n"
        f"• <b>Прощание:</b> {html.escape(cur_goodbye[:60])}...\n\n"
        f"Выберите, что хотите изменить:"
    )
    await cb.message.edit_text(text, reply_markup=_chat_manage_kb(chat_id))
    await cb.answer()


@router.callback_query(F.data.startswith("pm:edit_rules:"))
async def cb_edit_rules(cb: CallbackQuery, state: FSMContext):
    chat_id = int(cb.data.split(":")[2])
    await state.set_state(EditChatState.waiting_rules)
    await state.update_data(chat_id=chat_id)
    await cb.message.answer(
        f"📜 Отправьте новый текст <b>правил</b> для чата (или отправьте <code>-</code> чтобы вернуть стандартные):\n\n"
        f"<b>Текущие правила:</b>\n<blockquote expandable>{rules.get_rules(chat_id)}</blockquote>"
    )
    await cb.answer()


@router.message(EditChatState.waiting_rules)
async def msg_save_rules(message: Message, state: FSMContext):
    data = await state.get_data()
    chat_id = data["chat_id"]
    txt = (message.text or "").strip()
    db.set_setting(chat_id, "rules", None if txt == "-" else txt)
    await state.clear()
    await message.answer("✅ Правила чата обновлены!", reply_markup=_chat_manage_kb(chat_id))


@router.callback_query(F.data.startswith("pm:edit_welcome:"))
async def cb_edit_welcome(cb: CallbackQuery, state: FSMContext):
    chat_id = int(cb.data.split(":")[2])
    await state.set_state(EditChatState.waiting_welcome)
    await state.update_data(chat_id=chat_id)
    await cb.message.answer(
        "👋 Отправьте новый текст <b>приветствия</b>.\n"
        "Можно использовать переменные: <code>{user}</code> (упоминание новичка) и <code>{chat}</code> (название чата).\n"
        "Отправьте <code>-</code>, чтобы вернуть стандартное приветствие."
    )
    await cb.answer()


@router.message(EditChatState.waiting_welcome)
async def msg_save_welcome(message: Message, state: FSMContext):
    data = await state.get_data()
    chat_id = data["chat_id"]
    txt = (message.text or "").strip()
    db.set_setting(chat_id, "welcome_text", None if txt == "-" else txt)
    await state.clear()
    await message.answer("✅ Приветствие сохранено!", reply_markup=_chat_manage_kb(chat_id))


@router.callback_query(F.data.startswith("pm:edit_goodbye:"))
async def cb_edit_goodbye(cb: CallbackQuery, state: FSMContext):
    chat_id = int(cb.data.split(":")[2])
    await state.set_state(EditChatState.waiting_goodbye)
    await state.update_data(chat_id=chat_id)
    await cb.message.answer(
        "🚪 Отправьте новый текст <b>прощания</b> при выходе из группы.\n"
        "Можно использовать переменную <code>{user}</code>.\n"
        "Отправьте <code>-</code>, чтобы вернуть стандартное прощание."
    )
    await cb.answer()


@router.message(EditChatState.waiting_goodbye)
async def msg_save_goodbye(message: Message, state: FSMContext):
    data = await state.get_data()
    chat_id = data["chat_id"]
    txt = (message.text or "").strip()
    db.set_setting(chat_id, "goodbye_text", None if txt == "-" else txt)
    await state.clear()
    await message.answer("✅ Прощальное сообщение сохранено!", reply_markup=_chat_manage_kb(chat_id))
