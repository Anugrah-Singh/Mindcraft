---
name: ADC Reading - ESP32 + ESP-IDF
description: This skill covers ADC (Analog-to-Digital Converter) usage on ESP32 using ESP-IDF framework. ADC enab
---
# ADC Reading - ESP32 + ESP-IDF

## Overview
This skill covers ADC (Analog-to-Digital Converter) usage on ESP32 using ESP-IDF framework. ADC enables reading analog sensors like photoresistors, temperature sensors (TMP36), joysticks, water level sensors, and potentiometers.

## Target Platform
- **MCU:** ESP32 (ESP32-S3, ESP32-C3, etc.)
- **Framework:** ESP-IDF
- **API:** ADC Oneshot driver
- **Resolution:** 12-bit (0-4095) by default
- **Voltage Range:** 0-3.3V (with attenuation settings)

## Key Concepts
- **ADC Channels:** Multiple ADC channels mapped to GPIO pins
- **Attenuation:** Adjusts input voltage range (0dB, 2.5dB, 6dB, 11dB)
- **Bit Width:** Resolution of conversion (9-12 bits)
- **Calibration:** Improves accuracy by compensating for manufacturing variations
- **ADC Unit:** ESP32 has ADC1 and ADC2 (ADC2 conflicts with WiFi)

## ESP32-S3 ADC Pin Mapping
```
ADC1:
GPIO 1-10 -> ADC1_CH0 to ADC1_CH9

ADC2:
GPIO 11-20 -> ADC2_CH0 to ADC2_CH9
```

**Note:** Use ADC1 when WiFi is enabled, as ADC2 is used by WiFi driver.

## Implementation Pattern

### Basic ADC Setup (Oneshot Mode)
```c
#include "esp_adc/adc_oneshot.h"
#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"
#include "esp_log.h"

#define ADC_CHANNEL     ADC_CHANNEL_0  // GPIO 1 on ESP32-S3
#define ADC_ATTEN       ADC_ATTEN_DB_11  // 0-3.3V range
#define ADC_WIDTH       ADC_BITWIDTH_12  // 12-bit resolution

static adc_oneshot_unit_handle_t adc1_handle;
static adc_cali_handle_t adc1_cali_handle = NULL;

void setup_adc(void)
{
    // Initialize ADC
    adc_oneshot_unit_init_cfg_t init_config = {
        .unit_id = ADC_UNIT_1,
    };
    ESP_ERROR_CHECK(adc_oneshot_new_unit(&init_config, &adc1_handle));

    // Configure ADC channel
    adc_oneshot_chan_cfg_t config = {
        .bitwidth = ADC_WIDTH,
        .atten = ADC_ATTEN,
    };
    ESP_ERROR_CHECK(adc_oneshot_config_channel(adc1_handle, ADC_CHANNEL, &config));

    // Setup calibration
    adc_cali_curve_fitting_config_t cali_config = {
        .unit_id = ADC_UNIT_1,
        .atten = ADC_ATTEN,
        .bitwidth = ADC_WIDTH,
    };
    ESP_ERROR_CHECK(adc_cali_create_scheme_curve_fitting(&cali_config, &adc1_cali_handle));

    ESP_LOGI("ADC", "ADC initialized");
}

int read_adc_raw(void)
{
    int adc_raw;
    ESP_ERROR_CHECK(adc_oneshot_read(adc1_handle, ADC_CHANNEL, &adc_raw));
    return adc_raw;
}

int read_adc_voltage(void)
{
    int adc_raw = read_adc_raw();
    int voltage;
    ESP_ERROR_CHECK(adc_cali_raw_to_voltage(adc1_cali_handle, adc_raw, &voltage));
    return voltage;  // Returns millivolts
}
```

### Attenuation Settings
```c
// ADC_ATTEN_DB_0: 0-1.1V range (most accurate for low voltages)
// ADC_ATTEN_DB_2_5: 0-1.5V range
// ADC_ATTEN_DB_6: 0-2.2V range
// ADC_ATTEN_DB_11: 0-3.3V range (recommended for 3.3V sensors)

adc_oneshot_chan_cfg_t config = {
    .bitwidth = ADC_BITWIDTH_12,
    .atten = ADC_ATTEN_DB_11,  // Choose based on sensor voltage range
};
```

