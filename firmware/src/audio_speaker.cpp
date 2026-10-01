#include "audio_speaker.h"
#include "config.h"
#include <HTTPClient.h>
#include <vector>
#include "esp_coexist.h"

// --- Global Bluetooth A2DP Source Instance ---
static BluetoothA2DPSource a2dp_source;
static volatile bool btConnected = false;
static volatile bool isStreaming = false;

// --- Thread-Safe PCM Audio Ring Buffer ---
// 32 KB = ~180ms at 44.1kHz stereo 16-bit. Fits within DRAM0 limits (was 16KB before).
// MUST be static (not heap) so it is valid before a2dpDataCallback fires during BT init.
static const size_t RING_BUFFER_SIZE = 32 * 1024;
static uint8_t ringBuf[RING_BUFFER_SIZE];
static volatile size_t rbHead = 0;
static volatile size_t rbTail = 0;
static portMUX_TYPE rbMux = portMUX_INITIALIZER_UNLOCKED;

static size_t rbAvailable() {
    portENTER_CRITICAL(&rbMux);
    size_t head = rbHead;
    size_t tail = rbTail;
    portEXIT_CRITICAL(&rbMux);
    if (head >= tail) return head - tail;
    return RING_BUFFER_SIZE - (tail - head);
}

static size_t rbFree() {
    return RING_BUFFER_SIZE - 1 - rbAvailable();
}

static size_t rbWrite(const uint8_t* data, size_t len) {
    size_t written = 0;
    portENTER_CRITICAL(&rbMux);
    while (written < len) {
        size_t nextHead = (rbHead + 1) % RING_BUFFER_SIZE;
        if (nextHead == rbTail) break; // Buffer full
        ringBuf[rbHead] = data[written++];
        rbHead = nextHead;
    }
    portEXIT_CRITICAL(&rbMux);
    return written;
}

static size_t rbRead(uint8_t* out, size_t len) {
    size_t readCount = 0;
    portENTER_CRITICAL(&rbMux);
    while (readCount < len && rbTail != rbHead) {
        out[readCount++] = ringBuf[rbTail];
        rbTail = (rbTail + 1) % RING_BUFFER_SIZE;
    }
    portEXIT_CRITICAL(&rbMux);
    return readCount;
}

static void rbReset() {
    portENTER_CRITICAL(&rbMux);
    rbHead = 0;
    rbTail = 0;
    portEXIT_CRITICAL(&rbMux);
}

// --- Asynchronous HTTP Streaming Task ---
static String currentPlayUrl = "";
static TaskHandle_t streamTaskHandle = NULL;

