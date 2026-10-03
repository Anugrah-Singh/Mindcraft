---
name: Ultrasonic Distance Measurement (HC-SR04) - Generic Pattern
description: This skill covers ultrasonic distance measurement using the HC-SR04 sensor. The pattern is platform-
---
# Ultrasonic Distance Measurement (HC-SR04) - Generic Pattern

## Overview
This skill covers ultrasonic distance measurement using the HC-SR04 sensor. The pattern is platform-agnostic and can be implemented on ESP32, ATMega2560, or nRF52840 with minor GPIO adaptations.

## Target Hardware
- **Sensor:** HC-SR04 Ultrasonic Distance Sensor
- **Range:** 2cm - 400cm (effective: 2cm - 300cm)
- **Accuracy:** ±3mm
- **Connections:** 2 GPIO pins (TRIG, ECHO) + VCC (5V) + GND

## Key Concepts
- **Trigger Pulse:** Send 10μs HIGH pulse on TRIG pin to start measurement
- **Echo Pulse:** Sensor responds with pulse on ECHO pin, width proportional to distance
- **Speed of Sound:** ~343 m/s (or 29.1 μs/cm at room temperature)
- **Distance Formula:** Distance (cm) = (Echo pulse width in μs) / 58
  - Or: Distance (cm) = (Echo pulse width in μs) × 0.034 / 2
- **Timeout:** Implement timeout for echo pulse (38ms for max range)

## How HC-SR04 Works
```
1. Send 10μs HIGH pulse on TRIG pin
2. Sensor emits 8 ultrasonic pulses at 40kHz
3. Wait for ECHO pin to go HIGH (ultrasonic burst sent)
4. Measure how long ECHO pin stays HIGH
5. Calculate distance: distance_cm = echo_duration_us / 58
```

## Generic Algorithm

### Pseudocode
```
1. Configure TRIG pin as OUTPUT (LOW)
2. Configure ECHO pin as INPUT

3. Measurement sequence:
   a. Ensure TRIG is LOW for at least 2μs
   b. Set TRIG HIGH for 10μs
   c. Set TRIG LOW
   d. Wait for ECHO to go HIGH (with timeout)
   e. Start timer
   f. Wait for ECHO to go LOW (with timeout)
   g. Stop timer
   h. Calculate: distance_cm = elapsed_time_us / 58

4. Return distance or error code
```

## Implementation Examples

### ESP32 + ESP-IDF Implementation
```c
#include "driver/gpio.h"
#include "esp_timer.h"
#include "esp_log.h"

#define TRIG_GPIO 43
#define ECHO_GPIO 44
#define TIMEOUT_US 30000  // 30ms timeout (~500cm max range)

static const char *TAG = "HC-SR04";

void hcsr04_init(void)
{
    // Configure TRIG as output
    gpio_reset_pin(TRIG_GPIO);
    gpio_set_direction(TRIG_GPIO, GPIO_MODE_OUTPUT);
    gpio_set_level(TRIG_GPIO, 0);

    // Configure ECHO as input
    gpio_reset_pin(ECHO_GPIO);
    gpio_set_direction(ECHO_GPIO, GPIO_MODE_INPUT);
}

float hcsr04_measure_cm(void)
{
    // Ensure trigger is LOW
    gpio_set_level(TRIG_GPIO, 0);
    esp_rom_delay_us(2);

    // Send 10μs trigger pulse
    gpio_set_level(TRIG_GPIO, 1);
    esp_rom_delay_us(10);
    gpio_set_level(TRIG_GPIO, 0);

    // Wait for echo to go HIGH (start of pulse)
    uint32_t timeout_start = esp_timer_get_time();
    while (gpio_get_level(ECHO_GPIO) == 0) {
        if ((esp_timer_get_time() - timeout_start) > TIMEOUT_US) {
            ESP_LOGW(TAG, "Timeout waiting for echo start");
            return -1.0;
        }
    }

    // Measure echo pulse width
    uint32_t echo_start = esp_timer_get_time();

    // Wait for echo to go LOW (end of pulse)
    while (gpio_get_level(ECHO_GPIO) == 1) {
        if ((esp_timer_get_time() - echo_start) > TIMEOUT_US) {
            ESP_LOGW(TAG, "Timeout waiting for echo end");
            return -1.0;
        }
    }

    uint32_t echo_end = esp_timer_get_time();
    uint32_t echo_duration_us = echo_end - echo_start;

    // Calculate distance in cm
    // Speed of sound: 343 m/s = 0.0343 cm/μs
    // Distance = (time × speed) / 2 (round trip)
    // Distance (cm) = (time_us × 0.0343) / 2 = time_us / 58.0
    float distance_cm = echo_duration_us / 58.0;

    return distance_cm;
}

void app_main(void)
{
    hcsr04_init();

    while (1) {
        float distance = hcsr04_measure_cm();

        if (distance >= 0) {
            ESP_LOGI(TAG, "Distance: %.2f cm", distance);
        } else {
            ESP_LOGI(TAG, "Measurement failed");
        }

        vTaskDelay(pdMS_TO_TICKS(100));  // Measure every 100ms
    }
}
```

