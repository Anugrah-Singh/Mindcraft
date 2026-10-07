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
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS habit_logs (
            habit_id INTEGER NOT NULL,
            log_date DATE NOT NULL,
            UNIQUE (habit_id, log_date)
        )
        """)
        for name in DEFAULT_HABITS:
            cursor.execute("INSERT OR IGNORE INTO habits (name, streak_count, last_logged_date) VALUES (?, 0, NULL)", (name,))
        # Habits recorded before the log table existed: rebuild their history from the streak.
        for h in cursor.execute("SELECT * FROM habits WHERE streak_count > 0 AND last_logged_date IS NOT NULL").fetchall():
            if cursor.execute("SELECT 1 FROM habit_logs WHERE habit_id=?", (h["id"],)).fetchone():
                continue
            try:
                last = date.fromisoformat(h["last_logged_date"])
            except ValueError:
                continue
            for i in range(h["streak_count"]):
                cursor.execute("INSERT OR IGNORE INTO habit_logs (habit_id, log_date) VALUES (?, ?)",
                               (h["id"], (last - timedelta(days=i)).isoformat()))


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


def get_all_tasks() -> List[Dict[str, Any]]:
    """Open tasks first (by priority), then completed ones, newest completion first."""
    with _conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM tasks ORDER BY (status='COMPLETED'), {_PRIORITY_ORDER}, completed_at DESC, id DESC").fetchall()
    return [dict(r) for r in rows]


def update_task(task_id: int, title: Optional[str] = None, priority: Optional[str] = None) -> Optional[Dict[str, Any]]:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            return None
        title = _clean(title) or row["title"]
        priority = (priority or row["priority"]).upper()
        if priority not in ("HIGH", "MEDIUM", "LOW"):
            priority = row["priority"]
        conn.execute("UPDATE tasks SET title=?, priority=? WHERE id=?", (title, priority, task_id))
        return dict(conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone())


def delete_task(task_id: int) -> bool:
    with _conn() as conn:
        return conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,)).rowcount > 0


def clear_completed_tasks() -> int:
    with _conn() as conn:
        return conn.execute("DELETE FROM tasks WHERE status = 'COMPLETED'").rowcount


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


def find_task_by_title(query: Optional[str], include_completed: bool = False) -> Optional[Dict[str, Any]]:
    """Best fuzzy match for a spoken task name."""
    query = _clean(query).lower()
    if not query:
        return None
    best, best_score = None, 0.0
    for t in (get_all_tasks() if include_completed else get_tasks()):
        title = t["title"].lower()
        score = difflib.SequenceMatcher(None, query, title).ratio()
        if query in title or title in query:
            score = max(score, 0.9)
        if score > best_score:
            best, best_score = t, score
    return best if best is not None and best_score >= 0.5 else None


def complete_task_by_title(query: Optional[str]) -> Optional[Dict[str, Any]]:
    """Mark the pending task that best matches `query` as completed (voice: 'I finished X')."""
    best = find_task_by_title(query)
    return toggle_task(best["id"]) if best else None


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


def get_notes(limit: int = 500) -> List[Dict[str, Any]]:
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM notes ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def update_note(note_id: int, title: Optional[str] = None, content: Optional[str] = None) -> Optional[Dict[str, Any]]:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
        if not row:
            return None
        title = _clean(title) or row["title"]
        content = _clean(content) or row["content"]
        conn.execute("UPDATE notes SET title=?, content=? WHERE id=?", (title, content, note_id))
        return dict(conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone())


def find_note_by_title(query: Optional[str]) -> Optional[Dict[str, Any]]:
    """Best fuzzy match for a spoken note name (voice: 'play the voice note called X')."""
    query = _clean(query).lower()
    notes = get_notes(limit=200)
    if not notes:
        return None
    if not query:
        return notes[0]                       # "play my last note"
    best, best_score = None, 0.0
    for n in notes:                           # newest first, so ties go to the newest
        title = n["title"].lower()
        score = difflib.SequenceMatcher(None, query, title).ratio()
        if query in title or title in query:
            score = max(score, 0.9)
        if score > best_score:
            best, best_score = n, score
    return best if best_score >= 0.5 else None


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


def _sync_habit(conn, habit_id: int):
    """Recompute streak_count / last_logged_date from the habit's log rows."""
    dates = sorted((date.fromisoformat(r["log_date"]) for r in
                    conn.execute("SELECT log_date FROM habit_logs WHERE habit_id=?", (habit_id,)).fetchall()),
                   reverse=True)
    streak = 0
    if dates:
        streak = 1
        for prev, cur in zip(dates, dates[1:]):
            if (prev - cur).days != 1:
                break
            streak += 1
    conn.execute("UPDATE habits SET streak_count=?, last_logged_date=? WHERE id=?",
                 (streak, dates[0].isoformat() if dates else None, habit_id))


