# DevKit-LCD 触摸 I2C 不通 · 完整根因分析

> 对照两份飞书排查文档 + openvela `vendor_sifli` 源码 + COM7 实机日志（2026-08-23/24）

---

## 1. 最终结论（先看）

| 假设 | 是否成立 | 说明 |
|------|----------|------|
| FPC 接触不良 | **基本排除** | 多次插拔后 **390×450 显示始终正常**；QSPI（Pin 5–16）与 I2C 触摸（Pin 18–21）独立，但不能完全排除 18–21 未接触 |
| Kconfig 未开触摸/LVGL/I2C | **不成立** | 当前 `nsh/defconfig` **已全部开启**（见 §3） |
| RST(PA09) 未初始化 | **不成立** | `bsp_lcd_tp.c` 已实现 `BSP_TP_Reset()` / `BSP_TP_PowerUp()`，驱动 `ft6146_hw_init()` 会调用 |
| **软件引脚配错（主因）** | **成立** | `sifli_ap.c` 从 LCHSPI-ULP 拷贝，I2C0 SCL 打在 **PA37**，DevKit 硬件在 **PA30** |
| IRQ 引脚配错 | **成立** | `CONFIG_TOUCH_IRQ_PIN=41`（PA41），DevKit 应为 **31**（PA31） |
| IMU 与触摸抢脚 | **成立** | `CONFIG_SENSORS_LSM6DSL=y` 启动时占 **PA30/PA31** |
| PA37 与 LCD 电源冲突 | **成立** | DevKit 上 **PA37=LCD_VADD_EN**，却被误配成 I2C SCL |
| 扫错 I2C 总线 | **常见误操作** | 触摸在 NuttX **`/dev/i2c0`**（硬件 I2C1），不是 `i2c dev -b 1` |
| 模组/FPC 线序不对 | **待确认** | 1.85" AMOLED 转接板 **CN3 40P 空** 时，触摸可能未接到 J0102 |

**一句话**：显示正常 + I2C 始终 `--`，**不是「驱动没开」**，而是 **板级 bringup 引脚仍按 LCHSPI-ULP 写，时钟/中断打到错误 GPIO**；补丁见 `VMware_share/patches/devkit_lcd_touch_i2c.sh`。

---

## 2. 信号与引脚（硬件设计无误）

J0102 22P（与飞书、官方 README 一致）：

| FPC 脚 | 信号 | DevKit-LCD GPIO |
|--------|------|-----------------|
| 18 | INT | PA31 |
| 19 | SDA | PA33 |
| 20 | SCL | **PA30** |
| 21 | RST | PA09 |

- 触摸 IC：**FT6146**，I2C 地址 **0x38**（`ft6146.c` 中 `FT6146_DEV_ADDR`）
- 显示：**CO5300**，QSPI PA02–PA08，与触摸无关

---

## 3. Kconfig 实查（第二份飞书文档说「可能未启用」→ 已启用）

当前 `vendor/.../configs/nsh/defconfig` 关键项：

| 配置项 | 当前值 | 飞书建议 |
|--------|--------|----------|
| `CONFIG_GRAPHICS_LVGL` | **y** | 需开启 ✓ |
| `CONFIG_LV_USE_NUTTX_TOUCHSCREEN` | **y** | 需开启 ✓ |
| `CONFIG_BSP_USING_I2C1` | **y** | 触摸硬件 I2C1 ✓ |
| `CONFIG_BSP_USING_I2C2` | **y** | 文档写默认关，实际已开（给 LSM6DS3） |
| `CONFIG_INPUT_FT6146` | **y** | 触摸驱动 ✓ |
| `CONFIG_INPUT_TOUCHSCREEN` | **y** | ✓ |
| `CONFIG_SYSTEM_I2CTOOL` | **y** | NSH 用 `i2c` 命令 ✓ |
| `CONFIG_TOUCH_IRQ_PIN` | **41** | ❌ 应为 **31** |
| `CONFIG_SENSORS_LSM6DSL` | **y** | ❌ DevKit 建议关（占 PA30/31） |

