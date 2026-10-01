import os
import io
import json
import asyncio
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Request
from fastapi.responses import HTMLResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pathlib import Path
from dotenv import load_dotenv

import storage
import gemini_service
import tts_service

load_dotenv()

app = FastAPI(title="Mindcraft Companion Hub")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

WEB_DIR = Path(__file__).parent / "web"
LAST_AUDIO_PATH = Path(__file__).parent / "last_response.mp3"
LAST_WAV_PATH = Path(__file__).parent / "last_response.wav"

def convert_mp3_to_wav(mp3_path: Path, wav_path: Path):
    try:
        import miniaudio, time
        decoded = miniaudio.decode_file(str(mp3_path), sample_rate=44100, nchannels=2, output_format=miniaudio.SampleFormat.SIGNED16)
        written = False
        for attempt in range(5):
            try:
                miniaudio.wav_write_file(str(wav_path), decoded)
                written = True
                break
            except Exception:
                time.sleep(0.08)
        if written:
            print(f"[Audio] Prepared 44.1kHz stereo WAV ({len(decoded.samples)} samples) for Stone 190.")
        else:
            print("[WAV Convert Error] Could not write WAV after retries")
    except Exception as e:
        print(f"[WAV Convert Error] {e}")

# State Machine for ESP32 and UI
# Views: "MENU", "TASKS", "HABITS", "NOTES", "AI_RESULT"
current_view = "MENU"
menu_index = 0
note_index = 0
menu_items = ["Tasks App", "Habit Streaks", "Voice Notes", "AI Assistant"]

# Connection Managers
class ConnectionManager:
    def __init__(self):
        self.browser_sockets: List[WebSocket] = []
        self.esp32_sockets: List[WebSocket] = []

    async def connect_browser(self, websocket: WebSocket):
        await websocket.accept()
        self.browser_sockets.append(websocket)

    def disconnect_browser(self, websocket: WebSocket):
        if websocket in self.browser_sockets:
            self.browser_sockets.remove(websocket)

    async def connect_esp32(self, websocket: WebSocket):
        await websocket.accept()
        self.esp32_sockets.append(websocket)
        print("[ESP32] Device connected!")

    def disconnect_esp32(self, websocket: WebSocket):
        if websocket in self.esp32_sockets:
            self.esp32_sockets.remove(websocket)
            print("[ESP32] Device disconnected.")

    async def broadcast_screen(self, screen_data: dict):
        browser_payload = json.dumps({"type": "screen_update", "screen": screen_data})
        # Send full payload with HTML to web browsers
        for ws in self.browser_sockets:
            try:
                await ws.send_text(browser_payload)
            except Exception:
                pass

        # Send lightweight payload without HTML to ESP32 to conserve RAM
        esp32_data = {
            "title": screen_data.get("title", "MINDCRAFT"),
            "lines": screen_data.get("lines", []),
            "footer_left": screen_data.get("footer_left", ""),
            "footer_right": screen_data.get("footer_right", "")
        }
        esp32_payload = json.dumps({"type": "screen_update", "screen": esp32_data})
        for ws in self.esp32_sockets:
            try:
                await ws.send_text(esp32_payload)
            except Exception:
                pass

    async def broadcast_refresh(self):
        payload = json.dumps({"type": "data_refresh"})
        for ws in self.browser_sockets:
            try:
                await ws.send_text(payload)
            except Exception:
                pass

    async def notify_play_audio(self):
        payload = json.dumps({"type": "play_audio", "url": "/api/audio/last.wav"})
        print(f"[Audio Notify] Sending play_audio to {len(self.esp32_sockets)} ESP32 client(s)...")
        for ws in self.esp32_sockets:
            try:
                await ws.send_text(payload)
            except Exception as e:
                print(f"[Audio Notify Error] {e}")

manager = ConnectionManager()