## Complete Examples

### Example 1: TMP36 Temperature Sensor
```c
#include <stdio.h>
#include "esp_adc/adc_oneshot.h"
#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#define TMP36_ADC_CHANNEL  ADC_CHANNEL_0  // GPIO 1
#define ADC_ATTEN          ADC_ATTEN_DB_11
#define ADC_WIDTH          ADC_BITWIDTH_12

static adc_oneshot_unit_handle_t adc1_handle;
static adc_cali_handle_t adc1_cali_handle = NULL;

void setup_adc(void)
{
    adc_oneshot_unit_init_cfg_t init_config = {
        .unit_id = ADC_UNIT_1,
    };
    ESP_ERROR_CHECK(adc_oneshot_new_unit(&init_config, &adc1_handle));

    adc_oneshot_chan_cfg_t config = {
        .bitwidth = ADC_WIDTH,
        .atten = ADC_ATTEN,
    };
    ESP_ERROR_CHECK(adc_oneshot_config_channel(adc1_handle, TMP36_ADC_CHANNEL, &config));

    adc_cali_curve_fitting_config_t cali_config = {
        .unit_id = ADC_UNIT_1,
        .atten = ADC_ATTEN,
        .bitwidth = ADC_WIDTH,
    };
    ESP_ERROR_CHECK(adc_cali_create_scheme_curve_fitting(&cali_config, &adc1_cali_handle));
}

float read_tmp36_temperature(void)
{
    int adc_raw, voltage_mv;

    // Read ADC
    ESP_ERROR_CHECK(adc_oneshot_read(adc1_handle, TMP36_ADC_CHANNEL, &adc_raw));

    // Convert to voltage
    ESP_ERROR_CHECK(adc_cali_raw_to_voltage(adc1_cali_handle, adc_raw, &voltage_mv));

    // TMP36 formula: Temp (°C) = (Voltage in mV - 500) / 10
    float temp_c = (voltage_mv - 500.0) / 10.0;

    // Convert to Fahrenheit
    float temp_f = (temp_c * 9.0 / 5.0) + 32.0;

    return temp_f;
}

void app_main(void)
{
    setup_adc();

    while (1) {
        float temperature = read_tmp36_temperature();
        printf("Temperature: %.2f °F\n", temperature);

        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}
```

### Example 2: Photoresistor (Light Sensor)
```c
#include "esp_adc/adc_oneshot.h"
#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"
#include "driver/gpio.h"

#define PHOTO_ADC_CHANNEL  ADC_CHANNEL_0  // GPIO 1
#define LED_GPIO           10
#define LIGHT_THRESHOLD    2000  // ADC raw value threshold

static adc_oneshot_unit_handle_t adc1_handle;

void setup_photoresistor(void)
{
    // Setup ADC
    adc_oneshot_unit_init_cfg_t init_config = {
        .unit_id = ADC_UNIT_1,
    };
    ESP_ERROR_CHECK(adc_oneshot_new_unit(&init_config, &adc1_handle));

    adc_oneshot_chan_cfg_t config = {
        .bitwidth = ADC_BITWIDTH_12,
        .atten = ADC_ATTEN_DB_11,
    };
    ESP_ERROR_CHECK(adc_oneshot_config_channel(adc1_handle, PHOTO_ADC_CHANNEL, &config));

    // Setup LED
    gpio_reset_pin(LED_GPIO);
    gpio_set_direction(LED_GPIO, GPIO_MODE_OUTPUT);
}

void app_main(void)
{
    setup_photoresistor();

    while (1) {
        int adc_value;
        ESP_ERROR_CHECK(adc_oneshot_read(adc1_handle, PHOTO_ADC_CHANNEL, &adc_value));

        printf("Light level: %d\n", adc_value);

        // Turn on LED if dark (low light level)
        if (adc_value < LIGHT_THRESHOLD) {
            gpio_set_level(LED_GPIO, 1);
            printf("Dark - LED ON\n");
        } else {
            gpio_set_level(LED_GPIO, 0);
            printf("Bright - LED OFF\n");
        }

        vTaskDelay(pdMS_TO_TICKS(500));
    }
}
```

