"""Telegram Mini App (Web App) для управления чатами бота."""
import hashlib
import hmac
import json
import os
from urllib.parse import parse_qsl

from aiohttp import web
import config
import db
import rules

BOT_TOKEN = os.getenv("BOT_TOKEN", getattr(config, "BOT_TOKEN", "")).strip()
BOT_USERNAME = os.getenv("BOT_USERNAME", "chat_custodian_bot").strip().lstrip("@")

HTML_PAGE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Хранитель чата</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
  :root {
    --bg: var(--tg-theme-bg-color, #141416);
    --sec-bg: var(--tg-theme-secondary-bg-color, #1e1e22);
    --text: var(--tg-theme-text-color, #ffffff);
    --hint: var(--tg-theme-hint-color, #8e8e93);
    --btn: var(--tg-theme-button-color, #3b82f6);
    --btn-text: var(--tg-theme-button-text-color, #ffffff);
    --border: rgba(255,255,255,0.08);
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    padding: 16px 16px 84px 16px;
    min-height: 100vh;
  }
  .header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 16px;
  }
  .header-title {
    font-size: 20px;
    font-weight: 700;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .badge {
    background: rgba(59, 130, 246, 0.18);
    color: #60a5fa;
    font-size: 12px;
    padding: 4px 10px;
    border-radius: 12px;
    font-weight: 600;
  }
  .stats {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
    margin-bottom: 18px;
  }
  .stat-card {
    background: var(--sec-bg);
    padding: 14px;
    border-radius: 14px;
    border: 1px solid var(--border);
  }
  .stat-val { font-size: 22px; font-weight: 700; color: var(--btn); }
  .stat-lbl { font-size: 12px; color: var(--hint); margin-top: 4px; }
  .card {
    background: var(--sec-bg);
    border-radius: 16px;
    padding: 16px;
    margin-bottom: 12px;
    border: 1px solid var(--border);
  }
  .chat-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    cursor: pointer;
    transition: transform 0.1s;
  }
  .chat-item:active { transform: scale(0.98); }
  .chat-name { font-size: 16px; font-weight: 600; }
  .chat-sub { font-size: 12px; color: var(--hint); margin-top: 3px; }
  .btn {
    display: block;
    width: 100%;
    padding: 13px 16px;
    background: var(--btn);
    color: var(--btn-text);
    border: none;
    border-radius: 12px;
    font-size: 15px;
    font-weight: 600;
    text-align: center;
    text-decoration: none;
    cursor: pointer;
    margin-top: 10px;
  }
  .btn-sec {
    background: rgba(255,255,255,0.08);
    color: var(--text);
  }
  .section-title {
    font-size: 13px;
    font-weight: 600;
    color: var(--hint);
    text-transform: uppercase;
    margin: 16px 0 8px 4px;
  }
  textarea {
    width: 100%;
    min-height: 96px;
    background: var(--bg);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 12px;
    font-size: 14px;
    font-family: inherit;
    resize: vertical;
  }
  .toggle-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 0;
    border-bottom: 1px solid var(--border);
  }
  .toggle-row:last-child { border-bottom: none; }
  .switch {
    position: relative;
    display: inline-block;
    width: 46px;
    height: 26px;
  }
  .switch input { opacity: 0; width: 0; height: 0; }
  .slider {
    position: absolute;
    cursor: pointer;
    top: 0; left: 0; right: 0; bottom: 0;
    background-color: #3a3a3c;
    transition: .2s;
    border-radius: 26px;
  }
  .slider:before {
    position: absolute;
    content: "";
    height: 20px; width: 20px;
    left: 3px; bottom: 3px;
    background-color: white;
    transition: .2s;
    border-radius: 50%;
  }
  input:checked + .slider { background-color: var(--btn); }
  input:checked + .slider:before { transform: translateX(20px); }
  .nav {
    position: fixed;
    bottom: 0; left: 0; right: 0;
    background: var(--sec-bg);
    border-top: 1px solid var(--border);
    display: flex;
    padding: 8px 0 calc(8px + env(safe-area-inset-bottom));
    z-index: 100;
  }
  .nav-btn {
    flex: 1;
    background: none;
    border: none;
    color: var(--hint);
    font-size: 11px;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
    cursor: pointer;
  }
  .nav-btn.active { color: var(--btn); font-weight: 600; }
  .nav-icon { font-size: 20px; }
  .hidden { display: none !important; }
  .toast {
    position: fixed;
    top: 16px; left: 50%;
    transform: translateX(-50%);
    background: #10b981;
    color: #fff;
    padding: 10px 18px;
    border-radius: 20px;
    font-size: 14px;
    font-weight: 600;
    z-index: 999;
    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
  }
</style>
</head>
<body>

<div id="toast" class="toast hidden">Сохранено</div>

<div class="header">
  <div class="header-title">🛡️ Хранитель чата</div>
  <div class="badge">24/7 Online</div>
</div>

<div class="stats">
  <div class="stat-card">
    <div class="stat-val" id="chat-count">0</div>
    <div class="stat-lbl">Подключённых чатов</div>
  </div>
  <div class="stat-card">
    <div class="stat-val" style="color:#10b981;">Активна</div>
    <div class="stat-lbl">Защита от спама</div>
  </div>
</div>

<div id="tab-chats">
  <div id="chats-list">
    <div class="card" style="text-align:center; color:var(--hint);">Загрузка ваших чатов...</div>
  </div>
</div>

<div id="tab-settings" class="hidden">
  <button class="btn btn-sec" style="margin-top:0; margin-bottom:14px;" onclick="showTab('chats')">← Назад к списку чатов</button>
  <div class="card">
    <div class="chat-name" id="cur-chat-title">Настройки чата</div>
    <div class="chat-sub" id="cur-chat-id">ID: 0</div>
  </div>

  <div class="section-title">Фильтры автомодерации</div>
  <div class="card">
    <div class="toggle-row">
      <span>🤬 Антимат (удаление + пред)</span>
      <label class="switch"><input type="checkbox" id="f_mat" onchange="saveFilter('mat')"><span class="slider"></span></label>
    </div>
    <div class="toggle-row">
      <span>🔗 Защита от ссылок и рекламы</span>
      <label class="switch"><input type="checkbox" id="f_links" onchange="saveFilter('links')"><span class="slider"></span></label>
    </div>
    <div class="toggle-row">
      <span>🌊 Антифлуд (частые сообщения)</span>
      <label class="switch"><input type="checkbox" id="f_flood" onchange="saveFilter('flood')"><span class="slider"></span></label>
    </div>
    <div class="toggle-row">
      <span>🎭 Лимит стикеров и GIF</span>
      <label class="switch"><input type="checkbox" id="f_stickers" onchange="saveFilter('stickers')"><span class="slider"></span></label>
    </div>
  </div>

  <div class="section-title">Правила чата</div>
  <div class="card">
    <textarea id="txt-rules" placeholder="Введите правила группы..."></textarea>
    <button class="btn" onclick="saveText('rules')">Сохранить правила</button>
  </div>

  <div class="section-title">Приветствие новичков ({user}, {chat})</div>
  <div class="card">
    <textarea id="txt-welcome" placeholder="Оставьте пустым для стандартного приветствия..."></textarea>
    <button class="btn" onclick="saveText('welcome')">Сохранить приветствие</button>
  </div>

  <div class="section-title">Прощание при выходе ({user}, {chat})</div>
  <div class="card">
    <textarea id="txt-farewell" placeholder="Оставьте пустым для стандартного прощания..."></textarea>
    <button class="btn" onclick="saveText('farewell')">Сохранить прощание</button>
  </div>
</div>

<div id="tab-connect" class="hidden">
  <div class="card">
    <div class="chat-name" style="margin-bottom:8px;">Как подключить бота в группу</div>
    <div class="chat-sub" style="line-height:1.5; font-size:14px;">
      1. Нажмите кнопку ниже и выберите нужную группу.<br>
      2. Подтвердите выдачу прав администратора (удаление, бан, приглашение, закрепление).<br>
      3. Чат сразу появится во вкладке «Мои чаты».
    </div>
    <a class="btn" id="add-bot-link" href="#">➕ Добавить бота в чат</a>
  </div>
</div>

<div class="nav">
  <button class="nav-btn active" id="nav-chats" onclick="showTab('chats')">
    <span class="nav-icon">💬</span>
    <span>Мои чаты</span>
  </button>
  <button class="nav-btn" id="nav-connect" onclick="showTab('connect')">
    <span class="nav-icon">➕</span>
    <span>Подключение</span>
  </button>
</div>

<script>
  const tg = window.Telegram.WebApp;
  tg.ready();
  tg.expand();

  const botUsername = "__BOT_USERNAME__";
  const addUrl = `https://t.me/${botUsername}?startgroup=true&admin=delete_messages+restrict_members+invite_users+pin_messages`;
  document.getElementById("add-bot-link").href = addUrl;

  let currentChatId = null;

  function showToast(msg) {
    const t = document.getElementById("toast");
    t.textContent = msg;
    t.classList.remove("hidden");
    setTimeout(() => t.classList.add("hidden"), 2200);
  }

  function showTab(tab) {
    document.getElementById("tab-chats").classList.add("hidden");
    document.getElementById("tab-settings").classList.add("hidden");
    document.getElementById("tab-connect").classList.add("hidden");
    document.getElementById("nav-chats").classList.remove("active");
    document.getElementById("nav-connect").classList.remove("active");

    if (tab === "chats") {
      document.getElementById("tab-chats").classList.remove("hidden");
      document.getElementById("nav-chats").classList.add("active");
      loadChats();
    } else if (tab === "connect") {
      document.getElementById("tab-connect").classList.remove("hidden");
      document.getElementById("nav-connect").classList.add("active");
    } else if (tab === "settings") {
      document.getElementById("tab-settings").classList.remove("hidden");
      document.getElementById("nav-chats").classList.add("active");
    }
  }

  async function apiPost(url, payload) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ initData: tg.initData || "", ...payload })
    });
    const raw = await res.text();
    let data;
    try {
      data = JSON.parse(raw);
    } catch (e) {
      throw new Error("Сервер вернул некорректный ответ: " + raw.slice(0, 80));
    }
    if (!res.ok || data.error) {
      throw new Error(data.error || ("HTTP " + res.status));
    }
    return data;
  }

  async function loadChats() {
    const box = document.getElementById("chats-list");
    try {
      const data = await apiPost("/api/chats", {});
      const chats = data.chats || [];
      document.getElementById("chat-count").textContent = chats.length;
      if (chats.length === 0) {
        box.innerHTML = `
          <div class="card">
            <div class="chat-name">У вас пока нет подключённых чатов</div>
            <div class="chat-sub" style="margin-top:6px;">Добавьте бота администратором в вашу группу, и она сразу появится здесь.</div>
            <a class="btn" href="${addUrl}">➕ Добавить бота в чат</a>
          </div>`;
        return;
      }
      box.innerHTML = "";
      chats.forEach(c => {
        const div = document.createElement("div");
        div.className = "card chat-item";
        div.innerHTML = `
          <div>
            <div class="chat-name">${escapeHtml(c.title)}</div>
            <div class="chat-sub">ID: ${c.chat_id}</div>
          </div>
          <div style="color:var(--btn); font-weight:700;">Настроить ›</div>
        `;
        div.onclick = () => openChat(c.chat_id, c.title);
        box.appendChild(div);
      });
    } catch (err) {
      box.innerHTML = `
        <div class="card">
          <div class="chat-name" style="color:#f87171;">⚠️ Не удалось загрузить чаты</div>
          <div class="chat-sub" style="margin-top:6px;">${escapeHtml(err.message)}</div>
          <a class="btn" href="${addUrl}">➕ Добавить бота в чат</a>
        </div>`;
    }
  }

  async function openChat(chatId, title) {
    currentChatId = chatId;
    document.getElementById("cur-chat-title").textContent = title;
    document.getElementById("cur-chat-id").textContent = "ID: " + chatId;
    showTab("settings");
    try {
      const data = await apiPost("/api/chat_info", { chat_id: chatId });
      document.getElementById("f_mat").checked = !!data.filters.mat;
      document.getElementById("f_links").checked = !!data.filters.links;
      document.getElementById("f_flood").checked = !!data.filters.flood;
      document.getElementById("f_stickers").checked = !!data.filters.stickers;
      document.getElementById("txt-rules").value = data.rules || "";
      document.getElementById("txt-welcome").value = data.welcome || "";
      document.getElementById("txt-farewell").value = data.farewell || "";
    } catch (err) {
      showToast("Ошибка: " + err.message);
    }
  }

  async function saveFilter(kind) {
    if (!currentChatId) return;
    const val = document.getElementById("f_" + kind).checked;
    try {
      await apiPost("/api/save", { chat_id: currentChatId, field: "filter_" + kind, value: val ? "1" : "0" });
      showToast("Фильтр обновлён");
    } catch (err) {
      showToast("Ошибка: " + err.message);
    }
  }

  async function saveText(field) {
    if (!currentChatId) return;
    const value = document.getElementById("txt-" + field).value;
    try {
      await apiPost("/api/save", { chat_id: currentChatId, field: field, value: value });
      showToast("Сохранено в базу");
    } catch (err) {
      showToast("Ошибка: " + err.message);
    }
  }

  function escapeHtml(str) {
    return String(str).replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
  }

  loadChats();
