"""Работа с PostgreSQL (Neon): чаты, настройки, варны (30 дн.), экономика, репутация и РП."""
import json
import os
import psycopg

DATABASE_URL = os.getenv("DATABASE_URL", "")


def _conn():
    return psycopg.connect(DATABASE_URL, autocommit=True)


def init_db() -> None:
    if not DATABASE_URL:
        return
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                chat_id BIGINT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT 'Чат',
                profanity BOOLEAN NOT NULL DEFAULT TRUE,
                antispam BOOLEAN NOT NULL DEFAULT TRUE,
                antilink BOOLEAN NOT NULL DEFAULT TRUE,
                subcheck BOOLEAN NOT NULL DEFAULT TRUE,
                welcome BOOLEAN NOT NULL DEFAULT TRUE,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """)
        for col_sql in (
            "ALTER TABLE chats ADD COLUMN IF NOT EXISTS title TEXT NOT NULL DEFAULT 'Чат';",
            "ALTER TABLE chats ADD COLUMN IF NOT EXISTS profanity BOOLEAN NOT NULL DEFAULT TRUE;",
            "ALTER TABLE chats ADD COLUMN IF NOT EXISTS antispam BOOLEAN NOT NULL DEFAULT TRUE;",
            "ALTER TABLE chats ADD COLUMN IF NOT EXISTS antilink BOOLEAN NOT NULL DEFAULT TRUE;",
            "ALTER TABLE chats ADD COLUMN IF NOT EXISTS subcheck BOOLEAN NOT NULL DEFAULT TRUE;",
            "ALTER TABLE chats ADD COLUMN IF NOT EXISTS welcome BOOLEAN NOT NULL DEFAULT TRUE;",
            "ALTER TABLE chats ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();",
        ):
            cur.execute(col_sql)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                chat_id BIGINT NOT NULL,
                key TEXT NOT NULL,
                value TEXT,
                PRIMARY KEY (chat_id, key)
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS warns (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                reason TEXT,
                admin_id BIGINT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS warn_bans (
                chat_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                bans INT NOT NULL DEFAULT 0,
                PRIMARY KEY (chat_id, user_id)
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_stats (
                chat_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                balance BIGINT NOT NULL DEFAULT 0,
                reputation INT NOT NULL DEFAULT 0,
                vip_until TIMESTAMPTZ,
                prefix TEXT,
                partner_id BIGINT,
                inventory JSONB NOT NULL DEFAULT '{}'::jsonb,
                PRIMARY KEY (chat_id, user_id)
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS custom_rp (
                chat_id BIGINT NOT NULL,
                trigger TEXT NOT NULL,
                template TEXT NOT NULL,
                PRIMARY KEY (chat_id, trigger)
            );
        """)


def register_chat(chat_id: int, title: str | None) -> None:
    if not DATABASE_URL:
        return
    safe_title = (title or "Чат").strip() or "Чат"
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO chats (chat_id, title, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (chat_id) DO UPDATE SET
                title = EXCLUDED.title,
                updated_at = NOW();
        """, (chat_id, safe_title))


def delete_chat(chat_id: int) -> None:
    if not DATABASE_URL:
        return
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM chats WHERE chat_id = %s;", (chat_id,))


def get_chats() -> list[dict]:
    if not DATABASE_URL:
        return []
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT chat_id, title FROM chats ORDER BY updated_at DESC;")
        return [{"chat_id": str(r[0]), "title": r[1]} for r in cur.fetchall()]


def get_chat_settings(chat_id: int) -> dict:
    default = {
        "profanity": True,
        "antispam": True,
        "antilink": True,
        "subcheck": True,
        "welcome": True,
    }
    if not DATABASE_URL:
        return default
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT profanity, antispam, antilink, subcheck, welcome
            FROM chats WHERE chat_id = %s;
        """, (chat_id,))
        row = cur.fetchone()
        if not row:
            return default
        return {
            "profanity": bool(row[0]),
            "antispam": bool(row[1]),
            "antilink": bool(row[2]),
            "subcheck": bool(row[3]),
            "welcome": bool(row[4]),
        }


def update_chat_settings(chat_id: int, data: dict) -> None:
    if not DATABASE_URL:
        return
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO chats (chat_id, profanity, antispam, antilink, subcheck, welcome, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (chat_id) DO UPDATE SET
                profanity = EXCLUDED.profanity,
                antispam = EXCLUDED.antispam,
                antilink = EXCLUDED.antilink,
                subcheck = EXCLUDED.subcheck,
                welcome = EXCLUDED.welcome,
                updated_at = NOW();
        """, (
            chat_id,
            bool(data.get("profanity", True)),
            bool(data.get("antispam", True)),
            bool(data.get("antilink", True)),
            bool(data.get("subcheck", True)),
            bool(data.get("welcome", True)),
        ))


def filter_on(chat_id: int, kind: str) -> bool:
    settings = get_chat_settings(chat_id)
    if kind in settings:
        return settings[kind]
    val = get_setting(chat_id, "f_" + kind)
    return val != "0"


def set_setting(chat_id: int, key: str, value: str | None) -> None:
    if not DATABASE_URL:
        return
    if key.startswith("f_"):
        kind = key[2:]
        cur_settings = get_chat_settings(chat_id)
        if kind in cur_settings:
            cur_settings[kind] = value != "0"
            update_chat_settings(chat_id, cur_settings)
            return
    with _conn() as conn, conn.cursor() as cur:
        if value is None:
            cur.execute("DELETE FROM settings WHERE chat_id = %s AND key = %s;", (chat_id, key))
        else:
            cur.execute("""
                INSERT INTO settings (chat_id, key, value)
                VALUES (%s, %s, %s)
                ON CONFLICT (chat_id, key) DO UPDATE SET value = EXCLUDED.value;
            """, (chat_id, key, value))


def get_setting(chat_id: int, key: str) -> str | None:
    if not DATABASE_URL:
        return None
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT value FROM settings WHERE chat_id = %s AND key = %s;", (chat_id, key))
        row = cur.fetchone()
        return row[0] if row else None
