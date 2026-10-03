import os
import io
import re
import json
import asyncio
import textwrap
import unicodedata
import html as html_lib
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
import screens

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

def save_mp3_safely(audio_bytes: bytes):
    import time
    tmp_path = LAST_AUDIO_PATH.with_suffix(".tmp.mp3")
    tmp_path.write_bytes(audio_bytes)
    for _ in range(8):
        try:
            os.replace(tmp_path, LAST_AUDIO_PATH)
            return True
        except Exception:
            time.sleep(0.05)
    try:
        LAST_AUDIO_PATH.write_bytes(audio_bytes)
        tmp_path.unlink(missing_ok=True)
        return True
    except Exception as e:
        print(f"[MP3 Write Warning] {e}")
        return False

def convert_mp3_to_wav(mp3_path: Path, wav_path: Path):
    try:
        import miniaudio, time, array
        decoded = miniaudio.decode_file(str(mp3_path), sample_rate=22050, nchannels=1, output_format=miniaudio.SampleFormat.SIGNED16)
        
        # Boost volume by 3.5x so boAt Stone 190 plays with maximum loudness and clarity
        boost = 1.0
        amplified = [max(-32767, min(32767, int(s * boost))) for s in decoded.samples]
        boosted_samples = array.array('h', amplified)
        
        tmp_wav = wav_path.with_suffix(".tmp.wav")
        # Write to tmp file first
        boosted_sound = miniaudio.DecodedSoundFile(
            str(tmp_wav),
            1,
            22050,
            miniaudio.SampleFormat.SIGNED16,
            boosted_samples
        )
        miniaudio.wav_write_file(str(tmp_wav), boosted_sound)
        written = False
        for attempt in range(8):
            try:
                if tmp_wav.exists():
                    os.replace(tmp_wav, wav_path)
                written = True
                break
            except Exception:
                time.sleep(0.08)
        if not written and tmp_wav.exists():
            try:
                wav_path.write_bytes(tmp_wav.read_bytes())
                tmp_wav.unlink(missing_ok=True)
                written = True
            except Exception:
                pass
        if written:
            print(f"[Audio] Prepared boosted 44.1kHz stereo WAV ({len(boosted_samples)} samples) for Stone 190.")
        else:
            print("[WAV Convert Warning] Could not replace WAV immediately; will retry on next request.")
    except Exception as e:
        print(f"[WAV Convert Error] {e}")

# State machine shared by the device (OLED) and the dashboard
# Views: "MENU", "TASKS", "HABITS", "NOTES", "AI_RESULT"
current_view = "MENU"
menu_index = 0
task_index = 0
habit_index = 0
note_index = 0
ai_scroll = 0
last_ai = None          # {'action','spoken','oled'} of the latest AI reply
device_info = {"bt": False, "link": False}   # reported by the USB bridge
last_frame = None       # latest raw OLED frame (hex) from the device, for the dashboard mirror
screen_token = 0        # bumps on every screen change so delayed returns never fire on a newer screen

MENU_VIEWS = ["TASKS", "HABITS", "NOTES", "AI_RESULT"]