### Arduino (ATMega2560) Implementation
```cpp
#define TRIG_PIN 43
#define ECHO_PIN 44
#define TIMEOUT_US 30000

void hcsr04_init() {
    pinMode(TRIG_PIN, OUTPUT);
    pinMode(ECHO_PIN, INPUT);
    digitalWrite(TRIG_PIN, LOW);
}

float hcsr04_measure_cm() {
    // Ensure trigger is LOW
    digitalWrite(TRIG_PIN, LOW);
    delayMicroseconds(2);

    // Send 10μs trigger pulse
    digitalWrite(TRIG_PIN, HIGH);
    delayMicroseconds(10);
    digitalWrite(TRIG_PIN, LOW);

    // Measure echo pulse duration with timeout
    unsigned long duration_us = pulseIn(ECHO_PIN, HIGH, TIMEOUT_US);

    if (duration_us == 0) {
        // Timeout occurred
        return -1.0;
    }

    // Calculate distance
    float distance_cm = duration_us / 58.0;

    return distance_cm;
}

void setup() {
    Serial.begin(9600);
    hcsr04_init();
    Serial.println("HC-SR04 Ultrasonic Sensor");
}

void loop() {
    float distance = hcsr04_measure_cm();

    if (distance >= 0) {
        Serial.print("Distance: ");
        Serial.print(distance);
        Serial.println(" cm");
    } else {
        Serial.println("Measurement failed");
    }

    delay(100);  // Measure every 100ms
}
```

## Complete Application Examples

### Example 1: Parking Sensor with LED and Buzzer
```cpp
#define LED_PIN 10
#define BUZZER_PIN 11

void setup() {
    Serial.begin(9600);
    hcsr04_init();

    pinMode(LED_PIN, OUTPUT);
    pinMode(BUZZER_PIN, OUTPUT);
}

void loop() {
    float distance = hcsr04_measure_cm();

    if (distance >= 0 && distance < 200) {
        // Map distance to frequency (closer = higher frequency)
        // Distance 5-200cm maps to frequency 2000-100 Hz
        int frequency = map(distance, 5, 200, 2000, 100);
        int blink_delay = map(distance, 5, 200, 50, 500);

        // Control LED
        digitalWrite(LED_PIN, HIGH);
        delay(blink_delay / 2);
        digitalWrite(LED_PIN, LOW);
        delay(blink_delay / 2);

        // Control passive buzzer
        tone(BUZZER_PIN, frequency);
        delay(50);
        noTone(BUZZER_PIN);

        Serial.print("Distance: ");
        Serial.print(distance);
        Serial.print(" cm, Freq: ");
        Serial.print(frequency);
        Serial.println(" Hz");
    } else {
        // No object detected or too far
        digitalWrite(LED_PIN, LOW);
        noTone(BUZZER_PIN);
        delay(200);
    }
}
```

### Example 2: Distance Threshold Alarm
```cpp
#define ACTIVE_BUZZER_PIN 11
#define ALARM_THRESHOLD_CM 30

void loop() {
    float distance = hcsr04_measure_cm();

    if (distance >= 0 && distance < ALARM_THRESHOLD_CM) {
        // Object too close - sound alarm
        digitalWrite(ACTIVE_BUZZER_PIN, HIGH);
        Serial.print("ALARM! Object at ");
        Serial.print(distance);
        Serial.println(" cm");
    } else {
        digitalWrite(ACTIVE_BUZZER_PIN, LOW);
    }

    delay(100);
}
```

### Example 3: Distance Display on LCD
```cpp
#include <LiquidCrystal.h>

LiquidCrystal lcd(38, 39, 40, 41, 9, 21);

void setup() {
    hcsr04_init();
    lcd.begin(16, 2);
    lcd.print("Distance:");
}

void loop() {
    float distance = hcsr04_measure_cm();

    lcd.setCursor(0, 1);

    if (distance >= 0) {
        lcd.print(distance, 1);
        lcd.print(" cm    ");
    } else {
        lcd.print("Out of range");
    }

    delay(200);
}
```

