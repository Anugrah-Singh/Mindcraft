---
name: PWM Control - ESP32 + ESP-IDF
description: This skill covers PWM (Pulse Width Modulation) generation on ESP32 using ESP-IDF's LEDC (LED Control
---
# PWM Control - ESP32 + ESP-IDF

## Overview
This skill covers PWM (Pulse Width Modulation) generation on ESP32 using ESP-IDF's LEDC (LED Control) peripheral. PWM is essential for controlling LED brightness, motor speed, buzzer tones, and servo positions.

## Target Platform
- **MCU:** ESP32 (ESP32-S3, ESP32-C3, etc.)
- **Framework:** ESP-IDF
- **API:** LEDC (LED Control) peripheral
- **Channels:** 8 channels (6 on some variants)
- **Resolution:** Up to 20-bit duty cycle resolution

## Key Concepts
- **Duty Cycle:** Percentage of time signal is HIGH (0-100%)
- **Frequency:** Rate of PWM oscillation (Hz)
- **Resolution:** Bit-width of duty cycle control (8-20 bits)
- **LEDC Peripheral:** Hardware PWM generator, independent of CPU
- **Speed Mode:** High-speed or low-speed mode (affects available features)

## PWM Parameters Relationship
```
Max Duty = 2^resolution - 1
Example: 13-bit resolution → Max duty = 8191 (0-8191)

Actual duty cycle % = (duty_value / max_duty) × 100%
Example: duty = 4095 at 13-bit → 50% duty cycle

Frequency limits:
- Higher frequency → Lower max resolution
- Lower frequency → Higher max resolution
```

## Implementation Pattern

### Basic PWM Setup
```c
#include "driver/ledc.h"
#include "esp_log.h"

#define PWM_GPIO        10
#define PWM_FREQUENCY   1000    // 1 kHz
#define PWM_RESOLUTION  LEDC_TIMER_13_BIT  // 13-bit resolution (0-8191)
#define PWM_CHANNEL     LEDC_CHANNEL_0
#define PWM_TIMER       LEDC_TIMER_0

static const char *TAG = "PWM";

void pwm_init(void)
{
    // Configure timer
    ledc_timer_config_t timer_config = {
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .duty_resolution = PWM_RESOLUTION,
        .timer_num = PWM_TIMER,
        .freq_hz = PWM_FREQUENCY,
        .clk_cfg = LEDC_AUTO_CLK,
    };
    ESP_ERROR_CHECK(ledc_timer_config(&timer_config));

    // Configure channel
    ledc_channel_config_t channel_config = {
        .gpio_num = PWM_GPIO,
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .channel = PWM_CHANNEL,
        .timer_sel = PWM_TIMER,
        .duty = 0,  // Start with 0% duty cycle
        .hpoint = 0,
    };
    ESP_ERROR_CHECK(ledc_channel_config(&channel_config));

    ESP_LOGI(TAG, "PWM initialized on GPIO %d", PWM_GPIO);
}

void pwm_set_duty(uint32_t duty)
{
    ESP_ERROR_CHECK(ledc_set_duty(LEDC_LOW_SPEED_MODE, PWM_CHANNEL, duty));
    ESP_ERROR_CHECK(ledc_update_duty(LEDC_LOW_SPEED_MODE, PWM_CHANNEL));
}

void pwm_set_duty_percent(float percent)
{
    // Convert percentage to duty value
    uint32_t max_duty = (1 << PWM_RESOLUTION) - 1;  // 2^13 - 1 = 8191
    uint32_t duty = (uint32_t)(max_duty * percent / 100.0);
    pwm_set_duty(duty);
}

void pwm_set_frequency(uint32_t frequency_hz)
{
    ESP_ERROR_CHECK(ledc_set_freq(LEDC_LOW_SPEED_MODE, PWM_TIMER, frequency_hz));
}
```

## Complete Examples