def render_screen_state() -> dict:
    global current_view, menu_index, note_index
    if current_view == "MENU":
        items_html = ""
        for i, item in enumerate(menu_items):
            if i == menu_index:
                items_html += f'<div class="text-emerald-300 font-bold">► {item}</div>'
            else:
                items_html += f'<div class="text-slate-400 pl-4">{item}</div>'
        return {
            "title": "MINDCRAFT MENU",
            "html": items_html,
            "lines": [f"{'> ' if i == menu_index else '  '}{item}" for i, item in enumerate(menu_items)],
            "footer_left": "DOWN: Next",
            "footer_right": "SEL: Open"
        }
    elif current_view == "TASKS":
        tasks = storage.get_tasks()[:4]
        if not tasks:
            return {
                "title": "TASKS",
                "html": '<div class="text-slate-500 py-2">No pending tasks</div>',
                "lines": ["No pending tasks"],
                "footer_left": "BACK: Menu",
                "footer_right": "PTT: Add"
            }
        lines = []
        html = ""
        for t in tasks:
            p_tag = f"[{t['priority'][:1]}]"
            line = f"{p_tag} {t['title'][:16]}"
            lines.append(line)
            html += f'<div class="text-cyan-300 text-xs truncate">{line}</div>'
        return {
            "title": f"TASKS ({len(tasks)})",
            "html": html,
            "lines": lines,
            "footer_left": "BACK: Menu",
            "footer_right": "DOWN: Scroll"
        }
    elif current_view == "HABITS":
        habits = storage.get_habits()[:3]
        lines = []
        html = ""
        for h in habits:
            line = f"{h['name']}: {h['streak_count']}d streak"
            lines.append(line)
            html += f'<div class="text-amber-400 text-xs">🔥 {line}</div>'
        return {
            "title": "HABIT STREAKS",
            "html": html,
            "lines": lines,
            "footer_left": "BACK: Menu",
            "footer_right": "PTT: Log"
        }
    elif current_view == "NOTES":
        notes = storage.get_notes(limit=10)
        if not notes:
            return {
                "title": "VOICE NOTES",
                "html": '<div class="text-slate-500 py-2">No notes yet</div>',
                "lines": ["No notes captured"],
                "footer_left": "BACK: Menu",
                "footer_right": "PTT: Record"
            }
        if note_index >= len(notes):
            note_index = 0
        lines = []
        html = ""
        start = max(0, min(note_index, len(notes) - 3))
        slice_notes = notes[start:start+3]
        for idx, n in enumerate(slice_notes):
            actual_idx = start + idx
            is_sel = (actual_idx == note_index)
            prefix = "* " if is_sel else "  "
            lines.append(f"{prefix}{n['title'][:18]}")
            if is_sel:
                html += f'<div class="text-emerald-300 font-bold">► {n["title"]}</div>'
            else:
                html += f'<div class="text-slate-400 pl-4 text-xs truncate">{n["title"]}</div>'
        return {
            "title": f"NOTES ({note_index+1}/{len(notes)})",
            "html": html,
            "lines": lines,
            "footer_left": "BACK: Menu",
            "footer_right": "SEL: Play"
        }
    return {
        "title": "MINDCRAFT",
        "html": "<div>Ready</div>",
        "lines": ["Ready"],
        "footer_left": "",
        "footer_right": ""
    }

async def handle_button_press(button: str):
    global current_view, menu_index, note_index
    button = button.upper()
    
    if button == "BACK":
        current_view = "MENU"
    elif button == "UP":
        if current_view == "MENU":
            menu_index = (menu_index - 1) % len(menu_items)
        elif current_view == "NOTES":
            notes = storage.get_notes(limit=10)
            if notes:
                note_index = (note_index - 1) % len(notes)
    elif button == "DOWN":
        if current_view == "MENU":
            menu_index = (menu_index + 1) % len(menu_items)
        elif current_view == "NOTES":
            notes = storage.get_notes(limit=10)
            if notes:
                note_index = (note_index + 1) % len(notes)
    elif button == "SELECT":
        if current_view == "MENU":
            selected = menu_items[menu_index]
            if selected == "Tasks App":
                current_view = "TASKS"
            elif selected == "Habit Streaks":
                current_view = "HABITS"
            elif selected == "Voice Notes":
                current_view = "NOTES"
            elif selected == "AI Assistant":
                current_view = "AI_RESULT"
        elif current_view == "NOTES":
            notes = storage.get_notes(limit=10)
            if notes and note_index < len(notes):
                await play_note_audio(notes[note_index]["id"])
                return
        elif current_view == "TASKS":
            tasks = storage.get_tasks()
            if tasks:
                storage.toggle_task(tasks[0]["id"])
                await manager.broadcast_refresh()

    await manager.broadcast_screen(render_screen_state())

# API Routes
@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = WEB_DIR / "index.html"
    return HTMLResponse(content=index_file.read_text(encoding="utf-8"))

@app.get("/api/tasks")
async def get_tasks():
    return storage.get_tasks()