### Example 4: Multiple Distance Ranges with Visual Feedback
```cpp
#define GREEN_LED 10
#define YELLOW_LED 11
#define RED_LED 12

void setup() {
    hcsr04_init();
    pinMode(GREEN_LED, OUTPUT);
    pinMode(YELLOW_LED, OUTPUT);
    pinMode(RED_LED, OUTPUT);
}

void loop() {
    float distance = hcsr04_measure_cm();

    // Turn off all LEDs
    digitalWrite(GREEN_LED, LOW);
    digitalWrite(YELLOW_LED, LOW);
    digitalWrite(RED_LED, LOW);

    if (distance >= 0) {
        if (distance > 50) {
            // Safe distance - green
            digitalWrite(GREEN_LED, HIGH);
        } else if (distance > 20) {
            // Caution - yellow
            digitalWrite(YELLOW_LED, HIGH);
        } else {
            // Too close - red
            digitalWrite(RED_LED, HIGH);
        }
    }

    delay(100);
}
```

## Advanced: Non-Blocking Measurement

### State Machine Approach
```c
typedef enum {
    HC_IDLE,
    HC_TRIGGER,
    HC_WAIT_ECHO_START,
    HC_WAIT_ECHO_END,
    HC_DONE
} hcsr04_state_t;

typedef struct {
    hcsr04_state_t state;
    uint32_t trigger_time;
    uint32_t echo_start_time;
    uint32_t echo_end_time;
    float distance;
} hcsr04_data_t;

hcsr04_data_t sensor_data = {HC_IDLE, 0, 0, 0, 0.0};

void hcsr04_process(void)
{
    uint32_t current_time = esp_timer_get_time();

    switch (sensor_data.state) {
        case HC_IDLE:
            // Start new measurement
            gpio_set_level(TRIG_GPIO, 0);
            sensor_data.state = HC_TRIGGER;
            sensor_data.trigger_time = current_time;
            break;

        case HC_TRIGGER:
            if (current_time - sensor_data.trigger_time > 2) {
                gpio_set_level(TRIG_GPIO, 1);

                if (current_time - sensor_data.trigger_time > 12) {
                    gpio_set_level(TRIG_GPIO, 0);
                    sensor_data.state = HC_WAIT_ECHO_START;
                }
            }
            break;

        case HC_WAIT_ECHO_START:
            if (gpio_get_level(ECHO_GPIO) == 1) {
                sensor_data.echo_start_time = current_time;
                sensor_data.state = HC_WAIT_ECHO_END;
            } else if (current_time - sensor_data.trigger_time > TIMEOUT_US) {
                // Timeout
                sensor_data.distance = -1.0;
                sensor_data.state = HC_DONE;
            }
            break;

        case HC_WAIT_ECHO_END:
            if (gpio_get_level(ECHO_GPIO) == 0) {
                sensor_data.echo_end_time = current_time;
                uint32_t duration = sensor_data.echo_end_time - sensor_data.echo_start_time;
                sensor_data.distance = duration / 58.0;
                sensor_data.state = HC_DONE;
            } else if (current_time - sensor_data.echo_start_time > TIMEOUT_US) {
                // Timeout
                sensor_data.distance = -1.0;
                sensor_data.state = HC_DONE;
            }
            break;

        case HC_DONE:
            // Measurement complete
            // Process result, then reset to IDLE
            sensor_data.state = HC_IDLE;
            break;
    }
}

float hcsr04_get_distance(void)
{
    return sensor_data.distance;
}

bool hcsr04_is_ready(void)
{
    return sensor_data.state == HC_DONE;
}
```

## Filtering and Averaging

### Median Filter (Removes Outliers)
```c
#define NUM_SAMPLES 5

float hcsr04_measure_median(void)
{
    float samples[NUM_SAMPLES];

    // Take multiple samples
    for (int i = 0; i < NUM_SAMPLES; i++) {
        samples[i] = hcsr04_measure_cm();
        vTaskDelay(pdMS_TO_TICKS(10));
    }

    // Sort samples (bubble sort)
    for (int i = 0; i < NUM_SAMPLES - 1; i++) {
        for (int j = 0; j < NUM_SAMPLES - i - 1; j++) {
            if (samples[j] > samples[j + 1]) {
                float temp = samples[j];
                samples[j] = samples[j + 1];
                samples[j + 1] = temp;
            }
        }
    }

    // Return median
    return samples[NUM_SAMPLES / 2];
}
```

