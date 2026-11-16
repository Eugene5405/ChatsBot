"""Telegram Mini App (Web App) для управления чатами бота."""
import hashlib
import hmac
import html
import json
import logging
import os
from urllib.parse import parse_qsl

from aiohttp import web
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

import config
import db
import rules
from loader import bot

_ACTIVE_BOT = {ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}
_ADMIN_USER = {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}


def _verify_init_data(init_data: str) -> dict | None:
    if not init_data:
        return None
    try:
        parsed = dict(parse_qsl(init_data, strict_parsing=True))
    except ValueError:
        return None

    received_hash = parsed.pop("hash", None)
    if not received_hash:
        return None

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", config.BOT_TOKEN.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        return None

    user_raw = parsed.get("user")
    if not user_raw:
        return None
    try:
        return json.loads(user_raw)
    except json.JSONDecodeError:
        return None


def _ensure_tables():
    db._db.execute("""CREATE TABLE IF NOT EXISTS user_chats (
        user_id BIGINT,
        chat_id BIGINT,
        chat_title TEXT,
        PRIMARY KEY (user_id, chat_id)
    )""")


async def _is_bot_in_chat(chat_id: int) -> bool:
    try:
        me = await bot.get_me()
        member = await bot.get_chat_member(chat_id, me.id)
        return member.status in _ACTIVE_BOT
    except (TelegramBadRequest, TelegramForbiddenError):
        return False
    except Exception as e:
        logging.warning("Ошибка проверки бота в чате %s: %s", chat_id, e)
        return False


