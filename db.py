"""Работа с PostgreSQL (Neon): единая база для админ-панели, модерации и настроек."""
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
                bans INT NOT NULL DEFAULT 0,
                last_reason TEXT,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (chat_id, user_id)
            );
        """)
        cur.execute("""
            ALTER TABLE warns ADD COLUMN IF NOT EXISTS bans INT NOT NULL DEFAULT 0;
        """)
        cur.execute("""
            ALTER TABLE warns ADD COLUMN IF NOT EXISTS last_reason TEXT;
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS chat_kv (
                chat_id BIGINT NOT NULL,
                key TEXT NOT NULL,
                value TEXT,
                PRIMARY KEY (chat_id, key)
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
        "rules": get_setting(chat_id, "rules") or "",
    }
    if not DATABASE_URL:
        return default
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT profanity, antispam, antilink, subcheck, welcome
            FROM chats WHERE chat_id = %s;
        """, (chat_id,))
        row = cur.fetchone()
        if row:
            default.update({
                "profanity": bool(row[0]),
                "antispam": bool(row[1]),
                "antilink": bool(row[2]),
                "subcheck": bool(row[3]),
                "welcome": bool(row[4]),
            })
        return default


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
    if "rules" in data and data["rules"] is not None:
        raw_rules = str(data["rules"]).strip()
        if raw_rules:
            if "<blockquote" not in raw_rules:
                raw_rules = f"<blockquote expandable>{raw_rules}</blockquote>"
            set_setting(chat_id, "rules", raw_rules)
        else:
            set_setting(chat_id, "rules", None)


# --- Совместимость со старыми модулями (admin.py, moderation.py, automod.py, info.py) ---

_KIND_TO_COL = {
    "profanity": "profanity",
    "badwords": "profanity",
    "mat": "profanity",
    "spam": "antispam",
    "antispam": "antispam",
    "flood": "antispam",
    "links": "antilink",
    "antilink": "antilink",
    "ads": "antilink",
    "sub": "subcheck",
    "subcheck": "subcheck",
    "welcome": "welcome",
}


def get_setting(chat_id: int, key: str) -> str | None:
    if not DATABASE_URL:
        return None
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT value FROM chat_kv WHERE chat_id = %s AND key = %s;", (chat_id, key))
        row = cur.fetchone()
        return row[0] if row else None


def set_setting(chat_id: int, key: str, value: str | None) -> None:
    if not DATABASE_URL:
        return
    with _conn() as conn, conn.cursor() as cur:
        if value is None:
            cur.execute("DELETE FROM chat_kv WHERE chat_id = %s AND key = %s;", (chat_id, key))
        else:
            cur.execute("""
                INSERT INTO chat_kv (chat_id, key, value)
                VALUES (%s, %s, %s)
                ON CONFLICT (chat_id, key) DO UPDATE SET value = EXCLUDED.value;
            """, (chat_id, key, str(value)))

    if key.startswith("f_"):
        kind = key[2:]
        col = _KIND_TO_COL.get(kind)
        if col:
            flag = str(value) in ("1", "true", "True")
            with _conn() as conn, conn.cursor() as cur:
                cur.execute(f"""
                    INSERT INTO chats (chat_id, {col})
                    VALUES (%s, %s)
                    ON CONFLICT (chat_id) DO UPDATE SET {col} = EXCLUDED.{col}, updated_at = NOW();
                """, (chat_id, flag))


def filter_on(chat_id: int, kind: str) -> bool:
    col = _KIND_TO_COL.get(kind)
    if col and DATABASE_URL:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {col} FROM chats WHERE chat_id = %s;", (chat_id,))
            row = cur.fetchone()
            if row is not None:
                return bool(row[0])
    val = get_setting(chat_id, "f_" + kind)
    if val is not None:
        return val == "1"
    return True


def add_warn(chat_id: int, user_id: int, reason: str = "", admin_id: int = 0) -> tuple[int, int]:
    if not DATABASE_URL:
        return 1, 0
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT count, bans FROM warns WHERE chat_id = %s AND user_id = %s;", (chat_id, user_id))
        row = cur.fetchone()
        count = (row[0] if row else 0) + 1
        bans = row[1] if row else 0
        if count >= 3:
            count = 0
            bans += 1
        cur.execute("""
            INSERT INTO warns (chat_id, user_id, count, bans, last_reason, updated_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            ON CONFLICT (chat_id, user_id) DO UPDATE SET
                count = EXCLUDED.count,
                bans = EXCLUDED.bans,
                last_reason = EXCLUDED.last_reason,
                updated_at = NOW();
        """, (chat_id, user_id, count, bans, reason))
        return count, bans


def remove_last_warn(chat_id: int, user_id: int) -> int:
    if not DATABASE_URL:
        return 0
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT count FROM warns WHERE chat_id = %s AND user_id = %s;", (chat_id, user_id))
        row = cur.fetchone()
        count = max(0, (row[0] if row else 0) - 1)
        cur.execute("""
            INSERT INTO warns (chat_id, user_id, count, updated_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (chat_id, user_id) DO UPDATE SET
                count = EXCLUDED.count,
                updated_at = NOW();
        """, (chat_id, user_id, count))
        return count


def get_warns(chat_id: int, user_id: int) -> tuple[int, int]:
    if not DATABASE_URL:
        return 0, 0
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT count, bans FROM warns WHERE chat_id = %s AND user_id = %s;", (chat_id, user_id))
        row = cur.fetchone()
        return (row[0], row[1]) if row else (0, 0)
