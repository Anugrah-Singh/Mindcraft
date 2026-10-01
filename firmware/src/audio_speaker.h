#pragma once

#include <Arduino.h>
#include "BluetoothA2DPSource.h"

class AudioSpeaker {
public:
    AudioSpeaker();
    void begin();
    void loop();
    void playUrl(const char* url);
    void stop();
    bool isConnected();
    bool isPlaying();
    String getStatusString();

private:
    static int32_t a2dpDataCallback(Frame *frame, int32_t frame_count);
    static bool btSsidCallback(const char* ssid, esp_bd_addr_t address, int rssi);
    static void btConnectionStateCallback(esp_a2d_connection_state_t state, void *ptr);
};

extern AudioSpeaker speaker;
