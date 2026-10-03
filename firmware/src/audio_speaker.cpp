#include "audio_speaker.h"
#include "config.h"
#include <math.h>

// Wi-Fi is never started: Bluetooth gets the whole radio. The host (laptop) feeds audio
// over USB serial (see main.cpp) and this module plays it to the Stone 190 via A2DP.

static BluetoothA2DPSource a2dp_source;
static volatile bool btConnected = false;
static volatile bool btAudioStarted = false;
static int volState = 0;  // 0=idle, 1=ramping, 2=done; reset on BT disconnect

// --- Thread-safe ring buffer holding 22.05 kHz mono source samples ---
#define BUFFER_SIZE     12288  // ~557 ms of 22.05 kHz audio
#define PREBUFFER_MIN   4096   // ~186 ms before playback starts / resumes
static int16_t audioBuffer[BUFFER_SIZE];
static volatile uint32_t writePos = 0;
static volatile uint32_t readPos  = 0;
static volatile bool waitForPrebuffer = false;
static volatile bool clipActive = false;
static portMUX_TYPE bufferMux = portMUX_INITIALIZER_UNLOCKED;

static uint32_t samplesAvailable() {
    uint32_t w, r;
    portENTER_CRITICAL(&bufferMux);
    w = writePos;
    r = readPos;
    portEXIT_CRITICAL(&bufferMux);
    return (w >= r) ? (w - r) : (BUFFER_SIZE - r + w);
}

static void pushSample(int16_t sample) {
    portENTER_CRITICAL(&bufferMux);
    uint32_t next = (writePos + 1) % BUFFER_SIZE;
    if (next == readPos) readPos = (readPos + 1) % BUFFER_SIZE;
    audioBuffer[writePos] = sample;
    writePos = next;
    portEXIT_CRITICAL(&bufferMux);
}

static bool popSample(int16_t &sample) {
    bool ok = false;
    portENTER_CRITICAL(&bufferMux);
    if (readPos != writePos) {
        sample = audioBuffer[readPos];
        readPos = (readPos + 1) % BUFFER_SIZE;
        ok = true;
    }
    portEXIT_CRITICAL(&bufferMux);
    return ok;
}

static void resetBuffer() {
    portENTER_CRITICAL(&bufferMux);
    readPos = 0;
    writePos = 0;
    portEXIT_CRITICAL(&bufferMux);
}

// Test tone is synthesised directly inside the A2DP callback.
static volatile int32_t toneRemaining = 0;
static uint32_t tonePhase = 0;

void AudioSpeaker::queueStartupBeep() {
    Serial.println("[BT] Starting 1 kHz test tone (500 ms)...");
    toneRemaining = (BT_AUDIO_RATE * 500) / 1000;
}

// Shared volatile state - written by callback (Core 0), read by loop() (Core 1)
static volatile uint32_t btUnderruns = 0;
static volatile bool btPrebufferReady = false;

static inline void writeDither(Frame *frames, int32_t frame_count) {
    for (int i = 0; i < frame_count; i++) {
        int16_t d = (int16_t)((esp_random() & 0x7F) - 64);
        frames[i].channel1 = d;
        frames[i].channel2 = d;
    }
}

int32_t AudioSpeaker::a2dpDataCallback(Frame *frames, int32_t frame_count) {
    // NO Serial calls here (BT task runs on Core 0).
    if (toneRemaining > 0) {
        for (int i = 0; i < frame_count; i++) {
            int16_t v = 0;
            if (toneRemaining > 0) {
                v = (int16_t)(12000.0f * sinf(2.0f * PI * (float)(tonePhase % 44) / 44.1f));
                tonePhase++;
                toneRemaining--;
            }
            frames[i].channel1 = v;
            frames[i].channel2 = v;
        }
        return frame_count;
    }

    // Re-enter pre-buffering after any underrun so a gap is a clean pause, not stutter.
    if (clipActive && !waitForPrebuffer && samplesAvailable() == 0) {
        waitForPrebuffer = true;
    }
    if (waitForPrebuffer) {
        if (samplesAvailable() >= PREBUFFER_MIN) {
            waitForPrebuffer = false;
            btPrebufferReady = true;
        } else {
            if (clipActive) btUnderruns += frame_count;
            writeDither(frames, frame_count);  // keeps the A2DP session alive
            return frame_count;
        }
    }

    // 22.05 kHz mono -> 44.1 kHz: even output frames pull a new source sample and output
    // the midpoint with the previous one; odd frames output the current sample.
    static int16_t upPrev = 0, upCur = 0;
    static bool upPhase = false;
    for (int i = 0; i < frame_count; i++) {
        int16_t sample = 0;
        bool have = true;
        if (!upPhase) {
            int16_t n;
            have = popSample(n);
            if (have) {
                upPrev = upCur;
                upCur = n;
                sample = (int16_t)(((int32_t)upPrev + upCur) / 2);
                upPhase = true;
            }
        } else {
            sample = upCur;
            upPhase = false;
        }
        if (have) {
            frames[i].channel1 = sample;
            frames[i].channel2 = sample;
        } else {
            int16_t d = (int16_t)((esp_random() & 0x7F) - 64);
            frames[i].channel1 = d;
            frames[i].channel2 = d;
        }
    }
    return frame_count;
}

