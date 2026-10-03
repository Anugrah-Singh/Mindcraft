---
name: GPIO and Timers - nRF52840 + Zephyr RTOS
description: This skill covers GPIO control and timer usage on nRF52840 using Zephyr RTOS. It includes digital I/
---
# GPIO and Timers - nRF52840 + Zephyr RTOS

## Overview
This skill covers GPIO control and timer usage on nRF52840 using Zephyr RTOS. It includes digital I/O operations, interrupts, and timer-based periodic tasks essential for embedded IoT applications.

## Target Platform
- **MCU:** nRF52840
- **Board:** nRF52840-DK, Arduino Nano 33 BLE
- **Framework:** Zephyr RTOS
- **API:** Zephyr GPIO and Timer APIs

## Key Concepts
- **Device Tree:** Zephyr uses device tree for hardware description
- **GPIO Spec:** References to GPIO pins defined in device tree
- **Callbacks:** Interrupt handlers registered via callback functions
- **Timers:** Kernel timers for periodic and one-shot tasks
- **Thread-safe:** All operations are thread-safe by design

## Device Tree Basics

### Device Tree Overlay (.overlay file)
```dts
/ {
    aliases {
        led0 = &led0;
        sw0 = &button0;
    };

    leds {
        compatible = "gpio-leds";
        led0: led_0 {
            gpios = <&gpio0 13 GPIO_ACTIVE_LOW>;
            label = "User LED";
        };
    };

    buttons {
        compatible = "gpio-keys";
        button0: button_0 {
            gpios = <&gpio1 15 (GPIO_PULL_UP | GPIO_ACTIVE_LOW)>;
            label = "User Button";
        };
    };
};
```

## GPIO Implementation

### Basic GPIO Setup
```c
#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/sys/printk.h>

// Get LED from device tree
#define LED0_NODE DT_ALIAS(led0)
static const struct gpio_dt_spec led = GPIO_DT_SPEC_GET(LED0_NODE, gpios);

// Get button from device tree
#define SW0_NODE DT_ALIAS(sw0)
static const struct gpio_dt_spec button = GPIO_DT_SPEC_GET(SW0_NODE, gpios);

int main(void)
{
    int ret;

    // Configure LED as output
    if (!gpio_is_ready_dt(&led)) {
        printk("LED device not ready\n");
        return -1;
    }

    ret = gpio_pin_configure_dt(&led, GPIO_OUTPUT_ACTIVE);
    if (ret < 0) {
        printk("Error configuring LED\n");
        return -1;
    }

    // Configure button as input
    if (!gpio_is_ready_dt(&button)) {
        printk("Button device not ready\n");
        return -1;
    }

    ret = gpio_pin_configure_dt(&button, GPIO_INPUT);
    if (ret < 0) {
        printk("Error configuring button\n");
        return -1;
    }

    printk("GPIO initialized\n");

    // Blink LED
    while (1) {
        gpio_pin_toggle_dt(&led);
        k_sleep(K_MSEC(500));
    }

    return 0;
}
```

### GPIO Operations
```c
// Set pin HIGH
gpio_pin_set_dt(&led, 1);

// Set pin LOW
gpio_pin_set_dt(&led, 0);

// Toggle pin
gpio_pin_toggle_dt(&led);

// Read pin state
int state = gpio_pin_get_dt(&button);

// Configure as output
gpio_pin_configure_dt(&led, GPIO_OUTPUT_ACTIVE);

// Configure as input with pull-up
gpio_pin_configure_dt(&button, GPIO_INPUT | GPIO_PULL_UP);
```

## GPIO Interrupts