async def _is_user_admin(chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in _ADMIN_USER
    except Exception:
        return False


async def api_chats(request: web.Request) -> web.Response:
    _ensure_tables()
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

    user = _verify_init_data(body.get("initData", ""))
    if not user:
        return web.json_response({"ok": False, "error": "Откройте приложение внутри Telegram"}, status=401)

    user_id = int(user["id"])
    rows = db._db.execute("SELECT chat_id, chat_title FROM user_chats WHERE user_id=%s", (user_id,)).fetchall()

    valid_chats = []
    for row in rows:
        chat_id = row[0] if isinstance(row, (tuple, list)) else row["chat_id"]
        saved_title = row[1] if isinstance(row, (tuple, list)) else row["chat_title"]

        if not await _is_bot_in_chat(chat_id):
            db._db.execute("DELETE FROM user_chats WHERE chat_id=%s", (chat_id,))
            continue

        if not await _is_user_admin(chat_id, user_id):
            db._db.execute("DELETE FROM user_chats WHERE user_id=%s AND chat_id=%s", (user_id, chat_id))
            continue

        try:
            chat_obj = await bot.get_chat(chat_id)
            actual_title = chat_obj.title or saved_title or f"Чат {chat_id}"
            if actual_title != saved_title:
                db._db.execute(
                    "UPDATE user_chats SET chat_title=%s WHERE user_id=%s AND chat_id=%s",
                    (actual_title, user_id, chat_id),
                )
        except Exception:
            actual_title = saved_title or f"Чат {chat_id}"

        filters = {k: db.filter_on(chat_id, k) for k in config.FILTER_DEFAULTS}
        valid_chats.append({
            "chat_id": chat_id,
            "title": actual_title,
            "rules": rules.get_rules(chat_id),
            "welcome": db.get_setting(chat_id, "welcome_text") or "",
            "goodbye": db.get_setting(chat_id, "goodbye_text") or "",
            "filters": filters,
        })

    me = await bot.get_me()
    return web.json_response({
        "ok": True,
        "bot_username": me.username,
        "chats": valid_chats,
    })


async def api_save(request: web.Request) -> web.Response:
    _ensure_tables()
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

    user = _verify_init_data(body.get("initData", ""))
    if not user:
        return web.json_response({"ok": False, "error": "Ошибка авторизации Telegram"}, status=401)

    user_id = int(user["id"])
    chat_id = int(body.get("chat_id", 0))

    if not await _is_bot_in_chat(chat_id):
        db._db.execute("DELETE FROM user_chats WHERE chat_id=%s", (chat_id,))
        return web.json_response({"ok": False, "error": "Бот уже удалён из этого чата"}, status=404)

    if not await _is_user_admin(chat_id, user_id):
        return web.json_response({"ok": False, "error": "У вас нет прав администратора в этом чате"}, status=403)

    if "rules" in body:
        val = (body["rules"] or "").strip()
        db.set_setting(chat_id, "rules", val if val else None)

    if "welcome" in body:
        val = (body["welcome"] or "").strip()
        db.set_setting(chat_id, "welcome_text", val if val else None)

    if "goodbye" in body:
        val = (body["goodbye"] or "").strip()
        db.set_setting(chat_id, "goodbye_text", val if val else None)

    if "filters" in body and isinstance(body["filters"], dict):
        for k, v in body["filters"].items():
            if k in config.FILTER_DEFAULTS:
                db.set_setting(chat_id, "f_" + k, "1" if v else "0")

    return web.json_response({"ok": True})


HTML_PAGE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Хранитель чата — Панель</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
  :root {
    --bg: var(--tg-theme-bg-color, #18181b);
    --sec-bg: var(--tg-theme-secondary-bg-color, #27272a);
    --text: var(--tg-theme-text-color, #f4f4f5);
    --hint: var(--tg-theme-hint-color, #a1a1aa);
    --btn: var(--tg-theme-button-color, #3b82f6);
    --btn-text: var(--tg-theme-button-text-color, #ffffff);
  }
  * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
  body { background: var(--bg); color: var(--text); padding: 16px 16px 84px; }
  .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
  .header h1 { font-size: 20px; font-weight: 700; display: flex; align-items: center; gap: 8px; }
  .badge { background: rgba(34,197,94,0.18); color: #22c55e; font-size: 12px; padding: 4px 10px; border-radius: 20px; font-weight: 600; }
  .stats { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 16px; }
  .stat-card { background: var(--sec-bg); padding: 14px; border-radius: 14px; }
  .stat-val { font-size: 22px; font-weight: 700; color: var(--btn); }
  .stat-lbl { font-size: 12px; color: var(--hint); margin-top: 2px; }
  .card { background: var(--sec-bg); border-radius: 16px; padding: 16px; margin-bottom: 12px; }
  .card h2 { font-size: 16px; margin-bottom: 8px; }
  .card p { font-size: 13px; color: var(--hint); line-height: 1.45; margin-bottom: 12px; }
  .btn { width: 100%; border: none; border-radius: 12px; padding: 13px; font-size: 15px; font-weight: 600; cursor: pointer; background: var(--btn); color: var(--btn-text); display: inline-flex; justify-content: center; align-items: center; gap: 8px; text-decoration: none; }
  .btn-sec { background: rgba(255,255,255,0.08); color: var(--text); margin-top: 8px; }
  .chat-item { display: flex; justify-content: space-between; align-items: center; padding: 14px; background: var(--sec-bg); border-radius: 14px; margin-bottom: 10px; cursor: pointer; }
  .chat-title { font-weight: 600; font-size: 15px; }
  .chat-sub { font-size: 12px; color: var(--hint); margin-top: 3px; }
  label { display: block; font-size: 13px; font-weight: 600; margin: 12px 0 6px; color: var(--hint); }
  textarea { width: 100%; min-height: 88px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.1); background: var(--bg); color: var(--text); padding: 10px; font-size: 14px; resize: vertical; }
  .toggle-row { display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid rgba(255,255,255,0.06); }
  .toggle-row:last-child { border-bottom: none; }
  input[type="checkbox"] { width: 20px; height: 20px; accent-color: var(--btn); }
  .nav { position: fixed; bottom: 0; left: 0; right: 0; background: var(--sec-bg); display: flex; border-top: 1px solid rgba(255,255,255,0.08); padding: 8px 0; }
  .nav-btn { flex: 1; background: none; border: none; color: var(--hint); font-size: 12px; display: flex; flex-direction: column; align-items: center; gap: 4px; cursor: pointer; }
  .nav-btn.active { color: var(--btn); font-weight: 600; }
  .hidden { display: none !important; }
  .toast { position: fixed; top: 14px; left: 16px; right: 16px; background: #22c55e; color: #fff; padding: 12px; border-radius: 12px; text-align: center; font-weight: 600; font-size: 14px; z-index: 99; }
</style>
</head>
<body>
  <div id="toast" class="toast hidden">Сохранено!</div>

  <div class="header">
    <h1>🛡️ Хранитель чата</h1>
    <span class="badge">24/7 Online</span>
  </div>

  <div class="stats">
    <div class="stat-card">
      <div class="stat-val" id="chatCount">0</div>
      <div class="stat-lbl">Подключённых чатов</div>
    </div>
    <div class="stat-card">
      <div class="stat-val" style="color:#22c55e;">Активна</div>
      <div class="stat-lbl">Защита от спама</div>
    </div>
  </div>

  <div id="tabChats">
    <div id="chatsList"><div class="card"><p>Проверяю ваши чаты...</p></div></div>
  </div>

  <div id="tabEdit" class="hidden">
    <button class="btn btn-sec" onclick="backToList()" style="margin-bottom:12px;">← Назад к списку чатов</button>
    <div class="card">
      <h2 id="editTitle">Настройки чата</h2>
      <label>📜 Правила чата</label>
      <textarea id="editRules" placeholder="Введите правила..."></textarea>

      <label>👋 Приветствие (можно {user} и {chat})</label>
      <textarea id="editWelcome" placeholder="Оставьте пустым для стандартного приветствия"></textarea>

      <label>🚪 Прощание при выходе (можно {user})</label>
      <textarea id="editGoodbye" placeholder="Оставьте пустым для стандартного прощания"></textarea>

      <label>🛡️ Фильтры защиты</label>
      <div id="filtersBox"></div>

      <button class="btn" style="margin-top:16px;" onclick="saveChat()">💾 Сохранить изменения</button>
    </div>
  </div>

  <div id="tabConnect" class="hidden">
    <div class="card">
      <h2>➕ Подключение новой группы</h2>
      <p>1. Нажмите кнопку ниже и выберите группу.<br>2. Выдайте боту права администратора.<br>3. Чат автоматически появится во вкладке «Мои чаты».</p>
      <a id="addBotLink" class="btn" href="#" target="_blank">➕ Добавить бота в чат</a>
    </div>
  </div>

  <div class="nav">
    <button class="nav-btn active" id="navChats" onclick="switchTab('chats')">💬<span>Мои чаты</span></button>
    <button class="nav-btn" id="navConnect" onclick="switchTab('connect')">➕<span>Подключение</span></button>
  </div>

<script>
  const tg = window.Telegram.WebApp;
  tg.ready();
  tg.expand();

  let chatsData = [];
  let currentChat = null;

  const filterNames = {
    mat: "Антимат",
    ads: "Блокировка ссылок и рекламы",
    flood: "Антифлуд",
    stickers: "Защита от спама стикерами",
    inline: "Запрет инлайн-ботов"
  };

  function showToast(msg, isErr) {
    const t = document.getElementById("toast");
    t.textContent = msg;
    t.style.background = isErr ? "#ef4444" : "#22c55e";
    t.classList.remove("hidden");
    setTimeout(() => t.classList.add("hidden"), 2500);
  }

  function switchTab(tab) {
    document.getElementById("tabChats").classList.toggle("hidden", tab !== "chats");
    document.getElementById("tabConnect").classList.toggle("hidden", tab !== "connect");
    document.getElementById("tabEdit").classList.add("hidden");
    document.getElementById("navChats").classList.toggle("active", tab === "chats");
    document.getElementById("navConnect").classList.toggle("active", tab === "connect");
    if (tab === "chats") loadChats();
  }

  async function loadChats() {
    const box = document.getElementById("chatsList");
    try {
      const res = await fetch("/api/chats", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ initData: tg.initData || "" })
      });
      const data = await res.json();
      if (!data.ok) {
        box.innerHTML = `<div class="card"><h2>⚠️ Внимание</h2><p>${data.error || "Ошибка загрузки"}</p></div>`;
        return;
      }
      if (data.bot_username) {
        document.getElementById("addBotLink").href =
          `https://t.me/${data.bot_username}?startgroup=true&admin=change_info+delete_messages+restrict_members+invite_users+pin_messages`;
      }
      chatsData = data.chats || [];
      document.getElementById("chatCount").textContent = chatsData.length;

      if (!chatsData.length) {
        box.innerHTML = `<div class="card"><h2>Чатов пока нет</h2><p>Нажмите кнопку ниже, чтобы добавить бота в группу и выдать ему права администратора.</p><button class="btn" onclick="switchTab('connect')">➕ Добавить бота в чат</button></div>`;
        return;
      }

      box.innerHTML = "";
      chatsData.forEach((c, idx) => {
        const div = document.createElement("div");
        div.className = "chat-item";
        div.innerHTML = `<div><div class="chat-title">${c.title}</div><div class="chat-sub">ID: ${c.chat_id} • Нажмите для настройки</div></div><div>⚙️</div>`;
        div.onclick = () => openEditor(idx);
        box.appendChild(div);
      });
    } catch (e) {
      box.innerHTML = `<div class="card"><p>Ошибка соединения: ${e.message}</p></div>`;
    }
  }

  function openEditor(idx) {
    currentChat = chatsData[idx];
    document.getElementById("tabChats").classList.add("hidden");
    document.getElementById("tabEdit").classList.remove("hidden");
    document.getElementById("editTitle").textContent = currentChat.title;
    document.getElementById("editRules").value = currentChat.rules || "";
    document.getElementById("editWelcome").value = currentChat.welcome || "";
    document.getElementById("editGoodbye").value = currentChat.goodbye || "";

    const fBox = document.getElementById("filtersBox");
    fBox.innerHTML = "";
    Object.keys(currentChat.filters || {}).forEach(k => {
      const row = document.createElement("div");
      row.className = "toggle-row";
      row.innerHTML = `<span>${filterNames[k] || k}</span><input type="checkbox" id="flt_${k}" ${currentChat.filters[k] ? "checked" : ""}>`;
      fBox.appendChild(row);
    });
  }

  function backToList() {
    document.getElementById("tabEdit").classList.add("hidden");
    document.getElementById("tabChats").classList.remove("hidden");
    loadChats();
  }

  async function saveChat() {
    if (!currentChat) return;
    const filters = {};
    Object.keys(currentChat.filters || {}).forEach(k => {
      const el = document.getElementById("flt_" + k);
      if (el) filters[k] = el.checked;
    });

    try {
      const res = await fetch("/api/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          initData: tg.initData || "",
          chat_id: currentChat.chat_id,
          rules: document.getElementById("editRules").value,
          welcome: document.getElementById("editWelcome").value,
          goodbye: document.getElementById("editGoodbye").value,
          filters: filters
        })
      });
      const data = await res.json();
      if (data.ok) {
        showToast("✅ Настройки сохранены!");
      } else {
        showToast(data.error || "Ошибка сохранения", true);
      }
    } catch (e) {
      showToast("Ошибка сети", true);
    }
  }

  loadChats();
</script>
</body>
</html>
"""


async def serve_webapp(request: web.Request) -> web.Response:
    return web.Response(text=HTML_PAGE, content_type="text/html")


def setup_routes(app: web.Application):
    app.router.add_get("/webapp", serve_webapp)
    app.router.add_post("/api/chats", api_chats)
    app.router.add_post("/api/save", api_save)
