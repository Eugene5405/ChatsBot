"""PostgreSQL: предупреждения, счётчик банов, время последнего мата."""
import os
import time
import psycopg

import config

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    raise SystemExit("Не задан DATABASE_URL для подключения к облачной базе данных.")

_db = psycopg.connect(DATABASE_URL, autocommit=True)
_db.execute("""CREATE TABLE IF NOT EXISTS warnings (
    id SERIAL PRIMARY KEY, chat_id BIGINT, user_id BIGINT, ts BIGINT, reason TEXT, moderator_id BIGINT)""")
_db.execute("CREATE TABLE IF NOT EXISTS bans (chat_id BIGINT, user_id BIGINT, count INT, PRIMARY KEY(chat_id,user_id))")
_db.execute("CREATE TABLE IF NOT EXISTS mat_log (chat_id BIGINT, user_id BIGINT, ts BIGINT, PRIMARY KEY(chat_id,user_id))")
_db.execute("CREATE TABLE IF NOT EXISTS settings (chat_id BIGINT, key TEXT, value TEXT, PRIMARY KEY(chat_id,key))")

TTL = config.WARN_TTL_DAYS * 86400


def _purge():
    _db.execute("DELETE FROM warnings WHERE ts < %s", (int(time.time()) - TTL,))


def active_warns(chat_id: int, user_id: int) -> int:
    _purge()
    row = _db.execute("SELECT COUNT(*) FROM warnings WHERE chat_id=%s AND user_id=%s", (chat_id, user_id)).fetchone()
    return row[0] if row else 0


def list_warns(chat_id: int, user_id: int) -> list[tuple[int, str]]:
    _purge()
    return _db.execute("SELECT ts, reason FROM warnings WHERE chat_id=%s AND user_id=%s ORDER BY ts",
                       (chat_id, user_id)).fetchall()


def add_warn(chat_id: int, user_id: int, reason: str = "", moderator_id: int = 0) -> tuple[int, int]:
    _db.execute("INSERT INTO warnings (chat_id,user_id,ts,reason,moderator_id) VALUES (%s,%s,%s,%s,%s)",
                (chat_id, user_id, int(time.time()), reason, moderator_id))
    count = active_warns(chat_id, user_id)
    row = _db.execute("SELECT count FROM bans WHERE chat_id=%s AND user_id=%s", (chat_id, user_id)).fetchone()
    bans = row[0] if row else 0
    if count >= 3:
        bans += 1
        _db.execute("DELETE FROM warnings WHERE chat_id=%s AND user_id=%s", (chat_id, user_id))
        _db.execute("INSERT INTO bans (chat_id, user_id, count) VALUES (%s,%s,%s) "
                    "ON CONFLICT (chat_id, user_id) DO UPDATE SET count = EXCLUDED.count", (chat_id, user_id, bans))
        return 0, bans
    return count, bans


def remove_last_warn(chat_id: int, user_id: int) -> int:
    _purge()
    _db.execute("DELETE FROM warnings WHERE id = (SELECT id FROM warnings WHERE chat_id=%s AND user_id=%s "
                "ORDER BY ts DESC, id DESC LIMIT 1)", (chat_id, user_id))
    return active_warns(chat_id, user_id)


def get_last_mat(chat_id: int, user_id: int) -> int:
    row = _db.execute("SELECT ts FROM mat_log WHERE chat_id=%s AND user_id=%s", (chat_id, user_id)).fetchone()
    return row[0] if row else 0


def set_last_mat(chat_id: int, user_id: int):
    _db.execute("INSERT INTO mat_log (chat_id, user_id, ts) VALUES (%s,%s,%s) "
                "ON CONFLICT (chat_id, user_id) DO UPDATE SET ts = EXCLUDED.ts", (chat_id, user_id, int(time.time())))


# ---------- Настройки чата (правила, включённые фильтры) ----------
_cache: dict[tuple[int, str], str | None] = {}


def get_setting(chat_id: int, key: str) -> str | None:
    k = (chat_id, key)
    if k not in _cache:
        row = _db.execute("SELECT value FROM settings WHERE chat_id=%s AND key=%s", k).fetchone()
        _cache[k] = row[0] if row else None
    return _cache[k]


def set_setting(chat_id: int, key: str, value: str | None):
    if value is None:
        _db.execute("DELETE FROM settings WHERE chat_id=%s AND key=%s", (chat_id, key))
    else:
        _db.execute("INSERT INTO settings (chat_id, key, value) VALUES (%s,%s,%s) "
                    "ON CONFLICT (chat_id, key) DO UPDATE SET value = EXCLUDED.value", (chat_id, key, value))
    _cache[(chat_id, key)] = value


def filter_on(chat_id: int, kind: str) -> bool:
    v = get_setting(chat_id, "f_" + kind)
    return config.FILTER_DEFAULTS[kind] if v is None else v == "1"
