---
name: GPIO Interrupts - ATMega2560 + Arduino
description: This skill covers GPIO interrupt handling on Arduino Mega 2560 (ATMega2560) using the Arduino framew
---
# GPIO Interrupts - ATMega2560 + Arduino

## Overview
This skill covers GPIO interrupt handling on Arduino Mega 2560 (ATMega2560) using the Arduino framework. GPIO interrupts enable immediate response to external events without polling, critical for button presses and sensor triggers.

## Target Platform
- **MCU:** ATMega2560
- **Board:** Arduino Mega 2560
- **Framework:** Arduino
- **Available Interrupts:** 6 external interrupts (INT0-INT5) on pins 2, 3, 21, 20, 19, 18

## Key Concepts
- **Hardware Interrupts:** Limited to specific pins (2, 3, 18, 19, 20, 21)
- **Pin Change Interrupts:** Available on all pins but more complex to use
- **ISR:** Interrupt Service Routine - must be fast and non-blocking
- **Interrupt Modes:** LOW, CHANGE, RISING, FALLING
- **Volatile Variables:** Required for variables shared between ISR and main code

## Interrupt Pin Mapping
```
Pin 2  -> INT0
Pin 3  -> INT1
Pin 21 -> INT2
Pin 20 -> INT3
Pin 19 -> INT4
Pin 18 -> INT5
```

## Implementation Pattern

### Basic Setup
```cpp
// Volatile flag for communication between ISR and main loop
volatile bool buttonPressed = false;
volatile unsigned long lastInterruptTime = 0;

const int BUTTON_PIN = 2;  // Must be an interrupt pin (2, 3, 18, 19, 20, 21)
const int LED_PIN = 10;

// ISR - keep it short and fast
void buttonISR() {
    // Simple flag setting
    buttonPressed = true;
}

void setup() {
    Serial.begin(9600);

    pinMode(BUTTON_PIN, INPUT_PULLUP);  // Enable internal pull-up
    pinMode(LED_PIN, OUTPUT);

    // Attach interrupt: pin, ISR function, mode
    attachInterrupt(digitalPinToInterrupt(BUTTON_PIN), buttonISR, FALLING);

    Serial.println("Interrupt example ready");
}

void loop() {
    if (buttonPressed) {
        buttonPressed = false;  // Reset flag

        // Handle the button press here
        Serial.println("Button pressed!");
        digitalWrite(LED_PIN, !digitalRead(LED_PIN));  // Toggle LED
    }
}
```

### Interrupt Modes
```cpp
// FALLING: trigger when pin goes from HIGH to LOW (button press with pull-up)
attachInterrupt(digitalPinToInterrupt(pin), ISR, FALLING);

// RISING: trigger when pin goes from LOW to HIGH (button release or sensor trigger)
attachInterrupt(digitalPinToInterrupt(pin), ISR, RISING);

// CHANGE: trigger on any change (both RISING and FALLING)
attachInterrupt(digitalPinToInterrupt(pin), ISR, CHANGE);

// LOW: trigger continuously while pin is LOW (use with caution)
attachInterrupt(digitalPinToInterrupt(pin), ISR, LOW);
```

### Software Debouncing
```cpp
const int BUTTON_PIN = 2;
const int DEBOUNCE_TIME = 50;  // milliseconds

volatile bool buttonPressed = false;
volatile unsigned long lastInterruptTime = 0;

void buttonISR() {
    unsigned long currentTime = millis();

    // Simple debouncing in ISR
    if (currentTime - lastInterruptTime > DEBOUNCE_TIME) {
        lastInterruptTime = currentTime;
        buttonPressed = true;
    }
}

void setup() {
    Serial.begin(9600);
    pinMode(BUTTON_PIN, INPUT_PULLUP);
    attachInterrupt(digitalPinToInterrupt(BUTTON_PIN), buttonISR, FALLING);
}

void loop() {
    if (buttonPressed) {
        buttonPressed = false;
        Serial.println("Valid button press detected");
        // Handle the event
    }
}
```

## Complete Examples

