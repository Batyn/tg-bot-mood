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

# "с 11 до 16", "с 9:30 до 18:00"  — диапазон через «с...до»
_RANGE_WORD_RE = re.compile(
    r"с\s+(\d{1,2})(?::(\d{2}))?\s+до\s+(\d{1,2})(?::(\d{2}))?",
    re.IGNORECASE,
)

# "14-16", "9:30-18:00"  — диапазон через дефис
# Требуем, что перед первым числом нет знака +/- (иначе это оценка)
_RANGE_DASH_RE = re.compile(
    r"(?<![+\-\d])(\d{1,2})(?::(\d{2}))?-(\d{1,2})(?::(\d{2}))?(?!\d)",
)

# "11:00", "в 9:30"  — просто HH:MM без слова периода
_TIME_RE = re.compile(r"(?:в\s+)?(\d{1,2}):(\d{2})", re.IGNORECASE)

# Оценка: +5, -8, +10, или просто 0
_SCORE_RE = re.compile(r"([+-]\d+|(?<![:\d])0(?!\d))")


def _apply_period(hour: int, period: str) -> int:
    """Переводит час + период суток в 24-часовой формат."""
    p = _PERIOD_NORM.get(period.lower(), period.lower())
    if p == "утра":
        return hour
    if p in ("дня", "вечера"):
        return hour if hour == 12 else hour + 12
    if p == "ночи":
        if hour == 12:
            return 0
        return hour if hour <= 5 else hour + 12
    return hour


def _clean(text: str) -> str:
    return re.sub(r"\s{2,}", " ", text).strip().strip(",").strip()


def _valid_hour(h: int) -> bool:
    return 0 <= h <= 23


def parse_time(text: str) -> tuple[dtime | None, dtime | None, str]:
    """
    Ищет время в тексте.
    Возвращает (start_time | None, end_time | None, текст без времени).
    """
    # 0а. Диапазон «с 11 до 16»
    m = _RANGE_WORD_RE.search(text)
    if m:
        sh, sm = int(m.group(1)), int(m.group(2) or 0)
        eh, em = int(m.group(3)), int(m.group(4) or 0)
        if _valid_hour(sh) and _valid_hour(eh):
            cleaned = _clean(_RANGE_WORD_RE.sub("", text, count=1))
            return dtime(sh, sm), dtime(eh, em), cleaned

    # 0б. Диапазон через дефис «14-16», «9:30-18:00»
    m = _RANGE_DASH_RE.search(text)
    if m:
        sh, sm = int(m.group(1)), int(m.group(2) or 0)
        eh, em = int(m.group(3)), int(m.group(4) or 0)
        if _valid_hour(sh) and _valid_hour(eh) and sh != eh:
            cleaned = _clean(_RANGE_DASH_RE.sub("", text, count=1))
            return dtime(sh, sm), dtime(eh, em), cleaned

    # 1. Период после числа: «11 утра», «в 5 вечера»
    m = _PERIOD_AFTER_RE.search(text)
    if m:
        hour = _apply_period(int(m.group(1)), m.group(3))
        minute = int(m.group(2) or 0)
        if _valid_hour(hour):
            return dtime(hour, minute), None, _clean(_PERIOD_AFTER_RE.sub("", text, count=1))

    # 2. Период перед числом: «утром в 11», «вечером в 5»
    m = _PERIOD_BEFORE_RE.search(text)
    if m:
        hour = _apply_period(int(m.group(2)), m.group(1))
        minute = int(m.group(3) or 0)
        if _valid_hour(hour):
            return dtime(hour, minute), None, _clean(_PERIOD_BEFORE_RE.sub("", text, count=1))

    # 3. Просто HH:MM
    m = _TIME_RE.search(text)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        if _valid_hour(hour):
            return dtime(hour, minute), None, _clean(_TIME_RE.sub("", text, count=1))

    return None, None, text


def parse_message(text: str) -> tuple[int, str, dtime | None, dtime | None] | None:
    """
    Возвращает (score, description, start_time, end_time) или None.
    """
    start_time, end_time, text_no_time = parse_time(text)

    m = _SCORE_RE.search(text_no_time)
    if not m:
        return None

    score = int(m.group(1))
    description = _clean(_SCORE_RE.sub("", text_no_time, count=1))
    return score, description, start_time, end_time
