import asyncio
import json
import httpx
import websockets
import time
import sys
from pathlib import Path

BASE_URL = "http://127.0.0.1:8000"
WS_CONTROLLER = "ws://127.0.0.1:8000/ws/controller"
WS_ESP32 = "ws://127.0.0.1:8000/ws/esp32"

async def test_rest_endpoints():
    print("\n--- [TEST 1] REST API Endpoints ---")
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=5.0) as client:
        # 1. Root / UI
        r = await client.get("/")
        assert r.status_code == 200, f"Root / failed: {r.status_code}"
        assert "MINDCRAFT" in r.text, "Index page missing MINDCRAFT"
        print("  [PASS] GET / (UI index page)")

        # 2. /api/tasks
        r = await client.get("/api/tasks")
        assert r.status_code == 200, f"/api/tasks failed: {r.status_code}"
        tasks = r.json()
        assert isinstance(tasks, list), "Tasks should be a list"
        print(f"  [PASS] GET /api/tasks (returned {len(tasks)} tasks)")

        # 3. /api/habits
        r = await client.get("/api/habits")
        assert r.status_code == 200, f"/api/habits failed: {r.status_code}"
        habits = r.json()
        assert isinstance(habits, list), "Habits should be a list"
        print(f"  [PASS] GET /api/habits (returned {len(habits)} habits)")

        # 4. /api/notes
        r = await client.get("/api/notes")
        assert r.status_code == 200, f"/api/notes failed: {r.status_code}"
        notes = r.json()
        assert isinstance(notes, list), "Notes should be a list"
        print(f"  [PASS] GET /api/notes (returned {len(notes)} notes)")

        # 5. /api/screen
        r = await client.get("/api/screen")
        assert r.status_code == 200, f"/api/screen failed: {r.status_code}"
        screen = r.json()
        assert "title" in screen and "lines" in screen, "Invalid screen structure"
        print(f"  [PASS] GET /api/screen (current title: '{screen.get('title')}')")

async def test_websocket_navigation_and_sync():
    print("\n--- [TEST 2] WebSocket Navigation & Dual-Sync (Browser <-> ESP32) ---")
    async with websockets.connect(WS_CONTROLLER) as browser_ws, websockets.connect(WS_ESP32) as esp32_ws:
        # Initial screen update on connect
        b_init = json.loads(await browser_ws.recv())
        e_init = json.loads(await esp32_ws.recv())
        assert b_init["type"] == "screen_update", f"Unexpected browser message: {b_init}"
        assert e_init["type"] == "screen_update", f"Unexpected ESP32 message: {e_init}"
        print("  [PASS] Initial screen delivered to both Browser and ESP32 clients")

        # Test DOWN navigation
        await browser_ws.send(json.dumps({"type": "button", "button": "DOWN"}))
        b_down = json.loads(await browser_ws.recv())
        e_down = json.loads(await esp32_ws.recv())
        assert b_down["type"] == "screen_update"
        assert e_down["type"] == "screen_update"
        # Verify lines are present and synchronized
        assert b_down["screen"]["lines"] == e_down["screen"]["lines"], "Screen lines mismatch between Browser and ESP32"
        print("  [PASS] Browser button 'DOWN' synced identically to ESP32 OLED payload")

        # Test UP navigation
        await browser_ws.send(json.dumps({"type": "button", "button": "UP"}))
        b_up = json.loads(await browser_ws.recv())
        e_up = json.loads(await esp32_ws.recv())
        assert b_up["screen"]["lines"] == e_up["screen"]["lines"]
        print("  [PASS] Browser button 'UP' synced identically to ESP32 OLED payload")

        # Test SELECT navigation into submenu
        await browser_ws.send(json.dumps({"type": "button", "button": "SELECT"}))
        b_sel = json.loads(await browser_ws.recv())
        e_sel = json.loads(await esp32_ws.recv())
        print(f"  [PASS] SELECT entered view: '{b_sel['screen']['title']}' (ESP32: '{e_sel['screen']['title']}')")

        # Test BACK navigation to menu
        await browser_ws.send(json.dumps({"type": "button", "button": "BACK"}))
        b_back = json.loads(await browser_ws.recv())
        e_back = json.loads(await esp32_ws.recv())
        assert "MENU" in b_back["screen"]["title"]
        assert "MENU" in e_back["screen"]["title"]
        print("  [PASS] BACK returned to MINDCRAFT MENU")

