#!/bin/bash
# DevKit-LCD touch I2C pin fix: SCL=PA30, SDA=PA33, INT=PA31, RST=PA09
set -eu

ROOT="${1:-$HOME/openvela}"
AP="$ROOT/vendor/sifli/boards/sf32lb52/sf32lb52_devkit_lcd/src/sifli_ap.c"
DEF="$ROOT/vendor/sifli/boards/sf32lb52/sf32lb52_devkit_lcd/configs/nsh/defconfig"

if [ ! -f "$AP" ]; then
  echo "MISSING $AP"
  exit 2
fi

if grep -q 'HAL_PIN_Set(PAD_PA37, I2C1_SCL' "$AP"; then
  sed -i 's/HAL_PIN_Set(PAD_PA37, I2C1_SCL/HAL_PIN_Set(PAD_PA30, I2C1_SCL/' "$AP"
  echo "patched sifli_ap.c: I2C1_SCL PA37 -> PA30"
else
  echo "sifli_ap.c I2C1_SCL already PA30 or pattern changed"
fi

if [ -f "$DEF" ]; then
  if ! grep -q '^CONFIG_I2C=y' "$DEF"; then
    echo 'CONFIG_I2C=y' >>"$DEF"
    echo "patched defconfig: added CONFIG_I2C=y"
  fi
  if ! grep -q '^CONFIG_I2C_DRIVER=y' "$DEF"; then
    echo 'CONFIG_I2C_DRIVER=y' >>"$DEF"
    echo "patched defconfig: added CONFIG_I2C_DRIVER=y"
  fi
  if grep -q '^CONFIG_SENSORS_LSM6DSL=y' "$DEF"; then
    sed -i 's/^CONFIG_SENSORS_LSM6DSL=y/# CONFIG_SENSORS_LSM6DSL is not set/' "$DEF"
    sed -i 's/^CONFIG_EXAMPLES_LSM6DSL_READER=y/# CONFIG_EXAMPLES_LSM6DSL_READER is not set/' "$DEF"
    echo "patched defconfig: disabled LSM6DSL"
  fi
  if grep -q '^CONFIG_TOUCH_IRQ_PIN=41' "$DEF"; then
    sed -i 's/^CONFIG_TOUCH_IRQ_PIN=41/CONFIG_TOUCH_IRQ_PIN=31/' "$DEF"
    echo "patched defconfig: TOUCH_IRQ_PIN 41 -> 31"
  fi
fi

echo "devkit_lcd_touch_i2c patch OK"
