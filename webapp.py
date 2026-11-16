"""Telegram Mini App: backend API и полноценный интерфейс управления чатами."""
import hashlib
import hmac
import json
import urllib.parse
from aiohttp import web

import config
import db
import rules
from loader import bot


def _verify_init_data(init_data: str) -> dict | None:
    if not init_data:
        return None
    try:
        parsed = dict(urllib.parse.parse_qsl(init_data, strict_parsing=True))
        hash_val = parsed.pop("hash", None)
        if not hash_val:
            return None
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
        secret_key = hmac.new(b"WebAppData", config.BOT_TOKEN.encode(), hashlib.sha256).digest()
        calc_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calc_hash, hash_val):
            return None
        user_raw = parsed.get("user")
        return json.loads(user_raw) if user_raw else None
    except Exception:
        return None


async def handle_index(request: web.Request) -> web.Response:
    me = await bot.get_me()
    bot_username = me.username or ""
    html_page = _HTML_TEMPLATE.replace("__BOT_USERNAME__", bot_username)
    return web.Response(text=html_page, content_type="text/html", charset="utf-8")


async def handle_chats(request: web.Request) -> web.Response:
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    user = _verify_init_data(init_data)
    if not user:
        return web.json_response({"ok": False, "error": "Откройте приложение внутри Telegram"}, status=401)
    user_id = int(user["id"])
    raw = db.get_setting(user_id, "owned_chats")
    chats_map = json.loads(raw) if raw else {}
    items = []
    for cid_s, title in chats_map.items():
        cid = int(cid_s)
        items.append({
            "id": cid,
            "title": title,
            "rules": db.get_setting(cid, "rules") or "",
            "welcome": db.get_setting(cid, "welcome_text") or "",
            "goodbye": db.get_setting(cid, "goodbye_text") or "",
            "filters": {
                "mat": db.filter_on(cid, "mat"),
                "spam": db.filter_on(cid, "spam"),
                "ads": db.filter_on(cid, "ads"),
            },
        })
    return web.json_response({"ok": True, "user": user, "chats": items})


async def handle_save(request: web.Request) -> web.Response:
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    user = _verify_init_data(init_data)
    if not user:
        return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)
    user_id = int(user["id"])
    body = await request.json()
    chat_id = int(body.get("chat_id", 0))

    raw = db.get_setting(user_id, "owned_chats")
    chats_map = json.loads(raw) if raw else {}
    if str(chat_id) not in chats_map:
        return web.json_response({"ok": False, "error": "Нет доступа к этому чату"}, status=403)

    for key, db_key in [("rules", "rules"), ("welcome", "welcome_text"), ("goodbye", "goodbye_text")]:
        if key in body:
            val = (body[key] or "").strip()
            db.set_setting(chat_id, db_key, val if val else None)

    if "filters" in body and isinstance(body["filters"], dict):
        for fk in ("mat", "spam", "ads"):
            if fk in body["filters"]:
                db.set_setting(chat_id, "f_" + fk, "1" if body["filters"][fk] else "0")

    return web.json_response({"ok": True})


def setup_routes(app: web.Application):
    app.router.add_get("/webapp", handle_index)
    app.router.add_get("/api/chats", handle_chats)
    app.router.add_post("/api/save", handle_save)


