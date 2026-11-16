"""Telegram Mini App: интерфейс и API."""
import hashlib
import hmac
import json
from urllib.parse import parse_qsl

from aiohttp import web

import config
import db
import rules
from loader import bot


def _verify_init_data(init_data: str) -> int | None:
    if not init_data:
        return None
    parsed = dict(parse_qsl(init_data, strict_parsing=False))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        return None
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", config.BOT_TOKEN.encode(), hashlib.sha256).digest()
    calc_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc_hash, received_hash):
        return None
    user_raw = parsed.get("user")
    if not user_raw:
        return None
    try:
        return int(json.loads(user_raw)["id"])
    except Exception:
        return None


def _get_chats(user_id: int) -> dict[str, str]:
    raw = db.get_setting(0, f"owner_chats_{user_id}")
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


async def handle_index(request: web.Request) -> web.Response:
    me = await bot.get_me()
    rights = "change_info+delete_messages+restrict_members+invite_users+pin_messages+manage_chat"
    add_url = f"https://t.me/{me.username}?startgroup=true&admin={rights}"
    html_page = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<title>Панель управления</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
  :root {{
    --bg: var(--tg-theme-bg-color, #18222d);
    --sec: var(--tg-theme-secondary-bg-color, #212d3b);
    --text: var(--tg-theme-text-color, #ffffff);
    --hint: var(--tg-theme-hint-color, #8b9bb4);
    --btn: var(--tg-theme-button-color, #2ea6ff);
    --btn-text: var(--tg-theme-button-text-color, #ffffff);
  }}
  * {{ box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
  body {{ margin: 0; padding: 16px 16px 84px; background: var(--bg); color: var(--text); }}
  .header {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }}
  .header h1 {{ font-size: 20px; margin: 0; }}
  .badge {{ background: var(--sec); color: var(--btn); padding: 4px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; }}
  .stats {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 16px; }}
  .stat-box {{ background: var(--sec); padding: 14px; border-radius: 14px; }}
  .stat-val {{ font-size: 22px; font-weight: 700; color: var(--btn); }}
  .stat-lbl {{ font-size: 12px; color: var(--hint); margin-top: 4px; }}
  .card {{ background: var(--sec); border-radius: 14px; padding: 14px; margin-bottom: 12px; }}
  .card-title {{ font-weight: 600; font-size: 16px; margin-bottom: 6px; }}
  .card-sub {{ font-size: 13px; color: var(--hint); line-height: 1.4; }}
  .chat-item {{ display: flex; align-items: center; justify-content: space-between; background: var(--sec); padding: 14px; border-radius: 14px; margin-bottom: 10px; cursor: pointer; }}
  .btn {{ display: block; width: 100%; text-align: center; background: var(--btn); color: var(--btn-text); border: none; padding: 13px; border-radius: 12px; font-size: 15px; font-weight: 600; text-decoration: none; cursor: pointer; margin-top: 10px; }}
  .btn-sec {{ background: var(--sec); color: var(--text); }}
  .row {{ display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid rgba(128,128,128,0.15); }}
  .row:last-child {{ border-bottom: none; }}
  textarea {{ width: 100%; min-height: 85px; background: var(--bg); color: var(--text); border: 1px solid rgba(128,128,128,0.3); border-radius: 10px; padding: 10px; font-size: 14px; margin-top: 6px; resize: vertical; }}
  label {{ font-size: 13px; color: var(--hint); display: block; margin-top: 10px; }}
  .nav {{ position: fixed; bottom: 0; left: 0; right: 0; background: var(--sec); display: flex; border-top: 1px solid rgba(128,128,128,0.15); padding: 8px 0; }}
  .nav-item {{ flex: 1; text-align: center; font-size: 12px; color: var(--hint); cursor: pointer; padding: 4px; }}
  .nav-item.active {{ color: var(--btn); font-weight: 600; }}
  .hidden {{ display: none; }}
</style>
</head>
<body>
  <div class="header">
    <h1>🛡 Хранитель чата</h1>
    <span class="badge">24/7 Online</span>
  </div>

  <div id="tab-chats">
    <div class="stats">
      <div class="stat-box">
        <div class="stat-val" id="chat-count">0</div>
        <div class="stat-lbl">Подключённых чатов</div>
      </div>
      <div class="stat-box">
        <div class="stat-val">5</div>
        <div class="stat-lbl">Модулей защиты</div>
      </div>
    </div>
    <div id="chats-list"></div>
    <a class="btn" href="{add_url}" target="_blank">➕ Подключить бота в новый чат</a>
  </div>

  <div id="tab-edit" class="hidden">
    <button class="btn btn-sec" onclick="showTab('chats')" style="margin-top:0;margin-bottom:12px;">← Назад к списку чатов</button>
    <div class="card">
      <div class="card-title" id="edit-title">Настройка чата</div>
      <div class="card-sub">Изменения сразу сохраняются в облачную базу.</div>
    </div>
    <div class="card">
      <div class="card-title">🛡 Фильтры автомодерации</div>
      <div class="row"><span>Антимат</span><input type="checkbox" id="f_mat"></div>
      <div class="row"><span>Антифлуд</span><input type="checkbox" id="f_flood"></div>
      <div class="row"><span>Стикеры и GIF</span><input type="checkbox" id="f_stickers"></div>
      <div class="row"><span>Ссылки и реклама</span><input type="checkbox" id="f_links"></div>
      <div class="row"><span>Инлайн-боты</span><input type="checkbox" id="f_inline"></div>
    </div>
    <div class="card">
      <div class="card-title">📝 Тексты и правила</div>
      <label>Правила чата:</label>
      <textarea id="inp-rules"></textarea>
      <label>Приветствие (используй {{user}} и {{chat}}):</label>
      <textarea id="inp-welcome" placeholder="Оставь пустым для стандартного"></textarea>
      <label>Прощание при выходе (используй {{user}} и {{chat}}):</label>
      <textarea id="inp-bye" placeholder="Оставь пустым для стандартного"></textarea>
      <button class="btn" onclick="saveSettings()">💾 Сохранить изменения</button>
    </div>
  </div>

  <div id="tab-guide" class="hidden">
    <div class="card">
      <div class="card-title">Как подключить бота в группу</div>
      <div class="card-sub">
        1. Нажми кнопку ниже и выбери нужный чат.<br>
        2. Выдай боту права администратора (удаление, бан, приглашение, закрепление).<br>
        3. Бот пришлёт уведомление в ЛС, и чат появится во вкладке «Мои чаты».
      </div>
      <a class="btn" href="{add_url}" target="_blank">➕ Добавить бота в группу</a>
    </div>
    <div class="card">
      <div class="card-title">Команды в чате</div>
      <div class="card-sub">
        • <b>/warn</b> или <b>Пред</b> (ответом) — выдать предупреждение<br>
        • <b>/mute 1д</b> или <b>Мут 30м</b> — заглушить участника<br>
        • <b>/ban</b> или <b>Бан</b> — заблокировать нарушителя<br>
        • <b>/status</b> — проверить права бота в группе
      </div>
    </div>
  </div>

  <div class="nav">
    <div class="nav-item active" id="nav-chats" onclick="showTab('chats')">💬 Мои чаты</div>
    <div class="nav-item" id="nav-guide" onclick="showTab('guide')">📘 Инструкция</div>
  </div>

<script>
  const tg = window.Telegram.WebApp;
  tg.ready();
  tg.expand();

  let currentChatId = null;

  function showTab(name) {{
    document.getElementById('tab-chats').classList.add('hidden');
    document.getElementById('tab-edit').classList.add('hidden');
    document.getElementById('tab-guide').classList.add('hidden');
    document.getElementById('nav-chats').classList.remove('active');
    document.getElementById('nav-guide').classList.remove('active');
    document.getElementById('tab-' + name).classList.remove('hidden');
    if (document.getElementById('nav-' + name)) {{
      document.getElementById('nav-' + name).classList.add('active');
    }}
  }}

  async function loadChats() {{
    const res = await fetch('/api/chats', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ initData: tg.initData }})
    }});
    const data = await res.json();
    const list = document.getElementById('chats-list');
    const entries = Object.entries(data.chats || {{}});
    document.getElementById('chat-count').innerText = entries.length;
    if (!entries.length) {{
      list.innerHTML = '<div class="card"><div class="card-title">Пока нет чатов</div><div class="card-sub">Добавь бота в группу через кнопку ниже (или передобавь, если он уже там), чтобы управлять настройками здесь.</div></div>';
      return;
    }}
    list.innerHTML = '';
    for (const [cid, title] of entries) {{
      const el = document.createElement('div');
      el.className = 'chat-item';
      el.innerHTML = `<div><b>${{title}}</b><div class="card-sub">ID: ${{cid}}</div></div><div>⚙️ →</div>`;
      el.onclick = () => openChat(cid, title);
      list.appendChild(el);
    }}
  }}

  async function openChat(cid, title) {{
    currentChatId = cid;
    document.getElementById('edit-title').innerText = title;
    const res = await fetch('/api/chat_info', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ initData: tg.initData, chat_id: cid }})
    }});
    const d = await res.json();
    document.getElementById('f_mat').checked = d.filters.mat;
    document.getElementById('f_flood').checked = d.filters.flood;
    document.getElementById('f_stickers').checked = d.filters.stickers;
    document.getElementById('f_links').checked = d.filters.links;
    document.getElementById('f_inline').checked = d.filters.inline;
    document.getElementById('inp-rules').value = d.rules || '';
    document.getElementById('inp-welcome').value = d.welcome || '';
    document.getElementById('inp-bye').value = d.bye || '';
    showTab('edit');
  }}

  async function saveSettings() {{
    const payload = {{
      initData: tg.initData,
      chat_id: currentChatId,
      filters: {{
        mat: document.getElementById('f_mat').checked,
        flood: document.getElementById('f_flood').checked,
        stickers: document.getElementById('f_stickers').checked,
        links: document.getElementById('f_links').checked,
        inline: document.getElementById('f_inline').checked,
      }},
      rules: document.getElementById('inp-rules').value,
      welcome: document.getElementById('inp-welcome').value,
      bye: document.getElementById('inp-bye').value,
    }};
    await fetch('/api/save', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify(payload)
    }});
    tg.showAlert('✅ Настройки успешно сохранены!');
  }}

  loadChats();
