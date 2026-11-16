"""Все настройки бота. Значения берутся из переменных окружения или из файла .env"""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _int(name: str, default: int = 0) -> int:
    v = os.getenv(name, "").strip()
    return int(v) if v else default


def _set(name: str) -> set[str]:
    return {x.strip().lstrip("@").lower() for x in os.getenv(name, "").split(",") if x.strip()}


BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise SystemExit("Не задан BOT_TOKEN. Укажи токен от @BotFather в переменных окружения.")

# --- Канал для проверки подписки (0 = проверка подписки выключена) ---
CHANNEL_ID = _int("CHANNEL_ID")
CHANNEL_LINK = os.getenv("CHANNEL_LINK", "").strip()

# --- Чат для логов наказаний (0 = не писать логи) ---
LOG_CHAT_ID = _int("LOG_CHAT_ID")

CHAT_NAME = os.getenv("CHAT_NAME", "Чат бот")
DB_PATH = os.getenv("DB_PATH", "bot.db")

# --- Предупреждения ---
WARN_TTL_DAYS = _int("WARN_TTL_DAYS", 30)
DEFAULT_MUTE_SECONDS = _int("DEFAULT_MUTE_SECONDS", 3600)

# --- Антиспам ---
SPAM_COUNT = _int("SPAM_COUNT", 3)
SPAM_WINDOW = _int("SPAM_WINDOW", 20)
FLOOD_COUNT = _int("FLOOD_COUNT", 6)
FLOOD_WINDOW = _int("FLOOD_WINDOW", 8)
REPEAT_COUNT = _int("REPEAT_COUNT", 3)
ENABLE_FLOOD_FILTER = _int("ENABLE_FLOOD_FILTER", 1)

# --- Фильтр рекламы (п.6): ссылки на t.me ---
ENABLE_AD_FILTER = _int("ENABLE_AD_FILTER", 1)
ALLOWED_LINKS = _set("ALLOWED_LINKS")

# --- Фильтры, которые админ может включать/выключать командой /settings ---
FILTER_LABELS = {
    "mat": "Мат (п.9)",
    "spam": "Спам стикерами (п.1)",
    "ad": "Реклама (п.6)",
    "flood": "Флуд (п.2)",
    "inline": "Инлайн-боты (п.11)",
}
FILTER_DEFAULTS = {"mat": True, "spam": True, "ad": bool(ENABLE_AD_FILTER),
                   "flood": bool(ENABLE_FLOOD_FILTER), "inline": True}
