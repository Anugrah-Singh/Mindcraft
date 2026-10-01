#include "display.h"
#include "config.h"

MindcraftDisplay::MindcraftDisplay() 
    : u8g2(U8G2_R0, OLED_RESET_PIN, OLED_SCL_PIN, OLED_SDA_PIN) {}

void MindcraftDisplay::begin() {
    u8g2.begin();
    u8g2.enableUTF8Print();
    showBootScreen();
}

void MindcraftDisplay::showBootScreen() {
    u8g2.clearBuffer();
    u8g2.setFont(u8g2_font_helvB10_tr);
    u8g2.drawStr(24, 25, "MINDCRAFT");
    u8g2.setFont(u8g2_font_6x10_tr);
    u8g2.drawStr(18, 42, "AI Voice Assistant");
    u8g2.drawHLine(10, 50, 108);
    u8g2.sendBuffer();
}

void MindcraftDisplay::showConnecting(const char* ssid) {
    u8g2.clearBuffer();
    u8g2.setFont(u8g2_font_6x10_tr);
    u8g2.drawStr(10, 20, "Connecting Wi-Fi...");
    u8g2.drawStr(10, 36, ssid);
    u8g2.drawHLine(10, 48, 108);
    u8g2.sendBuffer();
}

void MindcraftDisplay::showConnected(const char* ip) {
    u8g2.clearBuffer();
    u8g2.setFont(u8g2_font_6x10_tr);
    u8g2.drawStr(10, 18, "Wi-Fi Connected!");
    u8g2.drawStr(10, 34, "IP:");
    u8g2.drawStr(32, 34, ip);
    u8g2.drawStr(10, 52, "Connecting Hub...");
    u8g2.sendBuffer();
}

void MindcraftDisplay::updateScreen(const String& title, const std::vector<String>& lines, const String& footer_left, const String& footer_right) {
    u8g2.clearBuffer();
    
    // 1. Inverted Header Bar (y: 0 to 11)
    u8g2.setDrawColor(1);
    u8g2.drawBox(0, 0, 128, 12);
    u8g2.setDrawColor(0); // Inverted black text on white header
    u8g2.setFont(u8g2_font_6x10_tf);
    u8g2.drawStr(3, 9, title.c_str());
    // Wi-Fi connectivity indicator dot
    u8g2.drawDisc(122, 5, 2);
    u8g2.setDrawColor(1); // Restore normal drawing color

    // 2. Body Content (y: 13 to 51)
    u8g2.setFont(u8g2_font_5x8_tr);
    int y = 21;
    for (size_t i = 0; i < lines.size() && i < 4; i++) {
        String line = lines[i];
        bool isSelected = false;

        // Check if line is the active selection
        if (line.startsWith(">") || line.startsWith("►") || line.startsWith("\xe2") || line.startsWith("*")) {
            isSelected = true;
            // Trim selection symbols for clean rendering
            if (line.startsWith("> ") || line.startsWith("* ")) {
                line = line.substring(2);
            } else if (line.startsWith(">")) {
                line = line.substring(1);
            }
        }

        if (isSelected) {
            // Draw sleek rounded highlight rectangle
            u8g2.setDrawColor(1);
            u8g2.drawRBox(1, y - 7, 126, 9, 1);
            u8g2.setDrawColor(0); // Inverted text inside highlight
            u8g2.drawStr(5, y, line.c_str());
            u8g2.setDrawColor(1); // Restore color
        } else {
            u8g2.setDrawColor(1);
            u8g2.drawStr(5, y, line.c_str());
        }
        y += 9; // Precise 9px line height
    }

    // 3. Footer Divider and Shortcuts (y: 52 to 63)
    u8g2.drawHLine(0, 52, 128);
    u8g2.setFont(u8g2_font_4x6_tr);
    if (footer_left.length() > 0) {
        u8g2.drawStr(2, 61, footer_left.c_str());
    }
    if (footer_right.length() > 0) {
        int width = u8g2.getStrWidth(footer_right.c_str());
        u8g2.drawStr(126 - width, 61, footer_right.c_str());
    }

    u8g2.sendBuffer();
}

void MindcraftDisplay::showRecording() {
    u8g2.clearBuffer();
    u8g2.setFont(u8g2_font_helvB08_tr);
    u8g2.drawStr(18, 25, "RECORDING...");
    u8g2.drawDisc(64, 42, 6);
    u8g2.setFont(u8g2_font_6x10_tr);
    u8g2.drawStr(22, 60, "Listening to you");
    u8g2.sendBuffer();
}

void MindcraftDisplay::showProcessing() {
    u8g2.clearBuffer();
    u8g2.setFont(u8g2_font_6x10_tr);
    u8g2.drawStr(24, 28, "PROCESSING...");
    u8g2.drawStr(16, 44, "Gemini Analyzing");
    u8g2.sendBuffer();
}

MindcraftDisplay display;
