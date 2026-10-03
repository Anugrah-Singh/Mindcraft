---
name: openclaw-skills-esp32
description: Avoid common ESP32 mistakes — GPIO conflicts, strapping pins, WiFi+ADC2 trap, deep sleep gotchas, and FreeRTOS pitfalls.
---

# ESP32 Development & Pitfalls Guide (openclaw-skills-esp32)

Avoid common ESP32 mistakes — GPIO conflicts, WiFi+ADC2 trap, deep sleep gotchas, and FreeRTOS pitfalls.

| Field      | Value                  |
| ---------- | ---------------------- |
| Identifier | `openclaw-skills-esp32`|
| Version    | 1.0.1                  |
| Author     | openclaw               |
| Category   | smart-home-iot         |

---

## Instructions & Checklist

### 1. GPIO Restrictions
- **Strapping pins boot behavior:** GPIO0, GPIO2, GPIO12, GPIO15 affect boot mode. Be careful pulling these high/low on power-up.
- **Flash Pins:** GPIO6-11 are internally connected to SPI flash — do NOT use; accessing them crashes immediately.
- **Input-Only Pins:** GPIO34-39 are input only — no output driver, no internal pullup/pulldown resistors.
- **WiFi + ADC2 Conflict Trap:** ADC2 cannot be used while WiFi is active. Always use ADC1 (GPIOs 32-39) when WiFi is enabled.

### 2. Deep Sleep
- **Wakeup Pins:** Only RTC GPIOs can wake from deep sleep: GPIO0, 2, 4, 12-15, 25-27, 32-39.
- **RTC RAM Persistence:** Use `RTC_DATA_ATTR` for persistent variables across sleep cycles; regular RAM is lost in deep sleep.
- **Wakeup APIs:** Use `esp_sleep_enable_ext0_wakeup()` for single pin wakeup, `ext1` for multiple pins.
- **WiFi Reconnection:** WiFi reconnect takes 1-3 seconds after waking from deep sleep — plan for this delay.

### 3. WiFi Gotchas
- **Mode initialization:** Always call `WiFi.mode()` before `WiFi.begin()`.
- **Auto Reconnect:** `WiFi.setAutoReconnect(true)` does not always handle network drops reliably — implement an explicit reconnect check in the main loop or event handler.
- **Event-Driven WiFi:** Use `WiFi.onEvent()` for reliable state tracking; avoid blocking while polling `WiFi.status()`.
- **Static IP speed:** Configuring a static IP connects 2-5 seconds faster than DHCP negotiation.

### 4. FreeRTOS
- **Stack Size:** Default stack size is often too small for `printf`, TLS/HTTPS, and WiFi operations. Use 4096+ words/bytes for complex FreeRTOS tasks.
- **Task Watchdog:** The task watchdog triggers at 5s by default. Call `vTaskDelay()` or feed the watchdog regularly.
- **Core Affinity:** Use `xTaskCreatePinnedToCore()` for core pinning — pin WiFi/network to core 0, application/UI/audio logic to core 1.
- **Yielding:** `delay()` in Arduino yields to the scheduler; in pure FreeRTOS tasks, always use `vTaskDelay(pdMS_TO_TICKS(ms))`.

### 5. Memory & Heap
- **Heap Fragmentation:** ESP32 heap fragments over time with dynamic allocations. Preallocate buffers; avoid repeated `malloc`/`free` or dynamic strings.
- **Free Heap Monitoring:** Monitor with `ESP.getFreeHeap()` and log periodically in long-running applications.
- **PSRAM / SPIRAM:** On boards with PSRAM (WROVER, ESP32-S3), use `heap_caps_malloc(size, MALLOC_CAP_SPIRAM)`.
- **String Concatenation:** Arduino `String` concatenation fragments heap. Use `reserve()` or C-style `char[]` / `snprintf`.

### 6. Peripherals (PWM, I2C, SPI, UART)
- **PWM:** ESP32 has no native `analogWrite()` in standard core; use LEDC peripheral (`ledcSetup()`, `ledcAttachPin()`, `ledcWrite()`).
- **I2C Pull-ups:** Internal pullups are weak (~45kΩ); always provide external 2.2kΩ–4.7kΩ pullup resistors for reliable I2C bus speeds.
- **SPI Chip Select:** SPI CS pin must be managed manually or explicitly configured; `SPI.begin()` does not auto-configure CS.
- **UART Ports:** UART0 is tied to Serial/USB flashing. Use UART1 or UART2 for external peripherals (GPS, Fingerprint, etc.).

### 7. OTA Updates
- **Partition Scheme:** OTA requires two OTA app partitions (`ota_0` and `ota_1`). Standard default partition schemes may only have a single `huge_app` or `factory` partition.
- **Sketch Space Check:** Check `ESP.getFreeSketchSpace()`; OTA fails silently if flash space is insufficient.
- **Non-blocking OTA:** `ArduinoOTA.handle()` must be called in the loop and should not block time-critical audio or sensor loops.

### 8. Power & Brown-Out
- **Brown-out Detector:** Resets the MCU when supply drops below ~2.4V. Disable via `esp_brownout_disable()` only if battery operating conditions require it and supply dips are transient.
- **Current Spikes:** WiFi transmission bursts can draw 300mA+ peak current; ensure power rail capacitors are adequate.
- **Deep Sleep Current:** Base deep sleep current is ~10µA, but active RTC peripherals or pullups will add extra consumption.
