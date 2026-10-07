"""USB bridge between the ESP32 and the Companion Hub (no Wi-Fi needed on the device).

Wi-Fi and Bluetooth share one radio on the ESP32, and Wi-Fi traffic starved the Bluetooth
speaker. The ESP32 therefore never starts Wi-Fi: this script connects to the Companion Hub
as if it were the device and relays everything over the USB serial cable.

Protocol (see firmware/src/main.cpp):
  laptop -> ESP32   "@J<json>\\n"            hub JSON (screen updates, record trigger)
                    "@P*\\n" + chunks        reply audio: [uint16 LE n][n bytes 16-bit mono 22.05 kHz PCM] ...,
                                       ended or cancelled by n=0; the ESP32 acks each chunk with "@A"
  ESP32 -> laptop   "@R*\\n" + chunks        microphone recording, started by speech / ended by silence:
                                       [uint16 LE n][n bytes PCM, 16-bit mono 22.05 kHz] ..., ended by n=0
                    "@A\\n"                  one audio block consumed
                    other lines              device log

Usage:  python serial_bridge.py [--port COM3] [--baud 921600] [--hub 127.0.0.1:8000]
"""
import argparse
import audioop
import json
import struct
import sys
import threading
import time
import struct
import urllib.request
import zlib
from pathlib import Path

import serial
from websockets.sync.client import connect

BLOCK_BYTES = 1024      # must match firmware BLOCK_BYTES
WINDOW_BLOCKS = 6       # unacknowledged blocks allowed in flight (firmware RX buffer is 8 KB)
AUDIO_RATE = 22050


def log(msg):
    print(msg, flush=True)


