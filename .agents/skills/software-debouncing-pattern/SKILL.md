---
name: Software Debouncing - Generic Pattern
description: This skill covers software debouncing techniques for buttons and switches. Debouncing eliminates fal
---
# Software Debouncing - Generic Pattern

## Overview
This skill covers software debouncing techniques for buttons and switches. Debouncing eliminates false triggers caused by mechanical switch bounce, a critical requirement for reliable button input across all embedded platforms.

## Target Platforms
- **Generic:** Applicable to all platforms (ESP32, ATMega2560, nRF52840, etc.)
- **Language:** C/C++
- **Hardware:** Mechanical buttons, switches, encoders

## Key Concepts
- **Bounce:** Mechanical contacts don't close cleanly - they "bounce" for 1-20ms
- **Debounce Time:** Typical 10-50ms delay to ensure stable reading
- **False Triggers:** Multiple interrupt/read events from single button press
- **Debouncing Methods:** Time-based, state machine, counter-based, integration

## The Problem: Switch Bounce

```
Ideal button press:
       ___________
______|           |_______
     Press      Release

Actual button press (with bounce):
       _|_|__|____|
______|_|_|__|    |_|__|__
     Press      Release
     (multiple transitions)
```

## Debouncing Techniques

### 1. Simple Time Delay Method

**Concept:** Wait a fixed time after detecting a change, then check if state is still valid.

```c
#define DEBOUNCE_DELAY_MS 50

bool read_button_debounced(int pin) {
    static bool last_button_state = false;
    static uint32_t last_debounce_time = 0;
    static bool button_state = false;

    bool reading = digitalRead(pin);

    // If reading changed, reset debounce timer
    if (reading != last_button_state) {
        last_debounce_time = millis();
    }

    // If enough time has passed, accept the reading
    if ((millis() - last_debounce_time) > DEBOUNCE_DELAY_MS) {
        if (reading != button_state) {
            button_state = reading;
            return true;  // State changed
        }
    }

    last_button_state = reading;
    return false;  // No change
}
```

### 2. Edge Detection with Debouncing

**Concept:** Detect button press/release edges with debouncing.

```c
#define DEBOUNCE_DELAY_MS 50

typedef enum {
    BUTTON_RELEASED,
    BUTTON_PRESSED
} button_event_t;

button_event_t button_get_event(int pin) {
    static bool last_stable_state = false;
    static bool last_reading = false;
    static uint32_t last_change_time = 0;

    bool current_reading = digitalRead(pin);

    // Detect reading change
    if (current_reading != last_reading) {
        last_change_time = millis();
        last_reading = current_reading;
    }

    // Check if debounce time has passed
    if ((millis() - last_change_time) > DEBOUNCE_DELAY_MS) {
        // Reading is stable
        if (current_reading != last_stable_state) {
            last_stable_state = current_reading;

            // Return edge event
            if (current_reading) {
                return BUTTON_PRESSED;
            } else {
                return BUTTON_RELEASED;
            }
        }
    }

    return -1;  // No event
}
```

### 3. State Machine Debouncing

**Concept:** Use explicit states to track button transitions.

```c
#define DEBOUNCE_TIME_MS 50

typedef enum {
    STATE_RELEASED,
    STATE_PRESSED,
    STATE_WAIT_RELEASE
} button_state_t;

bool button_pressed_debounced(int pin) {
    static button_state_t state = STATE_RELEASED;
    static uint32_t state_change_time = 0;

    bool reading = digitalRead(pin);
    uint32_t current_time = millis();

    switch (state) {
        case STATE_RELEASED:
            if (reading) {  // Button pressed
                state_change_time = current_time;
                state = STATE_PRESSED;
            }
            break;

        case STATE_PRESSED:
            if (current_time - state_change_time > DEBOUNCE_TIME_MS) {
                if (reading) {  // Still pressed after debounce time
                    state = STATE_WAIT_RELEASE;
                    return true;  // Valid press detected
                } else {  // Was a bounce
                    state = STATE_RELEASED;
                }
            }
            break;

        case STATE_WAIT_RELEASE:
            if (!reading) {  // Button released
                state_change_time = current_time;
                state = STATE_RELEASED;
            }
            break;
    }

    return false;  // No valid press
}
```

