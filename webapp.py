"""Telegram Mini App (WebApp) backend & UI."""
import hashlib
import hmac
import json
import logging
import urllib.parse
from aiohttp import web

import config
import db
import rules
from loader import bot

HTML_PAGE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Панель управления ботом</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
  :root {
    --bg: var(--tg-theme-bg-color, #18222d);
    --sec-bg: var(--tg-theme-secondary-bg-color, #212d3b);
    --text: var(--tg-theme-text-color, #ffffff);
    --hint: var(--tg-theme-hint-color, #8b9bb4);
    --btn: var(--tg-theme-button-color, #2ea6ff);
    --btn-text: var(--tg-theme-button-text-color, #ffffff);
    --border: rgba(255,255,255,0.08);
  }
  * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
  body { background: var(--bg); color: var(--text); padding-bottom: 76px; -webkit-tap-highlight-color: transparent; }
  .header { padding: 16px; background: var(--sec-bg); border-bottom: 1px solid var(--border); position: sticky; top: 0; z-index: 10; }
  .header h1 { font-size: 18px; font-weight: 700; }
  .header p { font-size: 13px; color: var(--hint); margin-top: 2px; }
  .container { padding: 14px; }
  .stats-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 16px; }
  .stat-card { background: var(--sec-bg); padding: 14px; border-radius: 14px; border: 1px solid var(--border); }
  .stat-val { font-size: 22px; font-weight: 700; color: var(--btn); }
  .stat-lbl { font-size: 12px; color: var(--hint); margin-top: 4px; }
  .card { background: var(--sec-bg); border-radius: 14px; padding: 14px; margin-bottom: 12px; border: 1px solid var(--border); }
  .card-title { font-size: 15px; font-weight: 600; margin-bottom: 6px; display: flex; justify-content: space-between; align-items: center; }
  .card-sub { font-size: 13px; color: var(--hint); line-height: 1.4; }
  .btn { display: block; width: 100%; background: var(--btn); color: var(--btn-text); border: none; border-radius: 12px; padding: 13px; font-size: 15px; font-weight: 600; text-align: center; text-decoration: none; cursor: pointer; margin-top: 10px; }
  .btn-outline { background: transparent; border: 1px solid var(--btn); color: var(--btn); }
  .chat-item { display: flex; justify-content: space-between; align-items: center; padding: 14px; background: var(--sec-bg); border-radius: 14px; margin-bottom: 10px; border: 1px solid var(--border); cursor: pointer; }
  .chat-item:active { opacity: 0.7; }
  .badge { background: rgba(46, 166, 255, 0.15); color: var(--btn); padding: 4px 8px; border-radius: 8px; font-size: 12px; font-weight: 600; }
  .toggle-row { display: flex; justify-content: space-between; align-items: center; padding: 12px 0; border-bottom: 1px solid var(--border); }
  .toggle-row:last-child { border-bottom: none; }
  .switch { position: relative; display: inline-block; width: 46px; height: 26px; }
  .switch input { opacity: 0; width: 0; height: 0; }
  .slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: #4a5568; transition: .2s; border-radius: 26px; }
  .slider:before { position: absolute; content: ""; height: 20px; width: 20px; left: 3px; bottom: 3px; background-color: white; transition: .2s; border-radius: 50%; }
  input:checked + .slider { background-color: var(--btn); }
  input:checked + .slider:before { transform: translateX(20px); }
  textarea { width: 100%; background: var(--bg); color: var(--text); border: 1px solid var(--border); border-radius: 10px; padding: 10px; font-size: 14px; min-height: 90px; margin-top: 8px; resize: vertical; }
  label { font-size: 13px; color: var(--hint); font-weight: 600; display: block; margin-top: 12px; }
  .nav { position: fixed; bottom: 0; left: 0; right: 0; background: var(--sec-bg); border-top: 1px solid var(--border); display: flex; height: 62px; z-index: 20; }
  .nav-btn { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; color: var(--hint); font-size: 11px; gap: 4px; border: none; background: none; cursor: pointer; }
  .nav-btn.active { color: var(--btn); font-weight: 600; }
  .nav-icon { font-size: 20px; }
  .hidden { display: none !important; }
  .back-btn { background: none; border: none; color: var(--btn); font-size: 15px; font-weight: 600; cursor: pointer; margin-bottom: 10px; display: flex; align-items: center; gap: 4px; }
  .toast { position: fixed; top: 16px; left: 50%; transform: translateX(-50%); background: #2ea6ff; color: #fff; padding: 10px 18px; border-radius: 20px; font-size: 14px; font-weight: 600; z-index: 100; box-shadow: 0 4px 12px rgba(0,0,0,0.3); }
</style>
</head>
<body>

<div id="toast" class="toast hidden">Сохранено!</div>

<div class="header">
  <h1 id="page-title">🛡 Панель управления</h1>
  <p id="page-sub">Управление вашими чатами и защитой</p>
</div>

<!-- Вкладка 1: Мои чаты -->
<div id="tab-chats" class="container">
  <div class="stats-grid">
    <div class="stat-card">
      <div class="stat-val" id="stat-chats">0</div>
      <div class="stat-lbl">Подключено чатов</div>
    </div>
    <div class="stat-card">
      <div class="stat-val">24/7</div>
      <div class="stat-lbl">Статус защиты</div>
    </div>
  </div>

  <div id="chats-list">
    <div class="card"><div class="card-sub">Загрузка списка чатов...</div></div>
  </div>
</div>

<!-- Вкладка 2: Подключение -->
<div id="tab-connect" class="container hidden">
  <div class="card">
    <div class="card-title">➕ Добавить бота в новую группу</div>
    <div class="card-sub">
      Нажмите кнопку ниже, выберите нужный чат и выдайте боту права администратора (удаление сообщений, блокировка участников, приглашение по ссылкам).
    </div>
    <a id="add-bot-link" href="#" class="btn" target="_blank">Выбрать группу в Telegram</a>
  </div>
  <div class="card">
    <div class="card-title">ℹ️ Как привязать уже добавленный чат?</div>
    <div class="card-sub">
      Если бот уже есть в группе, но не отображается во вкладке «Мои чаты» — просто снимите с него права администратора и выдайте заново, либо напишите в чат команду <b>/status</b>.
    </div>
  </div>
</div>

<!-- Экран редактирования конкретного чата -->
<div id="tab-edit" class="container hidden">
  <button class="back-btn" onclick="closeEdit()">← Назад к списку чатов</button>
  <div class="card">
    <div class="card-title" id="edit-chat-name">Настройки чата</div>
    <div class="card-sub" id="edit-chat-id">ID: 0</div>
  </div>

  <div class="card">
    <div class="card-title">🛡 Модули автомодерации</div>
    <div class="toggle-row">
      <span>Фильтр мата</span>
      <label class="switch"><input type="checkbox" id="f_mat"><span class="slider"></span></label>
    </div>
    <div class="toggle-row">
      <span>Антиспам (стикеры / гифки)</span>
      <label class="switch"><input type="checkbox" id="f_spam"><span class="slider"></span></label>
    </div>
    <div class="toggle-row">
      <span>Защита от рекламы (t.me / ссылки)</span>
      <label class="switch"><input type="checkbox" id="f_links"><span class="slider"></span></label>
    </div>
    <div class="toggle-row">
      <span>Антифлуд (частые сообщения)</span>
      <label class="switch"><input type="checkbox" id="f_flood"><span class="slider"></span></label>
    </div>
  </div>

  <div class="card">
    <div class="card-title">📝 Тексты и правила</div>
    <label>Правила чата (команда /rules)</label>
    <textarea id="inp-rules" placeholder="Введите правила чата..."></textarea>

    <label>Приветствие (можно использовать {user} и {chat})</label>
    <textarea id="inp-welcome" placeholder="Оставьте пустым для стандартного текста"></textarea>

    <label>Прощание при выходе (можно {user} и {chat})</label>
    <textarea id="inp-goodbye" placeholder="Оставьте пустым для стандартного текста"></textarea>

    <button class="btn" onclick="saveChatSettings()">💾 Сохранить изменения</button>
  </div>
</div>

<!-- Нижняя навигация -->
<div class="nav" id="bottom-nav">
  <button class="nav-btn active" id="nav-chats" onclick="switchTab('chats')">
    <span class="nav-icon">💬</span>
    <span>Мои чаты</span>
  </button>
  <button class="nav-btn" id="nav-connect" onclick="switchTab('connect')">
    <span class="nav-icon">➕</span>
    <span>Подключить</span>
  </button>
</div>

<script>
  const tg = window.Telegram.WebApp;
  tg.ready();
  tg.expand();

  let currentChatId = null;
  let chatsData = [];

  function showToast(msg) {
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.classList.remove('hidden');
    setTimeout(() => t.classList.add('hidden'), 2200);
  }

  function switchTab(tab) {
    document.getElementById('tab-chats').classList.add('hidden');
    document.getElementById('tab-connect').classList.add('hidden');
    document.getElementById('tab-edit').classList.add('hidden');
    document.getElementById('nav-chats').classList.remove('active');
    document.getElementById('nav-connect').classList.remove('active');

    if (tab === 'chats') {
      document.getElementById('tab-chats').classList.remove('hidden');
      document.getElementById('nav-chats').classList.add('active');
      document.getElementById('page-title').textContent = '🛡 Панель управления';
      document.getElementById('page-sub').textContent = 'Управление вашими чатами и защитой';
    } else if (tab === 'connect') {
      document.getElementById('tab-connect').classList.remove('hidden');
      document.getElementById('nav-connect').classList.add('active');
      document.getElementById('page-title').textContent = '➕ Подключение';
      document.getElementById('page-sub').textContent = 'Добавление бота в новые группы';
    }
  }

  async function loadData() {
    try {
      const res = await fetch('/api/chats', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ initData: tg.initData })
      });
      const data = await res.json();
      if (data.bot_username) {
        const url = `https://t.me/${data.bot_username}?startgroup=true&admin=change_info+delete_messages+restrict_members+invite_users+pin_messages`;
        document.getElementById('add-bot-link').href = url;
      }
      chatsData = data.chats || [];
      document.getElementById('stat-chats').textContent = chatsData.length;
      renderChats();
    } catch (e) {
      document.getElementById('chats-list').innerHTML = '<div class="card"><div class="card-sub">Ошибка загрузки данных. Откройте приложение через меню бота.</div></div>';
    }
  }

  function renderChats() {
    const list = document.getElementById('chats-list');
    if (!chatsData.length) {
      list.innerHTML = `
        <div class="card">
          <div class="card-title">Пока нет подключённых чатов</div>
          <div class="card-sub">Нажмите «Подключить» внизу экрана, чтобы добавить бота в вашу группу.</div>
          <button class="btn" onclick="switchTab('connect')">➕ Подключить первый чат</button>
        </div>`;
      return;
    }
    list.innerHTML = chatsData.map(c => `
      <div class="chat-item" onclick="openEdit(${c.chat_id})">
        <div>
          <div style="font-weight:600; font-size:15px;">${c.title}</div>
          <div style="font-size:12px; color:var(--hint); margin-top:3px;">ID: ${c.chat_id}</div>
        </div>
        <span class="badge">Настроить ›</span>
      </div>
    `).join('');
  }

  function openEdit(chatId) {
    currentChatId = chatId;
    const chat = chatsData.find(c => c.chat_id === chatId);
    if (!chat) return;

    document.getElementById('tab-chats').classList.add('hidden');
    document.getElementById('bottom-nav').classList.add('hidden');
    document.getElementById('tab-edit').classList.remove('hidden');

    document.getElementById('page-title').textContent = '⚙️ Настройка чата';
    document.getElementById('page-sub').textContent = chat.title;
    document.getElementById('edit-chat-name').textContent = chat.title;
    document.getElementById('edit-chat-id').textContent = 'ID: ' + chat.chat_id;

    document.getElementById('f_mat').checked = chat.filters.mat;
    document.getElementById('f_spam').checked = chat.filters.spam;
    document.getElementById('f_links').checked = chat.filters.links;
    document.getElementById('f_flood').checked = chat.filters.flood;

    document.getElementById('inp-rules').value = chat.rules || '';
    document.getElementById('inp-welcome').value = chat.welcome || '';
    document.getElementById('inp-goodbye').value = chat.goodbye || '';
  }

  function closeEdit() {
    currentChatId = null;
    document.getElementById('tab-edit').classList.add('hidden');
    document.getElementById('bottom-nav').classList.remove('hidden');
    switchTab('chats');
  }

  async function saveChatSettings() {
    if (!currentChatId) return;
    const payload = {
      initData: tg.initData,
      chat_id: currentChatId,
      filters: {
        mat: document.getElementById('f_mat').checked,
        spam: document.getElementById('f_spam').checked,
        links: document.getElementById('f_links').checked,
        flood: document.getElementById('f_flood').checked
      },
      rules: document.getElementById('inp-rules').value,
      welcome: document.getElementById('inp-welcome').value,
      goodbye: document.getElementById('inp-goodbye').value
    };
    try {
      const res = await fetch('/api/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (data.ok) {
        showToast('✅ Настройки сохранены!');
        await loadData();
      } else {
        showToast('❌ Ошибка сохранения');
      }
    } catch (e) {
      showToast('❌ Ошибка сети');
    }
  }

  loadData();
</script>
</body>
</html>
"""


def _verify_init_data(init_data: str) -> int | None:
    if not init_data:
        return None
    try:
        parsed = dict(urllib.parse.parse_qsl(init_data, strict_parsing=True))
        received_hash = parsed.pop("hash", None)
        if not received_hash:
            return None
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
        secret_key = hmac.new(b"WebAppData", config.BOT_TOKEN.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calculated_hash, received_hash):
            return None
        user_obj = json.loads(parsed.get("user", "{}"))
        return int(user_obj.get("id"))
    except Exception as e:
        logging.warning("Ошибка проверки initData: %s", e)
        return None


def _ensure_table():
    db._db.execute(
        "CREATE TABLE IF NOT EXISTS user_chats (user_id BIGINT, chat_id BIGINT, title TEXT, PRIMARY KEY(user_id, chat_id))"
    )


async def handle_webapp(request: web.Request) -> web.Response:
    return web.Response(text=HTML_PAGE, content_type="text/html")


async def handle_get_chats(request: web.Request) -> web.Response:
    _ensure_table()
    body = await request.json()
    user_id = _verify_init_data(body.get("initData", ""))
    me = await bot.get_me()
    if not user_id:
        return web.json_response({"ok": False, "bot_username": me.username, "chats": []})

    rows = db._db.execute("SELECT chat_id, title FROM user_chats WHERE user_id=%s", (user_id,)).fetchall()
    chats = []
    for cid, title in rows:
        chats.append({
            "chat_id": cid,
            "title": title or f"Чат {cid}",
            "filters": {
                "mat": db.filter_on(cid, "mat"),
                "spam": db.filter_on(cid, "spam"),
                "links": db.filter_on(cid, "links"),
                "flood": db.filter_on(cid, "flood"),
            },
            "rules": rules.get_rules(cid),
            "welcome": db.get_setting(cid, "custom_welcome") or "",
            "goodbye": db.get_setting(cid, "custom_goodbye") or "",
        })
    return web.json_response({"ok": True, "bot_username": me.username, "chats": chats})


async def handle_save_chat(request: web.Request) -> web.Response:
    _ensure_table()
    body = await request.json()
    user_id = _verify_init_data(body.get("initData", ""))
    chat_id = int(body.get("chat_id", 0))
    if not user_id or not chat_id:
        return web.json_response({"ok": False})

    owner = db._db.execute(
        "SELECT 1 FROM user_chats WHERE user_id=%s AND chat_id=%s", (user_id, chat_id)
    ).fetchone()
    if not owner:
        return web.json_response({"ok": False})

    filters = body.get("filters", {})
    for kind in ("mat", "spam", "links", "flood"):
        if kind in filters:
            db.set_setting(chat_id, f"f_{kind}", "1" if filters[kind] else "0")

    new_rules = body.get("rules", "").strip()
    db.set_setting(chat_id, "rules", new_rules if new_rules else None)

    new_welcome = body.get("welcome", "").strip()
    db.set_setting(chat_id, "custom_welcome", new_welcome if new_welcome else None)

    new_goodbye = body.get("goodbye", "").strip()
    db.set_setting(chat_id, "custom_goodbye", new_goodbye if new_goodbye else None)

    return web.json_response({"ok": True})


def setup_routes(app: web.Application):
    app.router.add_get("/webapp", handle_webapp)
    app.router.add_post("/api/chats", handle_get_chats)
    app.router.add_post("/api/save", handle_save_chat)