@app.post("/api/tasks/{task_id}/toggle")
async def toggle_task(task_id: int):
    result = storage.toggle_task(task_id)
    await manager.broadcast_refresh()
    await manager.broadcast_screen(render_screen_state())
    return result

@app.get("/api/habits")
async def get_habits():
    return storage.get_habits()

@app.get("/api/notes")
async def get_notes():
    return storage.get_notes()

async def play_note_audio(note_id: int):
    notes = storage.get_notes(limit=50)
    target = next((n for n in notes if n["id"] == note_id), None)
    if not target:
        return False
    text_to_speak = f"Voice note: {target['title']}. {target['content']}"
    try:
        audio_bytes = await tts_service.text_to_speech_mp3(text_to_speak)
        with open(LAST_AUDIO_PATH, "wb") as f:
            f.write(audio_bytes)
        convert_mp3_to_wav(LAST_AUDIO_PATH, LAST_WAV_PATH)
        await manager.notify_play_audio()
        screen_data = {
            "title": "PLAYING NOTE",
            "html": f'<div class="text-cyan-300 font-bold">{target["title"]}</div><div class="text-slate-400 text-xs mt-1">Streaming to boAt Stone 190...</div>',
            "lines": ["PLAYING NOTE", f"* {target['title'][:18]}", "boAt Stone 190"],
            "footer_left": "BACK: Notes",
            "footer_right": ""
        }
        await manager.broadcast_screen(screen_data)
        return True
    except Exception as e:
        print(f"[Play Note Error] {e}")
        return False

@app.post("/api/notes/{note_id}/play")
async def api_play_note(note_id: int):
    notes = storage.get_notes(limit=50)
    target = next((n for n in notes if n["id"] == note_id), None)
    success = await play_note_audio(note_id)
    if not success:
        return Response(status_code=404)
    return {
        "status": "playing",
        "audio_url": "/api/audio/last.mp3",
        "wav_url": "/api/audio/last.wav",
        "title": target["title"] if target else ""
    }

@app.get("/api/screen")
async def get_screen():
    return render_screen_state()

@app.post("/api/ai/listening")
async def ai_listening():
    screen_data = {
        "title": "AI ASSISTANT",
        "html": '<div class="text-rose-400 font-bold flex items-center gap-2"><span class="w-2.5 h-2.5 rounded-full bg-rose-500 animate-ping"></span> Listening...</div><div class="text-slate-400 text-xs mt-1">Speak into controller mic</div>',
        "lines": ["AI ASSISTANT", "* LISTENING...", "Speak now..."],
        "footer_left": "Cancel",
        "footer_right": "Done"
    }
    await manager.broadcast_screen(screen_data)
    return {"status": "listening"}

@app.post("/api/ai/cancel")
async def ai_cancel():
    await manager.broadcast_screen(render_screen_state())
    return {"status": "cancelled"}

class PromptRequest(BaseModel):
    prompt: str

@app.post("/api/process_prompt")
async def process_prompt(req: PromptRequest):
    await manager.broadcast_screen({
        "title": "AI ASSISTANT",
        "html": '<div class="text-cyan-300 font-bold flex items-center gap-2"><i class="fa-solid fa-brain animate-bounce"></i> Thinking...</div><div class="text-slate-400 text-xs mt-1">Processing request...</div>',
        "lines": ["AI ASSISTANT", "* Thinking...", req.prompt[:22]],
        "footer_left": "",
        "footer_right": ""
    })
    result = gemini_service.process_text_prompt(req.prompt)
    await handle_ai_action(result)
    result["audio_url"] = "/api/audio/last.mp3"
    result["wav_url"] = "/api/audio/last.wav"
    return result