class ConnectionManager:
    def __init__(self):
        self.browser_sockets: List[WebSocket] = []
        self.esp32_sockets: List[WebSocket] = []

    async def connect_browser(self, websocket: WebSocket):
        await websocket.accept()
        self.browser_sockets = [s for s in self.browser_sockets if s.client_state.name == "CONNECTED"]
        if websocket not in self.browser_sockets:
            self.browser_sockets.append(websocket)
        print(f"[Browser] Client connected! (Active clients: {len(self.browser_sockets)})")
        await self.set_mirror()

    def disconnect_browser(self, websocket: WebSocket):
        if websocket in self.browser_sockets:
            self.browser_sockets.remove(websocket)
            print(f"[Browser] Client disconnected. (Remaining: {len(self.browser_sockets)})")

    async def connect_esp32(self, websocket: WebSocket):
        subprotocol = websocket.headers.get("sec-websocket-protocol")
        selected_sub = subprotocol.split(",")[0].strip() if subprotocol else None
        await websocket.accept(subprotocol=selected_sub)
        self.esp32_sockets = [s for s in self.esp32_sockets if s.client_state.name == "CONNECTED"]
        if websocket not in self.esp32_sockets:
            self.esp32_sockets.append(websocket)
        print(f"[ESP32] Device connected! Subprotocol: {selected_sub} (Active clients: {len(self.esp32_sockets)})")

    def disconnect_esp32(self, websocket: WebSocket):
        if websocket in self.esp32_sockets:
            self.esp32_sockets.remove(websocket)
            print(f"[ESP32] Device disconnected. (Remaining: {len(self.esp32_sockets)})")

    async def _send(self, sockets: list, payload: str, drop):
        dead = []
        for ws in list(sockets):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            drop(ws)

    async def set_mirror(self):
        """The device streams its OLED frames only while a dashboard is open."""
        await self.to_device({"type": "mirror", "on": bool(self.browser_sockets)})

    async def to_browsers(self, message: dict):
        await self._send(self.browser_sockets, json.dumps(message), self.disconnect_browser)

    async def to_device(self, message: dict):
        await self._send(self.esp32_sockets, json.dumps(message), self.disconnect_esp32)

    async def broadcast_screen(self, screen_data: dict):
        await self.to_browsers({"type": "screen_update", "screen": screen_data})
        # The ESP32 gets a lightweight ASCII-only version to conserve RAM
        await self.to_device({"type": "screen_update", "screen": screens.oled_payload(screen_data)})

    async def broadcast_refresh(self):
        await self.to_browsers({"type": "data_refresh"})

    async def broadcast_ai_result(self, result: dict):
        await self.to_browsers({"type": "ai_result", "result": result})

    async def broadcast_device_info(self):
        info = dict(device_info, link=bool(self.esp32_sockets))
        await self.to_browsers({"type": "device_info", "info": info})

    async def notify_play_audio(self):
        print(f"[Audio Notify] Sending play_audio to {len(self.esp32_sockets)} ESP32 client(s)...")
        await self.to_device({"type": "play_audio", "url": "/api/audio/last.wav"})

    async def trigger_recording(self):
        print(f"[Record Trigger] Forwarding record_trigger to {len(self.esp32_sockets)} ESP32 client(s)...")
        if not self.esp32_sockets:
            print("[Record Trigger] Warning: No ESP32 device connected to record audio.")
            await self.broadcast_ai_result({
                "action": "ERROR",
                "spoken_response": "The device is not connected. Start the USB bridge and plug in the ESP32.",
                "oled_text": "Device Offline"
            })
            return
        await self.to_device({"type": "record_trigger"})


manager = ConnectionManager()

# Backwards-compatible names used by tests and older code
ascii_text = screens.ascii_text
OLED_COLS = screens.OLED_COLS
oled_payload = screens.oled_payload


def render_screen_state() -> dict:
    global ai_scroll
    if current_view == "TASKS":
        return screens.tasks_screen(task_index)
    if current_view == "HABITS":
        return screens.habits_screen(habit_index)
    if current_view == "NOTES":
        return screens.notes_screen(note_index)
    if current_view == "AI_RESULT":
        screen, ai_scroll = screens.ai_screen(last_ai, ai_scroll)
        return screen
    return screens.menu_screen(menu_index)


async def show_screen(screen: dict, back_to_menu_after: Optional[float] = None):
    """Broadcast a screen; optionally return to the menu later if nothing else happened."""
    global screen_token
    screen_token += 1
    token = screen_token
    await manager.broadcast_screen(screen)
    if back_to_menu_after:
        async def _return():
            global current_view
            await asyncio.sleep(back_to_menu_after)
            if token == screen_token:
                current_view = "MENU"
                await manager.broadcast_screen(render_screen_state())
        asyncio.create_task(_return())