### Moving Average Filter
```c
#define FILTER_SIZE 5

float hcsr04_measure_averaged(void)
{
    static float readings[FILTER_SIZE] = {0};
    static int index = 0;
    static bool filled = false;

    // Get new reading
    float new_reading = hcsr04_measure_cm();

    // Store in circular buffer
    readings[index] = new_reading;
    index = (index + 1) % FILTER_SIZE;

    if (index == 0) filled = true;

    // Calculate average
    float sum = 0;
    int count = filled ? FILTER_SIZE : index;

    for (int i = 0; i < count; i++) {
        sum += readings[i];
    }

    return sum / count;
}
```

## Distance Formula Variations

### Using inches
```c
// Distance (inches) = echo_duration_us / 148
float distance_inches = echo_duration_us / 148.0;
```

### Using millimeters
```c
// Distance (mm) = echo_duration_us / 5.8
float distance_mm = echo_duration_us / 5.8;
```

### Temperature Compensation
```c
// Speed of sound varies with temperature
// v = 331.3 + (0.606 × temp_celsius) m/s

float hcsr04_measure_with_temp_compensation(float temp_celsius)
{
    float speed_of_sound = 331.3 + (0.606 * temp_celsius);  // m/s

    uint32_t echo_duration_us = measure_echo_pulse();

    // Distance = (time × speed) / 2
    float distance_m = (echo_duration_us / 1000000.0) * speed_of_sound / 2.0;
    float distance_cm = distance_m * 100.0;

    return distance_cm;
}
```

## Best Practices
1. **Measurement interval** - Wait at least 60ms between measurements (sensor recovery time)
2. **Timeout handling** - Always implement timeout to avoid blocking
3. **Filtering** - Use median or moving average for stable readings
4. **Range limits** - HC-SR04 effective range is 2-300cm
5. **Power supply** - HC-SR04 needs 5V, ensure proper level shifting if needed
6. **Surface angle** - Works best with perpendicular, flat surfaces

## Common Pitfalls
- ❌ Measuring too frequently (< 60ms interval) - unreliable readings
- ❌ No timeout implementation - code hangs if no echo
- ❌ Voltage mismatch - HC-SR04 ECHO outputs 5V, may damage 3.3V MCUs
- ❌ Soft/angled surfaces - poor reflection, inaccurate readings
- ❌ Multiple sensors interference - use time-multiplexing

## Level Shifting for 3.3V MCUs

### Voltage Divider for ECHO Pin
```
HC-SR04 ECHO (5V) ----[R1: 1kΩ]---- MCU GPIO (3.3V)
                              |
                          [R2: 2kΩ]
                              |
                             GND

Vout = 5V × 2kΩ / (1kΩ + 2kΩ) = 3.3V
```

### Using Logic Level Converter
```
HC-SR04 ECHO (5V) <---> Level Converter <---> MCU GPIO (3.3V)
```

## Usage in Tasks

### Task: Ultrasonic_Sensor - Basic Distance Measurement
```c
void app_main(void)
{
    hcsr04_init();

    while (1) {
        float distance = hcsr04_measure_cm();
        printf("Distance: %.2f cm\n", distance);
        vTaskDelay(pdMS_TO_TICKS(100));
    }
}
```

### Task: ParkingSensor - Variable Frequency Feedback
```c
void app_main(void)
{
    hcsr04_init();
    setup_led_and_buzzer();

    while (1) {
        float distance = hcsr04_measure_cm();

        if (distance >= 5 && distance <= 200) {
            int freq = map_distance_to_frequency(distance, 5, 200, 2000, 100);
            control_buzzer_frequency(freq);
            control_led_blink_rate(distance);
        }

        vTaskDelay(pdMS_TO_TICKS(50));
    }
}
```

## Related Skills
- `pwm-control-[platform].md` - For buzzer frequency control
- `gpio-basics-[platform].md` - Basic GPIO operations
- `lcd1602-display-[platform].md` - Displaying distance values

## References
- HC-SR04 Datasheet: https://cdn.sparkfun.com/datasheets/Sensors/Proximity/HCSR04.pdf
- Ultrasonic Sensing Basics: https://www.maxbotix.com/articles/how-ultrasonic-sensors-work.htm