### 4. Counter-Based Debouncing

**Concept:** Require multiple consecutive identical readings before accepting change.

```c
#define DEBOUNCE_COUNT 5  // Number of consecutive readings needed

bool read_button_counter_debounce(int pin) {
    static int press_count = 0;
    static int release_count = 0;
    static bool button_state = false;

    bool reading = digitalRead(pin);

    if (reading) {  // Reading is HIGH (pressed)
        press_count++;
        release_count = 0;

        if (press_count >= DEBOUNCE_COUNT && !button_state) {
            button_state = true;
            return true;  // Button just pressed
        }
    } else {  // Reading is LOW (released)
        release_count++;
        press_count = 0;

        if (release_count >= DEBOUNCE_COUNT && button_state) {
            button_state = false;
        }
    }

    return false;  // No state change
}
```

### 5. Integration Debouncing (Accumulator)

**Concept:** Accumulate readings over time, change state when threshold reached.

```c
#define DEBOUNCE_THRESHOLD 5
#define MAX_ACCUMULATOR 10

bool read_button_integration(int pin) {
    static int accumulator = 0;
    static bool button_state = false;

    bool reading = digitalRead(pin);

    // Accumulate readings
    if (reading) {
        accumulator++;
        if (accumulator > MAX_ACCUMULATOR) {
            accumulator = MAX_ACCUMULATOR;
        }
    } else {
        accumulator--;
        if (accumulator < 0) {
            accumulator = 0;
        }
    }

    // Check thresholds
    bool changed = false;
    if (accumulator >= DEBOUNCE_THRESHOLD && !button_state) {
        button_state = true;
        changed = true;
    } else if (accumulator <= (MAX_ACCUMULATOR - DEBOUNCE_THRESHOLD) && button_state) {
        button_state = false;
    }

    return changed;
}
```

## Interrupt-Based Debouncing

### In ISR (Minimal)
```c
#define DEBOUNCE_TIME_MS 50

volatile bool button_pressed_flag = false;
volatile uint32_t last_interrupt_time = 0;

void IRAM_ATTR button_isr() {
    uint32_t current_time = millis();

    // Simple time-based debouncing in ISR
    if (current_time - last_interrupt_time > DEBOUNCE_TIME_MS) {
        last_interrupt_time = current_time;
        button_pressed_flag = true;
    }
}

// In main loop
void loop() {
    if (button_pressed_flag) {
        button_pressed_flag = false;
        // Handle button press
        handle_button_press();
    }
}
```

### In Task (Deferred)
```c
// ESP-IDF example with FreeRTOS queue

void IRAM_ATTR button_isr(void* arg) {
    uint32_t gpio_num = (uint32_t) arg;
    xQueueSendFromISR(gpio_evt_queue, &gpio_num, NULL);
}

void gpio_task(void* arg) {
    uint32_t io_num;
    static uint32_t last_press_time = 0;

    for(;;) {
        if(xQueueReceive(gpio_evt_queue, &io_num, portMAX_DELAY)) {
            uint32_t current_time = xTaskGetTickCount() * portTICK_PERIOD_MS;

            // Debounce in task
            if (current_time - last_press_time > DEBOUNCE_TIME_MS) {
                last_press_time = current_time;

                // Valid button press - process here
                printf("Button %lu pressed\n", io_num);
                handle_button_press(io_num);
            }
        }
    }
}
```

## Complete Application Examples