### Example 1: LED Brightness Control (Breathing LED)
```c
#include <stdio.h>
#include "driver/ledc.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#define LED_GPIO 10
#define LED_FREQUENCY 5000  // 5 kHz (smooth for LEDs)
#define LED_RESOLUTION LEDC_TIMER_13_BIT

void led_pwm_init(void)
{
    ledc_timer_config_t timer_config = {
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .duty_resolution = LED_RESOLUTION,
        .timer_num = LEDC_TIMER_0,
        .freq_hz = LED_FREQUENCY,
        .clk_cfg = LEDC_AUTO_CLK,
    };
    ESP_ERROR_CHECK(ledc_timer_config(&timer_config));

    ledc_channel_config_t channel_config = {
        .gpio_num = LED_GPIO,
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .channel = LEDC_CHANNEL_0,
        .timer_sel = LEDC_TIMER_0,
        .duty = 0,
        .hpoint = 0,
    };
    ESP_ERROR_CHECK(ledc_channel_config(&channel_config));
}

void app_main(void)
{
    led_pwm_init();

    uint32_t max_duty = (1 << LED_RESOLUTION) - 1;  // 8191
    bool increasing = true;

    // Breathing effect: 50 levels, 10ms per level = 1 Hz breathing
    int num_steps = 50;
    int delay_ms = 10;

    while (1) {
        for (int step = 0; step < num_steps; step++) {
            uint32_t duty;

            if (increasing) {
                duty = (max_duty * step) / num_steps;
            } else {
                duty = max_duty - (max_duty * step) / num_steps;
            }

            ledc_set_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0, duty);
            ledc_update_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0);

            vTaskDelay(pdMS_TO_TICKS(delay_ms));
        }

        increasing = !increasing;
    }
}
```

### Example 2: Passive Buzzer Tone Generation
```c
#define BUZZER_GPIO 11
#define BUZZER_RESOLUTION LEDC_TIMER_10_BIT  // Lower resolution for audio

// Musical note frequencies (Hz)
#define NOTE_C4  262
#define NOTE_D4  294
#define NOTE_E4  330
#define NOTE_F4  349
#define NOTE_G4  392
#define NOTE_A4  440
#define NOTE_B4  494
#define NOTE_C5  523

void buzzer_pwm_init(void)
{
    ledc_timer_config_t timer_config = {
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .duty_resolution = BUZZER_RESOLUTION,
        .timer_num = LEDC_TIMER_1,
        .freq_hz = NOTE_C4,  // Default frequency
        .clk_cfg = LEDC_AUTO_CLK,
    };
    ESP_ERROR_CHECK(ledc_timer_config(&timer_config));

    ledc_channel_config_t channel_config = {
        .gpio_num = BUZZER_GPIO,
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .channel = LEDC_CHANNEL_1,
        .timer_sel = LEDC_TIMER_1,
        .duty = 0,  // Start silent
        .hpoint = 0,
    };
    ESP_ERROR_CHECK(ledc_channel_config(&channel_config));
}

void buzzer_play_tone(uint32_t frequency_hz, uint32_t duration_ms)
{
    if (frequency_hz == 0) {
        // Silence
        ledc_set_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_1, 0);
        ledc_update_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_1);
    } else {
        // Set frequency
        ledc_set_freq(LEDC_LOW_SPEED_MODE, LEDC_TIMER_1, frequency_hz);

        // Set 50% duty cycle for clear tone
        uint32_t duty = (1 << BUZZER_RESOLUTION) / 2;
        ledc_set_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_1, duty);
        ledc_update_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_1);
    }

    vTaskDelay(pdMS_TO_TICKS(duration_ms));

    // Stop tone
    ledc_set_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_1, 0);
    ledc_update_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_1);
}

void app_main(void)
{
    buzzer_pwm_init();

    // Play a simple melody
    int melody[] = {NOTE_C4, NOTE_D4, NOTE_E4, NOTE_F4, NOTE_G4, NOTE_A4, NOTE_B4, NOTE_C5};
    int note_duration = 500;  // ms

    while (1) {
        for (int i = 0; i < 8; i++) {
            buzzer_play_tone(melody[i], note_duration);
            vTaskDelay(pdMS_TO_TICKS(50));  // Small gap between notes
        }

        vTaskDelay(pdMS_TO_TICKS(1000));  // Pause before repeating
    }
}
```