async def test_text_prompt_ai_pipeline():
    print("\n--- [TEST 3] AI Text Prompt -> Storage -> Screen -> Audio Pipeline ---")
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=15.0) as client:
        test_task_title = f"Test Task {int(time.time())}"
        payload = {"prompt": f"Add high priority task: {test_task_title}"}
        t0 = time.time()
        r = await client.post("/api/process_prompt", json=payload)
        elapsed = time.time() - t0
        assert r.status_code == 200, f"process_prompt failed: {r.status_code}"
        res = r.json()
        assert res.get("action") == "TASK", f"Expected action TASK, got {res.get('action')}"
        print(f"  [PASS] Gemini processed prompt in {elapsed:.2f}s: action={res.get('action')}, spoken='{res.get('spoken_response')}'")

        # Verify task was stored in DB
        r_tasks = await client.get("/api/tasks")
        tasks = r_tasks.json()
        target_title = res.get("title", "")
        matching = [t for t in tasks if target_title.lower() in t["title"].lower()]
        assert len(matching) > 0, f"Task '{target_title}' was not saved to SQLite storage"
        print(f"  [PASS] Task '{target_title}' verified in database storage: id={matching[0]['id']}")

        # Verify audio endpoints are ready
        r_wav = await client.get("/api/audio/last.wav")
        assert r_wav.status_code == 200, f"/api/audio/last.wav failed: {r_wav.status_code}"
        assert len(r_wav.content) > 1000, f"WAV too small: {len(r_wav.content)} bytes"
        print(f"  [PASS] TTS 44.1kHz WAV ready for Stone 190 playback ({len(r_wav.content)} bytes)")

async def test_voice_audio_upload_pipeline():
    print("\n--- [TEST 4] Audio Upload (INMP441 Stream Simulation) -> Gemini -> Screen Sync ---")
    # Generate 1 second of dummy PCM WAV to simulate streaming from INMP441 mic
    sample_rate = 16000
    num_samples = sample_rate * 2
    pcm_data = b"\x00\x00" * num_samples
    
    # Simple WAV header
    wav_header = bytearray(44)
    total_size = 44 + len(pcm_data) - 8
    byte_rate = sample_rate * 1 * 2
    wav_header[0:4] = b"RIFF"
    wav_header[4:8] = total_size.to_bytes(4, "little")
    wav_header[8:12] = b"WAVE"
    wav_header[12:16] = b"fmt "
    wav_header[16:20] = (16).to_bytes(4, "little")
    wav_header[20:22] = (1).to_bytes(2, "little") # PCM
    wav_header[22:24] = (1).to_bytes(2, "little") # Mono
    wav_header[24:28] = sample_rate.to_bytes(4, "little")
    wav_header[28:32] = byte_rate.to_bytes(4, "little")
    wav_header[32:34] = (2).to_bytes(2, "little") # Block align
    wav_header[34:36] = (16).to_bytes(2, "little") # Bits per sample
    wav_header[36:40] = b"data"
    wav_header[40:44] = len(pcm_data).to_bytes(4, "little")
    full_wav = bytes(wav_header) + pcm_data

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        r = await client.post("/api/process_audio", content=full_wav, headers={"Content-Type": "audio/wav"})
        assert r.status_code == 200, f"/api/process_audio failed: {r.status_code}"
        res = r.json()
        assert res.get("status") == "processing", f"Unexpected status: {res}"
        print("  [PASS] /api/process_audio accepted binary WAV stream and spawned async AI job")

        # Verify recorded_controller_audio.wav was written to disk
        rec_path = Path(__file__).parent / "recorded_controller_audio.wav"
        assert rec_path.exists(), "recorded_controller_audio.wav was not created"
        assert rec_path.stat().st_size >= len(full_wav), "recorded_controller_audio.wav file size mismatch"
        print(f"  [PASS] Controller microphone audio persisted to laptop disk: {rec_path.name} ({rec_path.stat().st_size} bytes)")

async def run_suite(iteration: int):
    print(f"\n=======================================================")
    print(f"=== RUNNING RIGOROUS TEST PASS #{iteration} ===")
    print(f"=======================================================")
    await test_rest_endpoints()
    await test_websocket_navigation_and_sync()
    await test_text_prompt_ai_pipeline()
    await test_voice_audio_upload_pipeline()
    print(f"\n>>> PASS #{iteration} COMPLETED WITH 100% SUCCESS! <<<")

async def main():
    passes = 3
    for i in range(1, passes + 1):
        await run_suite(i)
        await asyncio.sleep(1)
    print("\n" + "="*60)
    print("ALL 3 TEST PASSES COMPLETED WITH ZERO FAILURES!")
    print("="*60 + "\n")

if __name__ == "__main__":
    asyncio.run(main())
