"""Валюта 'Алиби' (/bag, мешок, /give, дать, /setcreds) и Магазин на 13 товаров (/shop, магазин)."""
import asyncio
import html
import random
from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup, Message

import db

router = Router()

_ADMINS = {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}

SHOP_ITEMS = [
    ("shield_mute", "🛡 Щит от мута", 150, "Автоматически спасает от 1 мута."),
    ("shield_warn", "🛡 Щит от преда", 200, "Автоматически блокирует 1 предупреждение."),
    ("shield_ban", "🛡 Щит от бана", 400, "Автоматически спасает от 1 бана."),
    ("unwarn_ticket", "🧹 Снятие 1 преда", 180, "Сразу снимает 1 активное предупреждение."),
    ("swear_pass", "🤬 Swear pass", 120, "Разрешение на 1 мат без удаления и наказания."),
    ("vip_30d", "👑 VIP-статус (30 дней)", 600, "+30% к заработку Алиби и вдвое короче кулдауны."),
    ("order_mute", "🔇 Заказной мут (10 мин)", 250, "Ответом на сообщение выдаёт мут выбранному игроку на 10 мин."),
    ("custom_prefix", "🏷 Кастомный префикс", 300, "Устанавливает личный титул в твоём мешке."),
    ("pin_1h", "📌 Закреп на 1 час", 140, "Закрепляет твоё сообщение ответом на 1 час."),
    ("fake_ban", "🎭 Фейк-бан (пранк)", 160, "Пишет о бане участника, а через 20 сек раскрывает пранк."),
    ("wedding_ring", "💍 Обручальное кольцо", 500, "Ответом на сообщение заключает брак в чате."),
    ("mystery_box", "🎁 Тайный подарок", 220, "Лутбокс со случайным призом: от монет до редкого щита или VIP."),
    ("silencer_1h", "🤐 Глушилка (1 час)", 260, "Запрещает выбранному игроку стикеры и голосовые на 1 час."),
]


def _mention(user) -> str:
    name = html.escape(user.full_name or user.first_name or "Участник")
    return f'<a href="tg://user?id={user.id}">{name}</a>'


async def _is_admin(message: Message) -> bool:
    if not message.from_user:
        return False
    member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
    return member.status in _ADMINS


def _shop_kb(user_id: int) -> InlineKeyboardMarkup:
    rows = []
    for idx, (key, title, price, _) in enumerate(SHOP_ITEMS, start=1):
        rows.append([
            InlineKeyboardButton(
                text=f"{idx}. {title} — {price} Алиби",
                callback_data=f"buy:{user_id}:{key}",
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}), Command("bag"))
@router.message(
    F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}),
    F.text.func(lambda t: t is not None and t.strip().lower() == "мешок"),
)
async def cmd_bag(message: Message):
    if not message.from_user:
        return
    stats = db.get_user_stats(message.chat.id, message.from_user.id)
    inv = stats["inventory"]
    names = {k: title for k, title, _, _ in SHOP_ITEMS}
    inv_lines = [f"• {names.get(k, k)}: <b>{v} шт.</b>" for k, v in inv.items() if v > 0]
    inv_text = "\n".join(inv_lines) if inv_lines else "<i>Пусто</i>"
    vip_line = "👑 <b>Активен</b>" if stats["vip"] else "Обычный"
    prefix_line = f"\n🏷 Титул: <b>{html.escape(stats['prefix'])}</b>" if stats.get("prefix") else ""

    await message.reply(
        f"🎒 <b>Мешок {_mention(message.from_user)}</b>\n\n"
        f"💰 Баланс: <b>{stats['balance']} Алиби</b>\n"
        f"🏅 Репутация: <b>{stats['reputation']}</b>\n"
        f"✨ Статус: {vip_line}{prefix_line}\n\n"
        f"<b>Инвентарь:</b>\n{inv_text}"
    )


@router.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}), Command("setcreds"))
async def cmd_setcreds(message: Message):
    if not await _is_admin(message):
        return
    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.reply("↩️ Ответьте на сообщение участника: <code>/setcreds 500</code>")
        return
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts.isdigit():
        await message.reply("ℹ️ Укажите сумму: <code>/setcreds 500</code>")
        return
    amount = int(parts)
    target = message.reply_to_message.from_user
    bal = db.set_balance(message.chat.id, target.id, amount)
    await message.reply(f"💰 Баланс {_mention(target)} установлен на <b>{bal} Алиби</b>.")


