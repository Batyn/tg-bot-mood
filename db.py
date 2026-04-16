import os
import sqlite3
from datetime import date, time as dtime
from pathlib import Path

# Локально: рядом со скриптом. На сервере: /data/mood.db (постоянный диск)
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
                score       INTEGER NOT NULL,
                description TEXT    NOT NULL
            )
        """)
        conn.commit()


def insert_log(
    user_id: int,
    score: int,
    description: str,
    custom_time: dtime | None = None,
) -> sqlite3.Row:
    if custom_time is not None:
        created_at = f"{date.today().isoformat()} {custom_time.strftime('%H:%M:%S')}"
        sql = "INSERT INTO mood_logs (user_id, created_at, score, description) VALUES (?, ?, ?, ?)"
        params = (user_id, created_at, score, description)
    else:
        sql = "INSERT INTO mood_logs (user_id, score, description) VALUES (?, ?, ?)"
        params = (user_id, score, description)

    with get_conn() as conn:
        conn.execute(sql, params)
        conn.commit()
        row = conn.execute(
            "SELECT * FROM mood_logs WHERE rowid = last_insert_rowid()"
        ).fetchone()
    return row


def fetch_stats(user_id: int, date_from: str, date_to: str) -> dict:
    """
    date_from / date_to — строки в формате 'YYYY-MM-DD'.
    date_to включительно (добавляем 23:59:59).
    """
    sql = """
        SELECT
            COUNT(*)        AS cnt,
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


def delete_user_logs(user_id: int) -> int:
    """Удаляет все записи пользователя. Возвращает количество удалённых строк."""
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM mood_logs WHERE user_id = ?", (user_id,))
        conn.commit()
    return cur.rowcount


def fetch_rows(user_id: int, date_from: str, date_to: str) -> list[sqlite3.Row]:
    sql = """
        SELECT created_at, score, description
        FROM mood_logs
        WHERE user_id = ?
          AND created_at >= ?
          AND created_at <= ?
        ORDER BY created_at
    """
    with get_conn() as conn:
        rows = conn.execute(
            sql, (user_id, f"{date_from} 00:00:00", f"{date_to} 23:59:59")
        ).fetchall()
    return rows