void AudioSpeaker::btConnectionStateCallback(esp_a2d_connection_state_t state, void *ptr) {
    if (state == ESP_A2D_CONNECTION_STATE_CONNECTED) {
        Serial.println("\n[BT] >>> CONNECTED TO STONE 190! <<<");
        btConnected = true;
    } else if (state == ESP_A2D_CONNECTION_STATE_DISCONNECTED) {
        Serial.println("[BT] Bluetooth speaker disconnected.");
        btConnected = false;
        btAudioStarted = false;
        volState = 0;
    }
}

void AudioSpeaker::btAudioStateCallback(esp_a2d_audio_state_t state, void *ptr) {
    if (state == ESP_A2D_AUDIO_STATE_STARTED) {
        btAudioStarted = true;
        Serial.println("\n[BT] >>> BLUETOOTH AUDIO STARTED <<<");
    } else if (state == ESP_A2D_AUDIO_STATE_STOPPED) {
        btAudioStarted = false;
        Serial.println("[BT] !!! AUDIO SUSPENDED by Stone 190 !!!");
    }
}

AudioSpeaker::AudioSpeaker() {}

void AudioSpeaker::begin() {
    Serial.println("[BT] Initializing Bluetooth A2DP Source for Stone 190...");
    resetBuffer();

    a2dp_source.set_on_connection_state_changed(btConnectionStateCallback);
    a2dp_source.set_on_audio_state_changed(btAudioStateCallback);

    Serial.printf("[BT] Starting A2DP source targeting: \"%s\"...\n", BT_SPEAKER_NAME);
    a2dp_source.start(BT_SPEAKER_NAME, a2dpDataCallback);
}

void AudioSpeaker::loop() {
    static unsigned long volTimer = 0;

    // Volume is set only after AUDIO: Started (setting it earlier is unreliable).
    if (btAudioStarted && volState == 0) {
        volState = 1;
        volTimer = millis();
        a2dp_source.set_volume(50);
        Serial.println("[BT] Ramping volume: 50...");
    } else if (volState == 1 && (millis() - volTimer >= 1500)) {
        volState = 2;
        a2dp_source.set_volume(DEFAULT_BT_VOLUME);
        Serial.printf("[BT] Operating volume set: %d/127\n", DEFAULT_BT_VOLUME);
        queueStartupBeep();
    }

    if (btPrebufferReady) {
        btPrebufferReady = false;
        Serial.println("[BT] Pre-buffer ready - playback started.");
    }
}

void AudioSpeaker::clipBegin() {
    a2dp_source.set_volume(DEFAULT_BT_VOLUME);
    resetBuffer();
    btUnderruns = 0;
    waitForPrebuffer = true;
    clipActive = true;
}

size_t AudioSpeaker::freeSamples() {
    return BUFFER_SIZE - 1 - samplesAvailable();
}

void AudioSpeaker::pushSamples(const int16_t* samples, size_t n) {
    for (size_t i = 0; i < n; i++) pushSample(samples[i]);
}

void AudioSpeaker::clipEnd() {
    waitForPrebuffer = false;  // let a short tail play even if below PREBUFFER_MIN
    clipActive = false;
    Serial.printf("[BT] Clip fully buffered (underrun frames so far=%u)\n", (unsigned)btUnderruns);
}

void AudioSpeaker::stop() {
    clipActive = false;
    waitForPrebuffer = false;
    resetBuffer();
}

bool AudioSpeaker::isConnected() {
    return btConnected || a2dp_source.is_connected();
}

bool AudioSpeaker::isAudioStarted() {
    return btAudioStarted;
}

bool AudioSpeaker::isPlaying() {
    return clipActive || (samplesAvailable() > 0);
}

String AudioSpeaker::getStatusString() {
    return isConnected() ? "BT: Connected" : "BT: Connecting...";
}

AudioSpeaker speaker;