### Example 3: LCD Backlight Control with Photoresistor
```c
#include "esp_adc/adc_oneshot.h"

#define BACKLIGHT_GPIO 14
#define PHOTO_ADC_CHANNEL ADC_CHANNEL_0

static adc_oneshot_unit_handle_t adc_handle;

void backlight_pwm_init(void)
{
    ledc_timer_config_t timer_config = {
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .duty_resolution = LEDC_TIMER_13_BIT,
        .timer_num = LEDC_TIMER_0,
        .freq_hz = 5000,
        .clk_cfg = LEDC_AUTO_CLK,
    };
    ESP_ERROR_CHECK(ledc_timer_config(&timer_config));

    ledc_channel_config_t channel_config = {
        .gpio_num = BACKLIGHT_GPIO,
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .channel = LEDC_CHANNEL_0,
        .timer_sel = LEDC_TIMER_0,
        .duty = 4095,  // Start at 50% brightness
        .hpoint = 0,
    };
    ESP_ERROR_CHECK(ledc_channel_config(&channel_config));
}

void adc_init(void)
{
    adc_oneshot_unit_init_cfg_t init_config = {
        .unit_id = ADC_UNIT_1,
    };
    ESP_ERROR_CHECK(adc_oneshot_new_unit(&init_config, &adc_handle));

    adc_oneshot_chan_cfg_t config = {
        .bitwidth = ADC_BITWIDTH_12,
        .atten = ADC_ATTEN_DB_11,
    };
    ESP_ERROR_CHECK(adc_oneshot_config_channel(adc_handle, PHOTO_ADC_CHANNEL, &config));
}

void app_main(void)
{
    backlight_pwm_init();
    adc_init();

    while (1) {
        // Read light level
        int adc_value;
        ESP_ERROR_CHECK(adc_oneshot_read(adc_handle, PHOTO_ADC_CHANNEL, &adc_value));

        // Map ADC (0-4095) to PWM duty (0-8191)
        // Invert: darker environment → brighter backlight
        uint32_t duty = 8191 - ((adc_value * 8191) / 4095);

        // Apply minimum brightness (10%)
        uint32_t min_duty = 819;  // 10% of 8191
        if (duty < min_duty) duty = min_duty;

        ledc_set_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0, duty);
        ledc_update_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0);

        printf("Light: %d, Backlight duty: %lu\n", adc_value, duty);

        vTaskDelay(pdMS_TO_TICKS(200));
    }
}
```

### Example 4: Variable Frequency Buzzer (Distance-Based)
```c
// For parking sensor: closer distance → higher frequency

void control_buzzer_by_distance(float distance_cm)
{
    if (distance_cm < 5 || distance_cm > 200) {
        // Out of range - silence
        ledc_set_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_1, 0);
        ledc_update_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_1);
        return;
    }

    // Map distance (5-200 cm) to frequency (2000-100 Hz)
    // Closer = higher frequency
    uint32_t frequency = 100 + ((200 - distance_cm) * 1900 / 195);

    // Set frequency
    ledc_set_freq(LEDC_LOW_SPEED_MODE, LEDC_TIMER_1, frequency);

    // Set 50% duty cycle
    uint32_t duty = (1 << BUZZER_RESOLUTION) / 2;
    ledc_set_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_1, duty);
    ledc_update_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_1);

    printf("Distance: %.1f cm, Frequency: %lu Hz\n", distance_cm, frequency);
}
```

### Example 5: Joystick-Controlled Buzzer Pitch
```c
// For Joystick_Music task

void app_main(void)
{
    buzzer_pwm_init();
    joystick_adc_init();

    while (1) {
        // Read joystick Y-axis
        int adc_value;
        ESP_ERROR_CHECK(adc_oneshot_read(adc_handle, JOYSTICK_Y_CHANNEL, &adc_value));

        // Map ADC (0-4095) to frequency (100-2000 Hz)
        uint32_t frequency = 100 + (adc_value * 1900 / 4095);

        // Set frequency and play tone
        ledc_set_freq(LEDC_LOW_SPEED_MODE, LEDC_TIMER_1, frequency);

        uint32_t duty = (1 << BUZZER_RESOLUTION) / 2;
        ledc_set_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_1, duty);
        ledc_update_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_1);

        printf("Joystick: %d, Frequency: %lu Hz\n", adc_value, frequency);

        vTaskDelay(pdMS_TO_TICKS(50));
    }
}
```

## Hardware Fade Feature (Smooth Transitions)

```c
void pwm_fade_to(uint32_t target_duty, uint32_t fade_time_ms)
{
    // Configure fade function
    ledc_set_fade_with_time(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0, target_duty, fade_time_ms);

    // Start fade
    ledc_fade_start(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0, LEDC_FADE_NO_WAIT);
}

void led_breathing_with_fade(void)
{
    uint32_t max_duty = (1 << LED_RESOLUTION) - 1;

    // Install fade service
    ledc_fade_func_install(0);

    while (1) {
        // Fade up
        pwm_fade_to(max_duty, 1000);  // 1 second fade up
        vTaskDelay(pdMS_TO_TICKS(1000));

        // Fade down
        pwm_fade_to(0, 1000);  // 1 second fade down
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}
```