### Basic Interrupt Setup
```c
#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>

static struct gpio_callback button_cb_data;

// Interrupt callback
void button_pressed(const struct device *dev, struct gpio_callback *cb, uint32_t pins)
{
    printk("Button pressed!\n");

    // Handle button press here
    // Keep ISR short - use work queue for longer tasks
}

int setup_button_interrupt(void)
{
    int ret;

    // Configure button as input
    if (!gpio_is_ready_dt(&button)) {
        return -1;
    }

    ret = gpio_pin_configure_dt(&button, GPIO_INPUT);
    if (ret < 0) {
        return ret;
    }

    // Configure interrupt
    ret = gpio_pin_interrupt_configure_dt(&button, GPIO_INT_EDGE_FALLING);
    if (ret < 0) {
        return ret;
    }

    // Initialize callback
    gpio_init_callback(&button_cb_data, button_pressed, BIT(button.pin));

    // Add callback
    ret = gpio_add_callback(button.port, &button_cb_data);
    if (ret < 0) {
        return ret;
    }

    printk("Button interrupt configured\n");
    return 0;
}
```

### Interrupt with Debouncing
```c
#define DEBOUNCE_DELAY_MS 50

static struct k_work_delayable button_work;
static volatile bool button_state = false;

void button_work_handler(struct k_work *work)
{
    // This runs in work queue context, not ISR
    button_state = !button_state;

    printk("Button state: %d\n", button_state);

    // Perform actions here (toggle LED, read sensor, etc.)
    gpio_pin_toggle_dt(&led);
}

void button_isr(const struct device *dev, struct gpio_callback *cb, uint32_t pins)
{
    // Schedule work with debounce delay
    k_work_reschedule(&button_work, K_MSEC(DEBOUNCE_DELAY_MS));
}

int main(void)
{
    // Initialize work queue
    k_work_init_delayable(&button_work, button_work_handler);

    // Setup GPIO
    gpio_pin_configure_dt(&led, GPIO_OUTPUT_ACTIVE);
    gpio_pin_configure_dt(&button, GPIO_INPUT);

    // Setup interrupt
    gpio_pin_interrupt_configure_dt(&button, GPIO_INT_EDGE_FALLING);
    gpio_init_callback(&button_cb_data, button_isr, BIT(button.pin));
    gpio_add_callback(button.port, &button_cb_data);

    printk("Button with debouncing ready\n");

    while (1) {
        k_sleep(K_FOREVER);
    }

    return 0;
}
```

## Timers

### Periodic Timer
```c
#include <zephyr/kernel.h>

static struct k_timer periodic_timer;
static int timer_count = 0;

void timer_expired_handler(struct k_timer *timer_id)
{
    timer_count++;
    printk("Timer expired %d times\n", timer_count);

    // Perform periodic task here
    gpio_pin_toggle_dt(&led);
}

int main(void)
{
    // Initialize timer
    k_timer_init(&periodic_timer, timer_expired_handler, NULL);

    // Start timer: 1000ms period, start immediately
    k_timer_start(&periodic_timer, K_MSEC(1000), K_MSEC(1000));

    printk("Periodic timer started (1 Hz)\n");

    while (1) {
        k_sleep(K_FOREVER);
    }

    return 0;
}
```

### One-Shot Timer
```c
static struct k_timer oneshot_timer;

void oneshot_handler(struct k_timer *timer_id)
{
    printk("One-shot timer expired\n");
    gpio_pin_set_dt(&led, 1);
}

int main(void)
{
    k_timer_init(&oneshot_timer, oneshot_handler, NULL);

    // Start one-shot timer: expire after 5000ms, no repeat
    k_timer_start(&oneshot_timer, K_MSEC(5000), K_NO_WAIT);

    printk("One-shot timer started (5 seconds)\n");

    while (1) {
        k_sleep(K_FOREVER);
    }

    return 0;
}
```

### Timer Control
```c
// Stop timer
k_timer_stop(&periodic_timer);

// Check timer status
uint32_t status = k_timer_status_get(&periodic_timer);
printk("Timer expired %u times since last check\n", status);

// Get remaining time
k_timeout_t remaining = k_timer_remaining_get(&periodic_timer);
```

## Complete Examples