</script>
</body>
</html>
""".replace("__BOT_USERNAME__", BOT_USERNAME)


def _ensure_table():
    db._db.execute("""CREATE TABLE IF NOT EXISTS user_chats (
        user_id BIGINT,
        chat_id BIGINT,
        title TEXT,
        PRIMARY KEY (user_id, chat_id)
    )""")


def register_chat(user_id: int, chat_id: int, title: str):
    _ensure_table()
    db._db.execute(
        "INSERT INTO user_chats (user_id, chat_id, title) VALUES (%s, %s, %s) "
        "ON CONFLICT (user_id, chat_id) DO UPDATE SET title = EXCLUDED.title",
        (user_id, chat_id, title or "Группа"),
    )


def get_user_chats(user_id: int) -> list[dict]:
    _ensure_table()
    rows = db._db.execute(
        "SELECT chat_id, title FROM user_chats WHERE user_id = %s ORDER BY title",
        (user_id,),
    ).fetchall()
    return [{"chat_id": r[0], "title": r[1]} for r in rows]


def _verify_init_data(init_data: str) -> int | None:
    if not init_data or not BOT_TOKEN:
        return None
    parsed = dict(parse_qsl(init_data, strict_parsing=False))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        return None
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated_hash, received_hash):
        return None
    user_raw = parsed.get("user")
    if not user_raw:
        return None
    try:
        user_obj = json.loads(user_raw)
        return int(user_obj["id"])
    except Exception:
        return None


async def handle_index(request: web.Request) -> web.Response:
    return web.Response(text=HTML_PAGE, content_type="text/html")


async def handle_chats(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Неверный формат запроса"}, status=400)
    user_id = _verify_init_data(body.get("initData", ""))
    if not user_id:
        return web.json_response({"error": "Откройте приложение через кнопку в чате с ботом"}, status=401)
    return web.json_response({"chats": get_user_chats(user_id)})


async def handle_chat_info(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Неверный формат запроса"}, status=400)
    user_id = _verify_init_data(body.get("initData", ""))
    if not user_id:
        return web.json_response({"error": "Нет авторизации Telegram"}, status=401)
    chat_id = int(body.get("chat_id", 0))
    allowed = {c["chat_id"] for c in get_user_chats(user_id)}
    if chat_id not in allowed:
        return web.json_response({"error": "Нет доступа к этому чату"}, status=403)
    filters = {
        "mat": db.filter_on(chat_id, "mat"),
        "links": db.filter_on(chat_id, "links"),
        "flood": db.filter_on(chat_id, "flood"),
        "stickers": db.filter_on(chat_id, "stickers"),
    }
    return web.json_response({
        "filters": filters,
        "rules": db.get_setting(chat_id, "rules") or rules.DEFAULT_RULES,
        "welcome": db.get_setting(chat_id, "custom_welcome") or "",
        "farewell": db.get_setting(chat_id, "custom_farewell") or "",
    })


async def handle_save(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Неверный формат запроса"}, status=400)
    user_id = _verify_init_data(body.get("initData", ""))
    if not user_id:
        return web.json_response({"error": "Нет авторизации Telegram"}, status=401)
    chat_id = int(body.get("chat_id", 0))
    allowed = {c["chat_id"] for c in get_user_chats(user_id)}
    if chat_id not in allowed:
        return web.json_response({"error": "Нет доступа к этому чату"}, status=403)
    field = str(body.get("field", ""))
    value = str(body.get("value", "")).strip()
    if field.startswith("filter_"):
        kind = field.replace("filter_", "", 1)
        db.set_setting(chat_id, "f_" + kind, "1" if value == "1" else "0")
    elif field == "rules":
        db.set_setting(chat_id, "rules", value if value else None)
    elif field == "welcome":
        db.set_setting(chat_id, "custom_welcome", value if value else None)
    elif field == "farewell":
        db.set_setting(chat_id, "custom_farewell", value if value else None)
    else:
        return web.json_response({"error": "Неизвестное поле"}, status=400)
    return web.json_response({"ok": True})


def setup_routes(app: web.Application):
    app.router.add_get("/webapp", handle_index)
    app.router.add_post("/api/chats", handle_chats)
    app.router.add_post("/api/chat_info", handle_chat_info)
    app.router.add_post("/api/save", handle_save)
