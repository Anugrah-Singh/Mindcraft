---
name: Hardware Timers - ESP32 + ESP-IDF
description: This skill covers hardware timer usage on ESP32 using ESP-IDF framework. Hardware timers enable prec
---
# Hardware Timers - ESP32 + ESP-IDF

## Overview
This skill covers hardware timer usage on ESP32 using ESP-IDF framework. Hardware timers enable precise, periodic task execution independent of main code execution, essential for sampling sensors, controlling PWM, and time-critical operations.

## Target Platform
- **MCU:** ESP32 (ESP32-S3, ESP32-C3, etc.)
- **Framework:** ESP-IDF
- **API:** Timer Group driver
- **Available Timers:** 4 hardware timers (2 groups × 2 timers per group)

## Key Concepts
- **Timer Groups:** ESP32 has 2 timer groups (TIMER_GROUP_0, TIMER_GROUP_1)
- **Timer Resolution:** 16 or 20 bits, configurable divider
- **Timer Modes:** One-shot or auto-reload (periodic)
- **Timer Precision:** Microsecond-level accuracy
- **ISR Context:** Timer callbacks run in interrupt context

## Implementation Pattern

### Basic Timer Setup
```c
#include "driver/gptimer.h"
#include "esp_log.h"

static const char *TAG = "TIMER";

// Timer handle
gptimer_handle_t gptimer = NULL;

// Timer callback function (ISR context)
static bool IRAM_ATTR timer_callback(gptimer_handle_t timer,
                                      const gptimer_alarm_event_data_t *edata,
                                      void *user_ctx)
{
    // This runs in ISR context - keep it minimal
    // Set a flag or send to queue
    BaseType_t high_task_awoken = pdFALSE;

    // Your periodic task here
    // e.g., toggle GPIO, send queue message, set flag

    return high_task_awoken == pdTRUE;  // Return if we need to yield
}

void setup_timer(uint64_t period_us)
{
    // Timer configuration
    gptimer_config_t timer_config = {
        .clk_src = GPTIMER_CLK_SRC_DEFAULT,
        .direction = GPTIMER_COUNT_UP,
        .resolution_hz = 1000000,  // 1MHz, 1 tick = 1us
    };
    ESP_ERROR_CHECK(gptimer_new_timer(&timer_config, &gptimer));

    // Set alarm configuration
    gptimer_alarm_config_t alarm_config = {
        .reload_count = 0,
        .alarm_count = period_us,  // Alarm at this count
        .flags.auto_reload_on_alarm = true,  // Auto-reload for periodic timer
    };
    ESP_ERROR_CHECK(gptimer_set_alarm_action(gptimer, &alarm_config));

    // Register callback
    gptimer_event_callbacks_t cbs = {
        .on_alarm = timer_callback,
    };
    ESP_ERROR_CHECK(gptimer_register_event_callbacks(gptimer, &cbs, NULL));

    // Enable and start timer
    ESP_ERROR_CHECK(gptimer_enable(gptimer));
    ESP_ERROR_CHECK(gptimer_start(gptimer));

    ESP_LOGI(TAG, "Timer started with period %llu us", period_us);
}
```

### One-Shot Timer
```c
void setup_oneshot_timer(uint64_t delay_us)
{
    gptimer_config_t timer_config = {
        .clk_src = GPTIMER_CLK_SRC_DEFAULT,
        .direction = GPTIMER_COUNT_UP,
        .resolution_hz = 1000000,
    };
    ESP_ERROR_CHECK(gptimer_new_timer(&timer_config, &gptimer));

    gptimer_alarm_config_t alarm_config = {
        .alarm_count = delay_us,
        .flags.auto_reload_on_alarm = false,  // One-shot mode
    };
    ESP_ERROR_CHECK(gptimer_set_alarm_action(gptimer, &alarm_config));

    gptimer_event_callbacks_t cbs = {
        .on_alarm = timer_callback,
    };
    ESP_ERROR_CHECK(gptimer_register_event_callbacks(gptimer, &cbs, NULL));

    ESP_ERROR_CHECK(gptimer_enable(gptimer));
    ESP_ERROR_CHECK(gptimer_start(gptimer));
}
```

## Complete Examples

