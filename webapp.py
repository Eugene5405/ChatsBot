"""Telegram Mini App: полноэкранный интерфейс управления чатами, фильтрами, правилами и приветствиями."""
import hashlib
import hmac
import json
import os
from urllib.parse import parse_qsl

from aiohttp import web

import config
import db
import rules
from loader import bot

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()


def _verify_init_data(init_data: str) -> int | None:
    if not init_data or not BOT_TOKEN:
        return None
    try:
        parsed = dict(parse_qsl(init_data, strict_parsing=True))
    except ValueError:
        return None
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
        user_data = json.loads(user_raw)
        return int(user_data["id"])
    except (json.JSONDecodeError, KeyError, ValueError):
        return None


def _get_user_chats(user_id: int) -> list[dict]:
    rows = db._db.execute(
        "SELECT chat_id, key, value FROM settings WHERE key LIKE 'owner_%' OR key = 'chat_title'"
    ).fetchall()
    titles = {}
    owned = set()
    for cid, k, v in rows:
        if k == "chat_title":
            titles[cid] = v
        elif k == f"owner_{user_id}" and v == "1":
            owned.add(cid)
    return [{"id": cid, "title": titles.get(cid, f"Чат {cid}")} for cid in sorted(owned)]


def _is_owner(user_id: int, chat_id: int) -> bool:
    return db.get_setting(chat_id, f"owner_{user_id}") == "1"


