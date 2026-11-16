"""Telegram Mini App (Web App) для управления чатами бота."""
import hashlib
import hmac
import json
import logging
import urllib.parse

from aiohttp import web
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

import config
import db
import rules
from loader import bot

_ACTIVE_STATUSES = {ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}


def _verify_init_data(init_data: str) -> int | None:
    if not init_data:
        return None
    try:
        parsed = dict(urllib.parse.parse_qsl(init_data, strict_parsing=True))
        hash_val = parsed.pop("hash", None)
        if not hash_val:
            return None
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
        secret_key = hmac.new(b"WebAppData", config.BOT_TOKEN.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calculated_hash, hash_val):
            return None
        user_data = json.loads(parsed.get("user", "{}"))
        return int(user_data.get("id"))
    except Exception as e:
        logging.warning("Ошибка проверки initData: %s", e)
        return None


def _get_user_chats_raw(user_id: int) -> list[dict]:
    rows = db._db.execute(
        "SELECT chat_id, value FROM settings WHERE key = %s",
        (f"owner_{user_id}",)
    ).fetchall()
    chats = []
    for row in rows:
        cid = row[0] if isinstance(row, tuple) else row
        title = row[1] if isinstance(row, tuple) and len(row) > 1 else f"Чат {cid}"
        chats.append({"chat_id": cid, "title": title})
    return chats


async def _get_valid_user_chats(user_id: int) -> list[dict]:
    raw_chats = _get_user_chats_raw(user_id)
    valid_chats = []
    for ch in raw_chats:
        cid = ch["chat_id"]
        try:
            member = await bot.get_chat_member(cid, bot.id)
            if member.status in _ACTIVE_STATUSES:
                chat_info = await bot.get_chat(cid)
                title = chat_info.title or ch["title"]
                if title != ch["title"]:
                    db.set_setting(cid, f"owner_{user_id}", title)
                valid_chats.append({"chat_id": cid, "title": title})
            else:
                db.set_setting(cid, f"owner_{user_id}", None)
        except (TelegramBadRequest, TelegramForbiddenError):
            db.set_setting(cid, f"owner_{user_id}", None)
        except Exception as e:
            logging.warning("Ошибка проверки чата %s: %s", cid, e)
            valid_chats.append(ch)
    return valid_chats


def _is_owner(user_id: int, chat_id: int) -> bool:
    return db.get_setting(chat_id, f"owner_{user_id}") is not None


