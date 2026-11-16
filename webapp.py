"""Telegram Mini App: полноэкранный интерфейс управления чатами."""
import hashlib
import hmac
import html
import json
from urllib.parse import parse_qsl

from aiohttp import web

import config
import db
import rules
from loader import bot

FILTER_KEYS = ["mat", "stickers", "links", "flood", "inline"]


def _verify_init_data(init_data: str) -> int | None:
    if not init_data:
        return None
    try:
        parsed = dict(parse_qsl(init_data, strict_parsing=True))
        received_hash = parsed.pop("hash", None)
        if not received_hash:
            return None
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
        secret_key = hmac.new(b"WebAppData", config.BOT_TOKEN.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calculated_hash, received_hash):
            return None
        user_obj = json.loads(parsed.get("user", "{}"))
        return int(user_obj["id"])
    except Exception:
        return None


def _get_chats(user_id: int) -> list[dict]:
    raw = db.get_setting(0, f"owner_chats:{user_id}")
    if not raw:
        return []
    try:
        return json.loads(raw)
    except Exception:
        return []


async def handle_index(request: web.Request) -> web.Response:
    me = await bot.get_me()
    bot_username = me.username
    page = HTML_TEMPLATE.replace("__BOT_USERNAME__", bot_username)
    return web.Response(text=page, content_type="text/html")


async def handle_api_chats(request: web.Request) -> web.Response:
    user_id = _verify_init_data(request.headers.get("X-Telegram-Init-Data", ""))
    if not user_id:
        return web.json_response({"error": "unauthorized"}, status=401)
    chats = _get_chats(user_id)
    return web.json_response({"chats": chats})


async def handle_api_chat_detail(request: web.Request) -> web.Response:
    user_id = _verify_init_data(request.headers.get("X-Telegram-Init-Data", ""))
    if not user_id:
        return web.json_response({"error": "unauthorized"}, status=401)

    chat_id = int(request.match_info["chat_id"])
    chats = {c["id"]: c["title"] for c in _get_chats(user_id)}
    if chat_id not in chats:
        return web.json_response({"error": "forbidden"}, status=403)

    filters = {k: db.filter_on(chat_id, k) for k in FILTER_KEYS}
    raw_rules = db.get_setting(chat_id, "rules")
    raw_welcome = db.get_setting(chat_id, "welcome_text") or ""
    raw_goodbye = db.get_setting(chat_id, "goodbye_text") or ""

    return web.json_response({
        "id": chat_id,
        "title": chats[chat_id],
        "rules": html.unescape(raw_rules) if raw_rules else "",
        "welcome": html.unescape(raw_welcome),
        "goodbye": html.unescape(raw_goodbye),
        "filters": filters,
    })


async def handle_api_save(request: web.Request) -> web.Response:
    user_id = _verify_init_data(request.headers.get("X-Telegram-Init-Data", ""))
    if not user_id:
        return web.json_response({"error": "unauthorized"}, status=401)

    chat_id = int(request.match_info["chat_id"])
    chats = {c["id"]: c["title"] for c in _get_chats(user_id)}
    if chat_id not in chats:
        return web.json_response({"error": "forbidden"}, status=403)

    body = await request.json()
    if "rules" in body:
        val = body["rules"].strip()
        db.set_setting(chat_id, "rules", html.escape(val) if val else None)
    if "welcome" in body:
        val = body["welcome"].strip()
        db.set_setting(chat_id, "welcome_text", html.escape(val) if val else None)
    if "goodbye" in body:
        val = body["goodbye"].strip()
        db.set_setting(chat_id, "goodbye_text", html.escape(val) if val else None)
    if "filters" in body and isinstance(body["filters"], dict):
        for k, v in body["filters"].items():
            if k in FILTER_KEYS:
                db.set_setting(chat_id, "f_" + k, "1" if v else "0")

    return web.json_response({"ok": True})


