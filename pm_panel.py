"""Панель управления ботом в личных сообщениях (меню, добавление в чат, настройка)."""
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


async def _add_to_chat_kb() -> InlineKeyboardMarkup:
    me = await bot.get_me()
    perms = "delete_messages+restrict_members+invite_users+pin_messages+manage_chat"
    url = f"https://t.me/{me.username}?startgroup=true&admin={perms}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Выбрать чат и подключить", url=url)]
        ]
    )


def _register_chat(chat_id: int, title: str, admin_id: int):
    db.set_setting(chat_id, "chat_title", title or "Без названия")
    raw = db.get_setting(admin_id, "admin_chats") or ""
    ids = [x for x in raw.split(",") if x]
    cid = str(chat_id)
    if cid not in ids:
        ids.append(cid)
        db.set_setting(admin_id, "admin_chats", ",".join(ids))


def _get_admin_chats(admin_id: int) -> list[tuple[int, str]]:
    raw = db.get_setting(admin_id, "admin_chats") or ""
    res = []
    for x in raw.split(","):
        if x.lstrip("-").isdigit():
            cid = int(x)
            title = db.get_setting(cid, "chat_title") or f"Чат {cid}"
            res.append((cid, title))
    return res


def _chats_inline_kb(admin_id: int) -> InlineKeyboardMarkup:
    chats = _get_admin_chats(admin_id)
    rows = []
    for cid, title in chats:
        rows.append([InlineKeyboardButton(text=f"💬 {title}", callback_data=f"pmchat:{cid}")])
    rows.append([InlineKeyboardButton(text="📱 Открыть Mini App", web_app=WebAppInfo(url=WEBAPP_URL))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _chat_manage_kb(chat_id: int) -> InlineKeyboardMarkup:
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
            [InlineKeyboardButton(text="« Назад к списку чатов", callback_data="pmback:chats")],
        ]
    )


