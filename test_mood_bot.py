import sqlite3
import re
from datetime import datetime

DB_FILE = "mood.db"

TEST_MESSAGES = [
    "проснулась с мыслями о нём, +5",
    "-8 ссора с мужем",
    "хороший завтрак +3",
    "прогулка за пивом, +7",
    "+10 путешествие с мужем",
]


def parse_message(text: str) -> tuple[int, str] | None:
    """Вытаскивает оценку и описание из произвольного текста."""
    match = re.search(r"([+-]\d+)", text)
    if not match:
        return None
    score = int(match.group(1))
    description = re.sub(r"[+-]\d+", "", text).strip().strip(",").strip()
    return score, description


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mood_logs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
            score       INTEGER NOT NULL,
            description TEXT    NOT NULL
        )
    """)
    conn.commit()


def insert_log(conn: sqlite3.Connection, user_id: int, score: int, description: str) -> int:
    cur = conn.execute(
        "INSERT INTO mood_logs (user_id, score, description) VALUES (?, ?, ?)",
        (user_id, score, description),
    )
    conn.commit()
    return cur.lastrowid


def fetch_all(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    cur = conn.execute(
        "SELECT id, user_id, created_at, score, description FROM mood_logs ORDER BY id"
    )
    return cur.fetchall()


def fetch_total(conn: sqlite3.Connection, user_id: int) -> int:
    cur = conn.execute(
        "SELECT COALESCE(SUM(score), 0) FROM mood_logs WHERE user_id = ?",
        (user_id,),
    )
    return cur.fetchone()[0]


def separator(char: str = "─", width: int = 60) -> str:
    return char * width


def main() -> None:
    user_id = 12345

    print(separator("═"))
    print("  ТЕСТ: бот трекинга настроения")
    print(separator("═"))

    # ── 1. Парсинг ──────────────────────────────────────────────
    print("\n[1] Парсинг тестовых сообщений\n")
    print(f"  {'Сообщение':<40} {'Оценка':>7}  Описание")
    print(separator())

    parsed: list[tuple[int, str]] = []
    for msg in TEST_MESSAGES:
        result = parse_message(msg)
        if result:
            score, desc = result
            parsed.append((score, desc))
            sign = "+" if score > 0 else ""
            print(f"  {msg:<40} {sign + str(score):>7}  {desc}")
        else:
            print(f"  {msg:<40}  [не удалось распознать оценку]")

    # ── 2. База данных ───────────────────────────────────────────
    print(f"\n[2] Инициализация базы ({DB_FILE})\n")
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    print("  Таблица mood_logs создана (или уже существует).")

    # ── 3. Запись ────────────────────────────────────────────────
    print(f"\n[3] Запись {len(parsed)} записей в базу\n")
    for score, desc in parsed:
        row_id = insert_log(conn, user_id, score, desc)
        sign = "+" if score > 0 else ""
        print(f"  id={row_id}  score={sign}{score}  desc={desc!r}")

    # ── 4. Выборка ───────────────────────────────────────────────
    print("\n[4] Все записи из базы\n")
    rows = fetch_all(conn)
    print(f"  {'id':>3}  {'user_id':>8}  {'created_at':<19}  {'score':>6}  описание")
    print(separator())
    for row in rows:
        sign = "+" if row["score"] > 0 else ""
        print(
            f"  {row['id']:>3}  {row['user_id']:>8}  {row['created_at']:<19}"
            f"  {sign + str(row['score']):>6}  {row['description']}"
        )

    # ── 5. Итог ──────────────────────────────────────────────────
    total = fetch_total(conn, user_id)
    sign = "+" if total > 0 else ""
    print(f"\n[5] Сумма баллов для пользователя {user_id}: {sign}{total}")

    conn.close()
    print(f"\n{separator('═')}")
    print("  Тест завершён.")
    print(separator("═"))


if __name__ == "__main__":
    main()
