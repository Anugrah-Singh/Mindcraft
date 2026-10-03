#include <Arduino.h>
#include <ArduinoJson.h>
#include <vector>

#include "config.h"
#include "display.h"
#include "audio_mic.h"
#include "audio_speaker.h"

// ---------------------------------------------------------------------------
// USB serial protocol with the laptop (companion/serial_bridge.py)
//
//   laptop -> ESP32
//     "@J<json>\n"          JSON message from the Companion Hub (screen_update, record_trigger, ...)
//     "@P*\n" + chunks      16-bit mono 22.05 kHz PCM for the Bluetooth speaker:
//                           [uint16 LE n][n bytes] ..., terminated (or cancelled) by n=0.
//                           The ESP32 answers "@A\n" after each chunk is buffered (flow control).
//   ESP32 -> laptop
//     "@R*\n" + chunks      microphone recording, started by speech and ended by silence:
//                           [uint16 LE n][n bytes of 16-bit mono 22.05 kHz PCM] ..., terminated by n=0
//     "@A\n"                ack for one audio block
//     anything else         plain-text log lines
// ---------------------------------------------------------------------------
#define BLOCK_BYTES 1024

static bool isRecording = false;

static void handleJson(const char* json) {
    JsonDocument doc;
    if (deserializeJson(doc, json)) return;

    const char* msgType = doc["type"] | "";

    if (strcmp(msgType, "screen") == 0 || strcmp(msgType, "screen_update") == 0) {
        JsonObject sObj = doc["screen"].is<JsonObject>() ? doc["screen"].as<JsonObject>()
                        : (doc["data"].is<JsonObject>() ? doc["data"].as<JsonObject>() : doc.as<JsonObject>());
        display.showScreen(sObj);   // structured layout, or the legacy text layout if "view" is missing
    }
    else if (strcmp(msgType, "mirror") == 0) {
        display.setMirror(doc["on"] | false);
        if (doc["on"] | false) display.dumpFrame();   // first frame right away
    }
    else if (strcmp(msgType, "dump_frame") == 0) {
        display.dumpFrame();
    }
    else if (strcmp(msgType, "record_trigger") == 0) {
        Serial.println("[HUB] record_trigger received.");
        isRecording = true;
    }
    else if (strcmp(msgType, "action") == 0) {
        const char* action = doc["data"]["action"] | doc["action"] | "";
        if (strcmp(action, "LISTEN") == 0) isRecording = true;
    }
}

// Incoming-audio state: after "@P*" the host sends chunks [uint16 LE byte_count][PCM bytes],
// terminated by a zero byte_count (also used by the host to cancel a clip cleanly).
enum RxState { RX_LINE, RX_CHUNK_HEADER, RX_CHUNK_DATA, RX_JSON_LINE };
static const uint16_t CHUNK_JSON = 0xFFFF;   // header value: a JSON line follows instead of audio
static char rxLine[2048];
static size_t rxLineLen = 0;
static RxState rxState = RX_LINE;
static uint16_t chunkLen = 0;
static unsigned long lastPayloadRx = 0;

static void abortClip(const char* why) {
    Serial.printf("[SPK] Audio stream aborted: %s\n", why);
    rxState = RX_LINE;
    speaker.clipEnd();
    Serial.print("@E\n");
}

static void handleLine(char* line) {
    // A clip header is recognised anywhere in the line, so a few stray bytes (e.g. left
    // over from an interrupted transfer) cannot make the ESP32 miss it.
    if (strstr(line, "@P*")) {
        speaker.clipBegin();
        rxState = RX_CHUNK_HEADER;
        lastPayloadRx = millis();
        Serial.println("[SPK] Receiving audio...");
        return;
    }
    if (line[0] == '@' && line[1] == 'J') {
        handleJson(line + 2);
    }
}

