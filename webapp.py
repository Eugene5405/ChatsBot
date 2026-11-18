"""Современная админ-панель Telegram Mini App: управление чатами, фильтрами, режимом тишины и правилами."""
import hashlib
import hmac
import html
import os
import re
from urllib.parse import parse_qsl

from aiohttp import web
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import ChatPermissions

import db
from loader import bot


_LOCKED_PERMS = ChatPermissions(
    can_send_messages=False,
    can_send_audios=False,
    can_send_documents=False,
    can_send_photos=False,
    can_send_videos=False,
    can_send_video_notes=False,
    can_send_voice_notes=False,
    can_send_polls=False,
    can_send_other_messages=False,
    can_add_web_page_previews=False,
)

_UNLOCKED_PERMS = ChatPermissions(
    can_send_messages=True,
    can_send_audios=True,
    can_send_documents=True,
    can_send_photos=True,
    can_send_videos=True,
    can_send_video_notes=True,
    can_send_voice_notes=True,
    can_send_polls=True,
    can_send_other_messages=True,
    can_add_web_page_previews=True,
)


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


def _strip_tags(raw: str) -> str:
    return re.sub(r"<[^>]+>", "", raw or "").strip()


async def health(request: web.Request) -> web.Response:
    return web.Response(text="Bot is alive!")


async def api_chats(request: web.Request) -> web.Response:
    chats = db.get_chats()
    return web.json_response({"ok": True, "chats": chats})


async def api_delete_chat(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        chat_id = int(data["chat_id"])
        db.delete_chat(chat_id)
        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=400)


async def api_get_settings(request: web.Request) -> web.Response:
    chat_id_s = request.query.get("chat_id", "")
    if not chat_id_s:
        return web.json_response({"ok": False, "error": "chat_id required"}, status=400)
    chat_id = int(chat_id_s)
    settings = db.get_chat_settings(chat_id)
    settings["rules_plain"] = _strip_tags(settings.get("rules", ""))

    members_count = None
    try:
        members_count = await bot.get_chat_member_count(chat_id)
    except Exception:
        pass

    return web.json_response({"ok": True, "settings": settings, "members_count": members_count})


async def api_save_settings(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        _verify_init_data(data.get("initData", ""))
        chat_id = int(data["chat_id"])
        db.update_chat_settings(chat_id, data)
        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=400)


async def api_chat_lock(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        chat_id = int(data["chat_id"])
        lock = bool(data["lock"])
        perms = _LOCKED_PERMS if lock else _UNLOCKED_PERMS
        await bot.set_chat_permissions(chat_id=chat_id, permissions=perms)
        msg = (
            "🔒 <b>Чат закрыт через админ-панель.</b> Писать теперь могут только администраторы."
            if lock
            else "🔓 <b>Чат открыт через админ-панель.</b> Участники снова могут отправлять сообщения."
        )
        await bot.send_message(chat_id, msg)
        return web.json_response({"ok": True})
    except TelegramBadRequest as e:
        return web.json_response({"ok": False, "error": e.message}, status=400)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=400)


