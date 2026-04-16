import re
from datetime import time as dtime

# ── Нормализация форм периода суток ───────────────────────────────────────

_PERIOD_NORM = {
    "утра": "утра", "утром": "утра",
    "дня": "дня", "днём": "дня", "днем": "дня",
    "вечера": "вечера", "вечером": "вечера",
    "ночи": "ночи", "ночью": "ночи",
}
_PERIOD_WORDS = "|".join(_PERIOD_NORM.keys())

# "в 5 вечера", "11 утра", "в 3 ночи", "9:30 утром"  — период ПОСЛЕ числа
_PERIOD_AFTER_RE = re.compile(
    rf"(?:в\s+)?(\d{{1,2}})(?::(\d{{2}}))?\s*({_PERIOD_WORDS})",
    re.IGNORECASE,
)

# "утром в 11", "вечером в 5:30", "ночью в 3"  — период ПЕРЕД числом
_PERIOD_BEFORE_RE = re.compile(
    rf"({_PERIOD_WORDS})\s+(?:в\s+)?(\d{{1,2}})(?::(\d{{2}}))?",
    re.IGNORECASE,
)

# "с 11 до 16", "с 9:30 до 18:00"  — диапазон времени
_RANGE_RE = re.compile(
    r"с\s+(\d{1,2})(?::(\d{2}))?\s+до\s+(\d{1,2})(?::(\d{2}))?",
    re.IGNORECASE,
)

# "11:00", "в 9:30"  — просто HH:MM без слова периода
_TIME_RE = re.compile(r"(?:в\s+)?(\d{1,2}):(\d{2})", re.IGNORECASE)

# Оценка: +5, -8, +10, или просто 0
_SCORE_RE = re.compile(r"([+-]\d+|(?<![:\d])0(?!\d))")


def _apply_period(hour: int, period: str) -> int:
    """Переводит час + период суток в 24-часовой формат."""
    p = _PERIOD_NORM.get(period.lower(), period.lower())
    if p == "утра":
        return hour                                    # 1–12 → 01:00–12:00
    if p in ("дня", "вечера"):
        return hour if hour == 12 else hour + 12       # 1–11 → 13:00–23:00
    if p == "ночи":
        if hour == 12:
            return 0                                   # 12 ночи = 00:00
        return hour if hour <= 5 else hour + 12        # 1–5 → AM, 6–11 → PM
    return hour


def _clean(text: str) -> str:
    return re.sub(r"\s{2,}", " ", text).strip().strip(",").strip()


def parse_time(text: str) -> tuple[dtime | None, str]:
    """
    Ищет время в тексте.
    Возвращает (time | None, текст без найденного времени).
    Для диапазона "с X до Y" берёт время начала, диапазон остаётся в описании.
    """
    # 0. Диапазон "с 11 до 16" — берём время начала, диапазон вырезаем из текста
    m = _RANGE_RE.search(text)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2)) if m.group(2) else 0
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return dtime(hour, minute), _clean(_RANGE_RE.sub("", text, count=1))

    # 1. Период после числа: "11 утра", "в 5 вечера", "утром" и т.д.
    m = _PERIOD_AFTER_RE.search(text)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2)) if m.group(2) else 0
        hour = _apply_period(hour, m.group(3))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return dtime(hour, minute), _clean(_PERIOD_AFTER_RE.sub("", text, count=1))

    # 2. Период перед числом: "утром в 11", "вечером в 5"
    m = _PERIOD_BEFORE_RE.search(text)
    if m:
        hour = int(m.group(2))
        minute = int(m.group(3)) if m.group(3) else 0
        hour = _apply_period(hour, m.group(1))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return dtime(hour, minute), _clean(_PERIOD_BEFORE_RE.sub("", text, count=1))

    # 3. Просто HH:MM
    m = _TIME_RE.search(text)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return dtime(hour, minute), _clean(_TIME_RE.sub("", text, count=1))

    return None, text


def parse_message(text: str) -> tuple[int, str, dtime | None] | None:
    """
    Возвращает (score, description, custom_time) или None, если оценка не найдена.
    """
    custom_time, text_no_time = parse_time(text)

    m = _SCORE_RE.search(text_no_time)
    if not m:
        return None

    score = int(m.group(1))
    description = _clean(_SCORE_RE.sub("", text_no_time, count=1))
    return score, description, custom_time
