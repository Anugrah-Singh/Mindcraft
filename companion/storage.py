import re
import sqlite3
import difflib
from contextlib import contextmanager
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Any

DB_PATH = Path(__file__).parent / "mindcraft.db"

DEFAULT_HABITS = ["Gym", "Daily Walk", "Read 20 Mins"]

# Words Gemini / the user might use -> the canonical habit they count towards.
HABIT_ALIASES = {
    "Gym": ["gym", "workout", "work out", "exercise", "exercised", "training", "lifting", "weights", "fitness", "run", "running", "jog", "jogging"],
    "Daily Walk": ["walk", "walking", "daily walk", "steps", "stroll"],
    "Read 20 Mins": ["read", "reading", "read 20 mins", "book", "books", "study", "studying"],
}


@contextmanager
def _conn():
    """Connection that is always committed/rolled back and closed (no leaked locks)."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with _conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            priority TEXT DEFAULT 'MEDIUM', -- HIGH, MEDIUM, LOW
            status TEXT DEFAULT 'PENDING',  -- PENDING, COMPLETED
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS habits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            streak_count INTEGER DEFAULT 0,
            last_logged_date DATE
        )
        """)
        for name in DEFAULT_HABITS:
            cursor.execute("INSERT OR IGNORE INTO habits (name, streak_count, last_logged_date) VALUES (?, 0, NULL)", (name,))


# ---------------------------------------------------------------- tasks
def _clean(text: Optional[str], fallback: str = "") -> str:
    text = (text or "").strip()
    return text if text else fallback


def add_task(title: Optional[str], priority: Optional[str] = "MEDIUM") -> Dict[str, Any]:
    title = _clean(title, "New Task")
    priority = (priority or "MEDIUM").upper()
    if priority not in ("HIGH", "MEDIUM", "LOW"):
        priority = "MEDIUM"
    with _conn() as conn:
        cur = conn.execute("INSERT INTO tasks (title, priority) VALUES (?, ?)", (title, priority))
        task_id = cur.lastrowid
    return {"id": task_id, "title": title, "priority": priority, "status": "PENDING"}


_PRIORITY_ORDER = "CASE priority WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 WHEN 'LOW' THEN 3 ELSE 2 END"


def get_tasks(include_completed: bool = False) -> List[Dict[str, Any]]:
    where = "" if include_completed else "WHERE status = 'PENDING'"
    with _conn() as conn:
        rows = conn.execute(f"SELECT * FROM tasks {where} ORDER BY {_PRIORITY_ORDER}, id DESC").fetchall()
    return [dict(r) for r in rows]


