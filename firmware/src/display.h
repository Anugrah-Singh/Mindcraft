#pragma once

#include <Arduino.h>
#include <U8g2lib.h>
#include <vector>

class MindcraftDisplay {
public:
    MindcraftDisplay();
    void begin();
    void showBootScreen();
    void showConnecting(const char* ssid);
    void showConnected(const char* ip);
    void updateScreen(const String& title, const std::vector<String>& lines, const String& footer_left, const String& footer_right);
    void showRecording();
    void showProcessing();

private:
    U8G2_SSD1306_128X64_NONAME_F_HW_I2C u8g2;
};

extern MindcraftDisplay display;
