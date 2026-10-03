---
name: Matrix Keypad Scanning - Generic Pattern
description: This skill covers matrix keypad scanning technique for 4x4 (16-key) keypads. The pattern is platform
---
# Matrix Keypad Scanning - Generic Pattern

## Overview
This skill covers matrix keypad scanning technique for 4x4 (16-key) keypads. The pattern is platform-agnostic and can be implemented on ESP32, ATMega2560, or nRF52840 with minor platform-specific GPIO adaptations.

## Target Hardware
- **Keypad:** 4x4 matrix keypad (16 keys)
- **Connections:** 8 GPIO pins (4 rows + 4 columns)
- **Platforms:** ESP32, Arduino, Zephyr

## Key Concepts
- **Matrix Structure:** Keys arranged in rows and columns to reduce pin count
- **Scanning Algorithm:** Activate one row at a time, read all columns
- **Pull-up/Pull-down:** Columns use pull-up resistors (internal or external)
- **Debouncing:** Software debouncing to prevent multiple key detections
- **Key Mapping:** Map row/column combinations to key characters

## Keypad Matrix Layout
```
       Col0  Col1  Col2  Col3
Row0    1     2     3     A
Row1    4     5     6     B
Row2    7     8     9     C
Row3    *     0     #     D
```

## Circuit Connection
```
Rows (Output):   GPIO pins configured as OUTPUT
Columns (Input): GPIO pins configured as INPUT with PULL-UP resistors

When a key is pressed:
- The row and column of that key are electrically connected
- Scanning algorithm detects which row-column pair is active
```

## Generic Scanning Algorithm

### Pseudocode
```
1. Configure all row pins as OUTPUT, set HIGH
2. Configure all column pins as INPUT with PULL-UP (reads HIGH when not pressed)

3. Scanning loop:
   For each row:
     a. Set current row pin LOW
     b. Small delay for signal stabilization
     c. Read all column pins
     d. If any column reads LOW:
        - Key at (current_row, that_column) is pressed
        - Map to character using lookup table
     e. Set current row pin back HIGH

4. Debounce the detected key
5. Return the key character
```

### Key Mapping Table
```c
const char KEYPAD_KEYS[4][4] = {
    {'1', '2', '3', 'A'},
    {'4', '5', '6', 'B'},
    {'7', '8', '9', 'C'},
    {'*', '0', '#', 'D'}
};
```

## Implementation Examples

### ESP32 + ESP-IDF Implementation
```c
#include "driver/gpio.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

// GPIO pin definitions
#define ROW0_GPIO    38
#define ROW1_GPIO    39
#define ROW2_GPIO    21
#define ROW3_GPIO    14

#define COL0_GPIO    10
#define COL1_GPIO    9
#define COL2_GPIO    41
#define COL3_GPIO    40

const int row_pins[4] = {ROW0_GPIO, ROW1_GPIO, ROW2_GPIO, ROW3_GPIO};
const int col_pins[4] = {COL0_GPIO, COL1_GPIO, COL2_GPIO, COL3_GPIO};

const char keys[4][4] = {
    {'1', '2', '3', 'A'},
    {'4', '5', '6', 'B'},
    {'7', '8', '9', 'C'},
    {'*', '0', '#', 'D'}
};

void keypad_init(void)
{
    // Configure row pins as output (HIGH by default)
    for (int i = 0; i < 4; i++) {
        gpio_reset_pin(row_pins[i]);
        gpio_set_direction(row_pins[i], GPIO_MODE_OUTPUT);
        gpio_set_level(row_pins[i], 1);
    }

    // Configure column pins as input with pull-up
    for (int i = 0; i < 4; i++) {
        gpio_reset_pin(col_pins[i]);
        gpio_set_direction(col_pins[i], GPIO_MODE_INPUT);
        gpio_set_pull_mode(col_pins[i], GPIO_PULLUP_ONLY);
    }
}

char keypad_scan(void)
{
    for (int row = 0; row < 4; row++) {
        // Set current row LOW
        gpio_set_level(row_pins[row], 0);

        // Small delay for signal stabilization
        vTaskDelay(pdMS_TO_TICKS(1));

        // Check all columns
        for (int col = 0; col < 4; col++) {
            if (gpio_get_level(col_pins[col]) == 0) {
                // Key pressed at (row, col)
                char key = keys[row][col];

                // Wait for key release
                while (gpio_get_level(col_pins[col]) == 0) {
                    vTaskDelay(pdMS_TO_TICKS(10));
                }

                // Set row back HIGH
                gpio_set_level(row_pins[row], 1);

                return key;
            }
        }

        // Set row back HIGH
        gpio_set_level(row_pins[row], 1);
    }

    return '\0';  // No key pressed
}

void app_main(void)
{
    keypad_init();

    while (1) {
        char key = keypad_scan();

        if (key != '\0') {
            printf("Key pressed: %c\n", key);
        }

        vTaskDelay(pdMS_TO_TICKS(50));  // Scan rate
    }
}
```