### Example 1: Button-Triggered LED Toggle with Debouncing
```cpp
const int BUTTON_PIN = 2;   // INT0
const int LED_PIN = 10;
const int DEBOUNCE_TIME = 50;

volatile bool buttonPressed = false;
volatile unsigned long lastInterruptTime = 0;

void buttonISR() {
    unsigned long currentTime = millis();
    if (currentTime - lastInterruptTime > DEBOUNCE_TIME) {
        lastInterruptTime = currentTime;
        buttonPressed = true;
    }
}

void setup() {
    Serial.begin(9600);
    pinMode(BUTTON_PIN, INPUT_PULLUP);
    pinMode(LED_PIN, OUTPUT);

    attachInterrupt(digitalPinToInterrupt(BUTTON_PIN), buttonISR, FALLING);
    Serial.println("Press button to toggle LED");
}

void loop() {
    if (buttonPressed) {
        buttonPressed = false;

        // Toggle LED
        digitalWrite(LED_PIN, !digitalRead(LED_PIN));
        Serial.println("LED toggled");
    }
}
```

### Example 2: Button Press Counter
```cpp
const int BUTTON_PIN = 2;
const int DEBOUNCE_TIME = 50;

volatile unsigned long buttonCount = 0;
volatile bool buttonPressed = false;
volatile unsigned long lastInterruptTime = 0;

void buttonISR() {
    unsigned long currentTime = millis();
    if (currentTime - lastInterruptTime > DEBOUNCE_TIME) {
        lastInterruptTime = currentTime;
        buttonCount++;
        buttonPressed = true;
    }
}

void setup() {
    Serial.begin(9600);
    pinMode(BUTTON_PIN, INPUT_PULLUP);
    attachInterrupt(digitalPinToInterrupt(BUTTON_PIN), buttonISR, FALLING);

    Serial.println("Button counter ready");
}

void loop() {
    if (buttonPressed) {
        buttonPressed = false;
        Serial.print("Button pressed ");
        Serial.print(buttonCount);
        Serial.println(" times");
    }
}
```

### Example 3: Button-Triggered Sensor Reading
```cpp
#include <DHT.h>

const int BUTTON_PIN = 2;
const int DHT_PIN = 14;
const int DEBOUNCE_TIME = 50;

volatile bool readSensor = false;
volatile unsigned long lastInterruptTime = 0;

DHT dht(DHT_PIN, DHT11);

void buttonISR() {
    unsigned long currentTime = millis();
    if (currentTime - lastInterruptTime > DEBOUNCE_TIME) {
        lastInterruptTime = currentTime;
        readSensor = true;
    }
}

void setup() {
    Serial.begin(9600);
    pinMode(BUTTON_PIN, INPUT_PULLUP);
    attachInterrupt(digitalPinToInterrupt(BUTTON_PIN), buttonISR, FALLING);

    dht.begin();
    Serial.println("Press button to read sensor");
}

void loop() {
    if (readSensor) {
        readSensor = false;

        float temp = dht.readTemperature();
        float humidity = dht.readHumidity();

        if (!isnan(temp) && !isnan(humidity)) {
            Serial.print("Temperature: ");
            Serial.print(temp);
            Serial.print("°C, Humidity: ");
            Serial.print(humidity);
            Serial.println("%");
        } else {
            Serial.println("Sensor read error");
        }
    }
}
```

### Example 4: Multiple Interrupts (Variable Frequency LED)
```cpp
const int BUTTON_PIN = 2;    // INT0
const int LED_PIN = 10;
const int BUZZER_PIN = 11;
const int DEBOUNCE_TIME = 50;

volatile bool buttonPressed = false;
volatile unsigned long lastInterruptTime = 0;

unsigned long previousMillis = 0;
int frequencyState = 0;  // 0=1Hz, 1=2Hz, 2=4Hz, 3=off
bool ledState = false;

void buttonISR() {
    unsigned long currentTime = millis();
    if (currentTime - lastInterruptTime > DEBOUNCE_TIME) {
        lastInterruptTime = currentTime;
        buttonPressed = true;
    }
}

void setup() {
    Serial.begin(9600);
    pinMode(BUTTON_PIN, INPUT_PULLUP);
    pinMode(LED_PIN, OUTPUT);
    pinMode(BUZZER_PIN, OUTPUT);

    attachInterrupt(digitalPinToInterrupt(BUTTON_PIN), buttonISR, FALLING);
}

void loop() {
    // Handle button press
    if (buttonPressed) {
        buttonPressed = false;

        // Sound buzzer briefly
        digitalWrite(BUZZER_PIN, HIGH);
        delay(100);
        digitalWrite(BUZZER_PIN, LOW);

        // Change frequency state
        frequencyState = (frequencyState + 1) % 4;
        Serial.print("Frequency state: ");
        Serial.println(frequencyState);
    }

    // Handle LED blinking based on frequency state
    unsigned long currentMillis = millis();
    unsigned long interval;

    switch(frequencyState) {
        case 0: interval = 500; break;   // 1 Hz (500ms per half cycle)
        case 1: interval = 250; break;   // 2 Hz
        case 2: interval = 125; break;   // 4 Hz
        case 3:
            digitalWrite(LED_PIN, LOW);  // Off
            return;
    }

    if (currentMillis - previousMillis >= interval) {
        previousMillis = currentMillis;
        ledState = !ledState;
        digitalWrite(LED_PIN, ledState);
    }
}
```

