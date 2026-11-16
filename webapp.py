"""Telegram Mini App: панель управления чатами и настройками."""
import hashlib
import hmac
import html
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


def _get_user_chats(user_id: int) -> list[int]:
    raw = db.get_setting(0, f"user_chats_{user_id}")
    if not raw:
        return []
    try:
        return [int(x) for x in json.loads(raw)]
    except Exception:
        return []


def register_user_chat(user_id: int, chat_id: int):
    chats = _get_user_chats(user_id)
    if chat_id not in chats:
        chats.append(chat_id)
        db.set_setting(0, f"user_chats_{user_id}", json.dumps(chats))


HTML_PAGE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Панель управления</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
  :root {
    --bg: var(--tg-theme-bg-color, #ffffff);
    --sec-bg: var(--tg-theme-secondary-bg-color, #f4f4f5);
    --text: var(--tg-theme-text-color, #18181b);
    --hint: var(--tg-theme-hint-color, #71717a);
    --btn: var(--tg-theme-button-color, #2481cc);
    --btn-text: var(--tg-theme-button-text-color, #ffffff);
  }
  * { box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
  body { margin: 0; padding: 16px; background: var(--bg); color: var(--text); }
  h2 { margin: 0 0 8px; font-size: 20px; }
  p.sub { margin: 0 0 16px; color: var(--hint); font-size: 14px; }
  .btn {
    display: block; width: 100%; padding: 12px; border: none; border-radius: 12px;
    background: var(--btn); color: var(--btn-text); font-size: 15px; font-weight: 600;
    text-align: center; text-decoration: none; cursor: pointer; margin-bottom: 12px;
  }
  .btn-sec { background: var(--sec-bg); color: var(--text); }
  .card {
    background: var(--sec-bg); border-radius: 14px; padding: 14px; margin-bottom: 12px;
  }
  .chat-item {
    display: flex; justify-content: space-between; align-items: center;
    padding: 12px; background: var(--sec-bg); border-radius: 12px; margin-bottom: 8px; cursor: pointer;
  }
  .chat-title { font-weight: 600; font-size: 15px; }
  .chat-id { font-size: 12px; color: var(--hint); }
  label { display: block; font-size: 13px; font-weight: 600; margin: 12px 0 6px; color: var(--hint); }
  textarea {
    width: 100%; min-height: 90px; padding: 10px; border-radius: 10px;
    border: 1px solid rgba(128,128,128,0.25); background: var(--bg); color: var(--text);
    font-size: 14px; resize: vertical;
  }
  .toggle-row {
    display: flex; justify-content: space-between; align-items: center;
    padding: 10px 0; border-bottom: 1px solid rgba(128,128,128,0.15);
  }
  .toggle-row:last-child { border-bottom: none; }
  .hidden { display: none; }
  .badge { font-size: 12px; padding: 3px 8px; border-radius: 8px; background: var(--btn); color: var(--btn-text); }
</style>
</head>
<body>

<div id="view-list">
  <h2>🛡 Панель управления</h2>
  <p class="sub">Выберите чат для настройки или добавьте бота в новую группу.</p>
  <a id="add-bot-link" class="btn" href="#" target="_blank">➕ Подключить бота в чат</a>
  <div id="chats-container"><p class="sub">Загрузка ваших чатов...</p></div>
</div>

<div id="view-edit" class="hidden">
  <button class="btn btn-sec" onclick="showList()">← Назад к списку чатов</button>
  <h2 id="edit-chat-title">Настройка чата</h2>
  <p class="sub" id="edit-chat-id"></p>

  <div class="card">
    <div class="toggle-row">
      <span>🤬 Антимат</span>
      <input type="checkbox" id="f_mat">
    </div>
    <div class="toggle-row">
      <span>🔗 Защита от ссылок</span>
      <input type="checkbox" id="f_links">
    </div>
    <div class="toggle-row">
      <span>⚡ Антифлуд</span>
      <input type="checkbox" id="f_flood">
    </div>
    <div class="toggle-row">
      <span>🎭 Лимит стикеров/гифок</span>
      <input type="checkbox" id="f_media">
    </div>
  </div>

  <div class="card">
    <label>📜 Правила чата</label>
    <textarea id="inp-rules" placeholder="Введите правила чата..."></textarea>

    <label>👋 Приветствие (переменные: {user}, {chat})</label>
    <textarea id="inp-welcome" placeholder="Оставьте пустым для стандартного приветствия"></textarea>

    <label>🚪 Прощание при выходе (переменная: {user})</label>
    <textarea id="inp-goodbye" placeholder="Оставьте пустым для стандартного прощания"></textarea>
  </div>

  <button class="btn" onclick="saveSettings()">💾 Сохранить изменения</button>
</div>

<script>
const tg = window.Telegram.WebApp;
tg.ready();
tg.expand();

let currentChatId = null;
const initData = tg.initData || "";

async function api(path, body = null) {
  const opts = {
    method: body ? "POST" : "GET",
    headers: { "Content-Type": "application/json", "X-Tg-Init-Data": initData }
  };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(path, opts);
  return await res.json();
}

async function loadChats() {
  const data = await api("/api/chats");
  if (data.bot_username) {
    document.getElementById("add-bot-link").href =
      `https://t.me/${data.bot_username}?startgroup=true&admin=change_info+delete_messages+restrict_members+invite_users+pin_messages`;
  }
  const box = document.getElementById("chats-container");
  if (!data.chats || data.chats.length === 0) {
    box.innerHTML = `<div class="card"><p style="margin:0;font-size:14px;">Пока нет подключённых чатов. Нажмите кнопку выше, чтобы добавить бота в группу и назначить его администратором.</p></div>`;
    return;
  }
  box.innerHTML = "";
  data.chats.forEach(c => {
    const el = document.createElement("div");
    el.className = "chat-item";
    el.innerHTML = `<div><div class="chat-title">${c.title}</div><div class="chat-id">ID: ${c.id}</div></div><span class="badge">Настроить</span>`;
    el.onclick = () => openChat(c.id, c.title);
    box.appendChild(el);
  });
}

async function openChat(chatId, title) {
  currentChatId = chatId;
  document.getElementById("view-list").classList.add("hidden");
  document.getElementById("view-edit").classList.remove("hidden");
  document.getElementById("edit-chat-title").innerText = title;
  document.getElementById("edit-chat-id").innerText = "ID: " + chatId;

  const data = await api(`/api/chat?chat_id=${chatId}`);
  document.getElementById("inp-rules").value = data.rules || "";
  document.getElementById("inp-welcome").value = data.welcome || "";
  document.getElementById("inp-goodbye").value = data.goodbye || "";
  document.getElementById("f_mat").checked = !!data.filters.mat;
  document.getElementById("f_links").checked = !!data.filters.links;
  document.getElementById("f_flood").checked = !!data.filters.flood;
  document.getElementById("f_media").checked = !!data.filters.media;
}

function showList() {
  currentChatId = null;
  document.getElementById("view-edit").classList.add("hidden");
  document.getElementById("view-list").classList.remove("hidden");
}

async function saveSettings() {
  if (!currentChatId) return;
  const payload = {
    chat_id: currentChatId,
    rules: document.getElementById("inp-rules").value,
    welcome: document.getElementById("inp-welcome").value,
    goodbye: document.getElementById("inp-goodbye").value,
    filters: {
      mat: document.getElementById("f_mat").checked,
      links: document.getElementById("f_links").checked,
      flood: document.getElementById("f_flood").checked,
      media: document.getElementById("f_media").checked,
    }
  };
  const res = await api("/api/chat/save", payload);
  if (res.ok) {
    tg.showAlert("✅ Настройки успешно сохранены!");
  } else {
    tg.showAlert("❌ Ошибка сохранения: " + (res.error || "нет доступа"));
  }
}

loadChats();
</script>
</body>
</html>
"""


async def handle_webapp_page(request: web.Request):
    return web.Response(text=HTML_PAGE, content_type="text/html")


async def handle_api_chats(request: web.Request):
    user = _verify_init_data(request.headers.get("X-Tg-Init-Data", ""))
    me = await bot.get_me()
    if not user:
        return web.json_response({"bot_username": me.username, "chats": []})
    user_id = int(user["id"])
    chat_ids = _get_user_chats(user_id)
    result = []
    for cid in chat_ids:
        try:
            chat = await bot.get_chat(cid)
            member = await bot.get_chat_member(cid, user_id)
            if member.status in ("administrator", "creator"):
                result.append({"id": cid, "title": html.escape(chat.title or f"Чат {cid}")})
        except Exception:
            continue
    return web.json_response({"bot_username": me.username, "chats": result})


async def handle_api_chat_get(request: web.Request):
    user = _verify_init_data(request.headers.get("X-Tg-Init-Data", ""))
    if not user:
        return web.json_response({"error": "unauthorized"}, status=401)
    chat_id = int(request.query.get("chat_id", "0"))
    member = await bot.get_chat_member(chat_id, int(user["id"]))
    if member.status not in ("administrator", "creator"):
        return web.json_response({"error": "forbidden"}, status=403)

    return web.json_response({
        "rules": db.get_setting(chat_id, "rules") or rules.DEFAULT_RULES,
        "welcome": db.get_setting(chat_id, "welcome_text") or "",
        "goodbye": db.get_setting(chat_id, "goodbye_text") or "",
        "filters": {
            "mat": db.filter_on(chat_id, "mat"),
            "links": db.filter_on(chat_id, "links"),
            "flood": db.filter_on(chat_id, "flood"),
            "media": db.filter_on(chat_id, "media"),
        }
    })


async def handle_api_chat_save(request: web.Request):
    user = _verify_init_data(request.headers.get("X-Tg-Init-Data", ""))
    if not user:
        return web.json_response({"ok": False, "error": "unauthorized"}, status=401)
    data = await request.json()
    chat_id = int(data.get("chat_id", 0))
    member = await bot.get_chat_member(chat_id, int(user["id"]))
    if member.status not in ("administrator", "creator"):
        return web.json_response({"ok": False, "error": "Нет прав администратора"}, status=403)

    rules_val = (data.get("rules") or "").strip()
    db.set_setting(chat_id, "rules", rules_val if rules_val else None)

    welcome_val = (data.get("welcome") or "").strip()
    db.set_setting(chat_id, "welcome_text", welcome_val if welcome_val else None)

    goodbye_val = (data.get("goodbye") or "").strip()
    db.set_setting(chat_id, "goodbye_text", goodbye_val if goodbye_val else None)

    filters = data.get("filters") or {}
    for kind in ("mat", "links", "flood", "media"):
        if kind in filters:
            db.set_setting(chat_id, "f_" + kind, "1" if filters[kind] else "0")

    return web.json_response({"ok": True})


def setup_routes(app: web.Application):
    app.router.add_get("/webapp", handle_webapp_page)
    app.router.add_get("/api/chats", handle_api_chats)
    app.router.add_get("/api/chat", handle_api_chat_get)
    app.router.add_post("/api/chat/save", handle_api_chat_save)