### Arduino (ATMega2560) Implementation
```cpp
// GPIO pin definitions
const int row_pins[4] = {38, 39, 21, 14};
const int col_pins[4] = {10, 9, 41, 40};

const char keys[4][4] = {
    {'1', '2', '3', 'A'},
    {'4', '5', '6', 'B'},
    {'7', '8', '9', 'C'},
    {'*', '0', '#', 'D'}
};

void keypad_init() {
    // Configure row pins as output (HIGH)
    for (int i = 0; i < 4; i++) {
        pinMode(row_pins[i], OUTPUT);
        digitalWrite(row_pins[i], HIGH);
    }

    // Configure column pins as input with pull-up
    for (int i = 0; i < 4; i++) {
        pinMode(col_pins[i], INPUT_PULLUP);
    }
}

char keypad_scan() {
    for (int row = 0; row < 4; row++) {
        // Set current row LOW
        digitalWrite(row_pins[row], LOW);

        // Small delay for stabilization
        delayMicroseconds(10);

        // Check all columns
        for (int col = 0; col < 4; col++) {
            if (digitalRead(col_pins[col]) == LOW) {
                // Key pressed at (row, col)
                char key = keys[row][col];

                // Wait for key release (debouncing)
                while (digitalRead(col_pins[col]) == LOW) {
                    delay(10);
                }

                // Set row back HIGH
                digitalWrite(row_pins[row], HIGH);

                return key;
            }
        }

        // Set row back HIGH
        digitalWrite(row_pins[row], HIGH);
    }

    return '\0';  // No key pressed
}

void setup() {
    Serial.begin(9600);
    keypad_init();
    Serial.println("4x4 Keypad ready");
}

void loop() {
    char key = keypad_scan();

    if (key != '\0') {
        Serial.print("Key pressed: ");
        Serial.println(key);
    }

    delay(50);  // Scan rate
}
```

## Complete Application Examples

### Example 1: Safe Box Password System
```cpp
#define PASSWORD_LENGTH 4
const char correct_password[PASSWORD_LENGTH] = {'1', '2', '3', '4'};
char input_password[PASSWORD_LENGTH];
int input_index = 0;

#define RELAY_PIN 12

void setup() {
    Serial.begin(9600);
    keypad_init();

    pinMode(RELAY_PIN, OUTPUT);
    digitalWrite(RELAY_PIN, LOW);  // Locked

    Serial.println("Enter password:");
}

void loop() {
    char key = keypad_scan();

    if (key != '\0') {
        Serial.print(key);

        // Store input
        input_password[input_index] = key;
        input_index++;

        // Check if password complete
        if (input_index == PASSWORD_LENGTH) {
            Serial.println();

            // Verify password
            bool correct = true;
            for (int i = 0; i < PASSWORD_LENGTH; i++) {
                if (input_password[i] != correct_password[i]) {
                    correct = false;
                    break;
                }
            }

            if (correct) {
                Serial.println("Access Granted!");
                digitalWrite(RELAY_PIN, HIGH);  // Unlock
                delay(3000);
                digitalWrite(RELAY_PIN, LOW);   // Lock again
            } else {
                Serial.println("Access Denied!");
            }

            // Reset input
            input_index = 0;
            Serial.println("Enter password:");
        }
    }

    delay(50);
}
```

### Example 2: Safe Box with LCD Display
```cpp
#include <LiquidCrystal.h>

// Note: LCD and keypad share some pins (time-multiplexed)
// This requires careful timing and pin management

LiquidCrystal lcd(38, 39, 40, 41, 9, 21);

void display_password_input() {
    lcd.clear();
    lcd.print("Input: ");

    // Display input as asterisks
    for (int i = 0; i < input_index; i++) {
        lcd.print('*');
    }

    lcd.setCursor(0, 1);
    if (input_index == PASSWORD_LENGTH) {
        // Check password
        bool correct = check_password();

        if (correct) {
            lcd.print("Status: Success");
            digitalWrite(RELAY_PIN, HIGH);
        } else {
            lcd.print("Status: Fail");
        }

        delay(2000);
        input_index = 0;
        digitalWrite(RELAY_PIN, LOW);
    }
}
```