## Pin Change Interrupts (Advanced)
For pins that don't have hardware interrupts, you can use Pin Change Interrupts (PCINT):

```cpp
// Enable PCINT on any pin (example for pin 10)
// This is more complex and requires direct register manipulation

#include <avr/interrupt.h>

const int PIN = 10;  // Can be any pin
volatile bool pinChanged = false;

void setup() {
    Serial.begin(9600);
    pinMode(PIN, INPUT_PULLUP);

    // Enable PCINT for the pin (complex register setup)
    // PCICR – Pin Change Interrupt Control Register
    // PCMSK – Pin Change Mask Register

    // For pin 10 (PB4 on Mega), use PCINT0
    PCICR |= (1 << PCIE0);    // Enable PCINT0
    PCMSK0 |= (1 << PCINT4);  // Enable PCINT4 (pin 10)

    sei();  // Enable global interrupts
}

// ISR for PCINT0 vector (covers pins 10-13, 50-53)
ISR(PCINT0_vect) {
    pinChanged = true;
}

void loop() {
    if (pinChanged) {
        pinChanged = false;
        Serial.println("Pin change detected");
    }
}
```

## Usage in Tasks

### Task: door_bell - Button-Triggered Buzzer
```cpp
const int BUTTON_PIN = 2;   // INT0 (pin 2)
const int BUZZER_PIN = 13;

volatile bool buttonPressed = false;

void buttonISR() {
    buttonPressed = true;
}

void setup() {
    pinMode(BUTTON_PIN, INPUT_PULLUP);
    pinMode(BUZZER_PIN, OUTPUT);
    attachInterrupt(digitalPinToInterrupt(BUTTON_PIN), buttonISR, FALLING);
}

void loop() {
    if (buttonPressed) {
        buttonPressed = false;
        digitalWrite(BUZZER_PIN, HIGH);
        delay(500);
        digitalWrite(BUZZER_PIN, LOW);
    }
}
```

## Best Practices
1. **Use volatile** - All variables shared between ISR and main code must be `volatile`
2. **Keep ISR short** - No `Serial.print()`, `delay()`, or complex operations in ISR
3. **Debounce properly** - Implement debouncing to avoid false triggers
4. **Choose correct mode** - FALLING for buttons with pull-up, RISING for sensors
5. **Atomic operations** - For multi-byte variables, disable interrupts during read/write

## ISR Restrictions
❌ **Don't use in ISR:**
- `Serial.print()` / `Serial.println()`
- `delay()` / `delayMicroseconds()`
- `millis()` (works but may not update during ISR)
- Complex calculations
- Library functions that use interrupts

✅ **Safe in ISR:**
- `digitalRead()` / `digitalWrite()`
- Simple variable assignments
- `millis()` for reading time
- Setting flags

## Common Pitfalls
- ❌ Using non-interrupt pins (only 6 pins support hardware interrupts)
- ❌ Forgetting `volatile` keyword
- ❌ Long ISR functions (causes missed interrupts)
- ❌ No debouncing (multiple false triggers)
- ❌ Using `delay()` in ISR (crashes or hangs)

## Related Skills
- `software-debouncing-pattern.md` - Software debouncing techniques
- `hardware-timers-atmega2560-arduino.md` - Timer interrupts
- `gpio-basics-atmega2560-arduino.md` - Basic GPIO operations

## References
- Arduino attachInterrupt(): https://www.arduino.cc/reference/en/language/functions/external-interrupts/attachinterrupt/
- ATMega2560 Datasheet: External Interrupts section
- Arduino Interrupt Guide: https://www.arduino.cc/en/Reference/AttachInterrupt