def toggle_task(task_id: int) -> Optional[Dict[str, Any]]:
    with _conn() as conn:
        row = conn.execute("SELECT status FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            return None
        if row["status"] == "PENDING":
            conn.execute("UPDATE tasks SET status='COMPLETED', completed_at=? WHERE id=?",
                         (datetime.now().isoformat(sep=" ", timespec="seconds"), task_id))
        else:
            conn.execute("UPDATE tasks SET status='PENDING', completed_at=NULL WHERE id=?", (task_id,))
        return dict(conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone())


def complete_task_by_title(query: Optional[str]) -> Optional[Dict[str, Any]]:
    """Mark the pending task that best matches `query` as completed (voice: 'I finished X')."""
    query = _clean(query).lower()
    if not query:
        return None
    pending = get_tasks()
    best, best_score = None, 0.0
    for t in pending:
        title = t["title"].lower()
        score = difflib.SequenceMatcher(None, query, title).ratio()
        if query in title or title in query:
            score = max(score, 0.9)
        if score > best_score:
            best, best_score = t, score
    if best is None or best_score < 0.5:
        return None
    return toggle_task(best["id"])


# ---------------------------------------------------------------- notes
def add_note(title: Optional[str], content: Optional[str]) -> Dict[str, Any]:
    content = _clean(content)
    title = _clean(title)
    if not content:
        content = title or "Empty note"
    if not title:
        title = (content[:28] + "...") if len(content) > 28 else content
    with _conn() as conn:
        cur = conn.execute("INSERT INTO notes (title, content) VALUES (?, ?)", (title, content))
        note_id = cur.lastrowid
    return {"id": note_id, "title": title, "content": content}


def get_notes(limit: int = 10) -> List[Dict[str, Any]]:
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM notes ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def delete_note(note_id: int) -> bool:
    with _conn() as conn:
        return conn.execute("DELETE FROM notes WHERE id = ?", (note_id,)).rowcount > 0


# ---------------------------------------------------------------- habits
def canonical_habit_name(name: Optional[str]) -> str:
    """Map what the user said ('workout', 'went for a walk') onto an existing habit name."""
    raw = _clean(name, "Habit")
    low = re.sub(r"[^a-z0-9 ]", " ", raw.lower())
    low = " ".join(low.split())
    with _conn() as conn:
        existing = [r["name"] for r in conn.execute("SELECT name FROM habits").fetchall()]
    words = set(low.split())
    for canon, aliases in HABIT_ALIASES.items():      # aliases first: 'Workout' -> 'Gym'
        if canon in existing and any(a == low or (" " not in a and a in words) or (" " in a and a in low) for a in aliases):
            return canon
    for e in existing:                               # otherwise an exact (case-insensitive) match
        if e.lower() == low:
            return e
    return raw.strip().title()[:30]


def _effective_streak(streak: int, last_logged: Optional[str], today: date) -> int:
    """A streak is only alive if it was logged today or yesterday."""
    if not last_logged:
        return 0
    try:
        last = date.fromisoformat(str(last_logged))
    except ValueError:
        return 0
    return streak if (today - last).days <= 1 else 0


def record_habit(name: Optional[str]) -> Dict[str, Any]:
    name = canonical_habit_name(name)
    today = date.today()
    with _conn() as conn:
        row = conn.execute("SELECT * FROM habits WHERE LOWER(name) = LOWER(?)", (name,)).fetchone()
        already = False
        if not row:
            conn.execute("INSERT INTO habits (name, streak_count, last_logged_date) VALUES (?, 1, ?)",
                         (name, today.isoformat()))
            streak = 1
        else:
            name = row["name"]
            last = row["last_logged_date"]
            if last == today.isoformat():
                already = True
                streak = max(row["streak_count"], 1)
            else:
                alive = last == (today - timedelta(days=1)).isoformat()
                streak = row["streak_count"] + 1 if alive else 1   # a missed day restarts the streak
                conn.execute("UPDATE habits SET streak_count=?, last_logged_date=? WHERE id=?",
                             (streak, today.isoformat(), row["id"]))
    return {"name": name, "streak_count": streak, "last_logged_date": today.isoformat(), "already_logged": already}


def get_habits() -> List[Dict[str, Any]]:
    today = date.today()
    with _conn() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM habits").fetchall()]
    for h in rows:
        h["logged_today"] = h["last_logged_date"] == today.isoformat()
        h["streak_count"] = _effective_streak(h["streak_count"], h["last_logged_date"], today)
    rows.sort(key=lambda h: h["id"])   # stable order so on-device selection does not jump
    return rows


def merge_duplicate_habits():
    """Fold habits created under an alias ('Workout', 'Reading', ...) into the canonical one."""
    with _conn() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM habits").fetchall()]
    by_name = {h["name"]: h for h in rows}
    for h in rows:
        if h["name"] in DEFAULT_HABITS:
            continue
        canon = canonical_habit_name(h["name"])
        if canon == h["name"] or canon not in by_name:
            continue
        keep = by_name[canon]
        a = (keep["last_logged_date"] or "", keep["streak_count"])
        b = (h["last_logged_date"] or "", h["streak_count"])
        best = max(a, b)    # most recent log wins; on a tie the longer streak
        with _conn() as conn:
            conn.execute("UPDATE habits SET last_logged_date=?, streak_count=? WHERE id=?",
                         (best[0] or None, best[1], keep["id"]))
            conn.execute("DELETE FROM habits WHERE id=?", (h["id"],))


init_db()
merge_duplicate_habits()
