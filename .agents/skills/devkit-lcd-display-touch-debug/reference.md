# DevKit-LCD 显示/触摸 · 参考

## J0102 22P 引脚（触摸段）

| FPC 脚 | 信号 | GPIO |
|--------|------|------|
| 17 | VDD_3V3 | 电源 |
| 18 | INT | PA31 |
| 19 | SDA | PA33 |
| 20 | SCL | **PA30** |
| 21 | RST | PA09 |

## 与 LCHSPI-ULP / 黄山派差异

| 功能 | DevKit-LCD | LCHSPI-ULP |
|------|------------|------------|
| 触摸 I2C SCL | **PA30** | PA37 |
| 触摸 IRQ | **PA31** | PA41 |
| LCD VADD_EN | **PA37** | PA01 |
| 背光 PWM | PA01 | — |

## NuttX I2C 总线对照

| 思澈硬件 | NuttX 设备 | NSH `-b` | 用途 |
|----------|------------|----------|------|
| I2C1 | `/dev/i2c0` | **0** | FT6146 触摸 |
| I2C2 | `/dev/i2c1` | 1 | IMU/充电（DevKit 常空） |

FT6146 地址：**0x38**（7-bit）。

## Kconfig 检查清单

必需（`configs/nsh/defconfig` 或编译 `.config`）：

```
CONFIG_I2C=y
CONFIG_I2C_DRIVER=y
CONFIG_BSP_USING_I2C1=y
CONFIG_INPUT_FT6146=y
CONFIG_INPUT_TOUCHSCREEN=y
CONFIG_LV_USE_NUTTX_TOUCHSCREEN=y
CONFIG_SYSTEM_I2CTOOL=y
CONFIG_TOUCH_IRQ_PIN=31
```

DevKit-LCD 建议关闭（与触摸抢 PA30/31）：

```
# CONFIG_SENSORS_LSM6DSL is not set
# CONFIG_EXAMPLES_LSM6DSL_READER is not set
```

## sifli_ap.c 补丁前后

**错误（LCHSPI-ULP 残留）：**

```c
HAL_PIN_Set(PAD_PA37, I2C1_SCL, PIN_PULLUP, 1);
HAL_PIN_Set(PAD_PA33, I2C1_SDA, PIN_PULLUP, 1);
i2c0 = sifli_i2cbus_initialize(0);
```

**正确（DevKit-LCD）：**

```c
HAL_PIN_Set(PAD_PA30, I2C1_SCL, PIN_PULLUP, 1);
HAL_PIN_Set(PAD_PA33, I2C1_SDA, PIN_PULLUP, 1);
i2c0 = sifli_i2cbus_initialize(0);
```

## 启动时序（为何能亮屏、无触摸）

```
sf32lb52_lchspi_ulp_bringup()
  ├─ [错] PA37 ← I2C1_SCL → /dev/i2c0
  ├─ [错] LSM6DS3 占 PA30/PA31
  └─ lcd_async_init
       ├─ BSP_PIN_LCD() → BSP_PIN_Touch() 暂时改对 PA30
       └─ ft6146_touch_initialize(i2c0, IRQ=PA41)
            └─ I2C 时钟仍在 PA37 → 读 0x38 失败
```

## 实机证据对照

| 观测 | 修复前 | 修复后（补丁+CONFIG_I2C） |
|------|--------|---------------------------|
| `i2c dev -b 0 0x38` | 全 `--` | **`38`** |
| `ls /dev` i2c0 | 有/无* | 有 |
| LSM6DS3 启动 log | `failed: -5` | 无（已关） |

*关 LSM6 且未补 `CONFIG_I2C=y` 时 i2c0/input0 会消失。

## 补丁脚本行为

`VMware_share/patches/devkit_lcd_touch_i2c.sh`：

1. `sifli_ap.c`：PA37 → PA30（I2C1_SCL）
2. `defconfig`：`TOUCH_IRQ_PIN` 41 → 31
3. `defconfig`：关闭 LSM6DSL / LSM6DSL_READER
4. `defconfig`：若无则追加 `CONFIG_I2C=y`、`CONFIG_I2C_DRIVER=y`

VM 上先 `sed -i 's/\r$//'` 去 CRLF。

## 硬件仍失败时

1. 万用表：SDA/SCL 对 3.3V 约 3.3V（上拉）
2. 逻辑分析仪：PA30 有时钟、0x38 有 ACK
3. 确认模组带 FT6146，非纯显示 TFT
4. AMOLED 转接板 CN3 40P 未接主控 → 触摸线可能未达 J0102

## 文档与脚本索引

- `docs/DevKit-LCD_屏幕接线与自检.md`
- `docs/DevKit-LCD_触摸I2C排查与补丁.md`
- `docs/模组确认_1.85_AMOLED_vs_DevKit-LCD.md`
- `scripts/touch_probe.ps1`
- `scripts/full_hw_check.ps1`
- `scripts/screen_test_ui.ps1`
