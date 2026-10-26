# DevKit-LCD · 接线、雷达与触摸

> 板：SF32LB52-DevKit-LCD V1.2.0 · 目标 `sf32lb52_devkit_lcd` · 固件 `nuttx.bin@0x12010000`

---

## 1. 接口总览

| 用途 | 接口 | 说明 |
|------|------|------|
| **LCD 屏** | 22P FPC **J0102** | 金手指朝下插到底；**不是** 40P 排针 |
| **LD2451 雷达** | 40P 排针 **J0117** UART2 | 脚 8/10/6/2，见 §3 |
| **NSH 调试/烧录** | Type-C **USB-UART** | COM7 @ 1Mbps；**勿占**给雷达 |
| **触摸（可选）** | FPC 18–21 脚 I2C | FT6146 @ 0x38，见 §5 |

---

## 2. 屏幕接线与自检

### 2.1 FPC 插入

- 连接器：主板 **22P FPC 座 J0102**（0.5mm，下接触上翻）
- 套件原装 LCD 模组；1.85" AMOLED 转接板若 CN3 40P 未接，触摸可能不通（见 [`archive/模组确认_1.85_AMOLED_vs_DevKit-LCD.md`](archive/模组确认_1.85_AMOLED_vs_DevKit-LCD.md)）

### 2.2 三步判断

**A. 硬件（断电）** — FPC 插到底、锁扣压紧、无折痕反插。

**B. NSH 节点** — `ls /dev` 应有 `fb0`、`lcd0`。

**C. 功能测试**

```text
lvgldemo
ew screen info
ew screen          # 红绿蓝黑
ew alert warn      # 橙 + 蜂鸣
ew alert crit      # 红 + 高频蜂鸣
```

| 现象 | 可能原因 |
|------|----------|
| 有 fb0 全黑 | FPC/背光/模组 |
| lvgldemo 正常 ew 不行 | 未烧含 edge_walker 固件 |
| 触摸无反应 | §5；**不影响** MVP 预警 |

`alert_output()` 当前：`/dev/fb0` 填色（NONE=黑，WARN=橙，CRIT=红）+ PWM 蜂鸣。

---

## 3. LD2451 排针接线（J0117）

来源：思澈 V1.2.0 设计包 · UART2 = PA27(TX) / PA20(RX) → `/dev/ttyS1`

针号从 **靠近两个 Type-C** 端为 1/2（左奇右偶）：

```text
 1  3V3     2  5V      ← 雷达 VIN
 3  ...     4  5V
 5  ...     6  GND     ← 雷达 GND
 7  ...     8  PA27 TX → 接 LD2451 RX
 9  GND    10  PA20 RX ← 接 LD2451 TX
```

| LD2451 | 排针 | 信号 |
|--------|------|------|
| TX | **脚 10** | 板 RX = PA20 |
| RX | **脚 8** | 板 TX = PA27 |
| GND | 脚 6 或 9 | GND |
| VIN | 脚 2 或 4 | **5V** |

波特率 **115200 8N1**。

**勿接** 板面 CH 旁 **TXD/RXD** 焊盘（UART1 调试口，与 NSH/烧录冲突）。

更完整雷达选型见 [`三款毫米波雷达综合选型与接线手册.md`](三款毫米波雷达综合选型与接线手册.md)。

---

## 4. 与雷达勿混

- 屏 = 22P FPC（J0102）
- 雷达 = 40P 排针 UART2
- 调试 = Type-C UART（COM7）

---

## 5. 触摸 I2C 排查

### 5.1 结论摘要

| 假设 | 结论 |
|------|------|
| Kconfig 未开触摸 | **不成立**（已开 LVGL/FT6146/I2C） |
| FPC 接触 | 显示稳定则 **降为次要** |
| **SCL 配错 PA37→应为 PA30** | **主因** |
| IRQ 配错 PA41→应为 PA31 | **成立** |
| LSM6DS3 占 PA30/31 | **成立** |

J0102 触摸脚：18=INT(PA31)，19=SDA(PA33)，20=SCL(**PA30**)，21=RST(PA09)。  
NuttX 设备：**`/dev/i2c0`**（不是 `i2c dev -b 1`），地址 **0x38**。

### 5.2 修复

```bash
cd ~/openvela
bash contest2026_313_bianyuanxingzhe/scripts/patches/devkit_lcd_touch_i2c.sh
bash contest2026_313_bianyuanxingzhe/scripts/guest/build_ew_main.sh
```

补丁：`sifli_ap.c` SCL PA37→PA30；`defconfig` IRQ=31；关 LSM6DS3。

验收：

```text
i2c dev -b 0 0x38 0x38
lvgldemo    # 保持运行再触摸
```

Windows：`powershell -ExecutionPolicy Bypass -File scripts\host\touch_probe.ps1`

触摸对本期 MVP **非阻塞**；预警靠雷达 + `ew` 即可。

---

## 6. 参考

- SiFli 资料外链：[`sifli_pinout_sources/README.md`](sifli_pinout_sources/README.md)
- 接线图：[`DevKit-LCD_LD2451_pinout.svg`](DevKit-LCD_LD2451_pinout.svg)

## 7. ESP32 UART3 实体排针复核（2026-10-25）

对照本机官方 V1.2.0 原理图和 PCB ASC 网表，J0117 的**物理脚位**为：

- **J0117 第19脚 → PA24**；当前固件复用为 USART3_TXD，连接 ESP32 **GPIO16**。
- **J0117 第21脚 → PA25**；当前固件复用为 USART3_RXD，连接 ESP32 **GPIO17**。
- **J0117 第20或25脚 → GND**，与 ESP32 共地。

GPIO16/17 是 ESP32 芯片号；19/21 是 SF32 开发板排针号；PA24/PA25 是 SF32 芯片端口号。这三套编号不能直接互换。硬件参考图给出 PA 与排针的连接，UART3 收发方向由当前 `bsp_pinmux.c` 的实际复用配置确定。

依据：`tools/sifli_docs/DevKit-LCD/SF32LB52-DevKit-LCD-1-SCH_V1.2.0.pdf`、同目录 `SF32LB52-DevKit-LCD_PCB_V1.2.0.asc`；`map_j0117.py` 得到 `J0117.19=PA_24`、`J0117.21=PA_25`。现有 Demo 脚本也已记录 ESP GPIO16/17，后续排查直接沿用此记录。