### Example 1: Button-Triggered LED Toggle
```c
#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>

#define LED0_NODE DT_ALIAS(led0)
#define SW0_NODE DT_ALIAS(sw0)

static const struct gpio_dt_spec led = GPIO_DT_SPEC_GET(LED0_NODE, gpios);
static const struct gpio_dt_spec button = GPIO_DT_SPEC_GET(SW0_NODE, gpios);

static struct gpio_callback button_cb_data;
static struct k_work button_work;

void button_work_handler(struct k_work *work)
{
    gpio_pin_toggle_dt(&led);
    printk("LED toggled\n");
}

void button_pressed(const struct device *dev, struct gpio_callback *cb, uint32_t pins)
{
    k_work_submit(&button_work);
}

int main(void)
{
    // Initialize work
    k_work_init(&button_work, button_work_handler);

    // Setup LED
    if (!gpio_is_ready_dt(&led)) {
        return -1;
    }
    gpio_pin_configure_dt(&led, GPIO_OUTPUT_INACTIVE);

    // Setup button
    if (!gpio_is_ready_dt(&button)) {
        return -1;
    }
    gpio_pin_configure_dt(&button, GPIO_INPUT);
    gpio_pin_interrupt_configure_dt(&button, GPIO_INT_EDGE_FALLING);

    // Setup callback
    gpio_init_callback(&button_cb_data, button_pressed, BIT(button.pin));
    gpio_add_callback(button.port, &button_cb_data);

    printk("Button-triggered LED ready\n");

    while (1) {
        k_sleep(K_FOREVER);
    }

    return 0;
}
```

### Example 2: Multi-Frequency LED Blinking
```c
#define LED1_NODE DT_ALIAS(led0)
#define LED2_NODE DT_ALIAS(led1)
#define SW0_NODE DT_ALIAS(sw0)

static const struct gpio_dt_spec led1 = GPIO_DT_SPEC_GET(LED1_NODE, gpios);
static const struct gpio_dt_spec led2 = GPIO_DT_SPEC_GET(LED2_NODE, gpios);
static const struct gpio_dt_spec button = GPIO_DT_SPEC_GET(SW0_NODE, gpios);

static struct k_timer timer1, timer2;
static struct gpio_callback button_cb;
static struct k_work button_work;

static int freq_state = 0;

void timer1_handler(struct k_timer *timer)
{
    gpio_pin_toggle_dt(&led1);
}

void timer2_handler(struct k_timer *timer)
{
    gpio_pin_toggle_dt(&led2);
}

void button_work_fn(struct k_work *work)
{
    freq_state = (freq_state + 1) % 4;

    switch (freq_state) {
        case 0:  // 1 Hz
            k_timer_start(&timer1, K_MSEC(500), K_MSEC(500));
            printk("LED frequency: 1 Hz\n");
            break;
        case 1:  // 2 Hz
            k_timer_start(&timer1, K_MSEC(250), K_MSEC(250));
            printk("LED frequency: 2 Hz\n");
            break;
        case 2:  // 4 Hz
            k_timer_start(&timer1, K_MSEC(125), K_MSEC(125));
            printk("LED frequency: 4 Hz\n");
            break;
        case 3:  // Off
            k_timer_stop(&timer1);
            gpio_pin_set_dt(&led1, 0);
            printk("LED: Off\n");
            break;
    }
}

void button_isr(const struct device *dev, struct gpio_callback *cb, uint32_t pins)
{
    k_work_submit(&button_work);
}

int main(void)
{
    // Initialize work
    k_work_init(&button_work, button_work_fn);

    // Initialize timers
    k_timer_init(&timer1, timer1_handler, NULL);
    k_timer_init(&timer2, timer2_handler, NULL);

    // Setup GPIOs
    gpio_pin_configure_dt(&led1, GPIO_OUTPUT_INACTIVE);
    gpio_pin_configure_dt(&led2, GPIO_OUTPUT_INACTIVE);
    gpio_pin_configure_dt(&button, GPIO_INPUT);

    // Setup button interrupt
    gpio_pin_interrupt_configure_dt(&button, GPIO_INT_EDGE_FALLING);
    gpio_init_callback(&button_cb, button_isr, BIT(button.pin));
    gpio_add_callback(button.port, &button_cb);

    // Start LED2 at 2 Hz
    k_timer_start(&timer2, K_MSEC(250), K_MSEC(250));

    printk("Multi-frequency LED ready. Press button to cycle LED1 frequency\n");

    while (1) {
        k_sleep(K_FOREVER);
    }

    return 0;
}
```

