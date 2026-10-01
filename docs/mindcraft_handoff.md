# Mindcraft Project Handoff Summary

## Overview
This document captures the state of the Mindcraft project, including code architecture, key files, known issues, and next steps. It is intended for continuation in a new chat or session.

---

### 1. Project Structure
- **Firmware (ESP32)**: `firmware/src/`
  - `main.cpp` – Wi‑Fi init, Bluetooth speaker init, WebSocket client.
  - `audio_speaker.cpp` – Bluetooth A2DP source, ring buffer, HTTP streaming task, A2DP data callback.
  - Dependencies: ESP32‑A2DP library, Arduino core.
- **Companion Server**: `companion/`
  - `app.py` – FastAPI + WebSocket server, handles UI, streams audio, converts MP3 to WAV, notifies ESP32.
  - Virtual environment at `companion/.venv/`.
- **Assets & UI**: (not detailed here) – Front‑end interacts via WebSockets.

---

### 2. Key Functional Flow
1. UI sends `play_audio` via WebSocket to companion.
2. Companion converts TTS MP3 to WAV and stores `last.wav`.
3. Companion calls `notify_play_audio` which sends JSON `{"type":"play_audio","url":"/api/audio/last.wav"}` to ESP32.
4. ESP32 (`main.cpp` → `speaker.begin()`) starts Bluetooth A2DP source and creates `httpStreamTask`.
5. `httpStreamTask` performs HTTP GET of the WAV file, skips WAV header, feeds PCM data into a 16 KB ring buffer, yielding 2 ms each chunk.
6. Bluetooth stack pulls frames via `a2dpDataCallback`, which reads from the ring buffer (pads with silence if empty) and always returns the requested frame count.
7. Wi‑Fi & Bluetooth coexistence configured via:
   - `esp_wifi_set_ps(WIFI_PS_MIN_MODEM);`
   - `esp_coex_preference_set(ESP_COEX_PREFER_BT);`
   - Runtime flags `ESP_COEX_BT_ST_A2DP_STREAMING` set/cleared around streaming.

---

### 3. Known Issue – Connection/Disconnection Loop
- Symptom: UI shows “reconnecting”, ESP32 constantly logs `0.0: =============` indicating the A2DP callback is continuously sending frames, even when the ring buffer is empty.
- Root Cause: `a2dpDataCallback` always returns the full `frame_count` regardless of actual data, causing the Bluetooth radio to stay occupied and starving Wi‑Fi, leading to repeated Wi‑Fi disconnect/reconnect cycles.
- Impact: Audio plays only on laptop speaker; Bluetooth speaker receives silence or no audio.

---

### 4. Suggested Fix
Modify `AudioSpeaker::a2dpDataCallback` (in `audio_speaker.cpp` lines ~167‑177) to:
```cpp
int32_t AudioSpeaker::a2dpDataCallback(Frame *frame, int32_t frame_count) {
    size_t bytesNeeded = frame_count * sizeof(Frame);
    size_t bytesRead = rbRead(frame, bytesNeeded);
    if (bytesRead < bytesNeeded) {
        // Pad remaining with silence
        memset(((uint8_t*)frame) + bytesRead, 0, bytesNeeded - bytesRead);
    }
    // Return the actual number of frames supplied
    return bytesRead / sizeof(Frame);
}
```
- This stops the endless stream of silent frames, freeing RF slots for Wi‑Fi.
- Re‑compile, flash, and test stability.

---

### 5. Next Development Steps
1. **Implement callback fix** as above and verify that the UI remains connected and audio plays on the Bluetooth speaker.
2. **Tune coexistence** if needed – consider increasing the `vTaskDelay` in the streaming loop or adjusting Wi‑Fi power‑save mode.
3. **Add diagnostic logging** to monitor ring‑buffer usage and Wi‑Fi RSSI during playback.
4. **Consider dynamic buffer sizing** if larger audio files are used.
5. **Update documentation** to reflect the new callback behavior and any configuration changes.

---

### 6. Remaining Tasks (if any)
- Review and potentially refactor the HTTP streaming task to handle back‑pressure more gracefully.
- Add unit‑tests for ring‑buffer read/write integrity.
- Ensure the companion server gracefully handles network interruptions.

---

### 7. How to Continue in a New Session
- Clone the repository (or copy the `Mindcraft` folder) to your workstation.
- Open the workspace at `C:\Users\poppi\OneDrive\Desktop\wincode\Mindcraft`.
- Re‑install the Python virtual environment (`cd companion && python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt`).
- Run the companion server: `python app.py`.
- Build & flash the ESP32 firmware using PlatformIO (`pio run -t upload`).
- Test the UI and Bluetooth speaker after applying the callback fix.

---

**End of Handoff**
