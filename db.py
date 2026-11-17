import os
from contextlib import contextmanager
import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.getenv("DATABASE_URL", "")


@contextmanager
def get_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set")
    conn = psycopg.connect(DATABASE_URL, row_factory=dict_row, autocommit=True)
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chats (
                    chat_id BIGINT PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT 'Без названия',
                    profanity BOOLEAN NOT NULL DEFAULT TRUE,
                    antispam BOOLEAN NOT NULL DEFAULT TRUE,
                    antilink BOOLEAN NOT NULL DEFAULT TRUE,
                    subcheck BOOLEAN NOT NULL DEFAULT TRUE,
                    welcome BOOLEAN NOT NULL DEFAULT TRUE,
                    rules_text TEXT NOT NULL DEFAULT 'Соблюдайте порядок, не спамьте и уважайте участников.'
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS warnings (
                    chat_id BIGINT NOT NULL,
                    user_id BIGINT NOT NULL,
                    count INT NOT NULL DEFAULT 0,
                    PRIMARY KEY (chat_id, user_id)
                );
            """)


def register_chat(chat_id: int, title: str):
    if chat_id >= 0:
        return
    clean_title = title or "Группа"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO chats (chat_id, title)
                VALUES (%s, %s)
                ON CONFLICT (chat_id) DO UPDATE SET title = EXCLUDED.title;
            """, (chat_id, clean_title))


def get_all_chats() -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM chats ORDER BY title ASC;")
            return cur.fetchall()


def get_chat_settings(chat_id: int) -> dict:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM chats WHERE chat_id = %s;", (chat_id,))
            row = cur.fetchone()
            if row:
                return row
    return {
        "chat_id": chat_id,
        "title": "Группа",
        "profanity": True,
        "antispam": True,
        "antilink": True,
        "subcheck": True,
        "welcome": True,
        "rules_text": "Соблюдайте порядок, не спамьте и уважайте участников."
    }


def update_chat_settings(chat_id: int, data: dict):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE chats
                SET profanity = %s,
                    antispam = %s,
                    antilink = %s,
                    subcheck = %s,
                    welcome = %s
                WHERE chat_id = %s;
            """, (
                bool(data.get("profanity", True)),
                bool(data.get("antispam", True)),
                bool(data.get("antilink", True)),
                bool(data.get("subcheck", True)),
                bool(data.get("welcome", True)),
                chat_id,
            ))


def get_rules(chat_id: int) -> str:
    return get_chat_settings(chat_id).get("rules_text", "Соблюдайте правила чата.")


def set_rules(chat_id: int, text: str):
    register_chat(chat_id, "Группа")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE chats SET rules_text = %s WHERE chat_id = %s;", (text, chat_id))


def add_warn(chat_id: int, user_id: int) -> int:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO warnings (chat_id, user_id, count)
                VALUES (%s, %s, 1)
                ON CONFLICT (chat_id, user_id)
                DO UPDATE SET count = warnings.count + 1
                RETURNING count;
            """, (chat_id, user_id))
            return cur.fetchone()["count"]


def reset_warns(chat_id: int, user_id: int):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM warnings WHERE chat_id = %s AND user_id = %s;", (chat_id, user_id))