### Example 1: Periodic LED Blink (1 Hz)
```c
#include <stdio.h>
#include "driver/gptimer.h"
#include "driver/gpio.h"
#include "esp_log.h"

#define LED_GPIO 10

static gptimer_handle_t gptimer = NULL;
static bool led_state = false;

static bool IRAM_ATTR timer_callback(gptimer_handle_t timer,
                                      const gptimer_alarm_event_data_t *edata,
                                      void *user_ctx)
{
    // Toggle LED
    led_state = !led_state;
    gpio_set_level(LED_GPIO, led_state);
    return false;
}

void app_main(void)
{
    // Configure LED
    gpio_reset_pin(LED_GPIO);
    gpio_set_direction(LED_GPIO, GPIO_MODE_OUTPUT);

    // Timer configuration (500ms = 500000us for 1Hz blink)
    gptimer_config_t timer_config = {
        .clk_src = GPTIMER_CLK_SRC_DEFAULT,
        .direction = GPTIMER_COUNT_UP,
        .resolution_hz = 1000000,  // 1MHz
    };
    ESP_ERROR_CHECK(gptimer_new_timer(&timer_config, &gptimer));

    // Alarm configuration
    gptimer_alarm_config_t alarm_config = {
        .reload_count = 0,
        .alarm_count = 500000,  // 500ms
        .flags.auto_reload_on_alarm = true,
    };
    ESP_ERROR_CHECK(gptimer_set_alarm_action(gptimer, &alarm_config));

    // Register callback
    gptimer_event_callbacks_t cbs = {
        .on_alarm = timer_callback,
    };
    ESP_ERROR_CHECK(gptimer_register_event_callbacks(gptimer, &cbs, NULL));

    // Start timer
    ESP_ERROR_CHECK(gptimer_enable(gptimer));
    ESP_ERROR_CHECK(gptimer_start(gptimer));

    printf("LED blinking at 1 Hz\n");
}
```

### Example 2: Periodic Sensor Reading (Every 100ms)
```c
#include "driver/gptimer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"

#define SAMPLE_PERIOD_MS 100

static gptimer_handle_t gptimer = NULL;
static QueueHandle_t sample_queue = NULL;

typedef struct {
    int16_t accel_x, accel_y, accel_z;
    int16_t gyro_x, gyro_y, gyro_z;
} imu_data_t;

static bool IRAM_ATTR timer_callback(gptimer_handle_t timer,
                                      const gptimer_alarm_event_data_t *edata,
                                      void *user_ctx)
{
    BaseType_t high_task_awoken = pdFALSE;

    // Signal to task to read sensor
    uint32_t signal = 1;
    xQueueSendFromISR(sample_queue, &signal, &high_task_awoken);

    return high_task_awoken == pdTRUE;
}

static void sensor_task(void *arg)
{
    uint32_t signal;
    imu_data_t imu_data;

    for(;;) {
        if (xQueueReceive(sample_queue, &signal, portMAX_DELAY)) {
            // Read IMU sensor (MPU6050)
            read_mpu6050(&imu_data);

            // Process data
            printf("Accel: %d, %d, %d | Gyro: %d, %d, %d\n",
                   imu_data.accel_x, imu_data.accel_y, imu_data.accel_z,
                   imu_data.gyro_x, imu_data.gyro_y, imu_data.gyro_z);
        }
    }
}

void app_main(void)
{
    // Create queue
    sample_queue = xQueueCreate(10, sizeof(uint32_t));

    // Create sensor task
    xTaskCreate(sensor_task, "sensor_task", 4096, NULL, 10, NULL);

    // Configure timer (100ms = 100000us)
    gptimer_config_t timer_config = {
        .clk_src = GPTIMER_CLK_SRC_DEFAULT,
        .direction = GPTIMER_COUNT_UP,
        .resolution_hz = 1000000,
    };
    ESP_ERROR_CHECK(gptimer_new_timer(&timer_config, &gptimer));

    gptimer_alarm_config_t alarm_config = {
        .reload_count = 0,
        .alarm_count = 100000,  // 100ms
        .flags.auto_reload_on_alarm = true,
    };
    ESP_ERROR_CHECK(gptimer_set_alarm_action(gptimer, &alarm_config));

    gptimer_event_callbacks_t cbs = {
        .on_alarm = timer_callback,
    };
    ESP_ERROR_CHECK(gptimer_register_event_callbacks(gptimer, &cbs, NULL));

    ESP_ERROR_CHECK(gptimer_enable(gptimer));
    ESP_ERROR_CHECK(gptimer_start(gptimer));

    printf("Sensor sampling started at %d ms intervals\n", SAMPLE_PERIOD_MS);
}
```