### Example 3: Joystick (2-Axis Analog Input)
```c
#define JOYSTICK_X_CHANNEL  ADC_CHANNEL_0  // GPIO 1
#define JOYSTICK_Y_CHANNEL  ADC_CHANNEL_1  // GPIO 2
#define BUZZER_GPIO         11

static adc_oneshot_unit_handle_t adc1_handle;

typedef struct {
    int x;
    int y;
} joystick_pos_t;

void setup_joystick(void)
{
    adc_oneshot_unit_init_cfg_t init_config = {
        .unit_id = ADC_UNIT_1,
    };
    ESP_ERROR_CHECK(adc_oneshot_new_unit(&init_config, &adc1_handle));

    adc_oneshot_chan_cfg_t config = {
        .bitwidth = ADC_BITWIDTH_12,
        .atten = ADC_ATTEN_DB_11,
    };
    ESP_ERROR_CHECK(adc_oneshot_config_channel(adc1_handle, JOYSTICK_X_CHANNEL, &config));
    ESP_ERROR_CHECK(adc_oneshot_config_channel(adc1_handle, JOYSTICK_Y_CHANNEL, &config));
}

joystick_pos_t read_joystick(void)
{
    joystick_pos_t pos;
    ESP_ERROR_CHECK(adc_oneshot_read(adc1_handle, JOYSTICK_X_CHANNEL, &pos.x));
    ESP_ERROR_CHECK(adc_oneshot_read(adc1_handle, JOYSTICK_Y_CHANNEL, &pos.y));
    return pos;
}

// Map joystick Y-axis to buzzer frequency (for Joystick_Music task)
uint32_t joystick_to_frequency(int adc_value)
{
    // Map ADC range (0-4095) to frequency range (100-2000 Hz)
    return 100 + (adc_value * 1900 / 4095);
}
```

### Example 4: Water Level Sensor with Bar Graph
```c
#include "lcd_hd44780.h"

#define WATER_ADC_CHANNEL  ADC_CHANNEL_0

void display_water_level_bar(int adc_value)
{
    // Map ADC value to bar graph (0-16 characters on LCD)
    int bar_length = (adc_value * 16) / 4095;

    lcd_clear();
    lcd_puts("Water Level:");
    lcd_set_cursor(0, 1);

    // Draw bar
    for (int i = 0; i < 16; i++) {
        if (i < bar_length) {
            lcd_putc(0xFF);  // Full block character
        } else {
            lcd_putc(' ');
        }
    }
}

void app_main(void)
{
    setup_adc();
    lcd_init();

    while (1) {
        int adc_value;
        ESP_ERROR_CHECK(adc_oneshot_read(adc1_handle, WATER_ADC_CHANNEL, &adc_value));

        display_water_level_bar(adc_value);
        printf("Water level ADC: %d\n", adc_value);

        vTaskDelay(pdMS_TO_TICKS(200));
    }
}
```

## Multi-Channel Reading
```c
void read_multiple_channels(void)
{
    int channel0_raw, channel1_raw, channel2_raw;

    ESP_ERROR_CHECK(adc_oneshot_read(adc1_handle, ADC_CHANNEL_0, &channel0_raw));
    ESP_ERROR_CHECK(adc_oneshot_read(adc1_handle, ADC_CHANNEL_1, &channel1_raw));
    ESP_ERROR_CHECK(adc_oneshot_read(adc1_handle, ADC_CHANNEL_2, &channel2_raw));

    printf("CH0: %d, CH1: %d, CH2: %d\n", channel0_raw, channel1_raw, channel2_raw);
}
```