**因此：不必再 menuconfig「从头开触摸」**；应修 **板级引脚 + defconfig 两项错误值**。

---

## 4. 软件 Bug 详解

### 4.1 `sifli_ap.c` 仍用 LCHSPI-ULP 引脚

函数名就叫 `sf32lb52_lchspi_ulp_bringup()`，I2C0（连 FT6146）初始化：

```c
/* 错误：DevKit-LCD 触摸 SCL 在 PA30，不在 PA37 */
HAL_PIN_Set(PAD_PA37, I2C1_SCL, PIN_PULLUP, 1);
HAL_PIN_Set(PAD_PA33, I2C1_SDA, PIN_PULLUP, 1);
i2c0 = sifli_i2cbus_initialize(0);   /* NuttX 注册为 /dev/i2c0 */
```

官方 README 明确：**DevKit SCL=PA30，LCHSPI-ULP SCL=PA37**。

### 4.2 `bsp_pinmux.c` 是对的，但会被覆盖

`BSP_PIN_Touch()` 正确配置 PA30/33/31/09，在 `BSP_PIN_LCD()` 里调用。  
但 **`sifli_ap.c` bringup 在注册 I2C 总线时再次把 SCL 改到 PA37**，且时序上可能与 LCD 初始化交错。

### 4.3 PA37 双重误用

DevKit-LCD 上 **PA37 = LCD_VADD_EN**（`bsp_pinmux.c` + CO5300）。  
bringup 把它当 I2C SCL → **I2C 时钟打到 LCD 电源使能脚**，触摸 SCL(PA30) 无时钟 → 总线扫不到 0x38。

### 4.4 LSM6DS3 占用 PA30/PA31

```c
/* sifli_ap.c — 注释仍写 LCHSPI-ULP 走线 */
HAL_PIN_Set(PAD_PA30, GPIO_A30, ...);  /* sensor LDO — 与触摸 SCL 冲突 */
HAL_PIN_Set(PAD_PA31, GPIO_A31, ...);  /* IMU INT — 与触摸 INT 冲突 */
```

实机启动已有：`ERROR: LSM6DS3 register failed on I2C1: -5`（板上本无此 IMU 或走线不对）。

### 4.5 NuttX I2C 总线号对照（易踩坑）

| 层级 | 触摸 FT6146 |
|------|-------------|
| 思澈硬件名 | **I2C1** |
| NuttX 设备 | **`/dev/i2c0`**（`sifli_i2cbus_initialize(0)`） |
| NSH 扫描 | **`i2c dev -b 0 0x38 0x38`** |
| `/dev/i2c1` | 硬件 **I2C2**（本板无 AW32001，仅 IMU 尝试） |

第二份飞书文档写 `i2ctool scan -b 1` → **扫的是 I2C2，不是触摸总线**。  
你们已扫过 bus0 和 bus1 皆 `--`，说明 **bus0 上也没有 0x38**，与 PA37 误配一致。

### 4.6 RST 时序（飞书提到，已实现）

`ft6146_hw_init()` → `BSP_TP_PowerUp()` → `BSP_TP_Reset(0/1)` → 读芯片 ID。  
`bsp_lcd_tp.c` 中 `TP_RESET = GPIO_A09`。**不是 RST 未做的问题**。

---

## 5. 实机证据链

| 观测 | 含义 |
|------|------|
| `fb` / `lvgldemo` 390×450 正常 | QSPI 显示链路 OK |
| `i2c dev -b 0/1` 全 `--` | 两路 I2C 均无 ACK；触摸不在 bus1，bus0 也无 0x38 |
| `/dev/input0` 存在 | 驱动节点已编译进固件；**≠ 芯片在线** |
| `lvgldemo` … `input0 open success` | 仅表示 **打开了字符设备**，不表示 FT6146 有坐标 |
| 启动 `LSM6DS3 … failed: -5` | I2C2/IMU 配置也不匹配本板 |
| 无任何 `ft6146 id_h=0x..` 日志 | 芯片 ID 读取未成功（或未抓到完整 boot log） |