async def handle_webapp_page(request: web.Request) -> web.Response:
    me = await bot.get_me()
    bot_username = me.username or "chat_custodian_bot"
    html_page = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Панель управления чатами</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
  :root {{
    --bg: var(--tg-theme-bg-color, #f4f4f5);
    --sec-bg: var(--tg-theme-secondary-bg-color, #ffffff);
    --text: var(--tg-theme-text-color, #18181b);
    --hint: var(--tg-theme-hint-color, #71717a);
    --btn: var(--tg-theme-button-color, #2563eb);
    --btn-text: var(--tg-theme-button-text-color, #ffffff);
    --border: rgba(128, 128, 128, 0.16);
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
  body {{ background: var(--bg); color: var(--text); padding-bottom: 84px; -webkit-tap-highlight-color: transparent; }}
  .header {{
    background: var(--sec-bg);
    padding: 16px;
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    justify-content: space-between;
    position: sticky;
    top: 0;
    z-index: 10;
  }}
  .header h1 {{ font-size: 18px; font-weight: 700; }}
  .badge {{ background: var(--btn); color: var(--btn-text); font-size: 11px; padding: 3px 8px; border-radius: 12px; font-weight: 600; }}
  .container {{ padding: 14px; max-width: 600px; margin: 0 auto; }}
  .stats-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 16px; }}
  .stat-card {{
    background: var(--sec-bg);
    padding: 14px;
    border-radius: 14px;
    border: 1px solid var(--border);
  }}
  .stat-val {{ font-size: 22px; font-weight: 700; color: var(--btn); }}
  .stat-lbl {{ font-size: 12px; color: var(--hint); margin-top: 4px; }}
  .card {{
    background: var(--sec-bg);
    border-radius: 14px;
    padding: 16px;
    margin-bottom: 14px;
    border: 1px solid var(--border);
  }}
  .card-title {{ font-size: 15px; font-weight: 700; margin-bottom: 10px; display: flex; align-items: center; gap: 8px; }}
  .chat-item {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px;
    background: var(--bg);
    border-radius: 12px;
    margin-bottom: 8px;
    cursor: pointer;
  }}
  .chat-item:last-child {{ margin-bottom: 0; }}
  .chat-name {{ font-weight: 600; font-size: 15px; }}
  .chat-id {{ font-size: 12px; color: var(--hint); }}
  .btn {{
    display: block;
    width: 100%;
    padding: 13px;
    background: var(--btn);
    color: var(--btn-text);
    border: none;
    border-radius: 12px;
    font-size: 15px;
    font-weight: 600;
    text-align: center;
    text-decoration: none;
    cursor: pointer;
    margin-top: 8px;
  }}
  .btn-outline {{
    background: transparent;
    color: var(--btn);
    border: 1.5px solid var(--btn);
  }}
  .toggle-row {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 11px 0;
    border-bottom: 1px solid var(--border);
  }}
  .toggle-row:last-child {{ border-bottom: none; }}
  .switch {{ position: relative; display: inline-block; width: 46px; height: 26px; }}
  .switch input {{ opacity: 0; width: 0; height: 0; }}
  .slider {{
    position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0;
    background-color: #cbd5e1; transition: .25s; border-radius: 26px;
  }}
  .slider:before {{
    position: absolute; content: ""; height: 20px; width: 20px; left: 3px; bottom: 3px;
    background-color: white; transition: .25s; border-radius: 50%;
  }}
  input:checked + .slider {{ background-color: var(--btn); }}
  input:checked + .slider:before {{ transform: translateX(20px); }}
  textarea {{
    width: 100%;
    min-height: 90px;
    padding: 10px;
    border-radius: 10px;
    border: 1px solid var(--border);
    background: var(--bg);
    color: var(--text);
    font-size: 14px;
    resize: vertical;
    margin-bottom: 8px;
  }}
  .hint-box {{ font-size: 12px; color: var(--hint); margin-bottom: 8px; line-height: 1.4; }}
  .bottom-nav {{
    position: fixed;
    bottom: 0; left: 0; right: 0;
    background: var(--sec-bg);
    border-top: 1px solid var(--border);
    display: flex;
    height: 64px;
    z-index: 20;
  }}
  .nav-item {{
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    font-size: 11px;
    color: var(--hint);
    cursor: pointer;
    gap: 4px;
  }}
  .nav-item.active {{ color: var(--btn); font-weight: 700; }}
  .nav-icon {{ font-size: 20px; }}
  .hidden {{ display: none !important; }}
  .step {{ display: flex; gap: 10px; margin-bottom: 12px; align-items: flex-start; }}
  .step-num {{
    min-width: 24px; height: 24px; border-radius: 50%; background: var(--btn);
    color: var(--btn-text); font-size: 13px; font-weight: 700;
    display: flex; align-items: center; justify-content: center;
  }}
</style>
</head>
<body>

<div class="header">
  <h1 id="headerTitle">🛡️ Чат-менеджер</h1>
  <span class="badge">24/7 ONLINE</span>
</div>

<div class="container">
  <!-- ВКЛАДКА 1: МОИ ЧАТЫ -->
  <div id="tabChats">
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-val" id="statChats">0</div>
        <div class="stat-lbl">Подключено чатов</div>
      </div>
      <div class="stat-card">
        <div class="stat-val">4</div>
        <div class="stat-lbl">Модуля защиты</div>
      </div>
    </div>

    <div class="card">
      <div class="card-title">💬 Ваши группы</div>
      <div id="chatsList">Загрузка списка чатов...</div>
      <a class="btn" href="https://t.me/{bot_username}?startgroup=true&admin=change_info+delete_messages+restrict_members+invite_users+pin_messages" target="_blank">
        ➕ Подключить новый чат
      </a>
    </div>
  </div>

  <!-- РЕДАКТОР КОНКРЕТНОГО ЧАТА -->
  <div id="tabEditor" class="hidden">
    <button class="btn btn-outline" style="margin-bottom: 12px; margin-top: 0;" onclick="closeEditor()">← Назад к списку чатов</button>

    <div class="card">
      <div class="card-title">🛡️ Фильтры автомодерации</div>
      <div class="toggle-row">
        <span>🤬 Фильтр мата и оскорблений</span>
        <label class="switch"><input type="checkbox" id="f_mat" onchange="saveFilter('mat')"><span class="slider"></span></label>
      </div>
      <div class="toggle-row">
        <span>🔗 Защита от рекламы и ссылок</span>
        <label class="switch"><input type="checkbox" id="f_ads" onchange="saveFilter('ads')"><span class="slider"></span></label>
      </div>
      <div class="toggle-row">
        <span>⚡ Антифлуд (частые сообщения)</span>
        <label class="switch"><input type="checkbox" id="f_flood" onchange="saveFilter('flood')"><span class="slider"></span></label>
      </div>
      <div class="toggle-row">
        <span>🎭 Спам стикерами и GIF</span>
        <label class="switch"><input type="checkbox" id="f_media" onchange="saveFilter('media')"><span class="slider"></span></label>
      </div>
    </div>

    <div class="card">
      <div class="card-title">📜 Правила чата</div>
      <textarea id="txtRules" placeholder="Введите правила группы..."></textarea>
      <button class="btn" onclick="saveText('rules')">💾 Сохранить правила</button>
    </div>

    <div class="card">
      <div class="card-title">👋 Приветствие новичков</div>
      <div class="hint-box">Доступные теги: <b>{{user}}</b> — имя новичка, <b>{{chat}}</b> — название чата.</div>
      <textarea id="txtWelcome" placeholder="Оставьте пустым для стандартного приветствия..."></textarea>
      <button class="btn" onclick="saveText('welcome')">💾 Сохранить приветствие</button>
    </div>

    <div class="card">
      <div class="card-title">🚪 Прощание при выходе</div>
      <div class="hint-box">Отправляется, когда участник сам покидает чат. Теги: <b>{{user}}</b>, <b>{{chat}}</b>.</div>
      <textarea id="txtGoodbye" placeholder="Оставьте пустым для стандартного прощания..."></textarea>
      <button class="btn" onclick="saveText('goodbye')">💾 Сохранить прощание</button>
    </div>
  </div>

  <!-- ВКЛАДКА 2: ИНСТРУКЦИЯ ПО ПОДКЛЮЧЕНИЮ -->
  <div id="tabConnect" class="hidden">
    <div class="card">
      <div class="card-title">🚀 Как подключить бота в группу</div>
      <div class="step">
        <div class="step-num">1</div>
        <div>Нажмите кнопку <b>«Добавить бота в чат»</b> ниже и выберите нужную группу.</div>
      </div>
      <div class="step">
        <div class="step-num">2</div>
        <div>Обязательно выдайте боту <b>права администратора</b> (удаление сообщений, бан, приглашение пользователей, закрепление).</div>
      </div>
      <div class="step">
        <div class="step-num">3</div>
        <div>После добавления бот пришлёт вам уведомление в личку, а чат сразу появится во вкладке <b>«Мои чаты»</b>.</div>
      </div>
      <a class="btn" href="https://t.me/{bot_username}?startgroup=true&admin=change_info+delete_messages+restrict_members+invite_users+pin_messages" target="_blank">
        ➕ Добавить бота в чат
      </a>
    </div>

    <div class="card">
      <div class="card-title">📌 Полезные команды в чате</div>
      <div class="hint-box" style="font-size: 13px; color: var(--text);">
        • <b>/status</b> — проверка прав бота в группе<br>
        • <b>/settings</b> — быстрая настройка фильтров<br>
        • <b>/rules</b> — показать правила чата<br>
        • <b>Пред / Мут 1д / Бан</b> — ответом на сообщение нарушителя
      </div>
    </div>
  </div>
</div>

<div class="bottom-nav">
  <div class="nav-item active" id="navChats" onclick="switchTab('chats')">
    <span class="nav-icon">💬</span>
    <span>Мои чаты</span>
  </div>
  <div class="nav-item" id="navConnect" onclick="switchTab('connect')">
    <span class="nav-icon">➕</span>
    <span>Подключение</span>
  </div>
</div>

<script>
  const tg = window.Telegram.WebApp;
  tg.ready();
  tg.expand();

  let currentChatId = null;

  function switchTab(tab) {{
    document.getElementById('tabChats').classList.add('hidden');
    document.getElementById('tabConnect').classList.add('hidden');
    document.getElementById('tabEditor').classList.add('hidden');
    document.getElementById('navChats').classList.remove('active');
    document.getElementById('navConnect').classList.remove('active');

    if (tab === 'chats') {{
      document.getElementById('tabChats').classList.remove('hidden');
      document.getElementById('navChats').classList.add('active');
      document.getElementById('headerTitle').innerText = '🛡️ Чат-менеджер';
    }} else if (tab === 'connect') {{
      document.getElementById('tabConnect').classList.remove('hidden');
      document.getElementById('navConnect').classList.add('active');
      document.getElementById('headerTitle').innerText = '➕ Подключение';
    }}
  }}

  async function api(path, body = {{}}) {{
    const res = await fetch(path, {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ initData: tg.initData, ...body }})
    }});
    return await res.json();
  }}

  async function loadChats() {{
    const data = await api('/api/chats');
    const list = document.getElementById('chatsList');
    if (!data.ok) {{
      list.innerHTML = '<div class="hint-box">Ошибка авторизации. Откройте приложение через кнопку внутри Telegram.</div>';
      return;
    }}
    document.getElementById('statChats').innerText = data.chats.length;
    if (data.chats.length === 0) {{
      list.innerHTML = '<div class="hint-box">У вас пока нет подключённых чатов. Нажмите кнопку ниже, чтобы добавить бота в группу.</div>';
      return;
    }}
    list.innerHTML = data.chats.map(c => `
      <div class="chat-item" onclick="openEditor(${{c.id}}, '${{c.title.replace(/'/g, "\\'")}}')">
        <div>
          <div class="chat-name">${{c.title}}</div>
          <div class="chat-id">ID: ${{c.id}}</div>
        </div>
        <span style="color: var(--btn); font-weight: 700;">Настроить →</span>
      </div>
    `).join('');
  }}

  async function openEditor(chatId, title) {{
    currentChatId = chatId;
    document.getElementById('tabChats').classList.add('hidden');
    document.getElementById('tabEditor').classList.remove('hidden');
    document.getElementById('headerTitle').innerText = title;

    const data = await api('/api/chat_settings', {{ chat_id: chatId }});
    if (data.ok) {{
      document.getElementById('f_mat').checked = data.filters.mat;
      document.getElementById('f_ads').checked = data.filters.ads;
      document.getElementById('f_flood').checked = data.filters.flood;
      document.getElementById('f_media').checked = data.filters.media;
      document.getElementById('txtRules').value = data.rules || '';
      document.getElementById('txtWelcome').value = data.welcome || '';
      document.getElementById('txtGoodbye').value = data.goodbye || '';
    }}
  }}

  function closeEditor() {{
    currentChatId = null;
    switchTab('chats');
    loadChats();
  }}

  async function saveFilter(kind) {{
    if (!currentChatId) return;
    const val = document.getElementById('f_' + kind).checked;
    await api('/api/save_filter', {{ chat_id: currentChatId, kind, value: val }});
    if (tg.HapticFeedback) tg.HapticFeedback.impactOccurred('light');
  }}

  async function saveText(field) {{
    if (!currentChatId) return;
    const map = {{ rules: 'txtRules', welcome: 'txtWelcome', goodbye: 'txtGoodbye' }};
    const text = document.getElementById(map[field]).value;
    const res = await api('/api/save_text', {{ chat_id: currentChatId, field, text }});
    if (res.ok) {{
      tg.showAlert('✅ Настройки успешно сохранены!');
    }}
  }}

  loadChats();