@app.post("/api/process_audio")
async def process_audio(request: Request):
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type:
        form = await request.form()
        file = form.get("file")
        if file and hasattr(file, "read"):
            audio_bytes = await file.read()
            raw_mime = getattr(file, "content_type", "audio/webm") or "audio/webm"
        else:
            return {"error": "No file uploaded"}
    else:
        # Raw bytes from ESP32 HTTPClient
        audio_bytes = await request.body()
        raw_mime = content_type or "audio/wav"

    # Clean mime type (e.g. 'audio/webm;codecs=opus' -> 'audio/webm')
    mime = raw_mime.split(";")[0].strip() if raw_mime else "audio/webm"
    print(f"[Audio In] Received {len(audio_bytes)} bytes ({mime}). Processing with Gemini...")

    await manager.broadcast_screen({
        "title": "AI ASSISTANT",
        "html": '<div class="text-cyan-300 font-bold flex items-center gap-2"><i class="fa-solid fa-brain animate-bounce"></i> Thinking...</div><div class="text-slate-400 text-xs mt-1">Analyzing voice audio...</div>',
        "lines": ["AI ASSISTANT", "* Thinking...", "Analyzing voice..."],
        "footer_left": "",
        "footer_right": ""
    })

    result = gemini_service.process_audio(audio_bytes, mime_type=mime)
    await handle_ai_action(result)
    result["audio_url"] = "/api/audio/last.mp3"
    result["wav_url"] = "/api/audio/last.wav"
    return result

async def handle_ai_action(result: dict):
    action = result.get("action", "CONVERSATION")
    spoken = result.get("spoken_response", "")
    oled_text = result.get("oled_text", "Processed")
    
    if action == "TASK":
        title = result.get("title", "New Task")
        priority = result.get("priority", "MEDIUM")
        storage.add_task(title, priority)
    elif action == "NOTE":
        title = result.get("title", "Voice Note")
        content = result.get("content", "")
        storage.add_note(title, content)
    elif action == "HABIT":
        habit_name = result.get("habit_name", "Habit")
        storage.record_habit(habit_name)
    
    # Generate TTS audio for playback on Bluetooth speaker
    if spoken:
        try:
            audio_bytes = await tts_service.text_to_speech_mp3(spoken)
            with open(LAST_AUDIO_PATH, "wb") as f:
                f.write(audio_bytes)
            convert_mp3_to_wav(LAST_AUDIO_PATH, LAST_WAV_PATH)
            await manager.notify_play_audio()
        except Exception as e:
            print(f"[TTS Error] {e}")

    # Display result screen formatted cleanly for OLED and web mirror
    sub_line1 = spoken[:24] if spoken else ""
    sub_line2 = spoken[24:48] if len(spoken) > 24 else ""
    screen_data = {
        "title": f"AI: {action}",
        "html": f'<div class="text-cyan-300 font-bold">{oled_text}</div><div class="text-slate-400 text-xs mt-1">{spoken}</div>',
        "lines": [f"* {oled_text[:20]}", sub_line1, sub_line2],
        "footer_left": "BACK: Return",
        "footer_right": "AI Done"
    }
    await manager.broadcast_screen(screen_data)
    await manager.broadcast_refresh()

@app.get("/api/audio/last.mp3")
async def get_last_audio():
    if LAST_AUDIO_PATH.exists():
        return FileResponse(LAST_AUDIO_PATH, media_type="audio/mpeg")
    return Response(status_code=404)

@app.get("/api/audio/last.wav")
async def get_last_wav():
    if LAST_WAV_PATH.exists():
        try:
            data = LAST_WAV_PATH.read_bytes()
            return Response(content=data, media_type="audio/wav", headers={
                "Content-Length": str(len(data)),
                "Accept-Ranges": "bytes"
            })
        except Exception as e:
            print(f"[WAV Serve Error] {e}")
    return Response(status_code=404)

# WebSockets
@app.websocket("/ws/controller")
async def controller_ws(websocket: WebSocket):
    await manager.connect_browser(websocket)
    # Send initial screen
    await websocket.send_text(json.dumps({"type": "screen_update", "screen": render_screen_state()}))
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "button":
                await handle_button_press(msg.get("button", ""))
            elif msg.get("type") == "trigger_esp32_record":
                payload = json.dumps({"type": "record_trigger"})
                for ws in manager.esp32_sockets:
                    try:
                        await ws.send_text(payload)
                    except Exception:
                        pass
    except WebSocketDisconnect:
        manager.disconnect_browser(websocket)

@app.websocket("/ws/esp32")
async def esp32_ws(websocket: WebSocket):
    await manager.connect_esp32(websocket)
    # Send initial screen state
    await websocket.send_text(json.dumps({"type": "screen_update", "screen": render_screen_state()}))
    try:
        while True:
            data = await websocket.receive_text()
            # ESP32 can send button events or status
            try:
                msg = json.loads(data)
                if msg.get("type") == "button":
                    await handle_button_press(msg.get("button", ""))
            except Exception:
                pass
    except WebSocketDisconnect:
        manager.disconnect_esp32(websocket)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
