#pragma once

#include <Arduino.h>

// ==========================================
// 1. Laptop link: USB serial only (no Wi-Fi)
// ==========================================
// Wi-Fi and Bluetooth share one radio on the ESP32. Wi-Fi traffic starved the A2DP
// stream and made speech choppy, so Wi-Fi is never started. The laptop runs
// companion/serial_bridge.py, which relays the Companion Hub over this USB port.
#define HOST_BAUD       921600

// ==========================================
// 2. Hardware Pin Definitions (Verified)
// ==========================================

// --- I2C Monochrome OLED Display (SSD1306 128x64) ---
#define OLED_SDA_PIN    21
#define OLED_SCL_PIN    22
#define OLED_RESET_PIN  U8X8_PIN_NONE

// --- I2S Microphone (INMP441) ---
// Note: INMP441 L/R pin connected to GND for Left Channel
#define I2S_MIC_SCK_PIN 26  // Serial Clock (BCLK)
#define I2S_MIC_WS_PIN  25  // Word Select (LRCK)
#define I2S_MIC_SD_PIN  32  // Serial Data (DIN)

// --- Buttons (optional): each between the GPIO and GND, internal pull-ups are used ---
// Avoid GPIO 12 (boot strapping pin). Unconnected buttons simply never fire.
#define BTN_UP_PIN      27
#define BTN_DOWN_PIN    14
#define BTN_SELECT_PIN  13
#define BTN_BACK_PIN    4

// --- Bluetooth Audio Speaker (boAt Stone 190) ---
#define BT_SPEAKER_NAME "Stone 190"
#define BT_AUDIO_RATE   44100
#define BT_AUDIO_CH     2
#define DEFAULT_BT_VOLUME 110
#define MAX_BT_VOLUME     110

// ==========================================
// 3. Audio & Recording Settings
// ==========================================
#define SAMPLE_RATE     44100   // I2S capture rate
#define MIC_OUT_RATE    22050   // rate of audio sent to the laptop (SAMPLE_RATE / 2)
#define RECORD_SECONDS  3