def record_habit(name: Optional[str]) -> Dict[str, Any]:
    name = canonical_habit_name(name)
    today = date.today().isoformat()
    with _conn() as conn:
        row = conn.execute("SELECT * FROM habits WHERE LOWER(name) = LOWER(?)", (name,)).fetchone()
        if not row:
            hid = conn.execute("INSERT INTO habits (name, streak_count, last_logged_date) VALUES (?, 0, NULL)", (name,)).lastrowid
        else:
            hid, name = row["id"], row["name"]
        already = conn.execute("SELECT 1 FROM habit_logs WHERE habit_id=? AND log_date=?", (hid, today)).fetchone() is not None
        if not already:
            conn.execute("INSERT INTO habit_logs (habit_id, log_date) VALUES (?, ?)", (hid, today))
            _sync_habit(conn, hid)
        streak = conn.execute("SELECT streak_count FROM habits WHERE id=?", (hid,)).fetchone()["streak_count"]
    return {"id": hid, "name": name, "streak_count": max(streak, 1), "last_logged_date": today, "already_logged": already}


def add_habit(name: Optional[str]) -> Optional[Dict[str, Any]]:
    """Create a habit without logging it. Returns None if one with that name already exists."""
    name = canonical_habit_name(name)
    with _conn() as conn:
        if conn.execute("SELECT 1 FROM habits WHERE LOWER(name) = LOWER(?)", (name,)).fetchone():
            return None
        hid = conn.execute("INSERT INTO habits (name, streak_count, last_logged_date) VALUES (?, 0, NULL)", (name,)).lastrowid
    return {"id": hid, "name": name}


def unlog_habit(name: Optional[str]) -> Optional[Dict[str, Any]]:
    """Undo today's log for a habit (tapped Log by mistake)."""
    name = canonical_habit_name(name)
    with _conn() as conn:
        row = conn.execute("SELECT * FROM habits WHERE LOWER(name) = LOWER(?)", (name,)).fetchone()
        if not row:
            return None
        conn.execute("DELETE FROM habit_logs WHERE habit_id=? AND log_date=?", (row["id"], date.today().isoformat()))
        _sync_habit(conn, row["id"])
        return {"id": row["id"], "name": row["name"]}


def rename_habit(habit_id: int, new_name: Optional[str]) -> Optional[Dict[str, Any]]:
    new_name = _clean(new_name)[:30]
    if not new_name:
        return None
    with _conn() as conn:
        if not conn.execute("SELECT 1 FROM habits WHERE id=?", (habit_id,)).fetchone():
            return None
        if conn.execute("SELECT 1 FROM habits WHERE LOWER(name)=LOWER(?) AND id<>?", (new_name, habit_id)).fetchone():
            return None
        conn.execute("UPDATE habits SET name=? WHERE id=?", (new_name, habit_id))
    return {"id": habit_id, "name": new_name}


def delete_habit(habit_id: int) -> bool:
    with _conn() as conn:
        conn.execute("DELETE FROM habit_logs WHERE habit_id=?", (habit_id,))
        return conn.execute("DELETE FROM habits WHERE id=?", (habit_id,)).rowcount > 0


def find_habit_by_name(name: Optional[str]) -> Optional[Dict[str, Any]]:
    name = _clean(name).lower()
    if not name:
        return None
    best, best_score = None, 0.0
    for h in get_habits():
        hn = h["name"].lower()
        score = difflib.SequenceMatcher(None, name, hn).ratio()
        if name in hn or hn in name:
            score = max(score, 0.9)
        if score > best_score:
            best, best_score = h, score
    return best if best is not None and best_score >= 0.5 else None


def get_habits() -> List[Dict[str, Any]]:
    today = date.today()
    since = (today - timedelta(days=13)).isoformat()
    with _conn() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM habits").fetchall()]
        logs = conn.execute("SELECT habit_id, log_date FROM habit_logs WHERE log_date >= ?", (since,)).fetchall()
    by_habit: Dict[int, List[str]] = {}
    for l in logs:
        by_habit.setdefault(l["habit_id"], []).append(l["log_date"])
    for h in rows:
        h["logged_today"] = h["last_logged_date"] == today.isoformat()
        h["streak_count"] = _effective_streak(h["streak_count"], h["last_logged_date"], today)
        h["history"] = sorted(by_habit.get(h["id"], []))
    rows.sort(key=lambda h: h["id"])   # stable order so on-device selection does not jump
    return rows


def export_all() -> Dict[str, Any]:
    with _conn() as conn:
        return {
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "tasks": [dict(r) for r in conn.execute("SELECT * FROM tasks ORDER BY id").fetchall()],
            "notes": [dict(r) for r in conn.execute("SELECT * FROM notes ORDER BY id").fetchall()],
            "habits": [dict(r) for r in conn.execute("SELECT * FROM habits ORDER BY id").fetchall()],
            "habit_logs": [dict(r) for r in conn.execute("SELECT * FROM habit_logs ORDER BY habit_id, log_date").fetchall()],
        }


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
            conn.execute("INSERT OR IGNORE INTO habit_logs (habit_id, log_date) SELECT ?, log_date FROM habit_logs WHERE habit_id=?",
                         (keep["id"], h["id"]))
            conn.execute("DELETE FROM habit_logs WHERE habit_id=?", (h["id"],))
            conn.execute("DELETE FROM habits WHERE id=?", (h["id"],))
            _sync_habit(conn, keep["id"])


init_db()
merge_duplicate_habits()
