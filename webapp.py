"""Веб-приложение (Telegram Mini App) для управления чатами и фильтрами."""
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
    html = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Админ-панель — Чат бот</title>
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: var(--tg-theme-bg-color, #121214); color: var(--tg-theme-text-color, #f4f4f5); padding: 16px; margin: 0; }
    .card { background: var(--tg-theme-secondary-bg-color, #1e1e24); border-radius: 14px; padding: 16px; margin-bottom: 14px; }
    h2 { margin: 0 0 10px; font-size: 17px; }
    p { margin: 0 0 12px; font-size: 13px; opacity: 0.8; line-height: 1.4; }
    select { width: 100%; padding: 11px; border-radius: 10px; border: 1px solid rgba(255,255,255,0.15); background: var(--tg-theme-bg-color, #121214); color: inherit; font-size: 15px; margin-bottom: 10px; }
    .btn { display: block; width: 100%; text-align: center; background: var(--tg-theme-button-color, #2563eb); color: var(--tg-theme-button-text-color, #fff); text-decoration: none; padding: 12px; border-radius: 10px; font-weight: 600; font-size: 15px; border: none; cursor: pointer; box-sizing: border-box; }
    .row { display: flex; justify-content: space-between; align-items: center; padding: 11px 0; border-bottom: 1px solid rgba(255,255,255,0.08); font-size: 15px; }
    .row:last-child { border-bottom: none; }
    input[type="checkbox"] { width: 20px; height: 20px; accent-color: #2563eb; }
  </style>
</head>
<body>
  <div class="card">
    <h2>💬 Выбор чата</h2>
    <select id="chatSelect" onchange="loadSettings()"></select>
    <a class="btn" href="https://t.me/chat_custodian_bot?startgroup=true&admin=change_info+delete_messages+restrict_members+invite_users+pin_messages" target="_blank">+ Добавить бота в чат</a>
  </div>

  <div class="card">
    <h2>⚙️ Настройки защиты</h2>
    <div class="row"><span>Умный антимат</span><input type="checkbox" id="profanity" /></div>
    <div class="row"><span>Антиспам и флуд</span><input type="checkbox" id="antispam" /></div>
    <div class="row"><span>Блокировка ссылок</span><input type="checkbox" id="antilink" /></div>
    <div class="row"><span>Проверка подписки</span><input type="checkbox" id="subcheck" /></div>
    <div class="row"><span>Приветствие и правила</span><input type="checkbox" id="welcome" /></div>
    <br />
    <button class="btn" onclick="saveSettings()">💾 Сохранить изменения</button>
  </div>

  <script>
    const tg = window.Telegram && window.Telegram.WebApp;
    if (tg) { tg.ready(); tg.expand(); }

    async function loadChats() {
      const res = await fetch("/api/chats");
      const data = await res.json();
      const sel = document.getElementById("chatSelect");
      sel.innerHTML = "";
      if (!data.chats || data.chats.length === 0) {
        const opt = document.createElement("option");
        opt.value = "";
        opt.textContent = "Нет чатов (напишите /status в группе)";
        sel.appendChild(opt);
        return;
      }
      data.chats.forEach(c => {
        const opt = document.createElement("option");
        opt.value = c.chat_id;
        opt.textContent = c.title;
        sel.appendChild(opt);
      });
      await loadSettings();
    }

    async function loadSettings() {
      const chatId = document.getElementById("chatSelect").value;
      if (!chatId) return;
      const res = await fetch("/api/settings?chat_id=" + encodeURIComponent(chatId));
      const s = await res.json();
      document.getElementById("profanity").checked = !!s.profanity;
      document.getElementById("antispam").checked = !!s.antispam;
      document.getElementById("antilink").checked = !!s.antilink;
      document.getElementById("subcheck").checked = !!s.subcheck;
      document.getElementById("welcome").checked = !!s.welcome;
    }

    async function saveSettings() {
      const chatId = document.getElementById("chatSelect").value;
      if (!chatId) {
        if (tg) tg.showAlert("Сначала добавьте бота в группу и напишите там /status");
        return;
      }
      const payload = {
        initData: tg ? tg.initData : "",
        chat_id: chatId,
        profanity: document.getElementById("profanity").checked,
        antispam: document.getElementById("antispam").checked,
        antilink: document.getElementById("antilink").checked,
        subcheck: document.getElementById("subcheck").checked,
        welcome: document.getElementById("welcome").checked,
      };
      const res = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (tg) {
        tg.showAlert(res.ok ? "✅ Настройки успешно сохранены!" : "❌ Ошибка сохранения");
      }
    }

    loadChats();
  </script>
</body>
</html>"""
    return web.Response(text=html, content_type="text/html")


async def api_chats(request: web.Request) -> web.Response:
    return web.json_response({"chats": db.get_chats()})


async def api_get_settings(request: web.Request) -> web.Response:
    chat_id = request.query.get("chat_id")
    if not chat_id:
        return web.json_response({})
    return web.json_response(db.get_chat_settings(int(chat_id)))


async def api_post_settings(request: web.Request) -> web.Response:
    data = await request.json()
    chat_id = data.get("chat_id")
    if not chat_id:
        return web.json_response({"ok": False}, status=400)
    db.update_chat_settings(int(chat_id), data)
    return web.json_response({"ok": True})


def setup_routes(app: web.Application) -> None:
    app.router.add_get("/webapp", webapp_page)
    app.router.add_get("/health", health)
    app.router.add_get("/api/chats", api_chats)
    app.router.add_get("/api/settings", api_get_settings)
    app.router.add_post("/api/settings", api_post_settings)