@router.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}), Command("give"))
@router.message(
    F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}),
    F.text.func(lambda t: t is not None and t.strip().lower().startswith("дать ")),
)
async def cmd_give(message: Message):
    if not message.from_user:
        return
    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.reply("↩️ Ответьте на сообщение участника: <code>дать 50</code> или <code>/give 50</code>")
        return

    parts = (message.text or "").split()
    if len(parts) < 2 or not parts.isdigit() or int(parts) <= 0:
        await message.reply("ℹ️ Укажите сумму больше 0: <code>дать 50</code>")
        return

    amount = int(parts)
    target = message.reply_to_message.from_user
    if target.id == message.from_user.id or target.is_bot:
        return

    sender_stats = db.get_user_stats(message.chat.id, message.from_user.id)
    if sender_stats["balance"] < amount:
        await message.reply(f"❌ Недостаточно Алиби (у вас <b>{sender_stats['balance']}</b>).")
        return

    db.add_balance(message.chat.id, message.from_user.id, -amount)
    db.add_balance(message.chat.id, target.id, amount)
    await message.reply(
        f"💸 {_mention(message.from_user)} передал(а) <b>{amount} Алиби</b> участнику {_mention(target)}!"
)
  @router.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}), Command("shop"))
@router.message(
    F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}),
    F.text.func(lambda t: t is not None and t.strip().lower() == "магазин"),
)
async def cmd_shop(message: Message):
    if not message.from_user:
        return
    lines = ["🏪 <b>Магазин чата (валюта: Алиби)</b>\n"]
    for idx, (_, title, price, desc) in enumerate(SHOP_ITEMS, start=1):
        lines.append(f"<b>{idx}. {title}</b> — <code>{price}</code> Алиби\n<i>{desc}</i>")
    lines.append("\nНажмите на кнопку ниже, чтобы купить товар:")
    await message.reply("\n".join(lines), reply_markup=_shop_kb(message.from_user.id))


@router.callback_query(F.data.startswith("buy:"))
async def on_buy_item(cb: CallbackQuery):
    _, owner_s, item_key = cb.data.split(":")
    if cb.from_user.id != int(owner_s):
        await cb.answer("Откройте свой магазин командой «магазин» или /shop.", show_alert=True)
        return

    item = next((x for x in SHOP_ITEMS if x == item_key), None)
    if not item:
        await cb.answer("Товар не найден.", show_alert=True)
        return

    _, title, price, _ = item
    chat_id = cb.message.chat.id
    user_id = cb.from_user.id
    stats = db.get_user_stats(chat_id, user_id)

    if stats["balance"] < price:
        await cb.answer(f"Не хватает Алиби! Нужно {price}, у вас {stats['balance']}.", show_alert=True)
        return

    db.add_balance(chat_id, user_id, -price)

    if item_key == "unwarn_ticket":
        left = db.remove_last_warn(chat_id, user_id)
        await cb.message.answer(f"🧹 {_mention(cb.from_user)} купил(а) снятие преда! Активных варнов: <b>{left}/3</b>.")
    elif item_key == "vip_30d":
        db.activate_vip(chat_id, user_id, days=30)
        await cb.message.answer(f"👑 {_mention(cb.from_user)} активировал(а) <b>VIP-статус на 30 дней</b>!")
    elif item_key == "mystery_box":
        roll = random.choice(["coins_100", "coins_350", "shield_mute", "shield_warn", "swear_pass"])
        if roll == "coins_100":
            db.add_balance(chat_id, user_id, 100)
            prize = "💰 100 Алиби"
        elif roll == "coins_350":
            db.add_balance(chat_id, user_id, 350)
            prize = "💎 Джекпот 350 Алиби"
        elif roll == "shield_mute":
            db.add_item(chat_id, user_id, "shield_mute", 1)
            prize = "🛡 Щит от мута"
        elif roll == "shield_warn":
            db.add_item(chat_id, user_id, "shield_warn", 1)
            prize = "🛡 Щит от преда"
        else:
            db.add_item(chat_id, user_id, "swear_pass", 1)
            prize = "🤬 Swear pass"
        await cb.message.answer(f"🎁 {_mention(cb.from_user)} открыл(а) тайный подарок и получил(а): <b>{prize}</b>!")
    else:
        db.add_item(chat_id, user_id, item_key, 1)
        await cb.message.answer(
            f"✅ {_mention(cb.from_user)} купил(а) <b>{title}</b>! Предмет добавлен в мешок (<code>мешок</code>)."
        )

    await cb.answer("Покупка совершена!")