static void httpStreamTask(void* param) {
    while (true) {
        ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
        if (currentPlayUrl.length() == 0) continue;

        Serial.printf("[BT Stream] Opening audio stream: %s\n", currentPlayUrl.c_str());

        // Wait if Bluetooth speaker is not yet ready (up to 5 seconds)
        int btWait = 0;
        while (!speaker.isConnected() && btWait < 50) {
            vTaskDelay(pdMS_TO_TICKS(100));
            btWait++;
        }

        if (!speaker.isConnected()) {
            Serial.println("[BT Stream] Warning: Speaker not connected yet. Stream may be silent.");
        } else {
            Serial.println("[BT Stream] Stone 190 is CONNECTED. Starting HTTP stream...");
        }

        HTTPClient http;
        http.begin(currentPlayUrl);
        http.setTimeout(15000);
        int httpCode = http.GET();

        if (httpCode == 200) {
            WiFiClient* stream = http.getStreamPtr();
            int totalBytes = http.getSize();
            Serial.printf("[BT Stream] Audio file size: %d bytes.\n", totalBytes);

            // Parse WAV header to find 'data' chunk dynamically
            // (miniaudio may write headers > 44 bytes with LIST/INFO chunks)
            {
                uint8_t hdr[12];
                stream->readBytes(hdr, 12); // Read RIFF header
                totalBytes -= 12;
                // Scan sub-chunks until 'data' is found (max 512 bytes of header)
                uint8_t chunk_id[4];
                uint8_t chunk_sz[4];
                int scanned = 0;
                while (scanned < 512) {
                    if (stream->readBytes(chunk_id, 4) < 4) break;
                    if (stream->readBytes(chunk_sz, 4) < 4) break;
                    totalBytes -= 8;
                    scanned += 8;
                    uint32_t csize = (uint32_t)chunk_sz[0] | ((uint32_t)chunk_sz[1] << 8)
                                   | ((uint32_t)chunk_sz[2] << 16) | ((uint32_t)chunk_sz[3] << 24);
                    if (memcmp(chunk_id, "data", 4) == 0) {
                        Serial.printf("[BT Stream] WAV 'data' chunk found, %u bytes of PCM.\n", csize);
                        totalBytes = (int)csize; // override with exact PCM size
                        break;
                    }
                    // Skip this non-data chunk
                    size_t skip = csize;
                    while (skip > 0) {
                        uint8_t junk[64];
                        size_t s = (skip < sizeof(junk)) ? skip : sizeof(junk);
                        stream->readBytes(junk, s);
                        skip -= s;
                        totalBytes -= s;
                        scanned += s;
                    }
                }
            }

            // Signal coexistence manager that active A2DP audio playback is underway
            esp_coex_status_bit_set(ESP_COEX_ST_TYPE_BT, ESP_COEX_BT_ST_A2DP_STREAMING);

            isStreaming = true;
            size_t totalBytesDownloaded = 0;
            unsigned long lastDataTime = millis();
            static uint8_t chunk[512];

            while (isStreaming && (totalBytes <= 0 || totalBytesDownloaded < (size_t)totalBytes)) {
                int avail = stream->available();
                if (avail > 0) {
                    lastDataTime = millis();
                    size_t toRead = (avail < (int)sizeof(chunk)) ? avail : sizeof(chunk);
                    
                    // If ring buffer is nearly full, yield to speaker draining
                    int waitLoops = 0;
                    while (rbFree() < toRead && isStreaming && waitLoops < 300) {
                        vTaskDelay(pdMS_TO_TICKS(10));
                        waitLoops++;
                    }
                    if (!isStreaming) break;

                    size_t bytesRead = stream->readBytes(chunk, toRead);
                    if (bytesRead > 0) {
                        rbWrite(chunk, bytesRead);
                        totalBytesDownloaded += bytesRead;
                    }

                    // CRITICAL COEXISTENCE PACING:
                    // Yield 2ms to FreeRTOS scheduler so the Classic Bluetooth A2DP
                    // stack gets guaranteed RF radio slots to transmit packets to Stone 190
                    vTaskDelay(pdMS_TO_TICKS(2));
                } else {
                    if (!http.connected() && stream->available() == 0) {
                        Serial.println("[BT Stream] Server finished stream.");
                        break;
                    }
                    // Wait for next TCP packets (timeout after 5s idle)
                    vTaskDelay(pdMS_TO_TICKS(15));
                    if (millis() - lastDataTime > 5000) {
                        Serial.println("[BT Stream] Network read timeout.");
                        break;
                    }
                }
            }
            Serial.printf("[BT Stream] Download finished: %d of %d bytes. Draining to speaker...\n",
                          totalBytesDownloaded, totalBytes);
        } else {
            Serial.printf("[BT Stream] HTTP GET failed: %d\n", httpCode);
        }
        http.end();

        // Allow ring buffer to finish playing through the Bluetooth speaker
        unsigned long drainStart = millis();
        while (rbAvailable() > 0 && isStreaming && (millis() - drainStart < 25000)) {
            vTaskDelay(pdMS_TO_TICKS(50));
        }
        isStreaming = false;
        esp_coex_status_bit_clear(ESP_COEX_ST_TYPE_BT, ESP_COEX_BT_ST_A2DP_STREAMING);
        Serial.println("[BT Stream] Audio playback complete.");
    }
}

// --- Bluetooth A2DP Callbacks ---
int32_t AudioSpeaker::a2dpDataCallback(Frame *frame, int32_t frame_count) {
    size_t bytesNeeded = frame_count * sizeof(Frame); // 4 bytes per stereo 16-bit frame
    size_t bytesRead = rbRead((uint8_t*)frame, bytesNeeded);

    if (bytesRead < bytesNeeded) {
        // Fill remaining with silence (0) to maintain BT connection
        memset(((uint8_t*)frame) + bytesRead, 0, bytesNeeded - bytesRead);
    }
    // Return actual frames supplied (not always frame_count) so the BT stack
    // knows how much real audio is available and doesn't flood with silent frames
    int32_t framesSupplied = (int32_t)(bytesRead / sizeof(Frame));
    return (framesSupplied > 0) ? framesSupplied : frame_count;
}