def setup_routes(app: web.Application):
    app.router.add_get("/webapp", handle_index)
    app.router.add_get("/api/chats", handle_api_chats)
    app.router.add_get("/api/chat/{chat_id}", handle_api_chat_detail)
    app.router.add_post("/api/chat/{chat_id}", handle_api_save)


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Хранитель чата</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
  :root {
    --bg: var(--tg-theme-bg-color, #121212);
    --sec-bg: var(--tg-theme-secondary-bg-color, #1e1e24);
    --text: var(--tg-theme-text-color, #ffffff);
    --hint: var(--tg-theme-hint-color, #9aa0a6);
    --btn: var(--tg-theme-button-color, #3390ec);
    --btn-text: var(--tg-theme-button-text-color, #ffffff);
    --accent: #3390ec;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
  body { background: var(--bg); color: var(--text); padding: 16px 16px 88px 16px; min-height: 100vh; }
  .header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 18px; }
  .header h1 { font-size: 22px; font-weight: 700; }
  .badge { background: rgba(51, 144, 236, 0.18); color: var(--accent); padding: 5px 10px; border-radius: 20px; font-size: 12px; font-weight: 600; }
  .stats-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 18px; }
  .stat-card { background: var(--sec-bg); border-radius: 14px; padding: 14px; }
  .stat-val { font-size: 24px; font-weight: 700; color: var(--accent); }
  .stat-lbl { font-size: 12px; color: var(--hint); margin-top: 4px; }
  .card { background: var(--sec-bg); border-radius: 16px; padding: 16px; margin-bottom: 14px; }
  .card-title { font-size: 15px; font-weight: 600; margin-bottom: 10px; display: flex; align-items: center; gap: 8px; }
  .chat-item { display: flex; align-items: center; justify-content: space-between; padding: 14px; background: var(--sec-bg); border-radius: 14px; margin-bottom: 10px; cursor: pointer; transition: transform 0.1s; }
  .chat-item:active { transform: scale(0.98); }
  .chat-info { display: flex; align-items: center; gap: 12px; }
  .chat-ava { width: 42px; height: 42px; border-radius: 50%; background: linear-gradient(135deg, #3390ec, #6c5ce7); display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 18px; color: #fff; }
  .chat-name { font-weight: 600; font-size: 16px; }
  .chat-sub { font-size: 12px; color: var(--hint); margin-top: 2px; }
  .btn { width: 100%; padding: 14px; border: none; border-radius: 12px; background: var(--btn); color: var(--btn-text); font-size: 15px; font-weight: 600; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 8px; text-decoration: none; }
  .btn-outline { background: transparent; border: 1px solid rgba(255,255,255,0.15); color: var(--text); margin-bottom: 12px; padding: 10px; font-size: 14px; }
  textarea { width: 100%; background: var(--bg); color: var(--text); border: 1px solid rgba(255,255,255,0.12); border-radius: 12px; padding: 12px; font-size: 14px; min-height: 95px; resize: vertical; margin-top: 6px; }
  .hint { font-size: 12px; color: var(--hint); margin-top: 6px; line-height: 1.4; }
  .toggle-row { display: flex; align-items: center; justify-content: space-between; padding: 11px 0; border-bottom: 1px solid rgba(255,255,255,0.06); }
  .toggle-row:last-child { border-bottom: none; }
  .switch { position: relative; display: inline-block; width: 46px; height: 26px; }
  .switch input { opacity: 0; width: 0; height: 0; }
  .slider { position: absolute; cursor: pointer; inset: 0; background: #444; border-radius: 26px; transition: .25s; }
  .slider:before { position: absolute; content: ""; height: 20px; width: 20px; left: 3px; bottom: 3px; background: white; border-radius: 50%; transition: .25s; }
  input:checked + .slider { background: var(--accent); }
  input:checked + .slider:before { transform: translateX(20px); }
  .nav-bar { position: fixed; bottom: 0; left: 0; right: 0; background: var(--sec-bg); border-top: 1px solid rgba(255,255,255,0.08); display: flex; padding: 8px 16px 14px 16px; gap: 10px; z-index: 100; }
  .nav-btn { flex: 1; background: none; border: none; color: var(--hint); display: flex; flex-direction: column; align-items: center; gap: 4px; font-size: 12px; font-weight: 600; cursor: pointer; padding: 6px; border-radius: 10px; }
  .nav-btn.active { color: var(--accent); background: rgba(51, 144, 236, 0.12); }
  .hidden { display: none !important; }
  .toast { position: fixed; top: 16px; left: 50%; transform: translateX(-50%); background: #2ecc71; color: #fff; padding: 10px 20px; border-radius: 20px; font-weight: 600; font-size: 14px; z-index: 999; box-shadow: 0 4px 15px rgba(0,0,0,0.3); }
</style>
</head>
<body>

<div id="toast" class="toast hidden">✅ Настройки сохранены!</div>

<!-- Вкладка 1: Мои чаты -->
<div id="tab-chats">
  <div class="header">
    <h1>🛡 Хранитель чата</h1>
    <span class="badge">24/7 Online</span>
  </div>

  <div class="stats-grid">
    <div class="stat-card">
      <div class="stat-val" id="stat-chats">0</div>
      <div class="stat-lbl">Подключено чатов</div>
    </div>
    <div class="stat-card">
      <div class="stat-val">5</div>
      <div class="stat-lbl">Модулей защиты</div>
    </div>
  </div>

  <div class="card-title" style="margin-bottom: 10px;">💬 Ваши группы</div>
  <div id="chats-list">
    <div class="card" style="text-align:center; color: var(--hint);">Загрузка списка чатов...</div>
  </div>

  <a id="add-btn-main" href="#" class="btn" style="margin-top: 12px;">➕ Подключить бота в чат</a>
</div>

<!-- Вкладка 2: Редактор конкретного чата -->
<div id="tab-editor" class="hidden">
  <button class="btn btn-outline" onclick="backToChats()">⬅️ Назад к списку чатов</button>
  <div class="header">
    <h1 id="ed-title">Настройка чата</h1>
  </div>

  <div class="card">
    <div class="card-title">🛡 Фильтры автомодерации</div>
    <div class="toggle-row"><span>🤬 Антимат</span><label class="switch"><input type="checkbox" id="f-mat"><span class="slider"></span></label></div>
    <div class="toggle-row"><span>🎭 Спам стикерами и GIF</span><label class="switch"><input type="checkbox" id="f-stickers"><span class="slider"></span></label></div>
    <div class="toggle-row"><span>🔗 Защита от ссылок</span><label class="switch"><input type="checkbox" id="f-links"><span class="slider"></span></label></div>
    <div class="toggle-row"><span>💬 Антифлуд</span><label class="switch"><input type="checkbox" id="f-flood"><span class="slider"></span></label></div>
    <div class="toggle-row"><span>🤖 Инлайн-боты</span><label class="switch"><input type="checkbox" id="f-inline"><span class="slider"></span></label></div>
  </div>

  <div class="card">
    <div class="card-title">📜 Правила чата</div>
    <textarea id="ed-rules" placeholder="Оставьте пустым для стандартных правил..."></textarea>
  </div>

  <div class="card">
    <div class="card-title">👋 Приветствие новичков</div>
    <textarea id="ed-welcome" placeholder="Например: Привет, {user}! Добро пожаловать в {chat}!"></textarea>
    <div class="hint">Переменные: <b>{user}</b> — имя участника, <b>{chat}</b> — название группы.</div>
  </div>

  <div class="card">
    <div class="card-title">🚪 Сообщение при выходе</div>
    <textarea id="ed-goodbye" placeholder="Например: 👋 {user} покинул(а) чат {chat}."></textarea>
  </div>

  <button class="btn" onclick="saveChat()">💾 Сохранить изменения</button>
</div>

<!-- Вкладка 3: Инструкция -->
<div id="tab-help" class="hidden">
  <div class="header"><h1>📖 Подключение</h1></div>
  <div class="card">
    <div class="card-title">Как подключить новый чат?</div>
    <p class="hint" style="font-size: 14px; color: var(--text);">
      1. Нажмите кнопку <b>«Подключить бота в чат»</b> ниже.<br><br>
      2. Выберите вашу группу из списка и обязательно оставьте галочки прав администратора.<br><br>
      3. Вернитесь во вкладку <b>«Мои чаты»</b> — группа появится автоматически.
    </p>
    <a id="add-btn-help" href="#" class="btn" style="margin-top: 16px;">➕ Подключить бота в чат</a>
  </div>
</div>

<!-- Нижняя навигация -->
<div class="nav-bar">
  <button class="nav-btn active" id="nav-chats" onclick="switchTab('chats')">
    <span>💬</span><span>Мои чаты</span>
  </button>
  <button class="nav-btn" id="nav-help" onclick="switchTab('help')">
    <span>➕</span><span>Подключение</span>
  </button>
</div>

<script>
  const tg = window.Telegram.WebApp;
  tg.ready();
  tg.expand();

  const BOT_USER = "__BOT_USERNAME__";
  const RIGHTS = "change_info+delete_messages+restrict_members+invite_users+pin_messages+manage_chat";
  const ADD_URL = `https://t.me/${BOT_USER}?startgroup=true&admin=${RIGHTS}`;

  document.getElementById("add-btn-main").href = ADD_URL;
  document.getElementById("add-btn-help").href = ADD_URL;

  let currentChatId = null;

  function switchTab(tab) {
    document.getElementById("tab-chats").classList.add("hidden");
    document.getElementById("tab-editor").classList.add("hidden");
    document.getElementById("tab-help").classList.add("hidden");
    document.getElementById("nav-chats").classList.remove("active");
    document.getElementById("nav-help").classList.remove("active");

    if (tab === "chats") {
      document.getElementById("tab-chats").classList.remove("hidden");
      document.getElementById("nav-chats").classList.add("active");
      loadChats();
    } else if (tab === "help") {
      document.getElementById("tab-help").classList.remove("hidden");
      document.getElementById("nav-help").classList.add("active");
    }
  }

  async function api(path, opts = {}) {
    opts.headers = Object.assign({}, opts.headers, {
      "X-Telegram-Init-Data": tg.initData || "",
      "Content-Type": "application/json"
    });
    const res = await fetch(path, opts);
    return res.json();
  }

  async function loadChats() {
    const list = document.getElementById("chats-list");
    const data = await api("/api/chats");
    const chats = data.chats || [];
    document.getElementById("stat-chats").innerText = chats.length;

    if (!chats.length) {
      list.innerHTML = `<div class="card" style="text-align:center; color:var(--hint);">Пока нет подключённых чатов.<br>Нажмите кнопку ниже, чтобы добавить бота в группу!</div>`;
      return;
    }

    list.innerHTML = chats.map(c => `
      <div class="chat-item" onclick="openChat(${c.id})">
        <div class="chat-info">
          <div class="chat-ava">${(c.title || "Ч")[0].toUpperCase()}</div>
          <div>
            <div class="chat-name">${c.title}</div>
            <div class="chat-sub">Нажмите для настройки</div>
          </div>
        </div>
        <span style="color:var(--hint); font-size:18px;">›</span>
      </div>
    `).join("");
  }

  async function openChat(chatId) {
    currentChatId = chatId;
    document.getElementById("tab-chats").classList.add("hidden");
    document.getElementById("tab-editor").classList.remove("hidden");
    document.getElementById("ed-title").innerText = "Загрузка...";

    const d = await api(`/api/chat/${chatId}`);
    document.getElementById("ed-title").innerText = d.title || "Настройка чата";
    document.getElementById("ed-rules").value = d.rules || "";
    document.getElementById("ed-welcome").value = d.welcome || "";
    document.getElementById("ed-goodbye").value = d.goodbye || "";

    ["mat", "stickers", "links", "flood", "inline"].forEach(k => {
      document.getElementById("f-" + k).checked = !!(d.filters && d.filters[k]);
    });
  }

  function backToChats() {
    currentChatId = null;
    switchTab("chats");
  }

  async function saveChat() {
    if (!currentChatId) return;
    const payload = {
      rules: document.getElementById("ed-rules").value,
      welcome: document.getElementById("ed-welcome").value,
      goodbye: document.getElementById("ed-goodbye").value,
      filters: {}
    };
    ["mat", "stickers", "links", "flood", "inline"].forEach(k => {
      payload.filters[k] = document.getElementById("f-" + k).checked;
    });

    await api(`/api/chat/${currentChatId}`, {
      method: "POST",
      body: JSON.stringify(payload)
    });

    const toast = document.getElementById("toast");
    toast.classList.remove("hidden");
    setTimeout(() => toast.classList.add("hidden"), 2500);
  }

  loadChats();
</script>
</body>
</html>
"""