def wav_header(pcm_len, rate=AUDIO_RATE, channels=1, bits=16):
    byte_rate = rate * channels * bits // 8
    return (b"RIFF" + struct.pack("<I", 36 + pcm_len) + b"WAVEfmt " +
            struct.pack("<IHHIIHH", 16, 1, channels, rate, byte_rate, channels * bits // 8, bits) +
            b"data" + struct.pack("<I", pcm_len))


def parse_wav(data):
    """Return (pcm_bytes, channels, rate) for a 16-bit PCM WAV file."""
    pos, channels, rate = 12, 1, AUDIO_RATE
    while pos + 8 <= len(data):
        cid = data[pos:pos + 4]
        size = struct.unpack("<I", data[pos + 4:pos + 8])[0]
        if cid == b"fmt ":
            channels, rate = struct.unpack("<HI", data[pos + 10:pos + 16])
        elif cid == b"data":
            return data[pos + 8:pos + 8 + size], channels, rate
        pos += 8 + size + (size & 1)
    raise ValueError("no data chunk in WAV")


def frame_to_png(hex_frame, scale=4):
    """Decode an SSD1306 page buffer (8 pages x 128 columns, bit0 = top pixel) into PNG bytes."""
    raw = bytes.fromhex(hex_frame)
    w, h = 128, 64
    out = bytearray()
    for y in range(h):
        line = bytearray([0])                      # PNG filter type 0 for this scanline
        for x in range(w):
            on = (raw[(y // 8) * w + x] >> (y % 8)) & 1
            line += bytes([232 if on else 10]) * scale
        out += bytes(line) * scale                 # repeat the scanline vertically

    def chunk(tag, data):
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    signature = bytes([137, 80, 78, 71, 13, 10, 26, 10])
    header = struct.pack(">IIBBBBB", w * scale, h * scale, 8, 0, 0, 0, 0)
    return signature + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(bytes(out))) + chunk(b"IEND", b"")


class Bridge:
    def __init__(self, port, baud, hub, snapshots=None):
        self.hub = hub
        self.snapshots = Path(snapshots) if snapshots else None
        self.frame_count = 0
        if self.snapshots:
            self.snapshots.mkdir(parents=True, exist_ok=True)
        self.ser = serial.Serial()
        self.ser.port = port
        self.ser.baudrate = baud
        self.ser.timeout = 1
        self.ser.dtr = False   # do not reset the ESP32 when the port opens
        self.ser.rts = False
        self.ser.open()
        self.tx_lock = threading.Lock()
        self.credits = threading.BoundedSemaphore(WINDOW_BLOCKS)
        self.play_lock = threading.Lock()
        self.cancel_play = threading.Event()
        self.streaming = False      # True while a reply clip is being streamed to the ESP32
        self.end_ack = threading.Event()   # set when the ESP32 confirms a clip stream is closed
        self.end_ack.set()
        self.ws = None              # current hub connection (None while reconnecting)
        self.bt_state = None        # last known Bluetooth speaker state reported by the ESP32

    def hub_send(self, message):
        """Send a JSON message to the hub (ignored while the hub is unreachable)."""
        ws = self.ws
        if ws is None:
            return
        try:
            ws.send(json.dumps(message, separators=(",", ":")))
        except Exception:
            pass

    def note_bt(self, connected):
        if connected != self.bt_state:
            self.bt_state = connected
            self.hub_send({"type": "device_info", "bt": connected})

    # ---- serial helpers ----
    def send(self, data):
        with self.tx_lock:
            self.ser.write(data)

    def send_json(self, data):
        """Hub message for the ESP32. During a clip it is wrapped in the chunk framing
        (header 0xFFFF) so the ESP32 can never mistake it for audio."""
        line = json.dumps(data, separators=(",", ":")).encode() + b"\n"
        with self.tx_lock:
            self.ser.write((b"\xff\xff" if self.streaming else b"@J") + line)

    def begin_stream(self):
        with self.tx_lock:
            self.streaming = True
            self.ser.write(b"@P*\n")

    def end_stream(self):
        with self.tx_lock:
            self.streaming = False
            self.end_ack.clear()
            self.ser.write(b"\x00\x00")

    def reopen_serial(self):
        """The USB port dropped (cable, brown-out, board reset): wait for it and open it again."""
        self.hub_send({"type": "device_info", "usb": False})
        self.cancel_play.set()
        with self.tx_lock:
            try:
                self.ser.close()
            except Exception:
                pass
        log("[bridge] Waiting for the ESP32 to come back...")
        while True:
            time.sleep(2)
            try:
                with self.tx_lock:
                    self.ser.open()
                break
            except (serial.SerialException, OSError):
                continue
        self.streaming = False
        self.end_ack.set()
        self.bt_state = None
        self.hub_send({"type": "device_info", "usb": True})
        log(f"[bridge] Reconnected to {self.ser.port}")

    def reader(self):
        while True:
            try:
                line = self.ser.readline()
            except (serial.SerialException, OSError) as e:
                log(f"[bridge] serial error: {e}")
                self.reopen_serial()
                continue
            if not line:
                continue
            if line.startswith(b"@A"):
                try:
                    self.credits.release()
                except ValueError:      # late ack from a cancelled clip
                    pass
            elif line.startswith(b"@E"):
                self.end_ack.set()
            elif line.startswith(b"@F"):
                frame = line[2:].strip()
                if len(frame) == 2048:
                    try:
                        text = frame.decode("ascii")
                        bytes.fromhex(text)
                    except ValueError:
                        continue            # garbled by an interleaved log line: drop it
                    self.hub_send({"type": "device_frame", "hex": text})
                    if self.snapshots:
                        try:                    # a debug aid must never be able to stop the bridge
                            self.snapshots.mkdir(parents=True, exist_ok=True)
                            self.frame_count += 1
                            (self.snapshots / "latest.png").write_bytes(frame_to_png(text))
                        except OSError as e:
                            log(f"[bridge] Could not save snapshot ({e}); snapshots turned off")
                            self.snapshots = None
            elif line.startswith(b"@S"):
                self.hub_send({"type": "get_screen"})     # the ESP32 has no screen yet
            elif line.startswith(b"@B"):
                name = line[2:].decode("ascii", errors="ignore").strip()
                if name in ("UP", "DOWN", "SELECT", "BACK"):
                    log(f"[bridge] Button {name}")
                    self.hub_send({"type": "button", "button": name})
            elif line.startswith(b"@R"):
                self.hub_send({"type": "device_state", "state": "recording"})
                self.receive_recording()
            else:
                text = line.decode("utf-8", errors="replace").rstrip()
                if text:
                    log(f"[ESP32] {text}")
                    if "| BT: Connected" in text or "CONNECTED TO STONE" in text:
                        self.note_bt(True)
                    elif "| BT: Connecting" in text or "speaker disconnected" in text:
                        self.note_bt(False)

    def read_exact(self, n, idle_timeout=5):
        buf = bytearray()
        last = time.time()
        while len(buf) < n and time.time() - last < idle_timeout:
            chunk = self.ser.read(n - len(buf))
            if chunk:
                buf += chunk
                last = time.time()
        return bytes(buf)

    def receive_recording(self):
        """Read length-prefixed chunks ([uint16 LE n][n bytes]) until a zero length."""
        pcm = bytearray()
        while True:
            head = self.read_exact(2)
            if len(head) < 2:
                log("[bridge] Recording stream stalled; using what was received")
                break
            n = head[0] | (head[1] << 8)
            if n == 0:
                break
            data = self.read_exact(n)
            pcm += data
            if len(data) < n:
                log("[bridge] Recording chunk truncated")
                break
        log(f"[bridge] Microphone recording received: {len(pcm)} bytes ({len(pcm) / 2 / AUDIO_RATE:.1f} s)")
        threading.Thread(target=self.upload_recording, args=(bytes(pcm),), daemon=True).start()

    def upload_recording(self, pcm):
        wav = wav_header(len(pcm)) + pcm
        req = urllib.request.Request(f"http://{self.hub}/api/process_audio", data=wav,
                                     headers={"Content-Type": "audio/wav"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                log(f"[bridge] Uploaded recording to hub: HTTP {r.status}")
        except Exception as e:
            log(f"[bridge] Upload failed: {e}")

    # ---- audio playback ----
    def play(self):
        self.cancel_play.set()          # stop any clip still being sent
        with self.play_lock:
            self.cancel_play.clear()
            try:
                with urllib.request.urlopen(f"http://{self.hub}/api/audio/last.wav", timeout=15) as r:
                    wav = r.read()
                pcm, ch, rate = parse_wav(wav)
                if ch == 2:
                    pcm = audioop.tomono(pcm, 2, 0.5, 0.5)
                if rate != AUDIO_RATE:
                    pcm, _ = audioop.ratecv(pcm, 2, 1, rate, AUDIO_RATE, None)
            except Exception as e:
                log(f"[bridge] Could not fetch reply audio: {e}")
                return
            pcm = pcm[:len(pcm) & ~1]
            log(f"[bridge] Sending {len(pcm)} bytes ({len(pcm) / 2 / AUDIO_RATE:.1f} s) of reply audio to ESP32")
            # The previous clip must be fully drained by the ESP32 before a new window starts,
            # otherwise its unread chunks plus the new ones would overflow the ESP32 RX buffer.
            if not self.end_ack.wait(timeout=8):
                log("[bridge] ESP32 did not confirm the previous clip; continuing anyway")
            while self.credits.acquire(blocking=False):   # reset flow-control window
                pass
            for _ in range(WINDOW_BLOCKS):
                try:
                    self.credits.release()
                except ValueError:
                    break
            self.begin_stream()
            t0 = time.time()
            first = True
            for i in range(0, len(pcm), BLOCK_BYTES):
                if self.cancel_play.is_set():
                    self.end_stream()          # close the clip cleanly so the ESP32 stays in sync
                    log("[bridge] Playback cancelled by newer clip")
                    return
                # The ESP32 may be busy recording when the first chunk is ready, so wait longer for it.
                if not self.credits.acquire(timeout=40 if first else 5):
                    self.end_stream()
                    log("[bridge] No ack from ESP32 - aborting clip")
                    return
                first = False
                chunk = pcm[i:i + BLOCK_BYTES]
                self.send(len(chunk).to_bytes(2, "little") + chunk)
            self.end_stream()                  # end of clip
            log(f"[bridge] Reply audio delivered in {time.time() - t0:.1f} s")

    # ---- hub websocket ----
    def hub_loop(self):
        url = f"ws://{self.hub}/ws/esp32"
        while True:
            try:
                with connect(url, max_size=None) as ws:
                    log(f"[bridge] Connected to Companion Hub {url}")
                    self.ws = ws
                    if self.bt_state is not None:
                        self.hub_send({"type": "device_info", "bt": self.bt_state})
                    for msg in ws:
                        try:
                            data = json.loads(msg)
                        except ValueError:
                            continue
                        if data.get("type") == "play_audio":
                            threading.Thread(target=self.play, daemon=True).start()
                        else:
                            if data.get("type") == "record_trigger":
                                # The ESP32 cannot read USB while recording: stop streaming a reply first.
                                self.cancel_play.set()
                            self.send_json(data)
            except Exception as e:
                self.ws = None
                log(f"[bridge] Hub connection lost ({e}); retrying in 2 s")
                time.sleep(2)
            self.ws = None

    def run(self):
        threading.Thread(target=self.hub_loop, daemon=True).start()
        self.reader()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="COM3")
    ap.add_argument("--baud", type=int, default=921600)
    ap.add_argument("--hub", default="127.0.0.1:8000")
    ap.add_argument("--snapshots", default=None, help="folder to write latest.png (the OLED as the device draws it)")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # boot-ROM noise can be garbage
    try:
        Bridge(args.port, args.baud, args.hub, args.snapshots).run()
    except KeyboardInterrupt:
        sys.exit(0)