def _filters_kb(chat_id: int) -> InlineKeyboardMarkup:
    names = [
        ("mat", "Антимат"),
        ("flood", "Антифлуд"),
        ("links", "Запрет ссылок"),
        ("stickers", "Спам стикерами"),
    ]
    rows = []
    for key, label in names:
        st = "✅ ВКЛ" if db.filter_on(chat_id, key) else "❌ ВЫКЛ"
        rows.append([InlineKeyboardButton(text=f"{label}: {st}", callback_data=f"pmtog:{key}:{chat_id}")])
    rows.append([InlineKeyboardButton(text="« Назад к чату", callback_data=f"pmchat:{chat_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("start", "panel"), F.chat.type == ChatType.PRIVATE)
async def cmd_start_pm(message: Message, state: FSMContext):
    await state.clear()
    name = html.escape(message.from_user.first_name or "друг")
    lines = [
        f"👋 Привет, <b>{name}</b>!",
        "",
        "Я — <b>Хранитель чата</b>. Помогаю следить за порядком, проверять заявки на вступление, приветствовать новичков и наказывать спамеров.",
        "",
        "📌 <b>Как подключить меня в группу:</b>",
        "1. Нажми кнопку <b>«➕ Добавить бота в чат»</b> внизу экрана.",
        "2. Выбери нужную группу и выдай права администратора.",
        "3. Я сразу пришлю уведомление сюда, и ты сможешь настроить правила и приветствие.",
    ]
    await message.answer("
".join(lines), reply_markup=_main_reply_kb())


@router.message(F.text == "➕ Добавить бота в чат", F.chat.type == ChatType.PRIVATE)
async def btn_add_chat(message: Message):
    lines = [
        "➕ <b>Подключение бота к группе</b>",
        "",
        "Нажми на кнопку ниже, выбери свой чат и подтверди выдачу прав администратора (удаление сообщений, бан, приглашение и закрепление).",
    ]
    await message.answer("
".join(lines), reply_markup=await _add_to_chat_kb())


@router.message(F.text == "⚙️ Настроить бота в ЛС", F.chat.type == ChatType.PRIVATE)
async def btn_settings_pm(message: Message, state: FSMContext):
    await state.clear()
    chats = _get_admin_chats(message.from_user.id)
    if not chats:
        lines = [
            "У тебя пока нет подключённых чатов.",
            "",
            "Добавь меня администратором в свою группу через кнопку <b>«➕ Добавить бота в чат»</b> (или сними и заново выдай права админа, если я уже там).",
        ]
        await message.answer("
".join(lines), reply_markup=await _add_to_chat_kb())
        return
    await message.answer("⚙️ <b>Выбери чат для настройки:</b>", reply_markup=_chats_inline_kb(message.from_user.id))


@router.my_chat_member()
async def on_bot_added_or_updated(event: ChatMemberUpdated):
    if event.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return
    new_st = event.new_chat_member.status
    actor = event.from_user
    if new_st in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR) and not actor.is_bot:
        _register_chat(event.chat.id, event.chat.title, actor.id)
        title = html.escape(event.chat.title or "группу")
        status_note = (
            "✅ Права администратора выданы — я готов к работе!"
            if new_st == ChatMemberStatus.ADMINISTRATOR
            else "⚠️ Выдай мне права администратора в группе, чтобы я мог удалять спам и принимать заявки."
        )
        lines = [
            f"🎉 Бот подключён к чату <b>{title}</b>!",
            "",
            status_note,
            "",
            "Настроить правила, приветствие и фильтры можно прямо сейчас:",
        ]
        try:
            await bot.send_message(actor.id, "
".join(lines), reply_markup=_chat_manage_kb(event.chat.id))
        except Exception:
            pass


@router.callback_query(F.data == "pmback:chats")
async def cb_back_chats(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text(
        "⚙️ <b>Выбери чат для настройки:</b>",
        reply_markup=_chats_inline_kb(cb.from_user.id),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("pmchat:"))
async def cb_select_chat(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    cid = int(cb.data.split(":", 1)[1])
    title = html.escape(db.get_setting(cid, "chat_title") or f"Чат {cid}")
    lines = [
        f"⚙️ Настройка чата <b>{title}</b>",
        "",
        "Выбери, что хочешь изменить:",
    ]
    await cb.message.edit_text("
".join(lines), reply_markup=_chat_manage_kb(cid))
    await cb.answer()


@router.callback_query(F.data.startswith("pmfilters:"))
async def cb_filters(cb: CallbackQuery):
    cid = int(cb.data.split(":", 1)[1])
    title = html.escape(db.get_setting(cid, "chat_title") or f"Чат {cid}")
    await cb.message.edit_text(f"🛡 <b>Фильтры чата {title}:</b>", reply_markup=_filters_kb(cid))
    await cb.answer()


@router.callback_query(F.data.startswith("pmtog:"))
async def cb_toggle_filter(cb: CallbackQuery):
    _, kind, cid_s = cb.data.split(":", 2)
    cid = int(cid_s)
    cur = db.filter_on(cid, kind)
    db.set_setting(cid, "f_" + kind, "0" if cur else "1")
    await cb.message.edit_reply_markup(reply_markup=_filters_kb(cid))
    await cb.answer("Сохранено")


@router.callback_query(F.data.startswith("pmedit:"))
async def cb_start_edit(cb: CallbackQuery, state: FSMContext):
    _, field, cid_s = cb.data.split(":", 2)
    cid = int(cid_s)
    await state.update_data(edit_chat_id=cid)
    if field == "rules":
        await state.set_state(EditState.waiting_rules)
        cur = rules.get_rules(cid)
        lines = [
            "📜 <b>Текущие правила чата:</b>",
            f"<blockquote expandable>{cur}</blockquote>",
            "",
            "Отправь новым сообщением текст новых правил (или напиши <code>сброс</code>, чтобы вернуть стандартные).",
        ]
        await cb.message.answer("
".join(lines))
    elif field == "welcome":
        await state.set_state(EditState.waiting_welcome)
        cur = db.get_setting(cid, "welcome_text") or "Стандартное приветствие с правилами"
        lines = [
            "👋 <b>Настройка приветствия</b>",
            f"Сейчас: <i>{html.escape(cur)}</i>",
            "",
            "Отправь новый текст приветствия. Можно использовать <code>{user}</code> (упоминание новичка) и <code>{chat}</code> (название чата). Напиши <code>сброс</code> для возврата стандартного.",
        ]
        await cb.message.answer("
".join(lines))
    elif field == "goodbye":
        await state.set_state(EditState.waiting_goodbye)
        cur = db.get_setting(cid, "goodbye_text") or "👋 {user} покинул(а) чат. Удачи и всего хорошего!"
        lines = [
            "🚪 <b>Настройка прощания</b>",
            f"Сейчас: <i>{html.escape(cur)}</i>",
            "",
            "Отправь новый текст при выходе участника. Доступны <code>{user}</code> и <code>{chat}</code>. Напиши <code>сброс</code> для возврата стандартного.",
        ]
        await cb.message.answer("
".join(lines))
    await cb.answer()


@router.message(EditState.waiting_rules, F.chat.type == ChatType.PRIVATE)
async def save_new_rules(message: Message, state: FSMContext):
    data = await state.get_data()
    cid = data["edit_chat_id"]
    txt = (message.html_text or message.text or "").strip()
    if txt.lower() == "сброс":
        db.set_setting(cid, "rules", None)
        await message.answer("✅ Правила сброшены на стандартные.", reply_markup=_chat_manage_kb(cid))
    else:
        db.set_setting(cid, "rules", txt)
        await message.answer("✅ Новые правила чата сохранены!", reply_markup=_chat_manage_kb(cid))
    await state.clear()


@router.message(EditState.waiting_welcome, F.chat.type == ChatType.PRIVATE)
async def save_new_welcome(message: Message, state: FSMContext):
    data = await state.get_data()
    cid = data["edit_chat_id"]
    txt = (message.html_text or message.text or "").strip()
    if txt.lower() == "сброс":
        db.set_setting(cid, "welcome_text", None)
        await message.answer("✅ Приветствие сброшено на стандартное.", reply_markup=_chat_manage_kb(cid))
    else:
        db.set_setting(cid, "welcome_text", txt)
        await message.answer("✅ Новое приветствие сохранено!", reply_markup=_chat_manage_kb(cid))
    await state.clear()


@router.message(EditState.waiting_goodbye, F.chat.type == ChatType.PRIVATE)
async def save_new_goodbye(message: Message, state: FSMContext):
    data = await state.get_data()
    cid = data["edit_chat_id"]
    txt = (message.html_text or message.text or "").strip()
    if txt.lower() == "сброс":
        db.set_setting(cid, "goodbye_text", None)
        await message.answer("✅ Прощальное сообщение сброшено на стандартное.", reply_markup=_chat_manage_kb(cid))
    else:
        db.set_setting(cid, "goodbye_text", txt)
        await message.answer("✅ Новое прощальное сообщение сохранено!", reply_markup=_chat_manage_kb(cid))
    await state.clear()