bool AudioSpeaker::btSsidCallback(const char* ssid, esp_bd_addr_t address, int rssi) {
    if (!ssid || strlen(ssid) == 0) return false;
    Serial.printf("[BT Scan] Found device: '%s' (RSSI: %d)\n", ssid, rssi);
    String s = String(ssid);
    s.toLowerCase();
    if (s.indexOf("stone") >= 0 || s.indexOf("190") >= 0 || s.indexOf("boat") >= 0 || s.indexOf("board") >= 0) {
        Serial.printf("[BT Scan] >>> MATCH FOUND! Connecting to: %s <<<\n", ssid);
        return true;
    }
    return false;
}

void AudioSpeaker::btConnectionStateCallback(esp_a2d_connection_state_t state, void *ptr) {
    static esp_a2d_connection_state_t last_state = (esp_a2d_connection_state_t)-1;
    if (state == last_state) return; // Prevent duplicate log floods
    last_state = state;

    if (state == ESP_A2D_CONNECTION_STATE_CONNECTED) {
        Serial.println("\n==============================================");
        Serial.println("[BT] >>> CONNECTED TO STONE 190 SPEAKER! <<<");
        Serial.println("==============================================\n");
        btConnected = true;
    } else if (state == ESP_A2D_CONNECTION_STATE_DISCONNECTED) {
        Serial.println("[BT] Bluetooth speaker disconnected.");
        btConnected = false;
    } else if (state == ESP_A2D_CONNECTION_STATE_CONNECTING) {
        Serial.println("[BT] Connecting to Stone 190 speaker...");
    }
}

// --- AudioSpeaker Implementation ---
AudioSpeaker::AudioSpeaker() {}

void AudioSpeaker::begin() {
    Serial.println("[BT] Initializing ESP32 Inbuilt Bluetooth A2DP Source...");
    rbReset();

    a2dp_source.set_ssp_enabled(true);
    
    // Direct auto-reconnect to Stone 190 MAC address
    esp_bd_addr_t stone_mac = BT_SPEAKER_MAC;
    a2dp_source.set_auto_reconnect(stone_mac, 10);
    
    // Accept all audio device classes during inquiry scan
    a2dp_source.set_valid_cod_service(0xFFFF);
    a2dp_source.set_ssid_callback(btSsidCallback);
    a2dp_source.set_on_connection_state_changed(btConnectionStateCallback);

    std::vector<const char*> target_names = {
        "Stone 190",
        "boAt Stone 190",
        "boat stone 190",
        "Boat Stone 190",
        "boAt Stone",
        "Board Stone 190"
    };

    a2dp_source.start(target_names, a2dpDataCallback);
    a2dp_source.set_volume(127);
    Serial.println("[BT] Target configured: Stone 190 (4A:D4:20:0E:94:A8)");

    // Spawn async background streaming task on Core 0
    // Priority 5: High enough to keep ring buffer filled ahead of BT callback drain
    // Stack 8KB: HTTPClient needs more headroom for TLS/chunked transfer
    xTaskCreatePinnedToCore(
        httpStreamTask,
        "BT_AudioStream",
        8192,
        NULL,
        5, // Priority 5 (must outrun BT callback that drains ring buffer)
        &streamTaskHandle,
        0  // Pin to Core 0 (leaving Core 1 for Arduino loop & OLED)
    );
}

void AudioSpeaker::loop() {
    // Bluetooth stack & FreeRTOS task handle streaming automatically
}

void AudioSpeaker::playUrl(const char* url) {
    if (!url || strlen(url) == 0) return;
    // Signal any running stream to stop, then reset buffer
    isStreaming = false;
    // Small delay to allow the streaming loop to notice the stop flag
    vTaskDelay(pdMS_TO_TICKS(50));
    rbReset();
    currentPlayUrl = String(url);
    if (streamTaskHandle) {
        xTaskNotifyGive(streamTaskHandle);
    }
}

void AudioSpeaker::stop() {
    isStreaming = false;
    rbReset();
}

bool AudioSpeaker::isConnected() {
    return btConnected || a2dp_source.is_connected();
}

bool AudioSpeaker::isPlaying() {
    return isStreaming || (rbAvailable() > 0);
}

String AudioSpeaker::getStatusString() {
    if (isConnected()) {
        return "BT: Connected";
    }
    return "BT: Pairing...";
}

AudioSpeaker speaker;