### Example 3: Multi-Frequency LED Blinking (Two LEDs)
```c
#include "driver/gptimer.h"
#include "driver/gpio.h"

#define LED1_GPIO 10
#define LED2_GPIO 11

static gptimer_handle_t timer1 = NULL;
static gptimer_handle_t timer2 = NULL;
static bool led1_state = false;
static bool led2_state = false;

static bool IRAM_ATTR timer1_callback(gptimer_handle_t timer,
                                       const gptimer_alarm_event_data_t *edata,
                                       void *user_ctx)
{
    led1_state = !led1_state;
    gpio_set_level(LED1_GPIO, led1_state);
    return false;
}

static bool IRAM_ATTR timer2_callback(gptimer_handle_t timer,
                                       const gptimer_alarm_event_data_t *edata,
                                       void *user_ctx)
{
    led2_state = !led2_state;
    gpio_set_level(LED2_GPIO, led2_state);
    return false;
}

void app_main(void)
{
    // Configure LEDs
    gpio_reset_pin(LED1_GPIO);
    gpio_set_direction(LED1_GPIO, GPIO_MODE_OUTPUT);
    gpio_reset_pin(LED2_GPIO);
    gpio_set_direction(LED2_GPIO, GPIO_MODE_OUTPUT);

    // Timer 1: 1 Hz (500ms period)
    gptimer_config_t timer_config = {
        .clk_src = GPTIMER_CLK_SRC_DEFAULT,
        .direction = GPTIMER_COUNT_UP,
        .resolution_hz = 1000000,
    };
    ESP_ERROR_CHECK(gptimer_new_timer(&timer_config, &timer1));

    gptimer_alarm_config_t alarm_config1 = {
        .alarm_count = 500000,  // 500ms
        .flags.auto_reload_on_alarm = true,
    };
    ESP_ERROR_CHECK(gptimer_set_alarm_action(timer1, &alarm_config1));

    gptimer_event_callbacks_t cbs1 = {
        .on_alarm = timer1_callback,
    };
    ESP_ERROR_CHECK(gptimer_register_event_callbacks(timer1, &cbs1, NULL));

    // Timer 2: 2 Hz (250ms period)
    ESP_ERROR_CHECK(gptimer_new_timer(&timer_config, &timer2));

    gptimer_alarm_config_t alarm_config2 = {
        .alarm_count = 250000,  // 250ms
        .flags.auto_reload_on_alarm = true,
    };
    ESP_ERROR_CHECK(gptimer_set_alarm_action(timer2, &alarm_config2));

    gptimer_event_callbacks_t cbs2 = {
        .on_alarm = timer2_callback,
    };
    ESP_ERROR_CHECK(gptimer_register_event_callbacks(timer2, &cbs2, NULL));

    // Start both timers
    ESP_ERROR_CHECK(gptimer_enable(timer1));
    ESP_ERROR_CHECK(gptimer_start(timer1));
    ESP_ERROR_CHECK(gptimer_enable(timer2));
    ESP_ERROR_CHECK(gptimer_start(timer2));

    printf("Two LEDs blinking at 1 Hz and 2 Hz\n");
}
```

### Example 4: Variable Timer Period (Changeable at Runtime)
```c
static gptimer_handle_t gptimer = NULL;

void change_timer_frequency(uint32_t frequency_hz)
{
    // Stop timer
    ESP_ERROR_CHECK(gptimer_stop(gptimer));
    ESP_ERROR_CHECK(gptimer_disable(gptimer));

    // Calculate new period (half period for toggle)
    uint64_t period_us = (1000000 / frequency_hz) / 2;

    // Reconfigure alarm
    gptimer_alarm_config_t alarm_config = {
        .reload_count = 0,
        .alarm_count = period_us,
        .flags.auto_reload_on_alarm = true,
    };
    ESP_ERROR_CHECK(gptimer_set_alarm_action(gptimer, &alarm_config));

    // Restart timer
    ESP_ERROR_CHECK(gptimer_enable(gptimer));
    ESP_ERROR_CHECK(gptimer_start(gptimer));

    printf("Timer frequency changed to %lu Hz\n", frequency_hz);
}
```

