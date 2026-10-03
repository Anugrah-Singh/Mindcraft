#pragma once

#include <Arduino.h>
#include <ArduinoJson.h>
#include <U8g2lib.h>
#include <vector>

// 128x64 SSD1306 UI. The hub sends structured screens ("view": menu / tasks / habits / notes /
// ai / status); the same layouts are drawn by the dashboard's OLED mirror.
class MindcraftDisplay {
public:
    MindcraftDisplay();
    void begin();

    // Structured screen from the hub (falls back to the legacy text layout without "view").
    void showScreen(JsonObjectConst screen);
    void updateScreen(const String& title, const std::vector<String>& lines,
                      const String& footer_left, const String& footer_right);

    void showWaiting();              // wordmark + link status, shown until the hub sends a screen
    void showProcessing();

    // Voice capture: base screen once, then cheap partial updates of the meter.
    void beginRecording();
    void recordLevel(uint16_t level, bool speaking, uint32_t elapsedMs);

    void setBtConnected(bool connected);
    void setHubLinked(bool linked);
    void tick();                     // call every loop: animates the status screens
    bool hasScreen() const { return haveScreen; }

    // Live mirror: when on, every redraw sends the raw 128x64 frame to the laptop ("@F<hex>").
    void setMirror(bool on) { mirror = on; }
    void dumpFrame();

private:
    U8G2_SSD1306_128X64_NONAME_F_HW_I2C u8g2;

    JsonDocument lastDoc;
    bool haveScreen = false;
    bool btUp = false;
    bool hubUp = false;
    bool recording = false;
    bool mirror = false;
    bool framePending = false;
    unsigned long lastFrame = 0;
    unsigned long lastAnim = 0;
    uint8_t animFrame = 0;

    void redraw();
    void drawHeader(const char* title, const char* counter);
    void drawFooter(const char* left, const char* right);
    void drawScrollbar(int pos, int posMax, int total, int visible);
    void drawBits(int x, int y, const uint16_t* rows, int w, int h, int scale = 1);
    void drawFlame(int x, int y);
    void drawMenu(JsonObjectConst s);
    void drawList(JsonObjectConst s);
    void drawAi(JsonObjectConst s);
    void drawStatus(JsonObjectConst s);
    void drawRecordingBody(uint16_t level, bool speaking, uint32_t elapsedMs, bool full);
    void drawLegacy(JsonObjectConst s);
    void drawWaiting();
};

extern MindcraftDisplay display;
