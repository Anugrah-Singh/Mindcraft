"""Screen model for the Mindcraft device.

Every screen is a plain dict that carries structured data ("view", "items", "sel", ...) so the
OLED firmware and the dashboard's OLED mirror can draw the same layout. The legacy text fields
("title", "lines", "footer_left", "footer_right") are still included as a fallback.

Display limits (SSD1306 128x64, 5x8 font): 24 columns, 4 rows, 17-character titles.
"""
import re
import textwrap
import unicodedata

import storage

OLED_COLS = 24
OLED_TITLE_COLS = 17
OLED_ROWS = 4

_CHAR_SUBS = {
    "‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-",
    "…": "...", " ": " ", "•": "-", "►": ">",
}

KIND_TITLES = {
    "TASK": "TASK ADDED", "NOTE": "NOTE SAVED", "HABIT": "HABIT LOGGED",
    "TASK_DONE": "TASK DONE", "CONVERSATION": "ANSWER", "ERROR": "OOPS",
}

MENU_LABELS = [("Tasks", "tasks"), ("Habits", "habit"), ("Notes", "note"), ("Ask AI", "mic")]


def ascii_text(s) -> str:
    """The OLED font is ASCII only: replace/strip anything else (accents, emoji, curly quotes)."""
    s = str(s if s is not None else "")
    for k, v in _CHAR_SUBS.items():
        s = s.replace(k, v)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[\r\n\t]+", " ", s)


def clip(s, n: int) -> str:
    return ascii_text(s)[:n]


def clip_dots(s, n: int) -> str:
    """Clip to n characters and end with '..' when something was cut off."""
    s = ascii_text(s).strip()
    return s if len(s) <= n else s[: n - 2].rstrip() + ".."


def wrap_oled(text, width: int = OLED_COLS) -> list:
    return textwrap.wrap(ascii_text(text), width=width, break_long_words=True) or [""]


def window_start(index: int, total: int, rows: int = OLED_ROWS) -> int:
    """First visible row so that the selected one is always on screen."""
    if total <= rows or index < rows:
        return 0
    return min(index - rows + 1, total - rows)


def _clamp(index: int, total: int) -> int:
    return max(0, min(index, total - 1)) if total else 0


def _legacy(lines, footer_left, footer_right):
    return {"lines": lines, "footer_left": footer_left, "footer_right": footer_right}


# ------------------------------------------------------------------ views
def menu_screen(index: int) -> dict:
    tasks = storage.get_tasks()
    habits = storage.get_habits()
    notes = storage.get_notes(limit=50)
    done = sum(1 for h in habits if h["logged_today"])
    subs = [f"{len(tasks)} open", f"{done}/{len(habits)} today", f"{len(notes)} saved", "Voice"]
    items = [{"label": label, "icon": icon, "sub": sub} for (label, icon), sub in zip(MENU_LABELS, subs)]
    index = _clamp(index, len(items))
    return {
        "view": "menu", "title": "MINDCRAFT", "items": items, "sel": index,
        **_legacy([f"{'> ' if i == index else '  '}{it['label']}" for i, it in enumerate(items)],
                  "UP/DOWN", "SEL: Open"),
    }


def tasks_screen(index: int) -> dict:
    tasks = storage.get_tasks()
    total = len(tasks)
    index = _clamp(index, total)
    start = window_start(index, total)
    items = [{"text": clip(t["title"], 20), "pri": t["priority"][:1]} for t in tasks[start:start + OLED_ROWS]]
    return {
        "view": "tasks", "title": "TASKS", "items": items, "sel": index - start,
        "pos": index, "total": total, "empty": "No open tasks",
        **_legacy([("* " if i == index - start else "  ") + f"[{it['pri']}] {it['text']}"[: OLED_COLS - 2]
                   for i, it in enumerate(items)] or ["No open tasks"], "BACK", "SEL: Done"),
    }


