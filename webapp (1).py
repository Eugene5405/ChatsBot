import hashlib
import hmac
import os
from urllib.parse import parse_qsl

from aiohttp import web
import db


def _verify_init_data(init_data: str) -> dict | None:
    bot_token = os.getenv("BOT_TOKEN", "")
    if not init_data or not bot_token:
        return None
    parsed = dict(parse_qsl(init_data, strict_parsing=False))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        return None
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated_hash, received_hash):
        return None
    return parsed


async def health(request: web.Request) -> web.Response:
    return web.Response(text="Bot is alive!")


async def webapp_page(request: web.Request) -> web.Response:
    bot_username = os.getenv("BOT_USERNAME", "chat_custodian_bot")
    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Админ-панель — Хранитель чата</title>
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: var(--tg-theme-bg-color, #121214); color: var(--tg-theme-text-color, #f4f4f5); padding: 16px; margin: 0; }}
    .card {{ background: var(--tg-theme-secondary-bg-color, #1e1e24); border-radius: 14px; padding: 16px; margin-bottom: 14px; }}
    h2 {{ margin: 0 0 10px; font-size: 18px; }}
    p {{ margin: 0 0 12px; font-size: 14px; opacity: 0.85; line-height: 1.4; }}
    select, .btn {{ display: block; width: 100%; padding: 12px; border-radius: 10px; font-size: 15px; border: none; box-sizing: border-box; }}
    select {{ background: var(--tg-theme-bg-color, #121214); color: var(--tg-theme-text-color, #f4f4f5); margin-bottom: 12px; border: 1px solid rgba(255,255,255,0.15); }}
    .btn {{ text-align: center; background: var(--tg-theme-button-color, #2563eb); color: var(--tg-theme-button-text-color, #fff); text-decoration: none; font-weight: 600; cursor: pointer; }}
    .row {{ display: flex; justify-content: space-between; align-items: center; padding: 11px 0; border-bottom: 1px solid rgba(255,255,255,0.08); }}
    .row:last-child {{ border-bottom: none; }}
    input[type="checkbox"] {{ width: 22px; height: 22px; accent-color: #2563eb; }}
  </style>
</head>
<body>
  <div class="card">
    <h2>🛡 Ваши группы</h2>
    <p>Выберите чат для настройки. Если чата нет в списке — добавьте бота админом и напишите в группе <b>/status</b>.</p>
    <select id="chatSelect" onchange="loadSettings()">
      <option value="">Загрузка чатов...</option>
    </select>
    <a class="btn" href="https://t.me/{bot_username}?startgroup=true&admin=change_info+delete_messages+restrict_members+invite_users+pin_messages" target="_blank">+ Добавить бота в чат</a>
  </div>

  <div class="card" id="settingsCard">
    <h2>⚙️ Настройки защиты</h2>
    <div class="row"><span>Антимат-фильтр</span><input type="checkbox" id="profanity" /></div>
    <div class="row"><span>Антиспам и флуд</span><input type="checkbox" id="antispam" /></div>
    <div class="row"><span>Блокировка ссылок</span><input type="checkbox" id="antilink" /></div>
    <div class="row"><span>Проверка подписки на канал</span><input type="checkbox" id="subcheck" /></div>
    <div class="row"><span>Приветствие и прощание</span><input type="checkbox" id="welcome" /></div>
    <br />
    <button class="btn" onclick="saveSettings()">Сохранить изменения</button>
  </div>

  <script>
    const tg = window.Telegram && window.Telegram.WebApp;
    if (tg) {{ tg.ready(); tg.expand(); }}
    let chatsData = [];

    async function fetchChats() {{
      const res = await fetch("/api/chats");
      const data = await res.json();
      chatsData = data.chats || [];
      const sel = document.getElementById("chatSelect");
      sel.innerHTML = "";
      if (chatsData.length === 0) {{
        sel.innerHTML = '<option value="">Нет добавленных чатов (напишите /status в группе)</option>';
        return;
      }}
      chatsData.forEach(c => {{
        const opt = document.createElement("option");
        opt.value = c.chat_id;
        opt.textContent = c.title + " (" + c.chat_id + ")";
        sel.appendChild(opt);
      }});
      loadSettings();
    }}

    function loadSettings() {{
      const id = document.getElementById("chatSelect").value;
      const chat = chatsData.find(c => String(c.chat_id) === String(id));
      if (!chat) return;
      document.getElementById("profanity").checked = chat.profanity;
      document.getElementById("antispam").checked = chat.antispam;
      document.getElementById("antilink").checked = chat.antilink;
      document.getElementById("subcheck").checked = chat.subcheck;
      document.getElementById("welcome").checked = chat.welcome;
    }}

    async function saveSettings() {{
      const chatId = document.getElementById("chatSelect").value;
      if (!chatId) {{
        if (tg) tg.showAlert("Сначала выберите чат из списка!");
        return;
      }}
      const payload = {{
        initData: tg ? tg.initData : "",
        chat_id: Number(chatId),
        profanity: document.getElementById("profanity").checked,
        antispam: document.getElementById("antispam").checked,
        antilink: document.getElementById("antilink").checked,
        subcheck: document.getElementById("subcheck").checked,
        welcome: document.getElementById("welcome").checked,
      }};
      const res = await fetch("/api/settings", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify(payload)
      }});
      if (res.ok) {{
        await fetchChats();
        if (tg) tg.showAlert("✅ Настройки успешно сохранены в базу!");
      }} else {{
        if (tg) tg.showAlert("❌ Ошибка при сохранении настроек.");
      }}
    }}

    fetchChats();
  </script>
</body>
</html>"""
    return web.Response(text=html, content_type="text/html")


async def api_chats(request: web.Request) -> web.Response:
    try:
        chats = db.get_all_chats()
        return web.json_response({"ok": True, "chats": chats})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def api_settings(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        chat_id = int(data["chat_id"])
        db.update_chat_settings(chat_id, data)
        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=400)


def setup_routes(app: web.Application) -> None:
    app.router.add_get("/webapp", webapp_page)
    app.router.add_get("/health", health)
    app.router.add_get("/api/chats", api_chats)
    app.router.add_post("/api/settings", api_settings)