## Usage in Tasks

### Task: Timer_triggered_MPU6050_average_display
```c
#define NUM_SAMPLES 10
#define SAMPLE_PERIOD_US 100000  // 100ms

static imu_data_t samples[NUM_SAMPLES];
static int sample_index = 0;
static bool samples_ready = false;

static bool IRAM_ATTR timer_callback(gptimer_handle_t timer,
                                      const gptimer_alarm_event_data_t *edata,
                                      void *user_ctx)
{
    BaseType_t high_task_awoken = pdFALSE;
    uint32_t signal = 1;
    xQueueSendFromISR(sample_queue, &signal, &high_task_awoken);
    return high_task_awoken == pdTRUE;
}

static void sensor_task(void *arg)
{
    uint32_t signal;

    for(;;) {
        if (xQueueReceive(sample_queue, &signal, portMAX_DELAY)) {
            // Read sensor
            read_mpu6050(&samples[sample_index]);
            sample_index++;

            // Calculate average after 10 samples
            if (sample_index >= NUM_SAMPLES) {
                sample_index = 0;
                samples_ready = true;

                // Calculate averages
                float avg_accel_x = 0, avg_accel_y = 0, avg_accel_z = 0;
                float avg_gyro_x = 0, avg_gyro_y = 0, avg_gyro_z = 0;

                for (int i = 0; i < NUM_SAMPLES; i++) {
                    avg_accel_x += samples[i].accel_x;
                    avg_accel_y += samples[i].accel_y;
                    avg_accel_z += samples[i].accel_z;
                    avg_gyro_x += samples[i].gyro_x;
                    avg_gyro_y += samples[i].gyro_y;
                    avg_gyro_z += samples[i].gyro_z;
                }

                avg_accel_x /= NUM_SAMPLES;
                avg_accel_y /= NUM_SAMPLES;
                avg_accel_z /= NUM_SAMPLES;
                avg_gyro_x /= NUM_SAMPLES;
                avg_gyro_y /= NUM_SAMPLES;
                avg_gyro_z /= NUM_SAMPLES;

                // Display on LCD
                lcd_clear();
                lcd_printf("Accel:%.2f %.2f %.2f", avg_accel_x, avg_accel_y, avg_accel_z);
                lcd_set_cursor(0, 1);
                lcd_printf("Gyro:%.2f %.2f %.2f", avg_gyro_x, avg_gyro_y, avg_gyro_z);
            }
        }
    }
}
```

## Timer Control Functions
```c
// Pause timer
ESP_ERROR_CHECK(gptimer_stop(gptimer));

// Resume timer
ESP_ERROR_CHECK(gptimer_start(gptimer));

// Get current counter value
uint64_t counter_value;
ESP_ERROR_CHECK(gptimer_get_raw_count(gptimer, &counter_value));

// Set counter value
ESP_ERROR_CHECK(gptimer_set_raw_count(gptimer, 0));

// Delete timer
ESP_ERROR_CHECK(gptimer_disable(gptimer));
ESP_ERROR_CHECK(gptimer_del_timer(gptimer));
```

## Best Practices
1. **Keep callbacks minimal** - Use queues to defer work to tasks
2. **Use IRAM_ATTR** - Mark callbacks for execution from internal RAM
3. **Accurate timing** - Use appropriate resolution_hz for your needs
4. **Resource cleanup** - Properly disable and delete timers when done
5. **Queue sizing** - Size queues to handle burst events

## Common Pitfalls
- ❌ Long timer callbacks (causes system instability)
- ❌ Not using queues (blocking operations in ISR)
- ❌ Incorrect period calculations
- ❌ Forgetting IRAM_ATTR on callbacks
- ❌ Not handling timer overflow for long periods

## Related Skills
- `gpio-interrupts-esp32-esp-idf.md` - GPIO-based interrupts
- `pwm-control-esp32-esp-idf.md` - PWM generation with timers
- `freertos-basics-esp32.md` - FreeRTOS queue and task management

## References
- ESP-IDF GPTimer Documentation: https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/peripherals/gptimer.html
- ESP32 Technical Reference Manual: Timer Group chapter
