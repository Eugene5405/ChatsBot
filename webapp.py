import hashlib
import hmac
import json
import os
from urllib.parse import parse_qsl

from aiohttp import web
import db


def _check_init_data(init_data: str) -> dict | None:
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


async def index(request: web.Request) -> web.Response:
    html = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Панель модерации — Чат бот</title>
  <script src="https://telegram.org"></script>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: var(--tg-theme-bg-color, #18181b); color: var(--tg-theme-text-color, #f4f4f5); padding: 16px; margin: 0; }
    .card { background: var(--tg-theme-secondary-bg-color, #27272a); border-radius: 12px; padding: 16px; margin-bottom: 12px; }
    h2 { margin: 0 0 8px; font-size: 18px; }
    p { margin: 0; font-size: 14px; opacity: 0.85; }
    .badge { display: inline-block; background: #16a34a; color: #fff; padding: 4px 10px; border-radius: 999px; font-size: 12px; font-weight: 600; margin-top: 8px; }
  </style>
</head>
<body>
  <div class="card">
    <h2>🛡 Чат бот — Панель управления</h2>
    <p>Сервер модерации и база данных подключены и работают стабильно.</p>
    <span class="badge">● Система активна</span>
  </div>
  <div class="card">
    <h2>⚙️ Управление через чат</h2>
    <p>Используйте команду <b>/settings</b> в группе для переключения антимата, антиспама и проверки подписки, а также <b>/status</b> для проверки прав бота.</p>
  </div>
  <script>
    if (window.Telegram && window.Telegram.WebApp) {
      window.Telegram.WebApp.ready();
      window.Telegram.WebApp.expand();
    }
  </script>
</body>
</html>"""
    return web.Response(text=html, content_type="text/html")


def setup_routes(app: web.Application) -> None:
    app.router.add_get("/webapp", index)
    app.router.add_get("/health", health)
