"""Автомодерация (вкл/выкл через /settings). ВАЖНО: этот роутер подключается ПОСЛЕДНИМ."""
import re
import time
from collections import defaultdict, deque

from aiogram import F, Router
from aiogram.types import Message

import config
import db
from profanity import has_bad_word
from utils import is_admin_msg, punish

router = Router()
router.message.filter(F.chat.type.in_({"group", "supergroup"}))
router.edited_message.filter(F.chat.type.in_({"group", "supergroup"}))

LINK_RE = re.compile(r"(?:https?://)?(?:t|telegram)\.(?:me|dog)/(\+?[A-Za-z0-9_]+)", re.I)
CHAR_RUN_RE = re.compile(r"(.)\1{14,}")

_media = defaultdict(deque)
_rate = defaultdict(deque)
_texts = defaultdict(lambda: deque(maxlen=config.REPEAT_COUNT))


def has_ad(m: Message, text: str) -> bool:
    urls = [text]
    for ent in (m.entities or []) + (m.caption_entities or []):
        if ent.type == "text_link" and ent.url:
            urls.append(ent.url)
    for chunk in urls:
        for mt in LINK_RE.finditer(chunk):
            handle = mt.group(1).lower()
            if handle.startswith("+") or handle not in config.ALLOWED_LINKS:
                return True
    return False


def _trim(dq: deque, now: float, window: float):
    while dq and now - dq[0] > window:
        dq.popleft()


def detect(m: Message, text: str, edited: bool, enabled: set) -> str | None:
    key = (m.chat.id, m.from_user.id)
    now = time.time()

    if m.via_bot and "inline" in enabled:
        return "inline"

    if "spam" in enabled and not edited and (m.sticker or m.animation):
        dq = _media[key]
        dq.append(now)
        _trim(dq, now, config.SPAM_WINDOW)
        if len(dq) >= config.SPAM_COUNT:
            dq.clear()
            return "spam"

    if "ad" in enabled and has_ad(m, text):
        return "ad"

    if "mat" in enabled and text and has_bad_word(text):
        return "mat"

    if "flood" in enabled and not edited:
        dq = _rate[key]
        dq.append(now)
        _trim(dq, now, config.FLOOD_WINDOW)
        if len(dq) >= config.FLOOD_COUNT:
            dq.clear()
            return "flood"
        if text:
            if CHAR_RUN_RE.search(text):
                return "flood"
            _texts[key].append((now, text.strip().lower()))
            hist = _texts[key]
            if len(hist) == config.REPEAT_COUNT and len({t for _, t in hist}) == 1 and now - hist[0][0] < 60:
                hist.clear()
                return "flood"
    return None


async def _delete(m: Message):
    try:
        await m.delete()
    except Exception:
        pass


async def check(m: Message, edited: bool):
    if not m.from_user or m.from_user.is_bot or m.sender_chat:
        return
    if m.new_chat_members or m.left_chat_member or m.pinned_message:
        return
    text = m.text or m.caption or ""
    enabled = {k for k in config.FILTER_LABELS if db.filter_on(m.chat.id, k)}
    kind = detect(m, text, edited, enabled)
    if not kind or await is_admin_msg(m):
        return

    u, chat = m.from_user, m.chat.id
    if kind == "inline":
        await _delete(m)
        await punish(chat, u, "использование инлайн-ботов (п. 11)", mute_seconds=86400)
    elif kind == "spam":
        await punish(chat, u, "спам стикерами/гифками (п. 1)", mute_seconds=86400)
    elif kind == "ad":
        await _delete(m)
        await punish(chat, u, "реклама (п. 6)", mute_seconds=7 * 86400)
    elif kind == "mat":
        await _delete(m)
        repeat = time.time() - db.get_last_mat(chat, u.id) < 86400
        db.set_last_mat(chat, u.id)
        if repeat:
            await punish(chat, u, "продолжение использования мата (п. 9)", mute_seconds=86400)
        else:
            await punish(chat, u, "использование мата (п. 9)")
    elif kind == "flood":
        await _delete(m)
        await punish(chat, u, "флуд (п. 2)", mute_seconds=12 * 3600, warn=False)


@router.message()
async def on_message(m: Message):
    await check(m, edited=False)


@router.edited_message()
async def on_edited(m: Message):
    await check(m, edited=True)
