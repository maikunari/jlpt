import sqlite3
import os
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(os.getenv("DB_PATH", "data/jlpt_study.db"))

def get_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

@contextmanager
def get_db_conn():
    conn = get_db()
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    with get_db_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                title TEXT,
                audio_path TEXT,
                transcript TEXT,
                jlpt_level TEXT DEFAULT 'N3',
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS extractions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                episode_id INTEGER NOT NULL,
                type TEXT NOT NULL,  -- 'vocab', 'grammar', 'collocation'
                japanese TEXT NOT NULL,
                reading TEXT,
                english TEXT NOT NULL,
                jlpt_tag TEXT,
                context_sentence TEXT,
                usage_note TEXT,
                anki_note_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (episode_id) REFERENCES episodes(id)
            );

            CREATE TABLE IF NOT EXISTS listens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                episode_id INTEGER NOT NULL,
                listened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                listen_number INTEGER DEFAULT 1,
                notes TEXT,
                FOREIGN KEY (episode_id) REFERENCES episodes(id)
            );

            CREATE TABLE IF NOT EXISTS relisten_schedule (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                episode_id INTEGER NOT NULL,
                scheduled_for DATE NOT NULL,
                completed INTEGER DEFAULT 0,
                interval_days INTEGER NOT NULL,
                FOREIGN KEY (episode_id) REFERENCES episodes(id)
            );

            CREATE INDEX IF NOT EXISTS idx_extractions_episode ON extractions(episode_id);
            CREATE INDEX IF NOT EXISTS idx_relisten_schedule ON relisten_schedule(completed, scheduled_for);
            CREATE INDEX IF NOT EXISTS idx_listens_episode ON listens(episode_id);
        """)
        conn.commit()

# --- Episode CRUD ---

def create_episode(url: str, title: str = None, jlpt_level: str = "N3") -> int:
    with get_db_conn() as conn:
        cur = conn.execute(
            "INSERT INTO episodes (url, title, jlpt_level) VALUES (?, ?, ?)",
            (url, title, jlpt_level)
        )
        conn.commit()
        return cur.lastrowid

_EPISODE_COLUMNS = {"url", "title", "audio_path", "transcript", "jlpt_level", "status"}

def update_episode(eid: int, **kwargs):
    unknown = set(kwargs) - _EPISODE_COLUMNS
    if unknown:
        raise ValueError(f"Unknown episode columns: {unknown}")
    with get_db_conn() as conn:
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [eid]
        conn.execute(f"UPDATE episodes SET {sets} WHERE id = ?", vals)
        conn.commit()

def get_episode(eid: int) -> dict | None:
    with get_db_conn() as conn:
        row = conn.execute("SELECT * FROM episodes WHERE id = ?", (eid,)).fetchone()
        return dict(row) if row else None

def get_all_episodes() -> list:
    with get_db_conn() as conn:
        rows = conn.execute("SELECT * FROM episodes ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

def delete_episode(eid: int):
    with get_db_conn() as conn:
        conn.execute("DELETE FROM extractions WHERE episode_id = ?", (eid,))
        conn.execute("DELETE FROM listens WHERE episode_id = ?", (eid,))
        conn.execute("DELETE FROM relisten_schedule WHERE episode_id = ?", (eid,))
        conn.execute("DELETE FROM episodes WHERE id = ?", (eid,))
        conn.commit()

# --- Extraction CRUD ---

def save_extractions(episode_id: int, items: list[dict]):
    with get_db_conn() as conn:
        for item in items:
            conn.execute(
                """INSERT INTO extractions
                   (episode_id, type, japanese, reading, english, jlpt_tag, context_sentence, usage_note)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (episode_id, item["type"], item["japanese"], item.get("reading"),
                 item["english"], item.get("jlpt_tag"), item.get("context_sentence"),
                 item.get("usage_note"))
            )
        conn.commit()

def get_extractions(episode_id: int) -> list:
    with get_db_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM extractions WHERE episode_id = ? ORDER BY type, id", (episode_id,)
        ).fetchall()
        return [dict(r) for r in rows]

def update_extraction_anki_id(extraction_id: int, anki_note_id: int):
    with get_db_conn() as conn:
        conn.execute(
            "UPDATE extractions SET anki_note_id = ? WHERE id = ?",
            (anki_note_id, extraction_id)
        )
        conn.commit()

def clear_extractions(episode_id: int):
    """Delete all extractions for an episode (used before retry)."""
    with get_db_conn() as conn:
        conn.execute("DELETE FROM extractions WHERE episode_id = ?", (episode_id,))
        conn.commit()

def delete_extraction(extraction_id: int):
    with get_db_conn() as conn:
        conn.execute("DELETE FROM extractions WHERE id = ?", (extraction_id,))
        conn.commit()

# --- Listen tracking ---

def record_listen(episode_id: int, notes: str = None) -> int:
    with get_db_conn() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM listens WHERE episode_id = ?", (episode_id,)
        ).fetchone()[0]
        cur = conn.execute(
            "INSERT INTO listens (episode_id, listen_number, notes) VALUES (?, ?, ?)",
            (episode_id, count + 1, notes)
        )
        conn.commit()
        listen_id = cur.lastrowid
    # Schedule next re-listen (uses its own connection)
    _schedule_relisten(episode_id, count + 1)
    return listen_id

def get_listens(episode_id: int) -> list:
    with get_db_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM listens WHERE episode_id = ? ORDER BY listened_at", (episode_id,)
        ).fetchall()
        return [dict(r) for r in rows]

# --- Re-listen SRS scheduling ---

RELISTEN_INTERVALS = [1, 3, 7, 14, 30]  # days after each listen

def _schedule_relisten(episode_id: int, listen_count: int):
    if listen_count - 1 < len(RELISTEN_INTERVALS):
        interval = RELISTEN_INTERVALS[listen_count - 1]
    else:
        interval = 30  # monthly after exhausting intervals

    scheduled = datetime.now() + timedelta(days=interval)
    with get_db_conn() as conn:
        conn.execute(
            """INSERT INTO relisten_schedule (episode_id, scheduled_for, interval_days)
               VALUES (?, ?, ?)""",
            (episode_id, scheduled.date().isoformat(), interval)
        )
        conn.commit()

def get_due_relistens() -> list:
    with get_db_conn() as conn:
        rows = conn.execute(
            """SELECT rs.*, e.title, e.url
               FROM relisten_schedule rs
               JOIN episodes e ON rs.episode_id = e.id
               WHERE rs.completed = 0 AND rs.scheduled_for <= date('now')
               ORDER BY rs.scheduled_for""",
        ).fetchall()
        return [dict(r) for r in rows]

def complete_relisten(schedule_id: int):
    with get_db_conn() as conn:
        conn.execute(
            "UPDATE relisten_schedule SET completed = 1 WHERE id = ?", (schedule_id,)
        )
        conn.commit()

def get_upcoming_relistens(days: int = 7) -> list:
    with get_db_conn() as conn:
        rows = conn.execute(
            """SELECT rs.*, e.title, e.url
               FROM relisten_schedule rs
               JOIN episodes e ON rs.episode_id = e.id
               WHERE rs.completed = 0
               AND rs.scheduled_for <= date('now', ?)
               ORDER BY rs.scheduled_for""",
            (f"+{days} days",)
        ).fetchall()
        return [dict(r) for r in rows]