## Averaging for Noise Reduction
```c
#define NUM_SAMPLES 10

int read_adc_averaged(adc_channel_t channel)
{
    int sum = 0;
    int adc_raw;

    for (int i = 0; i < NUM_SAMPLES; i++) {
        ESP_ERROR_CHECK(adc_oneshot_read(adc1_handle, channel, &adc_raw));
        sum += adc_raw;
        vTaskDelay(pdMS_TO_TICKS(1));  // Small delay between samples
    }

    return sum / NUM_SAMPLES;
}
```

## Usage in Tasks

### Task: NightLight - Automatic LED Control
```c
void app_main(void)
{
    setup_adc();
    setup_led();

    while (1) {
        int light_level = read_adc_raw();

        if (light_level < DARK_THRESHOLD) {
            gpio_set_level(LED_GPIO, 1);  // Turn on LED
        } else {
            gpio_set_level(LED_GPIO, 0);  // Turn off LED
        }

        vTaskDelay(pdMS_TO_TICKS(100));
    }
}
```

### Task: Automatic_Brightness_Control_for_LCD1602_Backlight
```c
#include "driver/ledc.h"

void control_lcd_backlight(void)
{
    int light_level = read_adc_raw();

    // Map ADC (0-4095) to PWM duty (0-8191 for 13-bit resolution)
    uint32_t duty = (light_level * 8191) / 4095;

    // Invert if needed (brighter backlight in darker environment)
    duty = 8191 - duty;

    ledc_set_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0, duty);
    ledc_update_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0);
}
```

## Mapping and Scaling Functions
```c
// Map ADC value to arbitrary range
int map_value(int value, int in_min, int in_max, int out_min, int out_max)
{
    return (value - in_min) * (out_max - out_min) / (in_max - in_min) + out_min;
}

// Example: Map ADC to percentage
int adc_to_percent(int adc_value)
{
    return map_value(adc_value, 0, 4095, 0, 100);
}

// Example: Map ADC to voltage (mV)
int adc_to_voltage(int adc_value)
{
    return map_value(adc_value, 0, 4095, 0, 3300);
}
```

## Best Practices
1. **Use calibration** - Improves accuracy significantly
2. **Choose correct attenuation** - Match sensor voltage range
3. **Average readings** - Reduces noise in measurements
4. **Use ADC1 with WiFi** - ADC2 conflicts with WiFi
5. **Consider conversion time** - Each read takes ~40-50us

## Common Pitfalls
- ❌ Using ADC2 with WiFi enabled (won't work)
- ❌ Wrong attenuation setting (readings out of range)
- ❌ No calibration (inaccurate readings)
- ❌ Reading too fast (noise in data)
- ❌ Floating input pins (unstable readings)

## Sensor-Specific Formulas

### TMP36 Temperature Sensor
```c
// Output: 10mV/°C with 500mV offset
// Temperature (°C) = (Voltage_mV - 500) / 10
float temp_c = (voltage_mv - 500.0) / 10.0;
float temp_f = (temp_c * 9.0 / 5.0) + 32.0;
```

### LM35 Temperature Sensor
```c
// Output: 10mV/°C with 0V at 0°C
// Temperature (°C) = Voltage_mV / 10
float temp_c = voltage_mv / 10.0;
```

### Voltage Divider (Generic)
```c
// For voltage divider: Vout = Vin * R2 / (R1 + R2)
// To get actual voltage: Vin = Vout * (R1 + R2) / R2
float actual_voltage = voltage_mv * (R1 + R2) / R2;
```

## Related Skills
- `pwm-control-esp32-esp-idf.md` - Using ADC values to control PWM
- `lcd1602-display-esp32-esp-idf.md` - Displaying ADC values on LCD
- `data-filtering-techniques.md` - Advanced filtering for noisy signals

## References
- ESP-IDF ADC Documentation: https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/peripherals/adc_oneshot.html
- ESP-IDF ADC Calibration: https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/peripherals/adc_calibration.html
- ESP32-S3 Datasheet: ADC section
