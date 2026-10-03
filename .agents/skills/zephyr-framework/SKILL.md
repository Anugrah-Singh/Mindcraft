---
name: Zephyr RTOS
description: This skill is for the Zephyr RTOS only.
---
## GPIO Best Practices

* Define pin polarity (GPIO_ACTIVE_HIGH / GPIO_ACTIVE_LOW) in the devicetree, not in code.

* Use gpio_pin_set(dev, pin, 1), logical ON to turn ON, gpio_pin_set(dev, pin, 0), logical OFF to turn OFF
Let Zephyr's GPIO driver handle the physical HIGH/LOW translation based on DT flags. Never assume physical voltage level.

* Use GPIO_INT_EDGE_TO_ACTIVE / GPIO_INT_EDGE_TO_INACTIVE instead of RISING/FALLING — stays polarity-agnostic

## ADC

* Define the ADC configuration in the devicetree overlay, not in C code. When calling
  `adc_channel_setup_dt()`, only pass the `adc_dt_spec` struct — no need to manually fill an
  `adc_channel_cfg` struct, as the driver reads gain, reference, acquisition time, and resolution
  directly from the devicetree. This keeps hardware configuration out of the application code and
  makes it easier to port across boards.

* To convert a raw ADC value to millivolts, use `adc_raw_to_millivolts_dt()` from `<zephyr/drivers/adc.h>`:
```c
  int adc_raw_to_millivolts_dt(const struct adc_dt_spec *spec, int32_t *valp);
```

  When using the devicetree API, prefer this over the lower-level `adc_raw_to_millivolts()`,
  since it reads gain, reference voltage, and resolution directly from the `adc_dt_spec`
  instead of requiring you to pass them manually.

## 1-Wire Bit-Bang Tips 

### Pin Control — Direction Switching for Maximum Compatibility

`GPIO_OPEN_DRAIN` is not universally supported across all Zephyr-supported MCUs.
Instead, use direction switching — `GPIO_INPUT | GPIO_PULL_UP` to release the line
HIGH, and `GPIO_OUTPUT_INACTIVE` to pull it LOW. This approach works reliably across
all Zephyr-supported hardware.
```c
#define OW_LOW()     gpio_pin_configure_dt(&ow_pin, GPIO_OUTPUT_INACTIVE)
#define OW_RELEASE() gpio_pin_configure_dt(&ow_pin, GPIO_INPUT | GPIO_PULL_UP)

/* Init — idle HIGH */
OW_RELEASE();

/* Pull LOW */
OW_LOW();

/* Release HIGH */
OW_RELEASE();
```

### Disable Interrupts During Bit-Bang

Kernel interrupts can fire mid-slot and corrupt timing. Wrap time-critical sections:
```c
int key = irq_lock();
/* bit-bang here */
irq_unlock(key);
```

### `k_busy_wait()` over `k_usleep()`

Use `k_busy_wait()` for microsecond delays inside bit-bang routines.
`k_usleep()` has jitter from the scheduler and system tick which can
violate timing windows.

### Measuring Bit Duration in 1-Wire Bit-Bang

In protocols that encode bits by pulse duration (1-Wire, DHT11, etc.), always
**separate the wait and the measurement** into two steps. Combining them adds
overhead and makes timeout handling unreliable.
```c
/* Step 1: wait for the expected level */
while (gpio_pin_get_dt(&pin) != expected_level) {
    if (/* timeout */) return -1;
}

/* Step 2: measure how long it stays there */
uint32_t start = k_cyc_to_us_floor32(k_cycle_get_32());
while (gpio_pin_get_dt(&pin) == expected_level) {
    if (/* timeout */) return -1;
}
uint32_t duration = k_cyc_to_us_floor32(k_cycle_get_32()) - start;

/* Step 3: decode bit from duration */
uint8_t bit = (duration > THRESHOLD_US) ? 1 : 0;
```

### Use `k_cyc_to_us_floor32()` for Duration Measurement

