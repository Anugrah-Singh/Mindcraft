# Mindcraft: Smart Voice & Productivity Assistant

Mindcraft is an ambient AI assistant combining an **ESP32 microcontroller**, **monochrome OLED display**, **I2S Microphone (INMP441)**, and **I2S Amplifier (MAX98357A)** with a high-speed **Laptop Companion Hub** powered by the **Google Gemini API**.

---

## 🚀 Features

* **Voice Notes App**: Fast capture of spontaneous thoughts, memos, and ideas.
* **Prioritized Tasks App**: Natural language task capture automatically ranked as High, Medium, or Low priority.
* **Habit Streaks Tracker**: Daily streak counters (Gym 🔥, reading, hydration) updated by voice.
* **Conversational AI**: High-speed conversational responses via Gemini 2.5 Flash with synthesized audio streaming through the speaker.
* **Laptop Virtual Controller**: Web dashboard providing virtual buttons (Up, Down, Select, Back, Push-to-Talk) and real-time OLED screen mirroring.

---

## 🔌 Hardware Connections (Breadboard)

| Peripheral | Peripheral Pin | Default ESP32 Pin | Description |
| :--- | :--- | :--- | :--- |
| **OLED (SSD1306)** | `SDA` | **GPIO 21** | I2C Data |
| | `SCL` | **GPIO 22** | I2C Clock |
| | `VCC` | **3V3** | Power (3.3V) |
| | `GND` | **GND** | Ground |
| **Mic (INMP441)** | `SCK` (BCLK) | **GPIO 14** | Serial Clock |
| | `WS` (LRCK) | **GPIO 15** | Word Select |
| | `SD` (DOUT) | **GPIO 32** | Serial Data |
| | `L/R` | **GND** | Left channel select |
| | `VDD` | **3V3** | Power (3.3V) |
| | `GND` | **GND** | Ground |
| **Amp (MAX98357A)** | `BCLK` | **GPIO 26** | Bit Clock |
| | `LRC` | **GPIO 25** | Left/Right Clock |
| | `DIN` | **GPIO 27** | Data Input |
| | `VIN` | **5V / VIN** | Power (5V recommended) |
| | `GND` | **GND** | Ground |

*(Pins can be customized in [`firmware/src/config.h`](file:///C:/Users/poppi/OneDrive/Desktop/wincode/Mindcraft/firmware/src/config.h))*

---

## 💻 Running the Companion Server

1. **Set your Google Gemini API Key**:
   Create a `.env` file in the `companion/` folder:
   ```env
   GEMINI_API_KEY=your_gemini_api_key_here
   ```

2. **Start the Hub**:
   ```powershell
   companion\.venv\Scripts\python.exe companion\app.py
   ```

3. Open `http://localhost:8000` in your browser to access the **Virtual Hardware Controller** and dashboard.
