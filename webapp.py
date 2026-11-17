"""Telegram Web App панель модерации и настроек (aiohttp + PostgreSQL)."""
import hashlib
import hmac
import json
import os
from urllib.parse import parse_qsl

from aiohttp import web

import config
import db

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()


def _verify_init_data(init_data: str) -> dict | None:
    if not init_data or not BOT_TOKEN:
        return None
    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        return None
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_hash, received_hash):
        return None
    user_raw = parsed.get("user")
    return json.loads(user_raw) if user_raw else {}


HTML_PAGE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Панель модерации</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: var(--tg-theme-bg-color, #18181b);
    color: var(--tg-theme-text-color, #f4f4f5);
    margin: 0;
    padding: 16px;
  }
  .card {
    background: var(--tg-theme-secondary-bg-color, #27272a);
    border-radius: 14px;
    padding: 16px;
    margin-bottom: 14px;
  }
  h2 { margin: 0 0 12px; font-size: 18px; }
  .row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 0;
    border-bottom: 1px solid rgba(255,255,255,0.08);
  }
  .row:last-child { border-bottom: none; }
  input[type="text"] {
    width: 100%;
    box-sizing: border-box;
    padding: 10px 12px;
    border-radius: 10px;
    border: 1px solid rgba(255,255,255,0.15);
    background: rgba(0,0,0,0.2);
    color: inherit;
    font-size: 15px;
    margin-bottom: 10px;
  }
  button {
    width: 100%;
    padding: 12px;
    border: none;
    border-radius: 10px;
    background: var(--tg-theme-button-color, #3b82f6);
    color: var(--tg-theme-button-text-color, #ffffff);
    font-size: 15px;
    font-weight: 600;
    cursor: pointer;
  }
  .status { font-size: 13px; opacity: 0.75; margin-top: 8px; text-align: center; }
</style>
</head>
<body>
  <div class="card">
    <h2>⚙️ Настройки фильтров чата</h2>
    <input type="text" id="chatId" placeholder="ID чата (например: -1001234567890)">
    <button onclick="loadSettings()">Загрузить настройки</button>
    <div id="filters" style="margin-top: 12px;"></div>
    <div class="status" id="status">Введите ID группы или откройте из меню чата</div>
  </div>

<script>
  const tg = window.Telegram.WebApp;
  tg.ready();
  tg.expand();

  const urlParams = new URLSearchParams(window.location.search);
  const startParam = tg.initDataUnsafe?.start_param || urlParams.get("chat_id");
  if (startParam) {
    document.getElementById("chatId").value = startParam;
    loadSettings();
  }

  const labels = {
    mat: "🤬 Фильтр мата",
    links: "🔗 Блокировка ссылок",
    stickers: "🎭 Антиспам стикерами/GIF",
    flood: "⚡ Защита от флуда",
    bots: "🤖 Запрет инлайн-ботов"
  };

  async function loadSettings() {
    const chatId = document.getElementById("chatId").value.trim();
    if (!chatId) return;
    document.getElementById("status").innerText = "Загрузка...";
    const res = await fetch(`/api/settings?chat_id=${encodeURIComponent(chatId)}`, {
      headers: { "X-Telegram-Init-Data": tg.initData || "" }
    });
    const data = await res.json();
    if (!res.ok) {
      document.getElementById("status").innerText = data.error || "Ошибка доступа";
      return;
    }
    const container = document.getElementById("filters");
    container.innerHTML = "";
    for (const [key, val] of Object.entries(data.filters)) {
      const row = document.createElement("div");
      row.className = "row";
      row.innerHTML = `
        <span>${labels[key] || key}</span>
        <input type="checkbox" ${val ? "checked" : ""} onchange="toggleFilter('${chatId}', '${key}', this.checked)">
      `;
      container.appendChild(row);
    }
    document.getElementById("status").innerText = "Настройки синхронизированы";
  }

  async function toggleFilter(chatId, kind, enabled) {
    await fetch("/api/settings", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Telegram-Init-Data": tg.initData || ""
      },
      body: JSON.stringify({ chat_id: Number(chatId), kind, enabled })
    });
    document.getElementById("status").innerText = "Сохранено!";
  }
</script>
</body>
</html>
"""


async def index(request: web.Request) -> web.Response:
    return web.Response(text=HTML_PAGE, content_type="text/html")


async def health(request: web.Request) -> web.Response:
    return web.Response(text="Bot is alive!")


async def api_get_settings(request: web.Request) -> web.Response:
    user = _verify_init_data(request.headers.get("X-Telegram-Init-Data", ""))
    if user is None:
        return web.json_response({"error": "Откройте панель через Telegram"}, status=401)
    try:
        chat_id = int(request.query.get("chat_id", "0"))
    except ValueError:
        return web.json_response({"error": "Неверный chat_id"}, status=400)
    if not chat_id:
        return web.json_response({"error": "Не указан chat_id"}, status=400)

    filters = {k: db.filter_on(chat_id, k) for k in config.FILTER_DEFAULTS}
    return web.json_response({"chat_id": chat_id, "filters": filters})


async def api_set_settings(request: web.Request) -> web.Response:
    user = _verify_init_data(request.headers.get("X-Telegram-Init-Data", ""))
    if user is None:
        return web.json_response({"error": "Откройте панель через Telegram"}, status=401)
    body = await request.json()
    chat_id = int(body.get("chat_id", 0))
    kind = str(body.get("kind", ""))
    enabled = bool(body.get("enabled", False))
    if not chat_id or kind not in config.FILTER_DEFAULTS:
        return web.json_response({"error": "Некорректные параметры"}, status=400)

    db.set_setting(chat_id, "f_" + kind, "1" if enabled else "0")
    return web.json_response({"ok": True})


def create_web_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/health", health)
    app.router.add_get("/api/settings", api_get_settings)
    app.router.add_post("/api/settings", api_set_settings)
    return app
