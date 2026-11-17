"""Работа с PostgreSQL (Neon): чаты, настройки фильтров и предупреждения."""
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
        cur.execute("""
            CREATE TABLE IF NOT EXISTS warns (
                chat_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                count INT NOT NULL DEFAULT 0,
                PRIMARY KEY (chat_id, user_id)
            );
        """)


def register_chat(chat_id: int, title: str | None) -> None:
    if not DATABASE_URL:
        return
    safe_title = (title or "Чат").strip() or "Чат"
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO chats (chat_id, title)
            VALUES (%s, %s)
            ON CONFLICT (chat_id) DO UPDATE SET
                title = EXCLUDED.title,
                updated_at = NOW();
        """, (chat_id, safe_title))


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
            INSERT INTO chats (chat_id, profanity, antispam, antilink, subcheck, welcome)
            VALUES (%s, %s, %s, %s, %s, %s)
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
