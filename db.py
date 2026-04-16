import os
import sqlite3
from datetime import date, time as dtime
from pathlib import Path

DB_PATH = Path(os.environ.get("DB_PATH", Path(__file__).parent / "mood.db"))


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mood_logs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                created_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
                end_time    TEXT,
                score       INTEGER NOT NULL,
                description TEXT    NOT NULL
            )
        """)
        # Миграция: добавляем end_time если таблица уже существует без неё
        try:
            conn.execute("ALTER TABLE mood_logs ADD COLUMN end_time TEXT")
        except sqlite3.OperationalError:
            pass  # Колонка уже есть
        conn.commit()


def insert_log(
    user_id: int,
    score: int,
    description: str,
    start_time: dtime | None = None,
    end_time: dtime | None = None,
) -> sqlite3.Row:
    created_at = (
        f"{date.today().isoformat()} {start_time.strftime('%H:%M:%S')}"
        if start_time else None
    )
    end_time_str = end_time.strftime("%H:%M:%S") if end_time else None

    if created_at:
        sql = """INSERT INTO mood_logs (user_id, created_at, end_time, score, description)
                 VALUES (?, ?, ?, ?, ?)"""
        params = (user_id, created_at, end_time_str, score, description)
    else:
        sql = """INSERT INTO mood_logs (user_id, end_time, score, description)
                 VALUES (?, ?, ?, ?)"""
        params = (user_id, end_time_str, score, description)

    with get_conn() as conn:
        conn.execute(sql, params)
        conn.commit()
        row = conn.execute(
            "SELECT * FROM mood_logs WHERE rowid = last_insert_rowid()"
        ).fetchone()
    return row


def get_last_log(user_id: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM mood_logs WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (user_id,)
        ).fetchone()


def delete_last_log(user_id: int) -> sqlite3.Row | None:
    """Удаляет последнюю запись пользователя. Возвращает удалённую строку или None."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM mood_logs WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (user_id,)
        ).fetchone()
        if row:
            conn.execute("DELETE FROM mood_logs WHERE id = ?", (row["id"],))
            conn.commit()
    return row


def delete_user_logs(user_id: int) -> int:
    """Удаляет все записи пользователя. Возвращает количество удалённых строк."""
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM mood_logs WHERE user_id = ?", (user_id,))
        conn.commit()
    return cur.rowcount


def fetch_stats(user_id: int, date_from: str, date_to: str) -> dict:
    sql = """
        SELECT
            COUNT(*)                 AS cnt,
            COALESCE(SUM(score), 0)  AS total,
            ROUND(AVG(score), 2)     AS avg_score
        FROM mood_logs
        WHERE user_id = ?
          AND created_at >= ?
          AND created_at <= ?
    """
    with get_conn() as conn:
        row = conn.execute(
            sql, (user_id, f"{date_from} 00:00:00", f"{date_to} 23:59:59")
        ).fetchone()
    return dict(row)


def fetch_rows(user_id: int, date_from: str, date_to: str) -> list[sqlite3.Row]:
    sql = """
        SELECT created_at, end_time, score, description
        FROM mood_logs
        WHERE user_id = ?
          AND created_at >= ?
          AND created_at <= ?
        ORDER BY created_at ASC, id ASC
    """
    with get_conn() as conn:
        rows = conn.execute(
            sql, (user_id, f"{date_from} 00:00:00", f"{date_to} 23:59:59")
        ).fetchall()
    return rows
