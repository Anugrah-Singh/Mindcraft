import sqlite3
import json
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Optional, Any

DB_PATH = Path(__file__).parent / "mindcraft.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Tasks table
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
    
    # Notes table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # Habits table (e.g. gym streak)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS habits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        streak_count INTEGER DEFAULT 0,
        last_logged_date DATE
    )
    """)
    
    # Insert default habits if not present
    cursor.execute("""
    INSERT OR IGNORE INTO habits (name, streak_count, last_logged_date)
    VALUES ('Gym', 0, NULL), ('Daily Walk', 0, NULL), ('Read 20 Mins', 0, NULL)
    """)
    
    conn.commit()
    conn.close()

def add_task(title: str, priority: str = "MEDIUM") -> Dict[str, Any]:
    priority = priority.upper()
    if priority not in ("HIGH", "MEDIUM", "LOW"):
        priority = "MEDIUM"
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO tasks (title, priority) VALUES (?, ?)", (title, priority))
    task_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {"id": task_id, "title": title, "priority": priority, "status": "PENDING"}

def get_tasks(include_completed: bool = False) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if include_completed:
        cursor.execute("SELECT * FROM tasks ORDER BY CASE priority WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 WHEN 'LOW' THEN 3 END, id DESC")
    else:
        cursor.execute("SELECT * FROM tasks WHERE status = 'PENDING' ORDER BY CASE priority WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 WHEN 'LOW' THEN 3 END, id DESC")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def toggle_task(task_id: int) -> Optional[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM tasks WHERE id = ?", (task_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None
    new_status = "COMPLETED" if row["status"] == "PENDING" else "PENDING"
    completed_at = datetime.utcnow() if new_status == "COMPLETED" else None
    cursor.execute("UPDATE tasks SET status = ?, completed_at = ? WHERE id = ?", (new_status, completed_at, task_id))
    conn.commit()
    cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    updated = dict(cursor.fetchone())
    conn.close()
    return updated

def add_note(title: str, content: str) -> Dict[str, Any]:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO notes (title, content) VALUES (?, ?)", (title, content))
    note_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {"id": note_id, "title": title, "content": content}

def get_notes(limit: int = 10) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM notes ORDER BY id DESC LIMIT ?", (limit,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def record_habit(name: str) -> Dict[str, Any]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    today = date.today().isoformat()
    cursor.execute("SELECT * FROM habits WHERE LOWER(name) = LOWER(?)", (name,))
    row = cursor.fetchone()
    
    if not row:
        # Create habit and set streak to 1
        cursor.execute("INSERT INTO habits (name, streak_count, last_logged_date) VALUES (?, 1, ?)", (name, today))
        streak = 1
    else:
        last_date = row["last_logged_date"]
        streak = row["streak_count"]
        if last_date == today:
            # Already logged today
            pass
        else:
            streak += 1
            cursor.execute("UPDATE habits SET streak_count = ?, last_logged_date = ? WHERE id = ?", (streak, today, row["id"]))
            
    conn.commit()
    conn.close()
    return {"name": name, "streak_count": streak, "last_logged_date": today}

def get_habits() -> List[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM habits ORDER BY streak_count DESC, name ASC")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

init_db()
