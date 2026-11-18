"""Красивая и функциональная админ-панель Telegram Mini App (/webapp)."""
from aiohttp import web
from aiogram.types import ChatPermissions

import db
from loader import bot

_LOCKED_PERMS = ChatPermissions(can_send_messages=False)
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


async def health(request: web.Request) -> web.Response:
    return web.Response(text="Bot is alive!")


async def webapp_page(request: web.Request) -> web.Response:
    html = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Хранитель чата — Админ-панель</title>
  <script src="https://telegram.org"></script>
  <style>
    :root {
      --bg: var(--tg-theme-bg-color, #0f1117);
      --card: var(--tg-theme-secondary-bg-color, #181b23);
      --text: var(--tg-theme-text-color, #f4f4f6);
      --hint: var(--tg-theme-hint-color, #9ca3af);
      --accent: var(--tg-theme-button-color, #3b82f6);
      --accent-text: var(--tg-theme-button-text-color, #ffffff);
      --danger: #ef4444;
      --success: #10b981;
      --border: rgba(255, 255, 255, 0.08);
    }
    * { box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      margin: 0;
      padding: 16px 16px 40px;
    }
    .header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 16px;
    }
    .header h1 { font-size: 20px; margin: 0; font-weight: 700; }
    .badge {
      background: rgba(16, 185, 129, 0.16);
      color: var(--success);
      padding: 4px 10px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 600;
    }
    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 16px;
      margin-bottom: 14px;
    }
    .card-title {
      font-size: 15px;
      font-weight: 700;
      margin: 0 0 12px;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    select, textarea {
      width: 100%;
      background: var(--bg);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 12px;
      font-size: 14px;
      outline: none;
    }
    textarea { min-height: 90px; resize: vertical; font-family: inherit; }
    .btn-row { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 10px; }
    .btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      width: 100%;
      padding: 12px 14px;
      border-radius: 12px;
      border: none;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      text-decoration: none;
      background: var(--accent);
      color: var(--accent-text);
    }
    .btn-secondary { background: rgba(255,255,255,0.08); color: var(--text); }
    .btn-danger { background: rgba(239, 68, 68, 0.16); color: var(--danger); }
    .btn-success { background: rgba(16, 185, 129, 0.16); color: var(--success); }
    .switch-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 11px 0;
      border-bottom: 1px solid var(--border);
    }
    .switch-row:last-child { border-bottom: none; }
    .switch-info { padding-right: 12px; }
    .switch-title { font-size: 14px; font-weight: 600; }
    .switch-desc { font-size: 12px; color: var(--hint); margin-top: 2px; }
    input[type="checkbox"] {
      width: 22px;
      height: 22px;
      accent-color: var(--accent);
      cursor: pointer;
      flex-shrink: 0;
    }
    .muted { font-size: 13px; color: var(--hint); margin: 0 0 10px; line-height: 1.4; }
  </style>
</head>
<body>
  <div class="header">
    <h1>🛡 Хранитель чата</h1>
    <span class="badge">● Online</span>
  </div>

  <div class="card">
    <div class="card-title">💬 Управление чатами</div>
    <p class="muted">Выберите группу для настройки или добавьте бота в новый чат.</p>
    <select id="chatSelect" onchange="loadChatData()"></select>
    <div class="btn-row">
      <a class="btn" href="https://t.me" target="_blank">➕ Добавить чат</a>
      <button class="btn btn-danger" onclick="removeChat()">🗑 Удалить чат</button>
    </div>
  </div>
    <div id="controls" style="display:none;">
    <div class="card">
      <div class="card-title">🔐 Режим общения (как в Ирисе)</div>
      <p class="muted">Мгновенно закрывает или открывает возможность писать сообщения обычным участникам.</p>
      <div class="btn-row">
        <button class="btn btn-danger" onclick="setChatLock(true)">🔒 -чат (Закрыть)</button>
        <button class="btn btn-success" onclick="setChatLock(false)">🔓 +чат (Открыть)</button>
      </div>
    </div>

    <div class="card">
      <div class="card-title">⚙️ Модули защиты и игры</div>
      <div class="switch-row">
        <div class="switch-info">
          <div class="switch-title">🤬 Умный антимат</div>
          <div class="switch-desc">Фильтрует мат в предложениях и с заменой букв</div>
        </div>
        <input type="checkbox" id="profanity" />
      </div>
      <div class="switch-row">
        <div class="switch-info">
          <div class="switch-title">⚡ Защита от флуда и спама</div>
          <div class="switch-desc">Блокирует частые однотипные сообщения</div>
        </div>
        <input type="checkbox" id="antispam" />
      </div>
      <div class="switch-row">
        <div class="switch-info">
          <div class="switch-title">🔗 Антиреклама и ссылки</div>
          <div class="switch-desc">Удаляет сторонние ссылки и инвайты</div>
        </div>
        <input type="checkbox" id="antilink" />
      </div>
      <div class="switch-row">
        <div class="switch-info">
          <div class="switch-title">📢 Проверка подписки на канал</div>
          <div class="switch-desc">Проверяет подписку при входе по заявкам</div>
        </div>
        <input type="checkbox" id="subcheck" />
      </div>
      <div class="switch-row">
        <div class="switch-info">
          <div class="switch-title">👋 Приветствия и прощания</div>
          <div class="switch-desc">Встречает новичков с правилами и прощается при выходе</div>
        </div>
        <input type="checkbox" id="welcome" />
      </div>
      <div class="switch-row">
        <div class="switch-info">
          <div class="switch-title">🎭 Ролеплей-команды</div>
          <div class="switch-desc">Обнять, дать леща, кастомные /newrp</div>
        </div>
        <input type="checkbox" id="rp_enabled" />
      </div>
      <div class="switch-row">
        <div class="switch-info">
          <div class="switch-title">🔫 Русская рулетка</div>
          <div class="switch-desc">Игра на мут и монеты «Алиби»</div>
        </div>
        <input type="checkbox" id="roulette_enabled" />
      </div>
      <button class="btn" style="margin-top:12px;" onclick="saveSettings()">💾 Сохранить настройки</button>
    </div>

    <div class="card">
      <div class="card-title">📜 Правила чата</div>
      <textarea id="rulesText" placeholder="Введите текст правил чата..."></textarea>
      <button class="btn btn-secondary" style="margin-top:10px;" onclick="saveRules()">📝 Обновить правила</button>
    </div>
  </div>

  <script>
    const tg = window.Telegram && window.Telegram.WebApp;
    if (tg) { tg.ready(); tg.expand(); }

    function notify(msg) {
      if (tg && tg.showAlert) tg.showAlert(msg);
      else alert(msg);
    }

    async function loadChats() {
      const res = await fetch("/api/chats");
      const data = await res.json();
      const sel = document.getElementById("chatSelect");
      sel.innerHTML = "";
      if (!data.chats || data.chats.length === 0) {
        const opt = document.createElement("option");
        opt.value = "";
        opt.textContent = "Нет подключённых чатов (напишите в группе)";
        sel.appendChild(opt);
        document.getElementById("controls").style.display = "none";
        return;
      }
      data.chats.forEach(c => {
        const opt = document.createElement("option");
        opt.value = c.chat_id;
        opt.textContent = `${c.title} (${c.chat_id})`;
        sel.appendChild(opt);
      });
      document.getElementById("controls").style.display = "block";
      await loadChatData();
    }

    async function loadChatData() {
      const chatId = document.getElementById("chatSelect").value;
      if (!chatId) return;
      const res = await fetch(`/api/chat/${chatId}`);
      const d = await res.json();
      document.getElementById("profanity").checked = d.profanity;
      document.getElementById("antispam").checked = d.antispam;
      document.getElementById("antilink").checked = d.antilink;
      document.getElementById("subcheck").checked = d.subcheck;
      document.getElementById("welcome").checked = d.welcome;
      document.getElementById("rp_enabled").checked = d.rp_enabled;
      document.getElementById("roulette_enabled").checked = d.roulette_enabled;
      document.getElementById("rulesText").value = d.rules || "";
    }

    async function saveSettings() {
      const chatId = document.getElementById("chatSelect").value;
      if (!chatId) return;
      const payload = {
        profanity: document.getElementById("profanity").checked,
        antispam: document.getElementById("antispam").checked,
        antilink: document.getElementById("antilink").checked,
        subcheck: document.getElementById("subcheck").checked,
        welcome: document.getElementById("welcome").checked,
        rp_enabled: document.getElementById("rp_enabled").checked,
        roulette_enabled: document.getElementById("roulette_enabled").checked,
      };
      const res = await fetch(`/api/chat/${chatId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      notify(res.ok ? "✅ Настройки успешно сохранены!" : "⚠️ Ошибка сохранения.");
    }

    async function saveRules() {
      const chatId = document.getElementById("chatSelect").value;
      if (!chatId) return;
      const rules = document.getElementById("rulesText").value;
      const res = await fetch(`/api/chat/${chatId}/rules`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rules })
      });
      notify(res.ok ? "📝 Правила чата обновлены!" : "⚠️ Не удалось обновить правила.");
    }

    async function setChatLock(locked) {
      const chatId = document.getElementById("chatSelect").value;
      if (!chatId) return;
      const res = await fetch(`/api/chat/${chatId}/lock`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ locked })
      });
      const d = await res.json();
      notify(d.ok ? (locked ? "🔒 Чат закрыт для участников!" : "🔓 Чат открыт для всех!") : `⚠️ ${d.error}`);
    }

    async function removeChat() {
      const chatId = document.getElementById("chatSelect").value;
      if (!chatId) return;
      const res = await fetch(`/api/chat/${chatId}`, { method: "DELETE" });
      if (res.ok) {
        notify("🗑 Чат удалён из панели.");
        await loadChats();
      }
    }

    loadChats();
  </script>
</body>
</html>"""
    return web.Response(text=html, content_type="text/html")


async def api_get_chats(request: web.Request) -> web.Response:
    return web.json_response({"chats": db.get_chats()})


async def api_get_chat(request: web.Request) -> web.Response:
    chat_id = int(request.match_info["chat_id"])
    st = db.get_chat_settings(chat_id)
    st["rp_enabled"] = db.get_setting(chat_id, "rp_enabled") != "0"
    st["roulette_enabled"] = db.get_setting(chat_id, "roulette_enabled") != "0"
    st["rules"] = db.get_setting(chat_id, "rules") or ""
    return web.json_response(st)


async def api_save_chat(request: web.Request) -> web.Response:
    chat_id = int(request.match_info["chat_id"])
    data = await request.json()
    db.update_chat_settings(chat_id, data)
    db.set_setting(chat_id, "rp_enabled", "1" if data.get("rp_enabled", True) else "0")
    db.set_setting(chat_id, "roulette_enabled", "1" if data.get("roulette_enabled", True) else "0")
    return web.json_response({"ok": True})


async def api_save_rules(request: web.Request) -> web.Response:
    chat_id = int(request.match_info["chat_id"])
    data = await request.json()
    raw = (data.get("rules") or "").strip()
    if not raw:
        db.set_setting(chat_id, "rules", None)
    else:
        formatted = raw if "<blockquote" in raw else f"<blockquote expandable>{raw}</blockquote>"
        db.set_setting(chat_id, "rules", formatted)
    return web.json_response({"ok": True})


async def api_lock_chat(request: web.Request) -> web.Response:
    chat_id = int(request.match_info["chat_id"])
    data = await request.json()
    locked = bool(data.get("locked", False))
    try:
        await bot.set_chat_permissions(chat_id, permissions=_LOCKED_PERMS if locked else _UNLOCKED_PERMS)
        await bot.send_message(
            chat_id,
            "🔒 <b>Чат закрыт через админ-панель.</b> Писать могут только админы."
            if locked
            else "🔓 <b>Чат открыт через админ-панель.</b> Участники снова могут писать.",
        )
        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=400)


async def api_delete_chat(request: web.Request) -> web.Response:
    chat_id = int(request.match_info["chat_id"])
    db.delete_chat(chat_id)
    return web.json_response({"ok": True})


def setup_routes(app: web.Application) -> None:
    app.router.add_get("/webapp", webapp_page)
    app.router.add_get("/health", health)
    app.router.add_get("/api/chats", api_get_chats)
    app.router.add_get("/api/chat/{chat_id}", api_get_chat)
    app.router.add_post("/api/chat/{chat_id}", api_save_chat)
    app.router.add_post("/api/chat/{chat_id}/rules", api_save_rules)
    app.router.add_post("/api/chat/{chat_id}/lock", api_lock_chat)
    app.router.add_delete("/api/chat/{chat_id}", api_delete_chat)
