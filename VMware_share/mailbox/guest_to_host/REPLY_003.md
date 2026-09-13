# REPLY_003 · 阶段0串口冒烟通过 + UART2定案

时间: 2026-08-12 12:08 CST  
执行: 主机 Windows Cursor → SSH 虚拟机 `/dev/ttyACM0`

## A. NSH 冒烟（通过）

- 设备: Ubuntu `/dev/ttyACM0`（USB 在虚拟机侧，Windows 当前不见 COM7 属正常）
- 波特率: **1000000 8N1**，无硬件流控
- 结果: 收到 `nsh>` → `artifacts/NSH_SMOKE_PASS.txt`
- 命令摘录:

```text
nsh> help
... Builtin Apps: hello, gpio, pwm, lvgldemo, ...
nsh> uname -a
NuttX 0.0.0 dd92bcf4-dirty Aug 12 2026 11:53:20 arm nsh
nsh> free
      total       used       free ...
    8775680     377616    8398064 ...
nsh> ls /
/:
 data/  dev/  etc/  proc/
```

完整捕获: `artifacts/nsh_commands.txt` / `nsh_console_printable.txt`

**阶段 0（环境+烧录+控制台）完成。**

## B. UART2 脚号定案（雷达用）

来源: `vendor/sifli/.../sf32lb52_devkit_lcd/README_zh-cn.md` + `bsp_pinmux.c`

| 功能 | SoC 脚 | 设备节点 | 备注 |
|------|--------|----------|------|
| UART1 RX/TX（控制台） | PA18 / PA19 | `/dev/console` `/dev/ttyS0` | **禁止接雷达** |
| UART2 RX/TX（业务） | **PA20 / PA27** | `/dev/ttyS1` | **LD2451 接这里** |

接线（交叉）:

```text
LD2451 TX  →  板 UART2 RX = PA20
LD2451 RX  →  板 UART2 TX = PA27
LD2451 GND →  GND
LD2451 VIN →  5V（独立升压，≥200mA）
雷达波特率 115200 8N1
```

明细: `artifacts/uart2_pins.txt`

## C. 软件骨架

专属仓已有: `app/edge_walker/ew_ld2451.{c,h}`（帧同步 + ≤15m 门限 + alert 桩）  
待补: 协议 V1.03 字段解码；上板挂到 `/dev/ttyS1`。

## D. 需人手（无法远程）

1. 按上表杜邦线接 LD2451（拍照回传最好）
2. 手机 HLKRadarTool 蓝牙验活（可选）
3. 接好后通知，继续阶段1：板上读 `/dev/ttyS1` 解析

## 阻塞

无软件阻塞。物理接线待郑同学完成。