### Example 1: Button Press Counter with Debouncing
```c
#include <stdio.h>

#define BUTTON_PIN 12
#define DEBOUNCE_DELAY_MS 50

uint32_t button_press_count = 0;

bool is_button_pressed() {
    static bool last_button_state = false;
    static bool current_button_state = false;
    static uint32_t last_debounce_time = 0;

    bool reading = digitalRead(BUTTON_PIN);

    if (reading != last_button_state) {
        last_debounce_time = millis();
    }

    if ((millis() - last_debounce_time) > DEBOUNCE_DELAY_MS) {
        if (reading != current_button_state) {
            current_button_state = reading;

            // Return true on press (LOW to HIGH transition with pull-up)
            if (current_button_state == LOW) {
                last_button_state = reading;
                return true;
            }
        }
    }

    last_button_state = reading;
    return false;
}

void setup() {
    Serial.begin(9600);
    pinMode(BUTTON_PIN, INPUT_PULLUP);
    Serial.println("Button counter with debouncing");
}

void loop() {
    if (is_button_pressed()) {
        button_press_count++;
        Serial.print("Button pressed ");
        Serial.print(button_press_count);
        Serial.println(" times");
    }
}
```

### Example 2: Variable Frequency LED (Button Cycles States)
```c
#define BUTTON_PIN 12
#define LED_PIN 10
#define BUZZER_PIN 11

typedef enum {
    FREQ_1HZ,
    FREQ_2HZ,
    FREQ_4HZ,
    FREQ_OFF
} frequency_state_t;

frequency_state_t freq_state = FREQ_OFF;

bool button_pressed_debounced() {
    static bool last_stable_state = false;
    static bool last_reading = false;
    static uint32_t last_change_time = 0;

    bool reading = digitalRead(BUTTON_PIN);

    if (reading != last_reading) {
        last_change_time = millis();
        last_reading = reading;
    }

    if ((millis() - last_change_time) > 50) {
        if (reading != last_stable_state) {
            last_stable_state = reading;

            // Button pressed (with pull-up, pressed = LOW)
            if (reading == LOW) {
                return true;
            }
        }
    }

    return false;
}

void setup() {
    pinMode(BUTTON_PIN, INPUT_PULLUP);
    pinMode(LED_PIN, OUTPUT);
    pinMode(BUZZER_PIN, OUTPUT);
}

void loop() {
    static unsigned long last_toggle = 0;
    static bool led_state = false;

    // Check for button press
    if (button_pressed_debounced()) {
        // Sound buzzer briefly
        digitalWrite(BUZZER_PIN, HIGH);
        delay(100);
        digitalWrite(BUZZER_PIN, LOW);

        // Cycle frequency state
        freq_state = (frequency_state_t)((freq_state + 1) % 4);
        Serial.print("Frequency state: ");
        Serial.println(freq_state);
    }

    // Handle LED blinking based on frequency
    unsigned long interval;
    switch (freq_state) {
        case FREQ_1HZ: interval = 500; break;  // 1 Hz
        case FREQ_2HZ: interval = 250; break;  // 2 Hz
        case FREQ_4HZ: interval = 125; break;  // 4 Hz
        case FREQ_OFF:
            digitalWrite(LED_PIN, LOW);
            return;
    }

    if (millis() - last_toggle >= interval) {
        last_toggle = millis();
        led_state = !led_state;
        digitalWrite(LED_PIN, led_state);
    }
}
```

### Example 3: Door Bell with Debouncing
```c
#define BUTTON_PIN 12
#define BUZZER_PIN 13
#define DEBOUNCE_TIME_MS 50

void setup() {
    pinMode(BUTTON_PIN, INPUT_PULLUP);
    pinMode(BUZZER_PIN, OUTPUT);
}

void loop() {
    static uint32_t last_press_time = 0;
    static bool last_button_state = HIGH;

    bool button_state = digitalRead(BUTTON_PIN);

    // Detect press (HIGH to LOW transition)
    if (button_state == LOW && last_button_state == HIGH) {
        uint32_t current_time = millis();

        // Check debounce time
        if (current_time - last_press_time > DEBOUNCE_TIME_MS) {
            last_press_time = current_time;

            // Valid button press - sound buzzer
            digitalWrite(BUZZER_PIN, HIGH);
            delay(500);
            digitalWrite(BUZZER_PIN, LOW);
        }
    }

    last_button_state = button_state;
    delay(10);  // Small polling delay
}
```

## Platform-Specific Implementations