async def handle_button_press(button: str):
    global current_view, menu_index, note_index, task_index, habit_index, ai_scroll, last_ai
    button = button.upper()

    if button in ["BACK", "SELECT"] and current_view == "AI_RESULT":
        current_view = "MENU"
        await show_screen(render_screen_state())
        return

    step = {"UP": -1, "DOWN": 1}.get(button)
    if button == "BACK":
        current_view = "MENU"
    elif step is not None:
        if current_view == "MENU":
            menu_index = (menu_index + step) % len(MENU_VIEWS)
        elif current_view == "TASKS":
            n = len(storage.get_tasks())
            if n:
                task_index = (task_index + step) % n
        elif current_view == "HABITS":
            n = len(storage.get_habits())
            if n:
                habit_index = (habit_index + step) % n
        elif current_view == "NOTES":
            n = len(storage.get_notes(limit=10))
            if n:
                note_index = (note_index + step) % n
        elif current_view == "AI_RESULT":
            ai_scroll = max(0, ai_scroll + step)
    elif button == "SELECT":
        if current_view == "MENU":
            target = MENU_VIEWS[menu_index]
            if target == "AI_RESULT":
                current_view = "AI_RESULT"
                last_ai = None
                ai_scroll = 0
                await show_screen(screens.status_screen("listening", "Listening", "Speak now", "ASK AI"))
                await manager.trigger_recording()
                return
            current_view = target
        elif current_view == "NOTES":
            notes = storage.get_notes(limit=10)
            if notes and note_index < len(notes):
                await show_screen(screens.status_screen("preparing", notes[note_index]["title"], "Preparing audio", "PLAYING"))
                await play_note_audio(notes[note_index]["id"])
                return
        elif current_view == "TASKS":
            tasks = storage.get_tasks()
            if tasks and task_index < len(tasks):
                storage.toggle_task(tasks[task_index]["id"])
                await manager.broadcast_refresh()
        elif current_view == "HABITS":
            habits = storage.get_habits()
            if habits and habit_index < len(habits):
                storage.record_habit(habits[habit_index]["name"])
                await manager.broadcast_refresh()

    await show_screen(render_screen_state())


# ----------------------------------------------------------------- API routes
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
    await show_screen(render_screen_state())
    return result

@app.get("/api/habits")
async def get_habits():
    return storage.get_habits()

class HabitLog(BaseModel):
    name: str

@app.post("/api/habits/log")
async def log_habit(req: HabitLog):
    result = storage.record_habit(req.name)
    await manager.broadcast_refresh()
    await show_screen(render_screen_state())
    return result

@app.get("/api/notes")
async def get_notes():
    return storage.get_notes()

@app.delete("/api/notes/{note_id}")
async def delete_note(note_id: int):
    if not storage.delete_note(note_id):
        return Response(status_code=404)
    await manager.broadcast_refresh()
    await show_screen(render_screen_state())
    return {"status": "deleted"}

@app.get("/api/last_ai")
async def get_last_ai():
    return last_ai

@app.get("/api/device")
async def get_device():
    return dict(device_info, link=bool(manager.esp32_sockets))

async def play_note_audio(note_id: int):
    notes = storage.get_notes(limit=50)
    target = next((n for n in notes if n["id"] == note_id), None)
    if not target:
        return False
    text_to_speak = f"Voice note: {target['title']}. {target['content']}"
    try:
        audio_bytes = await tts_service.text_to_speech_mp3(text_to_speak)
        await asyncio.to_thread(save_mp3_safely, audio_bytes)
        await asyncio.to_thread(convert_mp3_to_wav, LAST_AUDIO_PATH, LAST_WAV_PATH)
        await manager.notify_play_audio()
        await show_screen(screens.status_screen("playing", target["title"], "on Stone 190", "PLAYING"))
        return True
    except Exception as e:
        print(f"[Play Note Error] {e}")
        return False

@app.post("/api/notes/{note_id}/play")
async def api_play_note(note_id: int):
    notes = storage.get_notes(limit=50)
    target = next((n for n in notes if n["id"] == note_id), None)
    if target:
        await show_screen(screens.status_screen("preparing", target["title"], "Preparing audio", "PLAYING"))
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
    await show_screen(screens.status_screen("listening", "Listening", "Speak now", "ASK AI"))
    return {"status": "listening"}

@app.post("/api/ai/cancel")
async def ai_cancel():
    global current_view
    current_view = "MENU"
    await show_screen(render_screen_state())
    return {"status": "cancelled"}

class PromptRequest(BaseModel):
    prompt: str

@app.post("/api/process_prompt")
async def process_prompt(req: PromptRequest):
    await show_screen(screens.status_screen("thinking", "Thinking", req.prompt, "THINKING"))
    try:
        result = await asyncio.to_thread(gemini_service.process_text_prompt, req.prompt)
    except Exception as err:
        print(f"[Prompt AI Error] {err}")
        result = {
            "action": "CONVERSATION",
            "spoken_response": "Sorry, I could not process your prompt. Please try again.",
            "oled_text": "AI Error"
        }
    await handle_ai_action(result)
    result["audio_url"] = "/api/audio/last.mp3"
    result["wav_url"] = "/api/audio/last.wav"
    return result