</script>
</body>
</html>"""
    return web.Response(text=html_page, content_type="text/html")


async def api_chats(request: web.Request) -> web.Response:
    body = await request.json()
    uid = _verify_init_data(body.get("initData", ""))
    if not uid:
        return web.json_response({"chats": {}})
    return web.json_response({"chats": _get_chats(uid)})


async def api_chat_info(request: web.Request) -> web.Response:
    body = await request.json()
    uid = _verify_init_data(body.get("initData", ""))
    cid_str = str(body.get("chat_id", ""))
    if not uid or cid_str not in _get_chats(uid):
        return web.json_response({"error": "forbidden"}, status=403)
    cid = int(cid_str)
    filters = {k: db.filter_on(cid, k) for k in ("mat", "flood", "stickers", "links", "inline")}
    return web.json_response({
        "filters": filters,
        "rules": rules.get_rules(cid),
        "welcome": db.get_setting(cid, "welcome_text") or "",
        "bye": db.get_setting(cid, "bye_text") or "",
    })


async def api_save(request: web.Request) -> web.Response:
    body = await request.json()
    uid = _verify_init_data(body.get("initData", ""))
    cid_str = str(body.get("chat_id", ""))
    if not uid or cid_str not in _get_chats(uid):
        return web.json_response({"error": "forbidden"}, status=403)
    cid = int(cid_str)
    filters = body.get("filters") or {}
    for k in ("mat", "flood", "stickers", "links", "inline"):
        if k in filters:
            db.set_setting(cid, "f_" + k, "1" if filters[k] else "0")
    r_txt = (body.get("rules") or "").strip()
    db.set_setting(cid, "rules", r_txt if r_txt else None)
    w_txt = (body.get("welcome") or "").strip()
    db.set_setting(cid, "welcome_text", w_txt if w_txt else None)
    b_txt = (body.get("bye") or "").strip()
    db.set_setting(cid, "bye_text", b_txt if b_txt else None)
    return web.json_response({"ok": True})


def setup_routes(app: web.Application):
    app.router.add_get("/webapp", handle_index)
    app.router.add_post("/api/chats", api_chats)
    app.router.add_post("/api/chat_info", api_chat_info)
    app.router.add_post("/api/save", api_save)