### ESP32 + ESP-IDF
```c
#include "driver/gpio.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#define BUTTON_GPIO 12

bool button_debounced_esp32() {
    static bool last_state = false;
    static uint32_t last_change = 0;

    bool reading = gpio_get_level(BUTTON_GPIO);

    if (reading != last_state) {
        last_change = xTaskGetTickCount() * portTICK_PERIOD_MS;
        last_state = reading;
    }

    if ((xTaskGetTickCount() * portTICK_PERIOD_MS - last_change) > 50) {
        if (reading == 0 && last_state == 0) {  // Stable LOW
            last_state = 1;  // Reset for next press
            return true;
        }
    }

    return false;
}
```

### Arduino
```cpp
bool button_debounced_arduino() {
    static unsigned long lastDebounceTime = 0;
    static int lastButtonState = HIGH;
    static int buttonState = HIGH;

    int reading = digitalRead(BUTTON_PIN);

    if (reading != lastButtonState) {
        lastDebounceTime = millis();
    }

    if ((millis() - lastDebounceTime) > 50) {
        if (reading != buttonState) {
            buttonState = reading;

            if (buttonState == LOW) {
                return true;
            }
        }
    }

    lastButtonState = reading;
    return false;
}
```

## Advanced: Long Press Detection

```c
#define SHORT_PRESS_TIME_MS 50
#define LONG_PRESS_TIME_MS 1000

typedef enum {
    NO_PRESS,
    SHORT_PRESS,
    LONG_PRESS
} press_type_t;

press_type_t detect_press_type(int pin) {
    static bool last_state = HIGH;
    static uint32_t press_start_time = 0;
    static bool long_press_detected = false;

    bool current_state = digitalRead(pin);

    if (current_state == LOW && last_state == HIGH) {
        // Button just pressed
        press_start_time = millis();
        long_press_detected = false;
    } else if (current_state == LOW && last_state == LOW) {
        // Button being held
        uint32_t press_duration = millis() - press_start_time;

        if (press_duration > LONG_PRESS_TIME_MS && !long_press_detected) {
            long_press_detected = true;
            last_state = current_state;
            return LONG_PRESS;
        }
    } else if (current_state == HIGH && last_state == LOW) {
        // Button released
        uint32_t press_duration = millis() - press_start_time;

        if (press_duration > SHORT_PRESS_TIME_MS && !long_press_detected) {
            last_state = current_state;
            return SHORT_PRESS;
        }
    }

    last_state = current_state;
    return NO_PRESS;
}
```

## Best Practices
1. **Choose appropriate debounce time** - 10-50ms for most switches
2. **Use pull-up/pull-down resistors** - Prevents floating inputs
3. **Non-blocking implementation** - Don't use delay() for debouncing in main loop
4. **Interrupt + queue pattern** - Best for responsive systems with multiple inputs
5. **Test with real hardware** - Debounce characteristics vary by switch type

## Common Pitfalls
- ❌ No debouncing (multiple false triggers)
- ❌ Debounce time too short (bounce still detected)
- ❌ Debounce time too long (unresponsive UI)
- ❌ Using delay() for debouncing (blocks entire program)
- ❌ Not resetting debounce timer on reading change

## Choosing the Right Method

| Method | Pros | Cons | Best For |
|--------|------|------|----------|
| Time Delay | Simple, reliable | Requires timing | General use |
| Counter | Very stable | More processing | Noisy environments |
| Integration | Smooth, adaptive | Complex | Industrial applications |
| State Machine | Clear logic, predictable | More code | Complex input patterns |
| ISR + Time | Fast response | ISR constraints | Real-time systems |

## Related Skills
- `gpio-interrupts-[platform].md` - Interrupt-based button handling
- `hardware-timers-[platform].md` - Timer-based debouncing
- `gpio-basics-[platform].md` - Basic GPIO operations

## References
- A Guide to Debouncing: http://www.ganssle.com/debouncing.htm
- Switch Bounce and Debouncing: https://www.allaboutcircuits.com/technical-articles/switch-bounce-how-to-deal-with-it/
- Arduino Debounce Tutorial: https://www.arduino.cc/en/Tutorial/Debounce