</script>
</body>
</html>"""
    return web.Response(text=html_page, content_type="text/html")


async def api_chats(request: web.Request) -> web.Response:
    data = await request.json()
    uid = _verify_init_data(data.get("initData", ""))
    if not uid:
        return web.json_response({"ok": False, "error": "unauthorized"})
    return web.json_response({"ok": True, "chats": _get_user_chats(uid)})


async def api_chat_settings(request: web.Request) -> web.Response:
    data = await request.json()
    uid = _verify_init_data(data.get("initData", ""))
    chat_id = int(data.get("chat_id", 0))
    if not uid or not _is_owner(uid, chat_id):
        return web.json_response({"ok": False})
    filters = {k: db.filter_on(chat_id, k) for k in ("mat", "ads", "flood", "media")}
    return web.json_response({
        "ok": True,
        "filters": filters,
        "rules": db.get_setting(chat_id, "rules") or rules.DEFAULT_RULES,
        "welcome": db.get_setting(chat_id, "welcome_text") or "",
        "goodbye": db.get_setting(chat_id, "goodbye_text") or "",
    })


async def api_save_filter(request: web.Request) -> web.Response:
    data = await request.json()
    uid = _verify_init_data(data.get("initData", ""))
    chat_id = int(data.get("chat_id", 0))
    kind = data.get("kind", "")
    if not uid or not _is_owner(uid, chat_id) or kind not in config.FILTER_DEFAULTS:
        return web.json_response({"ok": False})
    db.set_setting(chat_id, "f_" + kind, "1" if data.get("value") else "0")
    return web.json_response({"ok": True})


async def api_save_text(request: web.Request) -> web.Response:
    data = await request.json()
    uid = _verify_init_data(data.get("initData", ""))
    chat_id = int(data.get("chat_id", 0))
    field = data.get("field", "")
    text = (data.get("text") or "").strip()
    if not uid or not _is_owner(uid, chat_id):
        return web.json_response({"ok": False})
    key_map = {"rules": "rules", "welcome": "welcome_text", "goodbye": "goodbye_text"}
    if field in key_map:
        db.set_setting(chat_id, key_map[field], text if text else None)
    return web.json_response({"ok": True})


def setup_webapp_routes(app: web.Application):
    app.router.add_get("/webapp", handle_webapp_page)
    app.router.add_post("/api/chats", api_chats)
    app.router.add_post("/api/chat_settings", api_chat_settings)
    app.router.add_post("/api/save_filter", api_save_filter)
    app.router.add_post("/api/save_text", api_save_text)