def habits_screen(index: int) -> dict:
    habits = storage.get_habits()
    total = len(habits)
    index = _clamp(index, total)
    start = window_start(index, total)
    items = [{"name": clip(h["name"], 12), "streak": h["streak_count"], "done": bool(h["logged_today"])}
             for h in habits[start:start + OLED_ROWS]]
    return {
        "view": "habits", "title": "HABITS", "items": items, "sel": index - start,
        "pos": index, "total": total, "empty": "No habits yet",
        **_legacy([("* " if i == index - start else "  ") +
                   f"{it['name']:<12} {it['streak']:>2}d {'[x]' if it['done'] else '[ ]'}"
                   for i, it in enumerate(items)] or ["No habits yet"], "BACK", "SEL: Log"),
    }


def notes_screen(index: int) -> dict:
    notes = storage.get_notes(limit=10)
    total = len(notes)
    index = _clamp(index, total)
    start = window_start(index, total)
    items = [{"text": clip(n["title"], 20)} for n in notes[start:start + OLED_ROWS]]
    return {
        "view": "notes", "title": "NOTES", "items": items, "sel": index - start,
        "pos": index, "total": total, "empty": "No notes yet",
        **_legacy([("* " if i == index - start else "  ") + it["text"] for i, it in enumerate(items)]
                  or ["No notes yet"], "BACK", "SEL: Play"),
    }


def ai_screen(last_ai, scroll: int):
    """AI result: headline + the reply word-wrapped, scrollable with UP/DOWN. Returns (screen, scroll)."""
    if not last_ai:
        return status_screen("listening", "Listening", "Speak now", "ASK AI"), 0
    body = wrap_oled(last_ai["spoken"])
    per_page = OLED_ROWS - 1
    max_scroll = max(0, len(body) - per_page)
    scroll = max(0, min(scroll, max_scroll))
    kind = last_ai["action"]
    return {
        "view": "ai", "kind": kind, "title": KIND_TITLES.get(kind, "ANSWER"),
        "head": clip_dots(last_ai["oled"], 22), "body": body[scroll: scroll + per_page],
        "more": scroll < max_scroll, "pos": scroll, "total": len(body),
        "full_text": last_ai["spoken"],
        **_legacy(["* " + clip(last_ai["oled"], OLED_COLS - 2)] + body[scroll: scroll + per_page],
                  "BACK", "DOWN: More" if scroll < max_scroll else "SEL: Menu"),
    }, scroll


def status_screen(anim: str, head: str, sub: str = "", title: str = "") -> dict:
    """Transient states: listening / thinking / playing / preparing / error."""
    titles = {"listening": "LISTENING", "thinking": "THINKING", "playing": "PLAYING",
              "preparing": "PLAYING", "error": "OOPS", "idle": "MINDCRAFT"}
    return {
        "view": "status", "anim": anim, "title": clip(title or titles.get(anim, "MINDCRAFT"), OLED_TITLE_COLS),
        "head": clip_dots(head, 22), "sub": clip_dots(sub, 32),
        **_legacy(["* " + clip(head, OLED_COLS - 2)] + ([clip(sub, OLED_COLS)] if sub else []), "", ""),
    }


# ------------------------------------------------------------------ device payload
def _clean(value, max_len=40):
    if isinstance(value, str):
        return clip(value, max_len)
    if isinstance(value, list):
        return [_clean(v, max_len) for v in value]
    if isinstance(value, dict):
        return {k: _clean(v, max_len) for k, v in value.items()}
    return value


_OLED_KEYS = ("view", "kind", "anim", "title", "items", "sel", "pos", "total", "head", "sub", "body",
              "more", "empty", "footer_left", "footer_right", "lines")


def oled_payload(screen: dict) -> dict:
    """Lightweight, ASCII-only screen for the ESP32 (no HTML, no full text)."""
    out = {k: _clean(screen[k]) for k in _OLED_KEYS if k in screen}
    out["title"] = clip(out.get("title", "MINDCRAFT"), OLED_TITLE_COLS)
    out["lines"] = [clip(l, OLED_COLS) for l in screen.get("lines", [])][:OLED_ROWS]
    out["footer_left"] = clip(screen.get("footer_left", ""), 14)
    out["footer_right"] = clip(screen.get("footer_right", ""), 14)
    return out
