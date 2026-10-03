---
name: GPIO Interrupts - ESP32 + ESP-IDF
description: This skill covers GPIO interrupt handling on ESP32 using ESP-IDF framework. GPIO interrupts allow im
---
# GPIO Interrupts - ESP32 + ESP-IDF

## Overview
This skill covers GPIO interrupt handling on ESP32 using ESP-IDF framework. GPIO interrupts allow immediate response to external events like button presses, sensor triggers, or signal changes without polling.

## Target Platform
- **MCU:** ESP32 (ESP32-S3, ESP32-C3, etc.)
- **Framework:** ESP-IDF
- **API:** GPIO driver from ESP-IDF

## Key Concepts
- **Interrupt Service Routine (ISR):** Function called immediately when GPIO state changes
- **Interrupt Types:** Rising edge, falling edge, both edges, low/high level
- **ISR Constraints:** Keep ISR short, use FreeRTOS queues to defer processing
- **GPIO Pull-up/down:** Internal resistors for stable input states

## Implementation Pattern

### Basic Setup
```c
#include "driver/gpio.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"

#define BUTTON_GPIO 12
#define ESP_INTR_FLAG_DEFAULT 0

static QueueHandle_t gpio_evt_queue = NULL;

// ISR handler - keep minimal
static void IRAM_ATTR gpio_isr_handler(void* arg)
{
    uint32_t gpio_num = (uint32_t) arg;
    xQueueSendFromISR(gpio_evt_queue, &gpio_num, NULL);
}

// Task to handle GPIO events
static void gpio_task(void* arg)
{
    uint32_t io_num;
    for(;;) {
        if(xQueueReceive(gpio_evt_queue, &io_num, portMAX_DELAY)) {
            // Process the interrupt here
            printf("GPIO[%lu] interrupt triggered\n", io_num);

            // Add your event handling logic here
            // e.g., read sensor, toggle LED, update state, etc.
        }
    }
}

void setup_gpio_interrupt(void)
{
    // Configure GPIO
    gpio_config_t io_conf = {
        .intr_type = GPIO_INTR_NEGEDGE,      // Interrupt on falling edge (button press)
        .mode = GPIO_MODE_INPUT,              // Input mode
        .pin_bit_mask = (1ULL << BUTTON_GPIO), // Pin mask
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .pull_up_en = GPIO_PULLUP_ENABLE      // Enable pull-up for button
    };
    gpio_config(&io_conf);

    // Create queue for GPIO events
    gpio_evt_queue = xQueueCreate(10, sizeof(uint32_t));

    // Start GPIO task
    xTaskCreate(gpio_task, "gpio_task", 2048, NULL, 10, NULL);

    // Install GPIO ISR service
    gpio_install_isr_service(ESP_INTR_FLAG_DEFAULT);

    // Attach ISR handler to specific GPIO
    gpio_isr_handler_add(BUTTON_GPIO, gpio_isr_handler, (void*) BUTTON_GPIO);
}
```

### Interrupt Types
```c
// Falling edge (button press with pull-up)
io_conf.intr_type = GPIO_INTR_NEGEDGE;

// Rising edge (button release or sensor trigger)
io_conf.intr_type = GPIO_INTR_POSEDGE;

// Both edges (detect any change)
io_conf.intr_type = GPIO_INTR_ANYEDGE;

// Low level (continuous while LOW)
io_conf.intr_type = GPIO_INTR_LOW_LEVEL;

// High level (continuous while HIGH)
io_conf.intr_type = GPIO_INTR_HIGH_LEVEL;
```

### Software Debouncing in ISR Task
```c
#define DEBOUNCE_TIME_MS 50

static void gpio_task_with_debounce(void* arg)
{
    uint32_t io_num;
    static TickType_t last_interrupt_time = 0;

    for(;;) {
        if(xQueueReceive(gpio_evt_queue, &io_num, portMAX_DELAY)) {
            TickType_t current_time = xTaskGetTickCount();

            // Check if enough time has passed since last interrupt
            if ((current_time - last_interrupt_time) * portTICK_PERIOD_MS > DEBOUNCE_TIME_MS) {
                last_interrupt_time = current_time;

                // Process the valid button press
                printf("Valid button press on GPIO[%lu]\n", io_num);

                // Your event handling here
            }
        }
    }
}
```

## Complete Example: Button-Triggered LED Toggle