---

## 6. 启动时序（理解为何显示亮、触摸死）

```text
board_late_initialize()
  └─ sf32lb52_lchspi_ulp_bringup()
       ├─ [错] PA37 ← I2C1_SCL，注册 /dev/i2c0
       ├─ [错] LSM6DS3：PA30/31 ← GPIO，I2C1(/dev/i2c1) 扫 IMU → 失败
       └─ task: lcd_async_init
            ├─ board_lcd_initialize() → BSP_PIN_LCD() → [对] BSP_PIN_Touch() PA30/33
            └─ ft6146_touch_initialize(i2c0, IRQ=PA41)  ← IRQ 也错
                 └─ I2C 读 0x38：SCL 实际仍在 PA37 侧 → 失败或假数据
```

显示能亮：`BSP_PIN_LCD()` 配 QSPI + CO5300 初始化成功。  
触摸不通：I2C 主控时钟从未稳定出现在 **PA30**。

---

## 7. 修复步骤（已准备补丁）

VM 连通后：

```bash
cd ~/openvela
bash contest2026_313_bianyuanxingzhe/VMware_share/patches/devkit_lcd_touch_i2c.sh
bash contest2026_313_bianyuanxingzhe/VMware_share/build_ew_main.sh
```

补丁内容：

1. `sifli_ap.c`：I2C1_SCL **PA37 → PA30**
2. `defconfig`：`CONFIG_TOUCH_IRQ_PIN=31`
3. `defconfig`：关闭 `CONFIG_SENSORS_LSM6DSL`（避免占 PA30/31）

烧录后验收：

```text
# 上电等 15s（等 lcd_async_init 完成）
i2c dev -b 0 0x38 0x38
i2c dev -b 0 0x03 0x77 -z
lvgldemo
# 启动 log 应出现：ft6146 id_h=0x.. id_l=0x..
```

Windows 一键：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\touch_probe.ps1
```

---

## 8. 补丁后仍不通 → 查硬件

1. **22P FPC 必须插 J0102**，18–21 脚连通（万用表/逻辑分析仪 PA30/33）
2. **确认屏模组带 FT6146**（官方 1.85" CO5300+FT6146 套件）
3. 若仍用 **AMOLED 转接板 + CN3 40P 空**：触摸线可能未进 J0102，需卖家 pinout 或换官方 FPC 模组
4. SDA/SCL 对 3.3V 上拉约 3.3V

---

## 9. 对两份飞书 AI 文档的校正

| 飞书说法 | 实际情况 |
|----------|----------|
| 「大概率软件未启用触摸驱动」 | **当前固件已启用**；问题是 **引脚配错** |
| `i2ctool scan -b 1` | 触摸应扫 **`i2c dev -b 0`**，地址 **0x38** |
| 「RST 未初始化导致一直复位」 | 驱动已有 RST 序列 |
| 「FPC 接触不良为主因」 | 多次插拔显示稳定 → **降为次要**；软件 bug 更吻合 |
| 「与 LCHSPI-ULP 同面板 FT6146」 | **对**；但 **DevKit 触摸 SCL 在 PA30 不是 PA37** |

---

## 10. 参考

- 官方 README：`vendor_sifli/.../sf32lb52_devkit_lcd/README_zh-cn.md`
- 补丁脚本：`VMware_share/patches/devkit_lcd_touch_i2c.sh`
- openvela AI Skills：[nuttx-driver-development](https://github.com/open-vela/.claude/blob/dev-ai-contest-2026/README_zh-cn.md)