static void pollHost() {
    static int16_t block[BLOCK_BYTES / 2];

    if (rxState == RX_CHUNK_HEADER) {
        if (Serial.available() >= 2) {
            uint8_t h[2];
            Serial.readBytes(h, 2);
            chunkLen = (uint16_t)(h[0] | (h[1] << 8));
            lastPayloadRx = millis();
            if (chunkLen == 0) {                   // end of clip
                rxState = RX_LINE;
                speaker.clipEnd();
                Serial.print("@E\n");              // tell the host the stream is closed and drained
            } else if (chunkLen == CHUNK_JSON) {   // hub message sent in the middle of a clip
                rxLineLen = 0;
                rxState = RX_JSON_LINE;
            } else if (chunkLen > BLOCK_BYTES || (chunkLen & 1)) {
                abortClip("bad chunk length");
            } else {
                rxState = RX_CHUNK_DATA;
            }
        } else if (millis() - lastPayloadRx > 3000) {
            abortClip("timeout");
        }
        return;
    }

    if (rxState == RX_JSON_LINE) {
        while (Serial.available()) {
            char c = (char)Serial.read();
            if (c == '\n') {
                rxLine[rxLineLen] = 0;
                rxLineLen = 0;
                handleJson(rxLine);
                rxState = RX_CHUNK_HEADER;
                lastPayloadRx = millis();
                return;
            }
            if (rxLineLen < sizeof(rxLine) - 1) rxLine[rxLineLen++] = c;
        }
        if (millis() - lastPayloadRx > 3000) abortClip("json timeout");
        return;
    }

    if (rxState == RX_CHUNK_DATA) {
        // Only take a chunk when the ring buffer has room for it (back-pressure).
        if (Serial.available() >= (int)chunkLen && speaker.freeSamples() >= chunkLen / 2u) {
            Serial.readBytes((uint8_t*)block, chunkLen);
            speaker.pushSamples(block, chunkLen / 2u);
            lastPayloadRx = millis();
            Serial.print("@A\n");
            rxState = RX_CHUNK_HEADER;
        } else if (millis() - lastPayloadRx > 3000) {
            abortClip("timeout");
        }
        return;
    }

    while (Serial.available()) {
        char c = (char)Serial.read();
        if (c == '\n') {
            rxLine[rxLineLen] = 0;
            rxLineLen = 0;
            handleLine(rxLine);
            if (rxState != RX_LINE) return;   // binary chunks follow
        } else if (c != '\r' && rxLineLen < sizeof(rxLine) - 1) {
            rxLine[rxLineLen++] = c;
        }
    }
}

// ---------------------------------------------------------------------------
// Physical buttons (optional): wire each between its GPIO and GND, no resistor needed.
// A debounced press is reported to the laptop as "@B<NAME>\n", which the bridge forwards to the hub.
// Unconnected pins sit high on the internal pull-ups, so the firmware works without buttons.
// ---------------------------------------------------------------------------
struct Button { uint8_t pin; const char* name; bool stable; bool last; unsigned long changed; };
static Button buttons[] = {
    {BTN_UP_PIN, "UP", true, true, 0},
    {BTN_DOWN_PIN, "DOWN", true, true, 0},
    {BTN_SELECT_PIN, "SELECT", true, true, 0},
    {BTN_BACK_PIN, "BACK", true, true, 0},
};
#define BUTTON_DEBOUNCE_MS 30

static void pollButtons() {
    for (Button& b : buttons) {
        const bool reading = digitalRead(b.pin);
        if (reading != b.last) {
            b.last = reading;
            b.changed = millis();
        }
        if (millis() - b.changed > BUTTON_DEBOUNCE_MS && reading != b.stable) {
            b.stable = reading;
            if (!b.stable) Serial.printf("@B%s\n", b.name);   // pressed (pulled to GND)
        }
    }
}

void setup() {
    for (Button& b : buttons) pinMode(b.pin, INPUT_PULLUP);
    Serial.setRxBufferSize(8192);
    Serial.begin(HOST_BAUD);
    delay(500);

    Serial.println("\n==============================================");
    Serial.println("  MINDCRAFT AI ASSISTANT - USB + BLUETOOTH     ");
    Serial.println("==============================================");

    display.begin();

    if (!mic.begin()) {
        Serial.println("[ERROR] INMP441 microphone initialization failed!");
    } else {
        Serial.println("[MIC] INMP441 initialized (44.1kHz, 32-bit slot, Left slot).");
    }

    // Bluetooth speaker - boAt Stone 190. Wi-Fi is intentionally never started.
    speaker.begin();
}

void loop() {
    speaker.loop();
    pollHost();
    pollButtons();
    display.tick();

    // Until the hub has sent a screen, ask for one every 2 s ("@S"; the bridge forwards the request).
    static unsigned long lastScreenRequest = 0;
    if (!display.hasScreen() && millis() - lastScreenRequest > 2000) {
        lastScreenRequest = millis();
        Serial.print("@S\n");
    }

    static bool lastBt = false;
    bool bt = speaker.isConnected();
    if (bt != lastBt) {
        lastBt = bt;
        display.setBtConnected(bt);
    }

    // Recording blocks the loop (and so the USB reads), so it only starts once any incoming
    // audio stream has been closed. Starting to record interrupts playback.
    if (isRecording && rxState == RX_LINE) {
        isRecording = false;
        speaker.stop();
        display.beginRecording();
        Serial.println("[AI] Recording...");
        mic.recordToSerial();
        while (Serial.available()) Serial.read();   // drop anything that arrived meanwhile
        rxLineLen = 0;
        Serial.println("[AI] Recording sent to laptop.");
        display.showProcessing();
    }

    static unsigned long lastHeartbeat = 0;
    if (rxState == RX_LINE && millis() - lastHeartbeat >= 5000) {
        lastHeartbeat = millis();
        Serial.printf("[SYS] Free Heap: %u bytes | %s\n", ESP.getFreeHeap(), speaker.getStatusString().c_str());
    }

    delay(1);
}