### Example 3: Calculator Keypad
```cpp
char operation = '\0';
int num1 = 0, num2 = 0;
bool entering_num1 = true;

void loop() {
    char key = keypad_scan();

    if (key != '\0') {
        if (key >= '0' && key <= '9') {
            // Number key
            int digit = key - '0';

            if (entering_num1) {
                num1 = num1 * 10 + digit;
                Serial.print(key);
            } else {
                num2 = num2 * 10 + digit;
                Serial.print(key);
            }
        } else if (key == 'A' || key == 'B' || key == 'C' || key == 'D') {
            // Operation key (A=+, B=-, C=*, D=/)
            operation = key;
            entering_num1 = false;
            Serial.print(" ");
            Serial.print(key);
            Serial.print(" ");
        } else if (key == '#') {
            // Equals key
            Serial.print(" = ");

            int result = 0;
            switch (operation) {
                case 'A': result = num1 + num2; break;
                case 'B': result = num1 - num2; break;
                case 'C': result = num1 * num2; break;
                case 'D': result = (num2 != 0) ? (num1 / num2) : 0; break;
            }

            Serial.println(result);

            // Reset
            num1 = 0;
            num2 = 0;
            operation = '\0';
            entering_num1 = true;
        } else if (key == '*') {
            // Clear key
            num1 = 0;
            num2 = 0;
            operation = '\0';
            entering_num1 = true;
            Serial.println("\nCleared");
        }
    }

    delay(50);
}
```

## Advanced: Non-Blocking Keypad Scanning
```c
char keypad_scan_nonblocking(void)
{
    static int current_row = 0;
    static uint32_t last_scan_time = 0;
    static char last_key = '\0';
    static uint32_t key_press_time = 0;

    uint32_t current_time = millis();

    // Scan one row per call
    if (current_time - last_scan_time >= 2) {  // 2ms between rows
        gpio_set_level(row_pins[current_row], 0);

        // Check columns
        for (int col = 0; col < 4; col++) {
            if (gpio_get_level(col_pins[col]) == 0) {
                char key = keys[current_row][col];

                // Debouncing
                if (key != last_key || (current_time - key_press_time) > 200) {
                    last_key = key;
                    key_press_time = current_time;

                    gpio_set_level(row_pins[current_row], 1);
                    current_row = (current_row + 1) % 4;
                    last_scan_time = current_time;

                    return key;
                }
            }
        }

        gpio_set_level(row_pins[current_row], 1);
        current_row = (current_row + 1) % 4;
        last_scan_time = current_time;
    }

    return '\0';
}
```

## Debouncing Strategies

### Simple Delay Method
```c
// Wait for stable LOW reading
if (gpio_get_level(col_pins[col]) == 0) {
    delay(10);  // Debounce delay
    if (gpio_get_level(col_pins[col]) == 0) {
        // Valid key press
    }
}
```

### State Machine Method
```c
typedef enum {
    KEY_IDLE,
    KEY_PRESSED,
    KEY_HELD
} key_state_t;

key_state_t key_state = KEY_IDLE;
uint32_t key_press_time = 0;

void handle_keypad_state() {
    char key = keypad_scan_raw();

    switch (key_state) {
        case KEY_IDLE:
            if (key != '\0') {
                key_state = KEY_PRESSED;
                key_press_time = millis();
            }
            break;

        case KEY_PRESSED:
            if (millis() - key_press_time > 50) {  // 50ms debounce
                if (key != '\0') {
                    // Valid key press
                    process_key(key);
                    key_state = KEY_HELD;
                } else {
                    key_state = KEY_IDLE;
                }
            }
            break;

        case KEY_HELD:
            if (key == '\0') {
                key_state = KEY_IDLE;
            }
            break;
    }
}
```

## Pin Multiplexing with LCD

When sharing pins between keypad and LCD (common in constrained designs):

```c
void multiplex_setup() {
    // Configure for keypad scanning
    keypad_init();
}

void switch_to_lcd() {
    // Reconfigure pins for LCD
    // Save keypad state
    lcd_init();
}

void switch_to_keypad() {
    // Reconfigure pins for keypad
    keypad_init();
}

// In main loop:
// 1. Scan keypad (quick)
// 2. Switch to LCD mode
// 3. Update LCD display
// 4. Switch back to keypad mode
```

## Best Practices
1. **Pull-up resistors** - Use internal pull-ups for cleaner design
2. **Debouncing** - Always implement debouncing (50-100ms)
3. **Scan rate** - Balance between responsiveness and CPU usage (50-100Hz)
4. **Key release detection** - Wait for key release before processing next input
5. **Non-blocking design** - Use non-blocking scans for better system responsiveness

## Common Pitfalls
- ❌ No pull-up resistors (floating inputs, erratic readings)
- ❌ No debouncing (multiple characters from single press)
- ❌ Scanning too fast (unnecessary CPU usage)
- ❌ Not waiting for key release (repeated inputs)
- ❌ Wrong row/column mapping (incorrect key detection)

## Related Skills
- `gpio-basics-[platform].md` - Basic GPIO configuration
- `lcd1602-display-[platform].md` - Displaying keypad input
- `software-debouncing-pattern.md` - Advanced debouncing techniques

## References
- Keypad Matrix Theory: https://www.circuitbasics.com/how-to-set-up-a-keypad-on-an-arduino/
- Debouncing Guide: http://www.ganssle.com/debouncing.htm