### Example 3: Periodic Sensor Reading
```c
static struct k_timer sensor_timer;
static int sample_count = 0;

void sensor_timer_handler(struct k_timer *timer)
{
    sample_count++;

    // Read sensor (simulated)
    int sensor_value = sample_count * 10;

    printk("Sample %d: Sensor value = %d\n", sample_count, sensor_value);

    // Perform averaging every 10 samples
    if (sample_count >= 10) {
        printk("10 samples collected, calculating average...\n");
        sample_count = 0;
    }
}

int main(void)
{
    k_timer_init(&sensor_timer, sensor_timer_handler, NULL);

    // Sample every 100ms
    k_timer_start(&sensor_timer, K_MSEC(100), K_MSEC(100));

    printk("Periodic sensor reading started (100ms interval)\n");

    while (1) {
        k_sleep(K_FOREVER);
    }

    return 0;
}
```

## Threads (Alternative to Timers)

### Using Threads for Periodic Tasks
```c
#define STACK_SIZE 1024
#define THREAD_PRIORITY 7

static K_THREAD_STACK_DEFINE(blink_stack, STACK_SIZE);
static struct k_thread blink_thread;

void blink_thread_fn(void *arg1, void *arg2, void *arg3)
{
    while (1) {
        gpio_pin_toggle_dt(&led);
        k_sleep(K_MSEC(500));
    }
}

int main(void)
{
    gpio_pin_configure_dt(&led, GPIO_OUTPUT_INACTIVE);

    // Create and start thread
    k_thread_create(&blink_thread, blink_stack,
                    K_THREAD_STACK_SIZEOF(blink_stack),
                    blink_thread_fn,
                    NULL, NULL, NULL,
                    THREAD_PRIORITY, 0, K_NO_WAIT);

    printk("Blink thread started\n");

    while (1) {
        k_sleep(K_FOREVER);
    }

    return 0;
}
```

## prj.conf Configuration

```ini
# Enable GPIO
CONFIG_GPIO=y

# Enable console for printk
CONFIG_CONSOLE=y
CONFIG_UART_CONSOLE=y

# Enable newlib for better libc support
CONFIG_NEWLIB_LIBC=y

# Thread stack size
CONFIG_MAIN_STACK_SIZE=2048
```

## Best Practices
1. **Use device tree** - Define hardware in device tree, not code
2. **Work queues** - Defer long operations from ISR to work queue
3. **Thread-safe** - Zephyr APIs are thread-safe, use them
4. **Timer granularity** - Be aware of system tick period (typically 10ms)
5. **Power management** - Use `k_sleep()` to allow CPU to sleep

## Common Pitfalls
- ❌ Long ISR handlers (use work queues for complex tasks)
- ❌ Not checking device readiness (`gpio_is_ready_dt()`)
- ❌ Forgetting to configure interrupt mode
- ❌ Hardcoding GPIO pins (use device tree)
- ❌ Blocking in ISR context (use work queues)

## Comparison with Other Platforms

| Feature | Zephyr | ESP-IDF | Arduino |
|---------|--------|---------|---------|
| GPIO API | Device tree based | Direct pin number | Direct pin number |
| Interrupts | Callback + work queue | ISR + queue | attachInterrupt() |
| Timers | k_timer | esp_timer/gptimer | millis() + logic |
| Debouncing | Work queue + delay | FreeRTOS queue | millis() + logic |
| Thread-safety | Built-in | FreeRTOS primitives | None (single-threaded) |

## Related Skills
- `gpio-interrupts-esp32-esp-idf.md` - ESP32 interrupt patterns
- `hardware-timers-esp32-esp-idf.md` - ESP32 timer usage
- `software-debouncing-pattern.md` - Generic debouncing techniques

## References
- Zephyr GPIO Documentation: https://docs.zephyrproject.org/latest/hardware/peripherals/gpio.html
- Zephyr Timers: https://docs.zephyrproject.org/latest/kernel/services/timing/timers.html
- Zephyr Device Tree Guide: https://docs.zephyrproject.org/latest/build/dts/index.html
- nRF52840 Product Specification: https://infocenter.nordicsemi.com/topic/ps_nrf52840/keyfeatures_html5.html