async def handle_index(request: web.Request) -> web.Response:
    bot_info = await bot.get_me()
    bot_username = bot_info.username or "chat_custodian_bot"
    html_content = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Хранитель чата</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
  :root {{
    --bg: var(--tg-theme-bg-color, #121212);
    --sec-bg: var(--tg-theme-secondary-bg-color, #1e1e1e);
    --text: var(--tg-theme-text-color, #ffffff);
    --hint: var(--tg-theme-hint-color, #8e8e93);
    --btn: var(--tg-theme-button-color, #3390ec);
    --btn-text: var(--tg-theme-button-text-color, #ffffff);
    --border: rgba(255, 255, 255, 0.08);
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
  body {{ background: var(--bg); color: var(--text); padding: 16px 16px 84px; min-height: 100vh; }}
  .header {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }}
  .header h1 {{ font-size: 20px; font-weight: 700; display: flex; align-items: center; gap: 8px; }}
  .badge {{ background: rgba(52, 199, 89, 0.15); color: #34c759; font-size: 12px; padding: 4px 10px; border-radius: 12px; font-weight: 600; }}
  .stats {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 18px; }}
  .stat-card {{ background: var(--sec-bg); padding: 14px; border-radius: 14px; border: 1px solid var(--border); }}
  .stat-val {{ font-size: 22px; font-weight: 700; color: var(--btn); }}
  .stat-val.green {{ color: #34c759; }}
  .stat-lbl {{ font-size: 12px; color: var(--hint); margin-top: 4px; }}
  .card {{ background: var(--sec-bg); border-radius: 14px; padding: 16px; margin-bottom: 12px; border: 1px solid var(--border); }}
  .chat-item {{ display: flex; align-items: center; justify-content: space-between; cursor: pointer; }}
  .chat-title {{ font-size: 16px; font-weight: 600; }}
  .chat-sub {{ font-size: 12px; color: var(--hint); margin-top: 2px; }}
  .btn {{ display: block; width: 100%; background: var(--btn); color: var(--btn-text); border: none; padding: 13px; border-radius: 12px; font-size: 15px; font-weight: 600; text-align: center; text-decoration: none; cursor: pointer; margin-top: 10px; }}
  .btn.sec {{ background: rgba(255, 255, 255, 0.08); color: var(--text); }}
  textarea {{ width: 100%; background: var(--bg); color: var(--text); border: 1px solid var(--border); border-radius: 10px; padding: 10px; font-size: 14px; min-height: 90px; margin-top: 8px; resize: vertical; }}
  .toggle-row {{ display: flex; align-items: center; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid var(--border); }}
  .toggle-row:last-child {{ border-bottom: none; }}
  input[type="checkbox"] {{ width: 20px; height: 20px; accent-color: var(--btn); }}
  .nav {{ position: fixed; bottom: 0; left: 0; right: 0; background: var(--sec-bg); border-top: 1px solid var(--border); display: flex; height: 64px; z-index: 100; }}
  .nav-btn {{ flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 4px; color: var(--hint); font-size: 12px; border: none; background: none; cursor: pointer; }}
  .nav-btn.active {{ color: var(--btn); font-weight: 600; }}
  .hidden {{ display: none !important; }}
  .err-box {{ background: rgba(255, 59, 48, 0.15); border: 1px solid rgba(255, 59, 48, 0.4); color: #ff6b6b; padding: 12px; border-radius: 12px; font-size: 13px; margin-bottom: 12px; word-break: break-word; }}
  .toast {{ position: fixed; top: 16px; left: 50%; transform: translateX(-50%); background: #34c759; color: #fff; padding: 10px 18px; border-radius: 20px; font-size: 14px; font-weight: 600; z-index: 200; }}
</style>
</head>
<body>

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
    <div class="stat-val green">Активна</div>
    <div class="stat-lbl">Защита от спама</div>
  </div>
</div>

<div id="errorBox" class="err-box hidden"></div>
<div id="toast" class="toast hidden">Сохранено!</div>

<!-- Вкладка: Мои чаты -->
<div id="tabChats">
  <div id="chatsList">
    <div class="card" style="text-align:center; color: var(--hint);">Загрузка чатов...</div>
  </div>
</div>

<!-- Вкладка: Подключение -->
<div id="tabConnect" class="hidden">
  <div class="card">
    <h3 style="margin-bottom:8px;">➕ Подключить новый чат</h3>
    <p style="font-size:13px; color:var(--hint); line-height:1.4;">
      Нажмите кнопку ниже, выберите группу и выдайте боту права администратора. После этого чат сразу появится в разделе «Мои чаты».
    </p>
    <a class="btn" href="https://t.me/{bot_username}?startgroup=true&admin=delete_messages+restrict_members+invite_users+pin_messages" target="_blank">
      ➕ Добавить бота в чат
    </a>
  </div>
</div>

<!-- Экран настроек конкретного чата -->
<div id="chatEditor" class="hidden">
  <button class="btn sec" style="margin-bottom:12px; margin-top:0;" onclick="closeEditor()">← Назад к списку чатов</button>
  <h2 id="editorTitle" style="font-size:18px; margin-bottom:12px;">Настройки чата</h2>

  <div class="card">
    <h3 style="font-size:15px;">🛡️ Фильтры защиты</h3>
    <div class="toggle-row"><span>Антимат</span><input type="checkbox" id="f_mat"></div>
    <div class="toggle-row"><span>Антиспам (флуд)</span><input type="checkbox" id="f_spam"></div>
    <div class="toggle-row"><span>Защита от рекламы (ссылки)</span><input type="checkbox" id="f_ads"></div>
    <div class="toggle-row"><span>Лимит стикеров и GIF</span><input type="checkbox" id="f_media"></div>
  </div>

  <div class="card">
    <h3 style="font-size:15px;">📜 Правила чата</h3>
    <textarea id="rulesText" placeholder="Введите правила чата..."></textarea>
  </div>

  <div class="card">
    <h3 style="font-size:15px;">👋 Приветствие новичков</h3>
    <p style="font-size:11px; color:var(--hint); margin-top:2px;">Переменные: {{user}} — имя, {{chat}} — название чата</p>
    <textarea id="welcomeText" placeholder="Оставьте пустым для стандартного приветствия"></textarea>
  </div>

  <div class="card">
    <h3 style="font-size:15px;">🚪 Прощание при выходе</h3>
    <textarea id="goodbyeText" placeholder="Оставьте пустым для стандартного прощания"></textarea>
  </div>

  <button class="btn" onclick="saveSettings()">💾 Сохранить настройки</button>
</div>

<div class="nav">
  <button class="nav-btn active" id="navChats" onclick="switchTab('chats')">💬<span>Мои чаты</span></button>
  <button class="nav-btn" id="navConnect" onclick="switchTab('connect')">➕<span>Подключение</span></button>
</div>

<script>
  const tg = window.Telegram.WebApp;
  tg.ready();
  tg.expand();

  let currentChatId = null;

  function showError(msg) {{
    const box = document.getElementById("errorBox");
    box.textContent = msg;
    box.classList.remove("hidden");
  }}

  function showToast(msg) {{
    const t = document.getElementById("toast");
    t.textContent = msg;
    t.classList.remove("hidden");
    setTimeout(() => t.classList.add("hidden"), 2500);
  }}

  function switchTab(tab) {{
    closeEditor();
    document.getElementById("navChats").classList.toggle("active", tab === "chats");
    document.getElementById("navConnect").classList.toggle("active", tab === "connect");
    document.getElementById("tabChats").classList.toggle("hidden", tab !== "chats");
    document.getElementById("tabConnect").classList.toggle("hidden", tab !== "connect");
  }}

  async function apiCall(endpoint, payload) {{
    const res = await fetch(endpoint, {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify({{ initData: tg.initData || "", ...payload }})
    }});
    const text = await res.text();
    let data;
    try {{
      data = JSON.parse(text);
    }} catch (e) {{
      throw new Error("Ответ сервера (" + res.status + "): " + text.slice(0, 120));
    }}
    if (!res.ok || data.error) {{
      throw new Error(data.error || ("Ошибка HTTP " + res.status));
    }}
    return data;
  }}

  async function loadChats() {{
    try {{
      const data = await apiCall("/api/chats", {{}});
      const chats = data.chats || [];
      document.getElementById("chatCount").textContent = chats.length;
      const list = document.getElementById("chatsList");
      if (chats.length === 0) {{
        list.innerHTML = `<div class="card" style="text-align:center;">
          <p style="color:var(--hint); margin-bottom:10px;">У вас пока нет подключённых чатов.</p>
          <button class="btn" onclick="switchTab('connect')">➕ Подключить первый чат</button>
        </div>`;
        return;
      }}
      list.innerHTML = chats.map(c => `
        <div class="card chat-item" onclick="openEditor(${{c.chat_id}}, '${{c.title.replace(/'/g, "\\'")}}')">
          <div>
            <div class="chat-title">${{c.title}}</div>
            <div class="chat-sub">Нажмите для настройки</div>
          </div>
          <span style="color:var(--btn); font-size:18px;">›</span>
        </div>
      `).join("");
    }} catch (e) {{
      showError("Ошибка загрузки: " + e.message);
      document.getElementById("chatsList").innerHTML = "";
    }}
  }}

  async function openEditor(chatId, title) {{
    currentChatId = chatId;
    document.getElementById("tabChats").classList.add("hidden");
    document.getElementById("tabConnect").classList.add("hidden");
    document.getElementById("chatEditor").classList.remove("hidden");
    document.getElementById("editorTitle").textContent = title;
    try {{
      const data = await apiCall("/api/chat_settings", {{ chat_id: chatId }});
      document.getElementById("f_mat").checked = !!data.filters.mat;
      document.getElementById("f_spam").checked = !!data.filters.spam;
      document.getElementById("f_ads").checked = !!data.filters.ads;
      document.getElementById("f_media").checked = !!data.filters.media;
      document.getElementById("rulesText").value = data.rules || "";
      document.getElementById("welcomeText").value = data.welcome || "";
      document.getElementById("goodbyeText").value = data.goodbye || "";
    }} catch (e) {{
      showError("Не удалось загрузить настройки: " + e.message);
    }}
  }}

  function closeEditor() {{
    currentChatId = null;
    document.getElementById("chatEditor").classList.add("hidden");
    document.getElementById("tabChats").classList.remove("hidden");
  }}

  async function saveSettings() {{
    if (!currentChatId) return;
    try {{
      await apiCall("/api/save_settings", {{
        chat_id: currentChatId,
        filters: {{
          mat: document.getElementById("f_mat").checked,
          spam: document.getElementById("f_spam").checked,
          ads: document.getElementById("f_ads").checked,
          media: document.getElementById("f_media").checked
        }},
        rules: document.getElementById("rulesText").value,
        welcome: document.getElementById("welcomeText").value,
        goodbye: document.getElementById("goodbyeText").value
      }});
      showToast("✅ Настройки сохранены!");
    }} catch (e) {{
      showError("Ошибка сохранения: " + e.message);
    }}
  }}

  loadChats();
</script>
</body>
</html>"""
    return web.Response(text=html_content, content_type="text/html")


async def handle_api_chats(request: web.Request) -> web.Response:
    try:
        body = await request.json()
        user_id = _verify_init_data(body.get("initData", ""))
        if not user_id:
            return web.json_response({"error": "Откройте приложение через кнопку внутри Telegram"}, status=401)
        chats = await _get_valid_user_chats(user_id)
        return web.json_response({"chats": chats})
    except Exception as e:
        logging.exception("Ошибка в /api/chats")
        return web.json_response({"error": str(e)}, status=500)


async def handle_api_chat_settings(request: web.Request) -> web.Response:
    try:
        body = await request.json()
        user_id = _verify_init_data(body.get("initData", ""))
        chat_id = int(body.get("chat_id", 0))
        if not user_id or not _is_owner(user_id, chat_id):
            return web.json_response({"error": "Нет доступа к этому чату"}, status=403)
        return web.json_response({
            "filters": {
                "mat": db.filter_on(chat_id, "mat"),
                "spam": db.filter_on(chat_id, "spam"),
                "ads": db.filter_on(chat_id, "ads"),
                "media": db.filter_on(chat_id, "media"),
            },
            "rules": rules.get_rules(chat_id),
            "welcome": db.get_setting(chat_id, "custom_welcome") or "",
            "goodbye": db.get_setting(chat_id, "custom_goodbye") or "",
        })
    except Exception as e:
        logging.exception("Ошибка в /api/chat_settings")
        return web.json_response({"error": str(e)}, status=500)


async def handle_api_save_settings(request: web.Request) -> web.Response:
    try:
        body = await request.json()
        user_id = _verify_init_data(body.get("initData", ""))
        chat_id = int(body.get("chat_id", 0))
        if not user_id or not _is_owner(user_id, chat_id):
            return web.json_response({"error": "Нет доступа к этому чату"}, status=403)

        filters = body.get("filters", {})
        for k in ("mat", "spam", "ads", "media"):
            if k in filters:
                db.set_setting(chat_id, f"f_{k}", "1" if filters[k] else "0")

        new_rules = body.get("rules", "").strip()
        if new_rules:
            rules.set_rules(chat_id, new_rules)

        welcome_txt = body.get("welcome", "").strip()
        db.set_setting(chat_id, "custom_welcome", welcome_txt if welcome_txt else None)

        goodbye_txt = body.get("goodbye", "").strip()
        db.set_setting(chat_id, "custom_goodbye", goodbye_txt if goodbye_txt else None)

        return web.json_response({"ok": True})
    except Exception as e:
        logging.exception("Ошибка в /api/save_settings")
        return web.json_response({"error": str(e)}, status=500)


def setup_routes(app: web.Application):
    app.router.add_get("/webapp", handle_index)
    app.router.add_post("/api/chats", handle_api_chats)
    app.router.add_post("/api/chat_settings", handle_api_chat_settings)
    app.router.add_post("/api/save_settings", handle_api_save_settings)
