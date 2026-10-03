# Mindcraft Project Handoff

AI note-taking device: an ESP32 with an OLED, an INMP441 microphone and a boAt "Stone 190"
Bluetooth speaker, backed by a Companion Hub (FastAPI + Gemini) running on the laptop.

## Architecture

```
INMP441 mic --I2S--> ESP32 --USB serial (921600)--> serial_bridge.py --HTTP/WS--> Companion Hub (app.py)
OLED <--I2C--------- ESP32 <--USB serial-----------  serial_bridge.py <--------- Gemini + edge-tts
                       ESP32 --Bluetooth A2DP--> Stone 190 speaker
```

**The ESP32 never starts Wi-Fi.** Wi-Fi and Bluetooth share one radio; streaming reply audio over
Wi-Fi starved the A2DP stream and made speech choppy. The laptop link is the USB cable instead.

### Running it
1. `cd companion && .venv\Scripts\activate && pip install -r requirements.txt`, put `GEMINI_API_KEY` in `companion/.env`.
2. `python -m uvicorn app:app --host 127.0.0.1 --port 8000` (the dashboard is at http://127.0.0.1:8000).
3. `python serial_bridge.py --port COM3` (only one program can hold COM3: stop the bridge before flashing).
4. Firmware: `cd firmware && pio run -t upload --upload-port COM3`.

### USB protocol (firmware/src/main.cpp, companion/serial_bridge.py)
| Direction | Frame | Meaning |
|---|---|---|
| laptop -> ESP32 | `@J<json>\n` | Hub message (screen update, `record_trigger`) |
| laptop -> ESP32 | `@P*\n` then chunks `[uint16 LE n][n bytes]`, ended/cancelled by `n=0` | Reply audio: 16-bit mono 22.05 kHz PCM. ESP32 acks each chunk with `@A\n` and the end with `@E\n` |
| laptop -> ESP32 | `0xFFFF` + json + `\n` (inside a clip) | A hub message that arrives while audio is streaming |
| ESP32 -> laptop | `@R*\n` then chunks, ended by `n=0` | Microphone recording (started by speech, ended by silence) |
| ESP32 -> laptop | anything else | Plain-text log lines |

The ESP32 cannot read USB while recording, so the bridge cancels any playing clip when it forwards a
`record_trigger`, and waits for the `@E` confirmation before starting the next clip (otherwise unread
chunks overflow the ESP32's 8 KB RX buffer).

## Hardware (known good)
OLED SDA 21 / SCL 22 (0x3C). INMP441 SCK 26 / WS 25 / SD 32, L/R to GND (left slot), 44.1 kHz 32-bit.
Bluetooth name is `Stone 190` (not "boAt Stone 190"). The MAX98357A wired speaker path was never
validated and is not used. Battery/TP4056 not integrated.

## Audio notes
- Volume is set only after `AUDIO: Started` (50, then `DEFAULT_BT_VOLUME`, currently 110; the speaker
  can shut off at very high volume - back off to ~100 if that happens).
- A2DP callback is fed from a ring buffer; it re-enters pre-buffering after any underrun.
- Wi-Fi power-save must not be disabled while Bluetooth runs (the ESP32 aborts); Wi-Fi is simply not used.
- Recording: the ESP32 waits for speech (adaptive noise floor), keeps a 0.5 s pre-roll, stops after 1.2 s of
  silence, gives up after 8 s without speech and caps a recording at 20 s (see `audio_mic.cpp`).
- The web page records only from the INMP441; the laptop microphone path is disabled.

## Features and behaviour (all covered by an end-to-end test against the real hub)
- **Voice commands** (Gemini): TASK, TASK_DONE ("I finished the tax report"), NOTE, HABIT, CONVERSATION.
- **Habits**: a streak continues only if the habit was logged yesterday or today, otherwise it restarts at 1;
  logging twice a day does not double count; a stale streak displays as 0. Names are mapped to the three
  defaults (Gym / Daily Walk / Read 20 Mins) via aliases ("workout" -> Gym) so no duplicates appear.

## UI

### Device (OLED, `firmware/src/display.cpp`)
The hub sends *structured* screens (`companion/screens.py`: `view` = menu / tasks / habits / notes / ai /
status, plus items, selection, scroll position) and the firmware draws them. Layout grid: 11 px inverted header
(title, `n/N` counter, Bluetooth rune struck through while the speaker is disconnected), 4 body rows of 10 px,
scrollbar on the right, footer hints. Menu = 2x2 icon tiles with live counts. Tasks show a checkbox and a
priority letter, habits a tick for "done today" and a flame with the streak, notes a play marker on the
selected row. Status screens animate (listening meter, thinking dots, speaker waves). Text is ASCII only and
ends in `..` when it does not fit. While recording, only the meter area is redrawn and sent (about 15 ms) so the
I2S microphone buffers never overflow. Reference images of every screen: `docs/images/oled-screens.png`.

**Physical buttons (optional):** wire a push button between each GPIO and GND (internal pull-ups, no
resistor): UP = GPIO 27, DOWN = GPIO 14, SELECT = GPIO 13, BACK = GPIO 4 (`config.h`). Presses are debounced
(30 ms), reported as `@B<NAME>` and forwarded by the bridge to the hub. Unconnected pins never fire.

### Dashboard (`companion/web/index.html`)
Designed with Anthropic's `frontend-design` skill process (design plan in the CSS header comment, reviewed
against its list of generic "AI design" defaults) plus the dashboard rules of the community UI/UX Pro Max skill
(4.5:1 contrast, visible focus, no emoji icons, meaning never carried by colour alone, 375/768/1024/1440 px).
Concept: a voice *notebook*. Left, a light matte hand-held device (live OLED mirror, four round keys, a round
record button). Right, one ruled notebook page with a red margin line: the latest reply as dictated text, a
bullet-journal habit tracker (one row per habit, one dot per day for the last 14 days), tasks with journal-style
`!!!` / `!!` / `!` priority marks, and notes as serif entries. Type: Schibsted Grotesk (interface) and Literata
(dictated text and notes), loaded from Google Fonts with system fallbacks; sentence case, no monospace, no
all-caps labels. The one motion is a highlighter sweep behind whatever just changed. Light and dark themes follow
the system setting with a manual toggle; it works down to 375 px.
The OLED mirror shows the **real pixels from the device**: while a dashboard is open the hub tells the ESP32 to
stream its 1 KB frame buffer as `@F<hex>` lines (about 7 fps at most), so what you see is exactly what the OLED
shows. It also shows a "no signal" state when the device is offline. Screenshots: `docs/images/dashboard-*.png`.
Keys: Space = record, W/S or arrows = move, Enter = select, Esc/Backspace = back.

### Developer tools
- `python serial_bridge.py --snapshots ../snapshots` also writes `latest.png`, the OLED exactly as drawn, which is
  how the layouts were checked without looking at the hardware.
- Hub messages added for the UI: `device_info` (USB link, Bluetooth), `device_state`, `device_frame`, `mirror`.

## Known limitations / next steps
- Battery/TP4056 power and the MAX98357A path are untested.
- Once speech has started during a recording, mirror frames pause, because text frames would
  corrupt the binary recording stream. They resume when the recording ends.
- A cosmetic burst of non-text bytes sometimes shows up in the bridge log when a clip starts; audio is unaffected.
- `companion/test_rigorous.py` and the `*.bak` files in `firmware/src` are leftovers from earlier sessions.
