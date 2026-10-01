#include <Arduino.h>
#include <WiFi.h>
#include <esp_wifi.h>
#include <esp_coexist.h>
#include <HTTPClient.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>

#include "config.h"
#include "display.h"
#include "audio_mic.h"
#include "audio_speaker.h"

WebSocketsClient webSocket;
bool isConnectedToHub = false;
volatile bool startRecordingRequested = false;

void sendAudioToCompanion(uint8_t* wavBuffer, size_t wavSize) {
    if (WiFi.status() != WL_CONNECTED) {
        display.updateScreen("ERROR", {"Wi-Fi Disconnected"}, "BACK: Menu", "");
        return;
    }

    display.showProcessing();
    HTTPClient http;
    String url = String("http://") + COMPANION_HOST + ":" + COMPANION_PORT + "/api/process_audio";
    
    http.begin(url);
    http.addHeader("Content-Type", "audio/wav");
    http.setTimeout(15000);
    
    int httpResponseCode = http.POST(wavBuffer, wavSize);
    Serial.printf("[HTTP] POST Result: %d\n", httpResponseCode);
    if (httpResponseCode > 0) {
        String response = http.getString();
        Serial.printf("[HTTP] Response: %s\n", response.c_str());
    } else {
        Serial.printf("[HTTP] Failed: %s\n", http.errorToString(httpResponseCode).c_str());
        display.updateScreen("MINDCRAFT", {"Upload Error", "Returning..."}, "BACK: Menu", "");
        delay(1500);
        webSocket.sendTXT("{\"type\":\"button\",\"button\":\"\"}");
    }
    http.end();
}

void triggerVoiceCapture() {
    display.showRecording();
    Serial.println("[AUDIO] Recording starting...");
    
    size_t wavSize = 0;
    uint8_t* wavData = mic.recordWav(RECORD_SECONDS, wavSize);
    
    if (wavData && wavSize > 44) {
        Serial.printf("[AUDIO] Recorded %d bytes. Uploading to Hub...\n", wavSize);
        sendAudioToCompanion(wavData, wavSize);
    } else {
        Serial.println("[AUDIO] Recording failed or empty!");
        display.updateScreen("MINDCRAFT", {"No audio captured", "Returning..."}, "BACK: Menu", "");
        delay(1500);
        webSocket.sendTXT("{\"type\":\"button\",\"button\":\"\"}");
    }
}

void webSocketEvent(WStype_t type, uint8_t * payload, size_t length) {
    switch (type) {
        case WStype_DISCONNECTED:
            Serial.println("[WS] Disconnected from Companion Hub");
            isConnectedToHub = false;
            break;
            
        case WStype_CONNECTED:
            Serial.println("[WS] Connected to Companion Hub!");
            isConnectedToHub = true;
            break;
            
        case WStype_TEXT: {
            Serial.printf("[WS] Received: %s\n", payload);
            JsonDocument doc;
            DeserializationError error = deserializeJson(doc, payload);
            if (error) {
                Serial.printf("[JSON] Deserialization failed: %s\n", error.c_str());
                return;
            }

            const char* msgType = doc["type"];
            if (msgType && strcmp(msgType, "screen_update") == 0) {
                JsonObject screen = doc["screen"];
                String title = screen["title"] | "MINDCRAFT";
                String footer_l = screen["footer_left"] | "";
                String footer_r = screen["footer_right"] | "";
                
                std::vector<String> lines;
                JsonArray arr = screen["lines"];
                for (JsonVariant v : arr) {
                    lines.push_back(v.as<String>());
                }
                
                display.updateScreen(title, lines, footer_l, footer_r);
            }
            else if (msgType && strcmp(msgType, "play_audio") == 0) {
                const char* path = doc["url"];
                if (path) {
                    String fullAudioUrl = String("http://") + COMPANION_HOST + ":" + COMPANION_PORT + path;
                    Serial.printf("[AUDIO] Streaming: %s\n", fullAudioUrl.c_str());
                    speaker.playUrl(fullAudioUrl.c_str());
                }
            }
            else if (msgType && strcmp(msgType, "record_trigger") == 0) {
                startRecordingRequested = true;
            }
            break;
        }
        
        default:
            break;
    }
}

void setup() {
    Serial.begin(115200);
    delay(400);
    Serial.println("\n--- Mindcraft Booting (Bluetooth Audio Mode) ---");

    // 1. Initialize Display
    display.begin();
    display.showConnecting(WIFI_SSID);

    // 2. Connect Wi-Fi with Modem Sleep for WiFi + Bluetooth Coexistence
    WiFi.disconnect(true);
    delay(200);
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    // Enable WPA3 SAE Hash-to-Element (H2E) and PMF for modern WPA3-Personal phone hotspots
    wifi_config_t sta_conf;
    if (esp_wifi_get_config(WIFI_IF_STA, &sta_conf) == ESP_OK) {
        sta_conf.sta.pmf_cfg.capable = true;
        sta_conf.sta.pmf_cfg.required = false;
        sta_conf.sta.sae_pwe_h2e = WPA3_SAE_PWE_BOTH;
        sta_conf.sta.threshold.authmode = WIFI_AUTH_OPEN;
        esp_wifi_set_config(WIFI_IF_STA, &sta_conf);
        esp_wifi_connect();
    }
    esp_wifi_set_ps(WIFI_PS_MIN_MODEM); // CRITICAL: Required for Wi-Fi + Bluetooth coexistence
    esp_coex_preference_set(ESP_COEX_PREFER_BT); // Prioritize Bluetooth ACL slots to prevent disconnects

    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 30) {
        delay(300);
        Serial.print(".");
        attempts++;
    }

    if (WiFi.status() == WL_CONNECTED) {
        Serial.println("\n[WiFi] Connected! IP: " + WiFi.localIP().toString());
        display.showConnected(WiFi.localIP().toString().c_str());
    } else {
        Serial.printf("\n[WiFi] Connection delayed (status: %d). Retrying in bg...\n", WiFi.status());
        display.updateScreen("WIFI SEARCH", {"Searching 2.4GHz...", "Need 2.4GHz band", "Enable Compatibility"}, "", "");
    }

    // 3. Initialize Inbuilt Bluetooth A2DP Source
    speaker.begin();

    // 4. Connect to Companion WebSocket
    webSocket.begin(COMPANION_HOST, COMPANION_PORT, WS_PATH);
    webSocket.onEvent(webSocketEvent);
    webSocket.setReconnectInterval(2000);
}

void loop() {
    webSocket.loop();
    speaker.loop();

    static bool wasConnected = false;
    bool isWifiConnected = (WiFi.status() == WL_CONNECTED);
    if (isWifiConnected && !wasConnected) {
        wasConnected = true;
        Serial.println("\n[WiFi] Connected! IP: " + WiFi.localIP().toString());
        display.showConnected(WiFi.localIP().toString().c_str());
    } else if (!isWifiConnected && wasConnected) {
        wasConnected = false;
        Serial.println("[WiFi] Lost connection.");
    }

    if (startRecordingRequested) {
        startRecordingRequested = false;
        triggerVoiceCapture();
    }

    static unsigned long lastWifiCheck = 0;
    if (millis() - lastWifiCheck > 8000) {
        lastWifiCheck = millis();
        if (WiFi.status() != WL_CONNECTED) {
            Serial.println("[WiFi] Reconnecting...");
            WiFi.reconnect();
        }
    }
}
