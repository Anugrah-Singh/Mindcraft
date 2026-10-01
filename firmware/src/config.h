#pragma once

#include <Arduino.h>

// ==========================================
// 1. Wi-Fi & Laptop Companion Configuration
// ==========================================
#define WIFI_SSID       "Dafuq"
#define WIFI_PASSWORD   "00000000"

// IP address of your laptop running the Mindcraft Companion server
#define COMPANION_HOST  "10.133.55.219" 
#define COMPANION_PORT  8000
#define WS_PATH         "/ws/esp32"

// ==========================================
// 2. Hardware Pin Definitions (Breadboard)
// ==========================================

// --- I2C Monochrome OLED Display (SSD1306 128x64) ---
#define OLED_SDA_PIN    21
#define OLED_SCL_PIN    22
#define OLED_RESET_PIN  U8X8_PIN_NONE

// --- I2S Microphone (INMP441) ---
// Note: INMP441 L/R pin must be connected to GND for Left Channel
#define I2S_MIC_SCK_PIN 26  // Serial Clock (BCLK)
#define I2S_MIC_WS_PIN  25  // Word Select (LRCK)
#define I2S_MIC_SD_PIN  32  // Serial Data (DIN from mic)

// --- Bluetooth Audio Speaker (boAt Stone 190) ---
#define BT_SPEAKER_NAME "Stone 190"
#define BT_SPEAKER_MAC  {0x4a, 0xd4, 0x20, 0x0e, 0x94, 0xa8}
#define BT_AUDIO_RATE   44100
#define BT_AUDIO_CH     2

// ==========================================
// 3. Audio & Recording Settings
// ==========================================
#define SAMPLE_RATE     16000
#define BITS_PER_SAMPLE 16
#define RECORD_SECONDS  4
#define AUDIO_BUF_SIZE  (SAMPLE_RATE * (BITS_PER_SAMPLE / 8) * RECORD_SECONDS)
