"""Умный антимат-фильтр (совместим со всеми старыми и новыми модулями)."""
import re

_HOMOGLYPHS = str.maketrans({
    "a": "а", "e": "е", "o": "о", "p": "р", "c": "с", "y": "у", "x": "х",
    "k": "к", "m": "м", "t": "т", "b": "в", "h": "н", "0": "о", "3": "з", "6": "б",
    "ё": "е",
})

_BAD_ROOTS = [
    r"\b[хx][уy][ййияеюё]\w*",
    r"\bп[ие]зд\w*",
    r"\b[её]б\w*",
    r"\b[а-я]*[её]б[ауоыи]\w*",
    r"\bбля[дт]?\w*",
    r"\bсуч?[кч]\w*",
    r"\bсук[аиуео]\w*",
    r"\bпид[аое]?р\w*",
    r"\bмуд[аиоу]\w*",
    r"\bгандон\w*|\bгондон\w*",
    r"\bзалуп\w*",
    r"\bшлюх\w*",
    r"\bублюд\w*",
    r"\bмраз[ьи]\w*",
    r"\bебл\w*",
    r"\bоху\w*|\bаху\w*",
    r"\bнаху\w*|\bпоху\w*",
]

_COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _BAD_ROOTS]

_WHITELIST = {
    "ребенок", "ребёнок", "ребенка", "учебник", "хлеб", "небо", "небеса",
    "стебель", "мебель", "лебедь", "гребля", "оскорблять", "употреблять",
    "истреблять", "колебать", "подстрахуй", "страхуй", "мандарин", "скипидар",
}


def _normalize(text: str) -> str:
    text = text.lower().translate(_HOMOGLYPHS)
    text = re.sub(r"(.)\1{2,}", r"\1", text)
    text = re.sub(r"(?<=\b[а-я])[\s._-]+(?=[а-я]\b)", "", text)
    return text


def contains_profanity(text: str | None) -> bool:
    if not text:
        return False
    normalized = _normalize(text)
    words = re.findall(r"[а-я]+", normalized)
    for word in words:
        if word in _WHITELIST:
            continue
        for pattern in _COMPILED_PATTERNS:
            if pattern.search(word):
                return True
    for pattern in _COMPILED_PATTERNS:
        if pattern.search(normalized):
            if not any(w in normalized for w in _WHITELIST):
                return True
    return False


# Алиасы на случай, если automod.py вызывает другое имя функции
def has_profanity(text: str | None) -> bool:
    return contains_profanity(text)


def check_profanity(text: str | None) -> bool:
    return contains_profanity(text)


def is_profane(text: str | None) -> bool:
    return contains_profanity(text)
    has_bad_word = contains_profanity
has_profanity = contains_profanity
check_profanity = contains_profanity
