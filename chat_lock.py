"""Команды -чат и +чат как в Ирисе: закрытие и открытие общения в группе."""
from aiogram import F, Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import ChatPermissions, Message

router = Router()

_ADMINS = {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}

_LOCKED_PERMISSIONS = ChatPermissions(
    can_send_messages=False,
    can_send_audios=False,
    can_send_documents=False,
    can_send_photos=False,
    can_send_videos=False,
    can_send_video_notes=False,
    can_send_voice_notes=False,
    can_send_polls=False,
    can_send_other_messages=False,
    can_add_web_page_previews=False,
)

_UNLOCKED_PERMISSIONS = ChatPermissions(
    can_send_messages=True,
    can_send_audios=True,
    can_send_documents=True,
    can_send_photos=True,
    can_send_videos=True,
    can_send_video_notes=True,
    can_send_voice_notes=True,
    can_send_polls=True,
    can_send_other_messages=True,
    can_add_web_page_previews=True,
)


async def _is_admin(message: Message) -> bool:
    if not message.from_user:
        return False
    if message.sender_chat and message.sender_chat.id == message.chat.id:
        return True
    member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
    return member.status in _ADMINS


@router.message(
    F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}),
    F.text.func(lambda t: t is not None and t.strip().lower() in {"-чат", "!чат стоп", "/lock"}),
)
async def close_chat(message: Message):
    if not await _is_admin(message):
        return
    try:
        await message.bot.set_chat_permissions(
            chat_id=message.chat.id,
            permissions=_LOCKED_PERMISSIONS,
        )
        await message.answer("🔒 <b>Чат закрыт.</b> Писать в чат теперь могут только администраторы.")
    except TelegramBadRequest as e:
        await message.answer(f"⚠️ Не удалось закрыть чат (проверьте право бота «Блокировка пользователей»): {e.message}")


@router.message(
    F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}),
    F.text.func(lambda t: t is not None and t.strip().lower() in {"+чат", "!чат старт", "/unlock"}),
)
async def open_chat(message: Message):
    if not await _is_admin(message):
        return
    try:
        await message.bot.set_chat_permissions(
            chat_id=message.chat.id,
            permissions=_UNLOCKED_PERMISSIONS,
        )
        await message.answer("🔓 <b>Чат открыт.</b> Участники снова могут отправлять сообщения.")
    except TelegramBadRequest as e:
        await message.answer(f"⚠️ Не удалось открыть чат: {e.message}")