async def _show_error(head: str, sub: str, spoken: str, oled: str):
    global current_view
    current_view = "MENU"
    await show_screen(screens.status_screen("error", head, sub), back_to_menu_after=6)
    await manager.broadcast_ai_result({"action": "ERROR", "spoken_response": spoken, "oled_text": oled})

@app.post("/api/process_audio")
async def process_audio(request: Request):
    content_type = request.headers.get("content-type", "")
    try:
        if "multipart/form-data" in content_type:
            form = await request.form()
            file = form.get("file")
            if file and hasattr(file, "read"):
                audio_bytes = await file.read()
                raw_mime = getattr(file, "content_type", "audio/webm") or "audio/webm"
            else:
                return {"error": "No file uploaded"}
        else:
            # Raw bytes from the USB bridge
            audio_bytes = await request.body()
            raw_mime = content_type or "audio/wav"
    except Exception as e:
        print(f"[Audio In] Upload stream ended prematurely: {e}")
        await _show_error("Upload interrupted", "Try again", "Audio upload was interrupted. Please try again.", "Upload Error")
        return {"status": "aborted", "error": str(e)}

    # Clean mime type (e.g. 'audio/webm;codecs=opus' -> 'audio/webm')
    mime = raw_mime.split(";")[0].strip() if raw_mime else "audio/wav"

    if len(audio_bytes) < 1000:
        print(f"[Audio In] Warning: Received only {len(audio_bytes)} bytes. Aborting AI job.")
        await _show_error("No speech heard", "Press Ask AI again",
                          "I didn't hear anything. Press the mic and speak after the beep.", "No Speech")
        return {"status": "aborted", "error": "Audio data too short"}

    saved_file = Path(__file__).parent / "recorded_controller_audio.wav"
    try:
        with open(saved_file, "wb") as f:
            f.write(audio_bytes)
        print(f"[Audio In] Stored controller audio on laptop: {saved_file} ({len(audio_bytes)} bytes)")
    except Exception as e:
        print(f"[Audio In] Error saving audio file: {e}")

    print(f"[Audio In] Received {len(audio_bytes)} bytes ({mime}). Processing with Gemini...")
    await show_screen(screens.status_screen("thinking", "Thinking", "Reading your voice", "THINKING"))

    async def async_ai_job(data: bytes, m: str):
        try:
            result = await asyncio.to_thread(gemini_service.process_audio, data, mime_type=m)
            await handle_ai_action(result)
        except Exception as err:
            print(f"[AI Processing Error] {err}")
            err_result = {
                "action": "ERROR",
                "spoken_response": "Sorry, I had trouble processing that. Please try speaking again.",
                "oled_text": "AI Error"
            }
            try:
                await handle_ai_action(err_result)
            except Exception as e:
                print(f"[AI Fallback Broadcast Error] {e}")
                await manager.broadcast_ai_result(err_result)

    # Return to the bridge right away; the result arrives over the websocket
    asyncio.create_task(async_ai_job(audio_bytes, mime))

    return {
        "status": "processing",
        "audio_url": "/api/audio/last.mp3",
        "wav_url": "/api/audio/last.wav"
    }