async def webapp_page(request: web.Request) -> web.Response:
    page_html = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
  <title>Админ-панель — Хранитель чата</title>
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <style>
    :root {
      --bg: #0f1117;
      --card: #181b24;
      --card-border: rgba(255,255,255,0.08);
      --text: #f3f4f6;
      --muted: #9ca3af;
      --accent: #3b82f6;
      --accent-hover: #2563eb;
      --danger: #ef4444;
      --success: #10b981;
    }
    * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      margin: 0;
      padding: 14px 14px 36px;
    }
    .header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 14px;
    }
    .header h1 { font-size: 20px; margin: 0; display: flex; align-items: center; gap: 8px; }
    .badge {
      background: rgba(16, 185, 129, 0.16);
      color: #34d399;
      border: 1px solid rgba(16, 185, 129, 0.35);
      padding: 4px 10px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 600;
    }
    .card {
      background: var(--card);
      border: 1px solid var(--card-border);
      border-radius: 16px;
      padding: 16px;
      margin-bottom: 14px;
      box-shadow: 0 6px 20px rgba(0,0,0,0.25);
    }
    .card-title {
      font-size: 15px;
      font-weight: 700;
      margin: 0 0 10px;
      color: #fff;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .muted { font-size: 13px; color: var(--muted); line-height: 1.4; margin: 0 0 12px; }
    select, textarea {
      width: 100%;
      background: #10131a;
      color: #fff;
      border: 1px solid rgba(255,255,255,0.14);
      border-radius: 12px;
      padding: 12px;
      font-size: 14px;
      outline: none;
    }
    select:focus, textarea:focus { border-color: var(--accent); }
    .btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      width: 100%;
      padding: 12px 14px;
      border-radius: 12px;
      font-weight: 600;
      font-size: 14px;
      border: none;
      cursor: pointer;
      text-decoration: none;
      transition: transform 0.08s ease, opacity 0.15s ease;
    }
    .btn:active { transform: scale(0.98); }
    .btn-primary { background: var(--accent); color: #fff; }
    .btn-secondary { background: rgba(255,255,255,0.08); color: #fff; }
    .btn-danger { background: rgba(239,68,68,0.15); color: #f87171; border: 1px solid rgba(239,68,68,0.3); }
    .btn-success { background: rgba(16,185,129,0.18); color: #34d399; border: 1px solid rgba(16,185,129,0.35); }
    .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 10px; }
    .switch-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 11px 0;
      border-bottom: 1px solid rgba(255,255,255,0.06);
    }
    .switch-row:last-child { border-bottom: none; padding-bottom: 0; }
    .switch-info { padding-right: 12px; }
    .switch-name { font-size: 14px; font-weight: 600; display: block; }
    .switch-desc { font-size: 12px; color: var(--muted); display: block; margin-top: 2px; }
    .toggle {
      position: relative;
      width: 46px;
      height: 26px;
      flex-shrink: 0;
    }
    .toggle input { opacity: 0; width: 0; height: 0; }
    .slider {
      position: absolute; cursor: pointer; inset: 0;
      background: #2d3240; border-radius: 999px; transition: .2s;
    }
    .slider:before {
      position: absolute; content: ""; height: 20px; width: 20px;
      left: 3px; bottom: 3px; background: white; border-radius: 50%; transition: .2s;
    }
    input:checked + .slider { background: var(--accent); }
    input:checked + .slider:before { transform: translateX(20px); }
    .stat-pill {
      font-size: 12px;
      background: rgba(59,130,246,0.15);
      color: #60a5fa;
      padding: 3px 9px;
      border-radius: 8px;
    }
  </style>
</head>
<body>
  <div class="header">
    <h1>🛡 Админ-панель</h1>
    <span class="badge">● Online</span>
  </div>

  <div class="card">
    <div class="card-title">
      <span>💬 Выбор чата</span>
      <span class="stat-pill" id="memberCount" style="display:none;"></span>
    </div>
    <select id="chatSelect" onchange="onChatChange()">
      <option value="">Загрузка списка чатов...</option>
    </select>
    <div class="grid-2">
      <a class="btn btn-secondary" href="https://t.me/chat_custodian_bot?startgroup=true&admin=change_info+delete_messages+restrict_members+invite_users+pin_messages" target="_blank">➕ Добавить чат</a>
      <button class="btn btn-danger" onclick="removeChat()">🗑 Удалить из списка</button>
    </div>
  </div>

  <div id="controlsArea" style="display:none;">
    <div class="card">
      <div class="card-title">⚡ Быстрое управление (Ирис-режим)</div>
      <p class="muted">Мгновенно закрывает или открывает чат для обычных участников.</p>
      <div class="grid-2">
        <button class="btn btn-danger" onclick="setChatLock(true)">🔒 -чат (Закрыть)</button>
        <button class="btn btn-success" onclick="setChatLock(false)">🔓 +чат (Открыть)</button>
      </div>
    </div>

    <div class="card">
      <div class="card-title">⚙️ Модули автомодерации</div>

      <div class="switch-row">
        <div class="switch-info">
          <span class="switch-name">🤬 Умный антимат</span>
          <span class="switch-desc">Ловит мат в предложениях и с латиницей</span>
        </div>
        <label class="toggle"><input type="checkbox" id="profanity"><span class="slider"></span></label>
      </div>

      <div class="switch-row">
        <div class="switch-info">
          <span class="switch-name">🌊 Антиспам и антифлуд</span>
          <span class="switch-desc">Защита от частых однотипных сообщений</span>
        </div>
        <label class="toggle"><input type="checkbox" id="antispam"><span class="slider"></span></label>
      </div>

      <div class="switch-row">
        <div class="switch-info">
          <span class="switch-name">🔗 Блокировка ссылок</span>
          <span class="switch-desc">Удаление сторонних ссылок и рекламы</span>
        </div>
        <label class="toggle"><input type="checkbox" id="antilink"><span class="slider"></span></label>
      </div>

      <div class="switch-row">
        <div class="switch-info">
          <span class="switch-name">📢 Проверка подписки</span>
          <span class="switch-desc">Одобрение заявок только подписчикам канала</span>
        </div>
        <label class="toggle"><input type="checkbox" id="subcheck"><span class="slider"></span></label>
      </div>

      <div class="switch-row">
        <div class="switch-info">
          <span class="switch-name">👋 Приветствие новичков</span>
          <span class="switch-desc">Встречает участников с правилами группы</span>
        </div>
        <label class="toggle"><input type="checkbox" id="welcome"><span class="slider"></span></label>
      </div>
    </div>

    <div class="card">
      <div class="card-title">📜 Правила чата</div>
      <p class="muted">Оставьте пустым, чтобы использовать стандартные правила.</p>
      <textarea id="rulesText" rows="4" placeholder="Введите правила вашего чата..."></textarea>
      <div style="margin-top:12px;">
        <button class="btn btn-primary" onclick="saveSettings()">💾 Сохранить все настройки</button>
      </div>
    </div>
  </div>

  <script>
    const tg = window.Telegram && window.Telegram.WebApp;
    if (tg) {
      tg.ready();
      tg.expand();
    }

    function notify(text) {
      if (tg && tg.showAlert) tg.showAlert(text);
      else alert(text);
    }

    async function loadChats() {
      const sel = document.getElementById("chatSelect");
      try {
        const res = await fetch("/api/chats");
        const data = await res.json();
        sel.innerHTML = "";
        if (!data.chats || data.chats.length === 0) {
          sel.innerHTML = '<option value="">Нет добавленных чатов (напишите /status в группе)</option>';
          document.getElementById("controlsArea").style.display = "none";
          return;
        }
        data.chats.forEach(c => {
          const opt = document.createElement("option");
          opt.value = c.chat_id;
          opt.textContent = `${c.title} (${c.chat_id})`;
          sel.appendChild(opt);
        });
        document.getElementById("controlsArea").style.display = "block";
        await onChatChange();
      } catch (e) {
        sel.innerHTML = '<option value="">Ошибка загрузки чатов</option>';
      }
    }

    async function onChatChange() {
      const chatId = document.getElementById("chatSelect").value;
      if (!chatId) return;
      const res = await fetch(`/api/settings?chat_id=${encodeURIComponent(chatId)}`);
      const data = await res.json();
      if (!data.ok) return;
      const s = data.settings;
      document.getElementById("profanity").checked = !!s.profanity;
      document.getElementById("antispam").checked = !!s.antispam;
      document.getElementById("antilink").checked = !!s.antilink;
      document.getElementById("subcheck").checked = !!s.subcheck;
      document.getElementById("welcome").checked = !!s.welcome;
      document.getElementById("rulesText").value = s.rules_plain || "";

      const badge = document.getElementById("memberCount");
      if (data.members_count) {
        badge.textContent = `👥 ${data.members_count} уч.`;
        badge.style.display = "inline-block";
      } else {
        badge.style.display = "none";
      }
    }

    async function saveSettings() {
      const chatId = document.getElementById("chatSelect").value;
      if (!chatId) return notify("Сначала выберите чат!");
      const payload = {
        initData: tg ? tg.initData : "",
        chat_id: chatId,
        profanity: document.getElementById("profanity").checked,
        antispam: document.getElementById("antispam").checked,
        antilink: document.getElementById("antilink").checked,
        subcheck: document.getElementById("subcheck").checked,
        welcome: document.getElementById("welcome").checked,
        rules: document.getElementById("rulesText").value
      };
      const res = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      notify(data.ok ? "✅ Настройки успешно сохранены!" : "❌ Ошибка: " + (data.error || "неизвестно"));
    }

    async function removeChat() {
      const chatId = document.getElementById("chatSelect").value;
      if (!chatId) return notify("Список чатов пуст.");
      const res = await fetch("/api/chats/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chat_id: chatId })
      });
      const data = await res.json();
      if (data.ok) {
        notify("🗑 Чат удалён из админ-панели.");
        await loadChats();
      } else {
        notify("❌ Не удалось удалить чат.");
      }
    }

    async function setChatLock(lock) {
      const chatId = document.getElementById("chatSelect").value;
      if (!chatId) return notify("Сначала выберите чат!");
      const res = await fetch("/api/chat_lock", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chat_id: chatId, lock })
      });
      const data = await res.json();
      notify(data.ok ? (lock ? "🔒 Чат закрыт!" : "🔓 Чат открыт!") : "⚠️ " + (data.error || "Проверьте права админа у бота"));
    }

    loadChats();
  </script>
</body>
</html>"""
    return web.Response(text=page_html, content_type="text/html")


def setup_routes(app: web.Application) -> None:
    app.router.add_get("/webapp", webapp_page)
    app.router.add_get("/health", health)
    app.router.add_get("/api/chats", api_chats)
    app.router.add_post("/api/chats/delete", api_delete_chat)
    app.router.add_get("/api/settings", api_get_settings)
    app.router.add_post("/api/settings", api_save_settings)
    app.router.add_post("/api/chat_lock", api_chat_lock)