_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Хранитель чата — Панель</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
  :root {
    --bg: var(--tg-theme-bg-color, #111318);
    --sec-bg: var(--tg-theme-secondary-bg-color, #1b1f27);
    --text: var(--tg-theme-text-color, #f3f4f6);
    --hint: var(--tg-theme-hint-color, #9ca3af);
    --btn: var(--tg-theme-button-color, #2ea6ff);
    --btn-text: var(--tg-theme-button-text-color, #ffffff);
  }
  * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
  body { background: var(--bg); color: var(--text); padding-bottom: 84px; min-height: 100vh; }
  .header { padding: 18px 16px 12px; display: flex; align-items: center; justify-content: space-between; }
  .header h1 { font-size: 20px; font-weight: 700; }
  .badge { background: rgba(46,166,255,0.16); color: var(--btn); padding: 4px 10px; border-radius: 999px; font-size: 12px; font-weight: 600; }
  .stats { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; padding: 0 16px 16px; }
  .stat-card { background: var(--sec-bg); border-radius: 14px; padding: 14px; }
  .stat-val { font-size: 22px; font-weight: 700; color: var(--btn); }
  .stat-lbl { font-size: 12px; color: var(--hint); margin-top: 4px; }
  .section { padding: 0 16px; }
  .card { background: var(--sec-bg); border-radius: 16px; padding: 16px; margin-bottom: 12px; }
  .card-title { font-size: 16px; font-weight: 600; margin-bottom: 6px; display: flex; justify-content: space-between; align-items: center; }
  .card-sub { font-size: 13px; color: var(--hint); line-height: 1.4; }
  .btn { width: 100%; border: none; border-radius: 12px; padding: 13px; font-size: 15px; font-weight: 600; cursor: pointer; background: var(--btn); color: var(--btn-text); margin-top: 10px; display: block; text-align: center; text-decoration: none; }
  .btn-sec { background: rgba(255,255,255,0.08); color: var(--text); }
  label { display: block; font-size: 13px; color: var(--hint); margin: 12px 0 6px; font-weight: 500; }
  textarea { width: 100%; background: var(--bg); color: var(--text); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 10px 12px; font-size: 14px; min-height: 82px; resize: vertical; }
  .toggle-row { display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid rgba(255,255,255,0.06); }
  .toggle-row:last-child { border-bottom: none; }
  input[type="checkbox"] { width: 20px; height: 20px; accent-color: var(--btn); }
  .nav { position: fixed; bottom: 0; left: 0; right: 0; background: var(--sec-bg); display: flex; border-top: 1px solid rgba(255,255,255,0.08); padding: 8px 0 18px; }
  .nav-item { flex: 1; text-align: center; color: var(--hint); font-size: 12px; font-weight: 600; cursor: pointer; }
  .nav-item.active { color: var(--btn); }
  .nav-icon { font-size: 20px; display: block; margin-bottom: 2px; }
  .hidden { display: none !important; }
  .toast { position: fixed; top: 14px; left: 16px; right: 16px; background: #16a34a; color: #fff; padding: 12px; border-radius: 12px; text-align: center; font-weight: 600; font-size: 14px; z-index: 99; }
</style>
</head>
<body>
<div id="toast" class="toast hidden">Сохранено!</div>

<div class="header">
  <h1>🛡 Хранитель чата</h1>
  <span class="badge">24/7 Online</span>
</div>

<div id="tab-chats">
  <div class="stats">
    <div class="stat-card">
      <div class="stat-val" id="stat-chats">0</div>
      <div class="stat-lbl">Подключённых чатов</div>
    </div>
    <div class="stat-card">
      <div class="stat-val">Активна</div>
      <div class="stat-lbl">Защита от спама</div>
    </div>
  </div>

  <div class="section" id="chats-list">
    <div class="card"><div class="card-sub">Загрузка списка чатов...</div></div>
  </div>

  <div class="section hidden" id="chat-editor">
    <div class="card">
      <div class="card-title"><span id="ed-title">Настройка чата</span></div>
      <div class="toggle-row"><span>🤬 Фильтр мата</span><input type="checkbox" id="f-mat"></div>
      <div class="toggle-row"><span>⚡ Антиспам и флуд</span><input type="checkbox" id="f-spam"></div>
      <div class="toggle-row"><span>🔗 Защита от рекламы</span><input type="checkbox" id="f-ads"></div>

      <label>📜 Правила чата (пусто = стандартные)</label>
      <textarea id="ed-rules" placeholder="Впиши свои правила чата..."></textarea>

      <label>👋 Текст приветствия ({user}, {chat})</label>
      <textarea id="ed-welcome" placeholder="Добро пожаловать в {chat}, {user}!"></textarea>

      <label>🚪 Текст прощания ({user}, {chat})</label>
      <textarea id="ed-goodbye" placeholder="{user} покинул(а) чат."></textarea>

      <button class="btn" onclick="saveChat()">💾 Сохранить настройки</button>
      <button class="btn btn-sec" onclick="closeEditor()">⬅️ Назад к чатам</button>
    </div>
  </div>
</div>

<div id="tab-connect" class="section hidden">
  <div class="card">
    <div class="card-title">➕ Подключить новую группу</div>
    <div class="card-sub">
      1. Нажми кнопку ниже и выбери группу.<br>
      2. Подтверди выдачу прав администратора.<br>
      3. Чат автоматически появится во вкладке «Мои чаты».
    </div>
    <a class="btn" id="add-bot-link" href="#">➕ Выбрать чат в Telegram</a>
  </div>
</div>

<div class="nav">
  <div class="nav-item active" id="nav-chats" onclick="switchTab('chats')">
    <span class="nav-icon">💬</span>Мои чаты
  </div>
  <div class="nav-item" id="nav-connect" onclick="switchTab('connect')">
    <span class="nav-icon">➕</span>Подключение
  </div>
</div>

<script>
  const tg = window.Telegram.WebApp;
  tg.ready();
  tg.expand();

  const botUser = "__BOT_USERNAME__";
  const addUrl = `https://t.me/${botUser}?startgroup=true&admin=change_info+delete_messages+restrict_members+invite_users+pin_messages`;
  document.getElementById("add-bot-link").href = addUrl;

  let allChats = [];
  let currentChatId = null;

  function showToast(msg) {
    const t = document.getElementById("toast");
    t.textContent = msg;
    t.classList.remove("hidden");
    setTimeout(() => t.classList.add("hidden"), 2200);
  }

  function switchTab(tab) {
    document.getElementById("tab-chats").classList.toggle("hidden", tab !== "chats");
    document.getElementById("tab-connect").classList.toggle("hidden", tab !== "connect");
    document.getElementById("nav-chats").classList.toggle("active", tab === "chats");
    document.getElementById("nav-connect").classList.toggle("active", tab === "connect");
  }

  async function loadChats() {
    try {
      const res = await fetch("/api/chats", {
        headers: { "X-Telegram-Init-Data": tg.initData || "" }
      });
      const data = await res.json();
      const box = document.getElementById("chats-list");
      if (!data.ok) {
        box.innerHTML = `<div class="card"><div class="card-title">⚠️ Внимание</div><div class="card-sub">${data.error}</div><a class="btn" href="${addUrl}">➕ Добавить бота в чат</a></div>`;
        return;
      }
      allChats = data.chats || [];
      document.getElementById("stat-chats").textContent = allChats.length;
      if (allChats.length === 0) {
        box.innerHTML = `<div class="card"><div class="card-title">Чатов пока нет</div><div class="card-sub">Добавь бота администратором в свою группу, чтобы управлять ей здесь.</div><a class="btn" href="${addUrl}">➕ Добавить бота в группу</a></div>`;
        return;
      }
      box.innerHTML = allChats.map(c => `
        <div class="card">
          <div class="card-title"><span>💬 ${c.title}</span><span class="badge">Активен</span></div>
          <div class="card-sub">Нажми ниже, чтобы изменить правила, приветствие или фильтры.</div>
          <button class="btn" onclick="openEditor(${c.id})">⚙️ Настроить чат</button>
        </div>
      `).join("");
    } catch (e) {
      document.getElementById("chats-list").innerHTML = `<div class="card"><div class="card-sub">Ошибка загрузки: ${e}</div></div>`;
    }
  }

  function openEditor(id) {
    const c = allChats.find(x => x.id === id);
    if (!c) return;
    currentChatId = id;
    document.getElementById("ed-title").textContent = c.title;
    document.getElementById("f-mat").checked = !!c.filters.mat;
    document.getElementById("f-spam").checked = !!c.filters.spam;
    document.getElementById("f-ads").checked = !!c.filters.ads;
    document.getElementById("ed-rules").value = c.rules || "";
    document.getElementById("ed-welcome").value = c.welcome || "";
    document.getElementById("ed-goodbye").value = c.goodbye || "";
    document.getElementById("chats-list").classList.add("hidden");
    document.getElementById("chat-editor").classList.remove("hidden");
  }

  function closeEditor() {
    currentChatId = null;
    document.getElementById("chat-editor").classList.add("hidden");
    document.getElementById("chats-list").classList.remove("hidden");
  }

  async function saveChat() {
    if (!currentChatId) return;
    const payload = {
      chat_id: currentChatId,
      rules: document.getElementById("ed-rules").value,
      welcome: document.getElementById("ed-welcome").value,
      goodbye: document.getElementById("ed-goodbye").value,
      filters: {
        mat: document.getElementById("f-mat").checked,
        spam: document.getElementById("f-spam").checked,
        ads: document.getElementById("f-ads").checked
      }
    };
    const res = await fetch("/api/save", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Telegram-Init-Data": tg.initData || ""
      },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (data.ok) {
      showToast("✅ Настройки сохранены!");
      await loadChats();
      closeEditor();
    } else {
      showToast("❌ Ошибка сохранения");
    }
  }

  loadChats();
</script>
</body>
</html>
"""