async def handle_ai_action(result: dict):
    global last_ai, current_view, ai_scroll
    action = str(result.get("action") or "CONVERSATION").upper()
    spoken = str(result.get("spoken_response") or "")
    oled_text = str(result.get("oled_text") or "Processed")

    # Apply the action and make the spoken reply reflect what really happened.
    try:
        if action == "TASK":
            task = storage.add_task(result.get("title"), result.get("priority"))
            oled_text = task["title"]
            if not spoken:
                spoken = f"Added {task['priority'].lower()} priority task: {task['title']}."
        elif action == "NOTE":
            note = storage.add_note(result.get("title"), result.get("content"))
            oled_text = note["title"]
            if not spoken:
                spoken = f"Note saved: {note['title']}."
        elif action == "HABIT":
            habit = storage.record_habit(result.get("habit_name"))
            days = habit["streak_count"]
            if habit["already_logged"]:
                spoken = f"You already logged {habit['name']} today. Your streak is {days} days."
                oled_text = f"{habit['name']} - {days}d"
            else:
                spoken = (f"{habit['name']} logged. That is a {days} day streak!" if days > 1
                          else f"{habit['name']} logged. Day one of your streak!")
                oled_text = f"{habit['name']} - {days}d"
        elif action == "TASK_DONE":
            done = storage.complete_task_by_title(result.get("title"))
            if done:
                spoken = f"Marked done: {done['title']}."
                oled_text = done["title"]
            else:
                spoken = "I could not find a matching pending task."
                oled_text = "Task Not Found"
    except Exception as storage_err:
        print(f"[Storage Error in handle_ai_action] {storage_err}")
        spoken = "Sorry, I heard you but could not save that. Please try again."
        oled_text = "Save Failed"
        action = "ERROR"

    # 1. Update the OLED and the dashboard immediately
    last_ai = {"action": action, "spoken": spoken, "oled": oled_text}
    ai_scroll = 0
    current_view = "AI_RESULT"
    try:
        await show_screen(render_screen_state())
        await manager.broadcast_refresh()
    except Exception as be:
        print(f"[Broadcast Screen Error] {be}")
    finally:
        # Always tell the dashboard, so it never stays stuck on "thinking"
        try:
            result.update(action=action, spoken_response=spoken, oled_text=oled_text)
            await manager.broadcast_ai_result(result)
        except Exception as br_err:
            print(f"[Broadcast AI Result Error] {br_err}")

    # 2. Synthesize speech and tell the device to play it on the Bluetooth speaker
    if spoken:
        try:
            audio_bytes = await tts_service.text_to_speech_mp3(spoken)
            await asyncio.to_thread(save_mp3_safely, audio_bytes)
            await asyncio.to_thread(convert_mp3_to_wav, LAST_AUDIO_PATH, LAST_WAV_PATH)
            await asyncio.sleep(0.25)
            await manager.notify_play_audio()
        except Exception as e:
            print(f"[TTS Error] {e}")

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

# ----------------------------------------------------------------- WebSockets
@app.websocket("/ws/controller")
async def controller_ws(websocket: WebSocket):
    await manager.connect_browser(websocket)
    try:
        await websocket.send_text(json.dumps({"type": "screen_update", "screen": render_screen_state()}))
        await websocket.send_text(json.dumps({"type": "device_info", "info": dict(device_info, link=bool(manager.esp32_sockets))}))
        if last_frame:
            await websocket.send_text(json.dumps({"type": "device_frame", "hex": last_frame}))
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
            except Exception:
                continue
            if msg.get("type") == "button":
                await handle_button_press(msg.get("button", ""))
            elif msg.get("type") == "trigger_esp32_record":
                await manager.trigger_recording()
            elif msg.get("type") == "dump_frame":
                await manager.to_device({"type": "dump_frame"})
    except Exception as e:
        print(f"[Browser WS] Disconnected/Error: {e}")
    finally:
        manager.disconnect_browser(websocket)
        if not manager.browser_sockets:
            await manager.set_mirror()

@app.websocket("/ws/esp32")
async def esp32_ws(websocket: WebSocket):
    await manager.connect_esp32(websocket)
    await manager.broadcast_device_info()
    await manager.set_mirror()
    try:
        await websocket.send_text(json.dumps({"type": "screen_update", "screen": screens.oled_payload(render_screen_state())}))
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                kind = msg.get("type")
                if kind == "button":
                    await handle_button_press(msg.get("button", ""))
                elif kind == "get_screen":
                    await show_screen(render_screen_state())
                    await manager.set_mirror()
                elif kind == "device_frame":      # raw OLED pixels, relayed to the dashboard mirror
                    global last_frame
                    last_frame = msg.get("hex")
                    await manager.to_browsers(msg)
                elif kind == "device_state":      # recording started / finished, reported by the bridge
                    await manager.to_browsers({"type": "device_state", "state": msg.get("state", "")})
                elif kind == "device_info":       # e.g. {"bt": true}
                    if "bt" in msg:
                        device_info["bt"] = bool(msg["bt"])
                        await manager.broadcast_device_info()
            except Exception as e:
                print(f"[ESP32 WS] message error: {e}")
    except Exception as e:
        print(f"[ESP32 WS] Disconnected/Error: {e}")
    finally:
        manager.disconnect_esp32(websocket)
        if not manager.esp32_sockets:
            device_info["bt"] = False
        await manager.broadcast_device_info()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