## Multiple PWM Channels

```c
#define LED1_GPIO 10
#define LED2_GPIO 11
#define BUZZER_GPIO 13

void multi_channel_pwm_init(void)
{
    // Configure timer (shared by all channels)
    ledc_timer_config_t timer_config = {
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .duty_resolution = LEDC_TIMER_13_BIT,
        .timer_num = LEDC_TIMER_0,
        .freq_hz = 5000,
        .clk_cfg = LEDC_AUTO_CLK,
    };
    ESP_ERROR_CHECK(ledc_timer_config(&timer_config));

    // Configure LED1 channel
    ledc_channel_config_t led1_config = {
        .gpio_num = LED1_GPIO,
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .channel = LEDC_CHANNEL_0,
        .timer_sel = LEDC_TIMER_0,
        .duty = 0,
        .hpoint = 0,
    };
    ESP_ERROR_CHECK(ledc_channel_config(&led1_config));

    // Configure LED2 channel
    ledc_channel_config_t led2_config = {
        .gpio_num = LED2_GPIO,
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .channel = LEDC_CHANNEL_1,
        .timer_sel = LEDC_TIMER_0,
        .duty = 0,
        .hpoint = 0,
    };
    ESP_ERROR_CHECK(ledc_channel_config(&led2_config));

    // Configure buzzer channel (separate timer for different frequency)
    ledc_timer_config_t buzzer_timer = {
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .duty_resolution = LEDC_TIMER_10_BIT,
        .timer_num = LEDC_TIMER_1,
        .freq_hz = 1000,
        .clk_cfg = LEDC_AUTO_CLK,
    };
    ESP_ERROR_CHECK(ledc_timer_config(&buzzer_timer));

    ledc_channel_config_t buzzer_config = {
        .gpio_num = BUZZER_GPIO,
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .channel = LEDC_CHANNEL_2,
        .timer_sel = LEDC_TIMER_1,
        .duty = 0,
        .hpoint = 0,
    };
    ESP_ERROR_CHECK(ledc_channel_config(&buzzer_config));
}
```

## Resolution and Frequency Trade-offs

```c
// Example configurations:

// High resolution, low frequency (LEDs, slow PWM)
// 20-bit, 1 kHz - very smooth control
ledc_timer.duty_resolution = LEDC_TIMER_20_BIT;
ledc_timer.freq_hz = 1000;

// Medium resolution, medium frequency (general purpose)
// 13-bit, 5 kHz - good for most applications
ledc_timer.duty_resolution = LEDC_TIMER_13_BIT;
ledc_timer.freq_hz = 5000;

// Low resolution, high frequency (audio, buzzers)
// 10-bit, 20 kHz - for high-frequency applications
ledc_timer.duty_resolution = LEDC_TIMER_10_BIT;
ledc_timer.freq_hz = 20000;
```

## Best Practices
1. **Choose appropriate resolution** - Higher resolution for smooth control, lower for high frequencies
2. **LED frequency** - Use 5-20 kHz to avoid visible flicker
3. **Buzzer frequency** - Match desired audio frequency (100 Hz - 20 kHz)
4. **50% duty for buzzers** - Produces clearest tone
5. **Fade feature** - Use hardware fade for smooth LED transitions

## Common Pitfalls
- ❌ Too high frequency for resolution (won't work)
- ❌ Visible LED flicker (frequency too low, use > 1kHz)
- ❌ Forgetting ledc_update_duty() (changes won't apply)
- ❌ Wrong duty calculation (exceeding max duty value)
- ❌ Sharing timer between incompatible frequencies

## Related Skills
- `adc-reading-esp32-esp-idf.md` - Reading sensors to control PWM
- `gpio-basics-esp32-esp-idf.md` - Basic GPIO operations
- `hardware-timers-esp32-esp-idf.md` - Timer-based PWM effects

## References
- ESP-IDF LEDC Documentation: https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/peripherals/ledc.html
- PWM Theory: https://learn.sparkfun.com/tutorials/pulse-width-modulation