Prefer `k_cyc_to_us_floor32()` over manual cycle division for cleaner
and more portable timing across different MCUs:
```c
/* Avoid */
uint32_t cycles_per_us = sys_clock_hw_cycles_per_sec() / 1000000;
uint32_t elapsed = (k_cycle_get_32() - start) / cycles_per_us;

/* Prefer */
uint32_t start = k_cyc_to_us_floor32(k_cycle_get_32());
/* ... wait ... */
uint32_t elapsed = k_cyc_to_us_floor32(k_cycle_get_32()) - start;
```


## Timer and Interrupt Handlers

Never call driver APIs (I2C, SPI, UART, GPIO configure) from a timer callback
or ISR. These APIs use kernel mutexes internally which cannot be used in ISR
context, causing a deadlock or kernel panic.

Use the timer only to set a flag or give a semaphore, then handle the work in
a thread or the main loop:
```c
/* Timer handler — flag only */
static volatile bool do_sample = false;

static void timer_handler(struct k_timer *timer)
{
    do_sample = true;   /* never call i2c_write(), gpio_pin_configure_dt(), etc. here */
}

/* Main loop — do the actual work */
while (1) {
    if (do_sample) {
        do_sample = false;
        /* safe to call driver APIs here */
        i2c_write_read(...);
    }
    k_msleep(10);
}
```

## I2C


### Getting the I2C Bus in C
```c
/* By bus label */
static const struct device *i2c_dev = DEVICE_DT_GET(DT_NODELABEL(i2c0));

/* Always check before use */
if (!device_is_ready(i2c_dev)) {
    printk("I2C device not ready\n");
    return -ENODEV;
}
```

---

### Writing a Register
```c
uint8_t buf[2] = {reg, value};   /* {register address, value} */
i2c_write(i2c_dev, buf, 2, DEVICE_ADDR);
```

---

### Reading Registers — 3 Options

**Option 1 — `i2c_write_read()` (recommended, most common)**

Write register address then read bytes back in one transaction:
```c
uint8_t reg = 0x3B;
uint8_t data[6];

i2c_write_read(i2c_dev,       /* bus */
               DEVICE_ADDR,   /* 7-bit I2C address */
               &reg, 1,       /* write: register pointer */
               data, 6);      /* read: number of bytes */
```

**Option 2 — `i2c_write()` + `i2c_read()` (explicit two-step)**

Use when the sensor requires a stop condition between write and read:
```c
uint8_t reg = 0x3B;
uint8_t data[6];

i2c_write(i2c_dev, &reg, 1, DEVICE_ADDR);
i2c_read(i2c_dev, data, 6, DEVICE_ADDR);
```

**Option 3 — `i2c_transfer()` (full control)**

Use for complex transactions or repeated starts:
```c
uint8_t reg = 0x3B;
uint8_t data[6];

struct i2c_msg msgs[2] = {
    {
        .buf   = &reg,
        .len   = 1,
        .flags = I2C_MSG_WRITE,
    },
    {
        .buf   = data,
        .len   = 6,
        .flags = I2C_MSG_READ | I2C_MSG_STOP,
    },
};

i2c_transfer(i2c_dev, msgs, 2, DEVICE_ADDR);
```

---

### Important Notes

* Never call I2C APIs from a timer callback or ISR — I2C uses mutexes
  internally and will deadlock. Set a flag in the ISR and read in the main loop.

* Always check the return value — all I2C functions return negative errno on failure.

* `i2c_write_read()` is sufficient for most sensors. Use `i2c_transfer()`
  only when the datasheet explicitly requires a repeated start or specific
  stop/start conditions between write and read phases.


### ⚠️ Always scan before trusting an address

Many I2C sensors (BME280, SHT3x, OLED, MPU-6050, etc.) have **two possible addresses**
selectable by a physical pin. If the address in your DTS is wrong the sensor will
silently fail `device_is_ready()`. Always run a bus scan during development to confirm
the actual address before declaring it in the overlay.
