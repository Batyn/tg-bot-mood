import os
import sqlite3
from datetime import date, datetime, time as dtime
from pathlib import Path

DB_PATH = Path(os.environ.get("DB_PATH", Path(__file__).parent / "mood.db"))


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        # Трекер настроения
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mood_logs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                created_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
                end_time    TEXT,
                sent_at     TEXT,
                score       INTEGER NOT NULL,
                description TEXT    NOT NULL
            )
        """)
        # КПТ ABC
        conn.execute("""
            CREATE TABLE IF NOT EXISTS abc_logs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                created_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
                sent_at     TEXT,
                situation   TEXT    NOT NULL,
                thoughts    TEXT    NOT NULL,
                feelings    TEXT    NOT NULL,
                comment     TEXT
            )
        """)
        # Настройки пользователя
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id  INTEGER PRIMARY KEY,
                mode     TEXT    NOT NULL DEFAULT 'mood'
            )
        """)
        # Миграции
        for col in ("end_time TEXT", "sent_at TEXT"):
            try:
                conn.execute(f"ALTER TABLE mood_logs ADD COLUMN {col}")
            except sqlite3.OperationalError:
                pass
        conn.commit()


# ── Настройки пользователя ─────────────────────────────────────────────────

def get_user_mode(user_id: int) -> str:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT mode FROM user_settings WHERE user_id = ?", (user_id,)
        ).fetchone()
    return row["mode"] if row else "mood"


def set_user_mode(user_id: int, mode: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO user_settings (user_id, mode) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET mode = excluded.mode",
            (user_id, mode),
        )
        conn.commit()


# ── Трекер настроения ──────────────────────────────────────────────────────

def insert_log(
    user_id: int,
    score: int,
    description: str,
    start_time: dtime | None = None,
    end_time: dtime | None = None,
) -> sqlite3.Row:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    created_at = (
        f"{date.today().isoformat()} {start_time.strftime('%H:%M:%S')}"
        if start_time else now
    )
    end_time_str = end_time.strftime("%H:%M:%S") if end_time else None

    with get_conn() as conn:
        conn.execute(
            "INSERT INTO mood_logs (user_id, created_at, end_time, sent_at, score, description) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, created_at, end_time_str, now, score, description),
        )
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
        SELECT created_at, end_time, sent_at, score, description
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


# ── КПТ ABC ────────────────────────────────────────────────────────────────

def insert_abc_log(
    user_id: int,
    situation: str,
    thoughts: str,
    feelings: str,
    comment: str | None = None,
) -> sqlite3.Row:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO abc_logs (user_id, sent_at, situation, thoughts, feelings, comment) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, now, situation, thoughts, feelings, comment),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM abc_logs WHERE rowid = last_insert_rowid()"
        ).fetchone()
    return row


def get_last_abc_log(user_id: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM abc_logs WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (user_id,)
        ).fetchone()


def delete_last_abc_log(user_id: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM abc_logs WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (user_id,)
        ).fetchone()
        if row:
            conn.execute("DELETE FROM abc_logs WHERE id = ?", (row["id"],))
            conn.commit()
    return row


def delete_user_abc_logs(user_id: int) -> int:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM abc_logs WHERE user_id = ?", (user_id,))
        conn.commit()
    return cur.rowcount


def fetch_abc_rows(user_id: int, date_from: str, date_to: str) -> list[sqlite3.Row]:
    sql = """
        SELECT created_at, sent_at, situation, thoughts, feelings, comment
        FROM abc_logs
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