@router.message(
    F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}),
    F.text.func(
        lambda t: t is not None
        and any(
            t.strip().lower().startswith(p)
            for p in ("использовать ", "префикс ", "брак", "закрепить", "фейкбан", "глушилка", "заказной мут")
        )
    ),
)
async def use_purchased_items(message: Message):
    if not message.from_user or not message.text:
        return
    raw = message.text.strip()
    low = raw.lower()
    chat_id = message.chat.id
    uid = message.from_user.id

    if low.startswith("префикс "):
        new_pref = raw.split(maxsplit=1).strip()[:24]
        if not db.consume_item(chat_id, uid, "custom_prefix"):
            await message.reply("❌ У вас нет предмета «Кастомный префикс» в мешке.")
            return
        with db._conn() as conn, conn.cursor() as cur:
            cur.execute("UPDATE user_stats SET prefix = %s WHERE chat_id = %s AND user_id = %s;", (new_pref, chat_id, uid))
        await message.reply(f"🏷 Ваш новый префикс установлен: <b>{html.escape(new_pref)}</b>!")
        return

    if low == "закрепить" and message.reply_to_message:
        if not db.consume_item(chat_id, uid, "pin_1h"):
            await message.reply("❌ У вас нет предмета «Закреп на 1 час» в мешке.")
            return
        try:
            await message.bot.pin_chat_message(chat_id, message.reply_to_message.message_id)
            await message.reply("📌 Сообщение закреплено на 1 час!")

            async def _unpin_later():
                await asyncio.sleep(3600)
                try:
                    await message.bot.unpin_chat_message(chat_id, message.reply_to_message.message_id)
                except TelegramBadRequest:
                    pass

            asyncio.create_task(_unpin_later())
        except TelegramBadRequest:
            await message.reply("⚠️ У бота нет права закреплять сообщения.")
        return

    if low == "брак" and message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_message.from_user
        if target.id == uid or target.is_bot:
            return
        if not db.consume_item(chat_id, uid, "wedding_ring"):
            await message.reply("❌ Купите «Обручальное кольцо» в магазине.")
            return
        db.set_partner(chat_id, uid, target.id)
        await message.answer(f"💍 Поздравляем! {_mention(message.from_user)} и {_mention(target)} теперь в браке!")
        return

    if low == "фейкбан" and message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_message.from_user
        if not db.consume_item(chat_id, uid, "fake_ban"):
            await message.reply("❌ У вас нет предмета «Фейк-бан» в мешке.")
            return
        prank_msg = await message.answer(f"⛔ {_mention(target)} навсегда заблокирован(а) в чате за нарушение правил!")

        async def _reveal_prank():
            await asyncio.sleep(20)
            try:
                await prank_msg.edit_text(
                    f"🎭 <b>Шутка!</b> Фейк-бан от {_mention(message.from_user)} — {_mention(target)} остаётся в чате!"
                )
            except TelegramBadRequest:
                pass

        asyncio.create_task(_reveal_prank())
        return

    if low == "заказной мут" and message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_message.from_user
        if not db.consume_item(chat_id, uid, "order_mute"):
            await message.reply("❌ У вас нет предмета «Заказной мут» в мешке.")
            return
        try:
            until = datetime.now(timezone.utc) + timedelta(minutes=10)
            await message.bot.restrict_chat_member(
                chat_id, target.id, permissions=ChatPermissions(can_send_messages=False), until_date=until
            )
            await message.answer(f"🔇 {_mention(message.from_user)} использовал(а) заказной мут на {_mention(target)} (10 мин)!")
        except TelegramBadRequest:
            await message.reply("⚠️ Не удалось выдать мут (возможно, цель — администратор).")
        return

    if low == "глушилка" and message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_message.from_user
        if not db.consume_item(chat_id, uid, "silencer_1h"):
            await message.reply("❌ У вас нет предмета «Глушилка» в мешке.")
            return
        try:
            until = datetime.now(timezone.utc) + timedelta(hours=1)
            await message.bot.restrict_chat_member(
                chat_id,
                target.id,
                permissions=ChatPermissions(
                    can_send_messages=True,
                    can_send_voice_notes=False,
                    can_send_other_messages=False,
                ),
                until_date=until,
            )
            await message.answer(
                f"🤐 {_mention(message.from_user)} повесил(а) глушилку на {_mention(target)} — стикеры и голосовые отключены на 1 час!"
            )
        except TelegramBadRequest:
            await message.reply("⚠️ Не удалось применить глушилку.")