```c
#include <stdio.h>
#include "driver/gpio.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"

#define BUTTON_GPIO 12
#define LED_GPIO 10
#define ESP_INTR_FLAG_DEFAULT 0
#define DEBOUNCE_TIME_MS 50

static QueueHandle_t gpio_evt_queue = NULL;
static bool led_state = false;

static void IRAM_ATTR gpio_isr_handler(void* arg)
{
    uint32_t gpio_num = (uint32_t) arg;
    xQueueSendFromISR(gpio_evt_queue, &gpio_num, NULL);
}

static void gpio_task(void* arg)
{
    uint32_t io_num;
    TickType_t last_interrupt_time = 0;

    for(;;) {
        if(xQueueReceive(gpio_evt_queue, &io_num, portMAX_DELAY)) {
            TickType_t current_time = xTaskGetTickCount();

            if ((current_time - last_interrupt_time) * portTICK_PERIOD_MS > DEBOUNCE_TIME_MS) {
                last_interrupt_time = current_time;

                // Toggle LED
                led_state = !led_state;
                gpio_set_level(LED_GPIO, led_state);
                printf("Button pressed! LED is now %s\n", led_state ? "ON" : "OFF");
            }
        }
    }
}

void app_main(void)
{
    // Configure LED as output
    gpio_reset_pin(LED_GPIO);
    gpio_set_direction(LED_GPIO, GPIO_MODE_OUTPUT);
    gpio_set_level(LED_GPIO, 0);

    // Configure button as input with interrupt
    gpio_config_t io_conf = {
        .intr_type = GPIO_INTR_NEGEDGE,
        .mode = GPIO_MODE_INPUT,
        .pin_bit_mask = (1ULL << BUTTON_GPIO),
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .pull_up_en = GPIO_PULLUP_ENABLE
    };
    gpio_config(&io_conf);

    // Create event queue
    gpio_evt_queue = xQueueCreate(10, sizeof(uint32_t));

    // Start task
    xTaskCreate(gpio_task, "gpio_task", 2048, NULL, 10, NULL);

    // Install ISR service and handler
    gpio_install_isr_service(ESP_INTR_FLAG_DEFAULT);
    gpio_isr_handler_add(BUTTON_GPIO, gpio_isr_handler, (void*) BUTTON_GPIO);

    printf("GPIO interrupt example started. Press button on GPIO %d\n", BUTTON_GPIO);
}
```

## Usage in Tasks

### Button-Triggered DHT11 Reading (task: Button_triggered_DHT11_display)
```c
static void gpio_task(void* arg)
{
    uint32_t io_num;
    TickType_t last_interrupt_time = 0;

    for(;;) {
        if(xQueueReceive(gpio_evt_queue, &io_num, portMAX_DELAY)) {
            TickType_t current_time = xTaskGetTickCount();

            if ((current_time - last_interrupt_time) * portTICK_PERIOD_MS > DEBOUNCE_TIME_MS) {
                last_interrupt_time = current_time;

                // Read DHT11 sensor
                float temperature, humidity;
                if (read_dht11(&temperature, &humidity) == ESP_OK) {
                    // Display on LCD
                    lcd_clear();
                    lcd_printf("Temp: %.1fC", temperature);
                    lcd_set_cursor(0, 1);
                    lcd_printf("RH: %.1f%%", humidity);
                }
            }
        }
    }
}
```

### Button Press Counter
```c
static uint32_t button_press_count = 0;

static void gpio_task(void* arg)
{
    uint32_t io_num;
    TickType_t last_interrupt_time = 0;

    for(;;) {
        if(xQueueReceive(gpio_evt_queue, &io_num, portMAX_DELAY)) {
            TickType_t current_time = xTaskGetTickCount();

            if ((current_time - last_interrupt_time) * portTICK_PERIOD_MS > DEBOUNCE_TIME_MS) {
                last_interrupt_time = current_time;
                button_press_count++;
                printf("Button pressed %lu times\n", button_press_count);
            }
        }
    }
}
```

## Best Practices
1. **Keep ISR minimal** - Use queues to defer processing to a task
2. **Use IRAM_ATTR** - Mark ISR functions to run from internal RAM (faster, more reliable)
3. **Debounce in task** - Handle debouncing in the task, not ISR
4. **Appropriate pull resistors** - Use pull-up for active-low buttons, pull-down for active-high sensors
5. **Queue sizing** - Size queue appropriately to handle burst events
6. **Task priority** - Set appropriate priority for interrupt handling task

## Common Pitfalls
- ❌ Long ISR functions (causes system instability)
- ❌ Calling blocking functions in ISR (FreeRTOS functions without FromISR suffix)
- ❌ No debouncing (multiple false triggers)
- ❌ Forgetting IRAM_ATTR (ISR may fail if flash cache is disabled)

## Related Skills
- `software-debouncing-pattern.md` - Software debouncing techniques
- `hardware-timers-esp32-esp-idf.md` - Timer-based interrupts
- `gpio-basics-esp32-esp-idf.md` - Basic GPIO configuration

## References
- ESP-IDF GPIO Documentation: https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/peripherals/gpio.html
- FreeRTOS Queue Documentation: https://www.freertos.org/a00018.html
