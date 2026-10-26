---
name: devkit-serial-debug
description: >-
  Debug SF32LB52-DevKit-LCD over USB-UART on Windows (COM7 @ 1Mbps) or VM
  (/dev/ttyACM0). Use when flashing, NSH commands, ew wifi/at tests, @ remote
  control, serial scripts fail, COM port busy, no nsh prompt, or Codex needs
  to operate the board instead of telling the user to use PuTTY.
---

# DevKit 串口调试（边缘行者 / openvela NSH）

板：**SF32LB52-DevKit-LCD** · 控制台：**USB-UART（CH343）** · 应用 NSH 命令：**`ew`**

## Agent 行为要求

1. **先跑脚本再下结论**——用 `scripts/host/` 或 `python scripts/host/*.py`，不要只输出 PuTTY 教程。
2. 串口占用冲突时，提示关 **sscom5 / PuTTY**，不要反复重试同一 COM。
3. **Host（Windows）** 负责烧录与 COM7 验收；**Guest（VM）** 编译，USB 直通 VM 时用 `/dev/ttyACM0`，勿与 host 同时抢板。
4. 每次操作 **保存或引用日志路径**（`VMware_share/artifacts/`）。

## 1. 硬件与端口

| 项 | 值 |
|----|-----|
| 接口 | 板子丝印 **USB to UART / USB转串口** Type-C（不是 USB Device 下载口） |
| Windows 默认 | **COM7**（以 Device Manager 为准） |
| 波特率 | **1000000**（1 Mbps）8N1 |
| 流控 | **无**；`DTR=False`, `RTS=False`（必须，否则 ESP/WiFi 探针异常） |
| VM | `/dev/ttyACM0` @ 1000000（USB 直通时） |

发现 COM：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/host/smoke_com_watch.ps1
```

## 2. 两种串口协议

### 2.1 NSH 交互（Nuttx Shell）

- 提示符：`nsh>`
- 行尾：`\r\n`
- 适用：驱动检查、`ew wifi *`、`i2c`、`fb`、`lvgldemo`（无 UI 时）

**上电流程：**

```
插 USB-UART → 等 12–15s → 见启动 log → 出现 nsh>（或发 Enter 唤醒）
```

**常用 NSH 命令：**

```text
ls /dev
uname -a
fb
i2c bus
i2c dev -b 0 0x38 0x38
lvgldemo
ew alert soft test
ew fake 10 20
ew wifi ping
ew wifi scan          # 慢，约 60–130s
ew wifi join "SSID" "pass"
ew at AT+GMR
```

命令表见 `app/edge_walker/README.md`。

### 2.2 `@` 遥控（UI 运行时）

`rcS` 启动 **`ew boot`** 后，LVGL 占住控制台；此时 **NSH 可能无 echo**，应发 **`@` 行**（不经 `nsh>`）：

```text
@help
@goto warn|wifi|chat
@alert soft|strong|none [reason]
@fake 10 20
@ping
@status
@scan
@join SSID password
@ask 你好
@tap 195 225
@touch down 195 225
@mirror on|off|snap|fast|normal|hd
```

实现：`app/edge_walker/ew_serial_ctl.c`（读 `/dev/console`，行首 `@`）。

**Python 示例（1Mbps，RTS/DTR 关）：**

```python
import serial, time
sp = serial.Serial("COM7", 1_000_000, timeout=0.1)
sp.dtr = sp.rts = False
sp.write(b"@ping\r\n")
time.sleep(2)
print(sp.read(sp.in_waiting).decode("utf-8", "replace"))
sp.close()
```

## 3. 仓库脚本速查

| 脚本 | 用途 |
|------|------|
| `scripts/host/nsh_auto.ps1` | 复位 + 等 boot + 多条 NSH + 写 `artifacts/nsh_auto_*.txt` |
| `scripts/host/nsh_cmd.ps1` | 单条 NSH，`-WaitSec` 可调 |
| `scripts/host/NSH_PROBE.ps1` | 被动听 log + WiFi 命令，写 `nsh_probe_latest.txt` |
| `scripts/host/一键烧录并测屏.ps1` | sftool 烧录 + nsh_auto 测屏 |
| `scripts/host/flash_sf32.ps1` | 仅烧录（`-Firmware path@0x12010000`） |
| `scripts/host/wifi_at_diagnose.ps1` | WiFi/AT 全链路诊断 |
| `scripts/host/wifi_hotspot_test.ps1` | 热点 join 测试 |
| `scripts/host/full_hw_check.ps1` | 显示 + I2C + 触摸 |
| `scripts/host/touch_probe.ps1` | 触摸 I2C @ 0x38 |
| `scripts/host/serial_send_now.py` | `@ping` + NSH WiFi 快速探针 |
| `scripts/host/wifi_at_probe_once.py` | 交互式 WiFi 命令逐条 |
| `tools/ew_panel.py` | PC 镜像 + `@` 遥控 GUI |

**推荐一键冒烟：**

```powershell
cd e:\openvela\contest2026_313_bianyuanxingzhe
powershell -ExecutionPolicy Bypass -File scripts/host/nsh_auto.ps1 `
  -Port COM7 -BootWaitSec 12 `
  -Commands "ls /dev","ew alert soft","ew wifi ping"
```

## 4. 烧录

仅 **Windows host**（sftool + COM7）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/host/flash_sf32.ps1 `
  -Port COM7 -Firmware "VMware_share/artifacts/nuttx.bin@0x12010000"
```

- 地址：`0x12010000`
- 1Mbps 失败时脚本可回退 **115200 --compat**（仅烧录，不是控制台日常波特率）

## 5. 故障分流

```
无 COM 口？
  → smoke_com_watch.ps1 插拔对比；确认 USB-UART 口与数据线

Permission denied？
  → 关 sscom/PuTTY/ew_panel；taskkill 占口进程

有 COM 无数据？
  → RESET；BootWaitSec 加到 15；查线

乱码？
  → 必须 1000000；勿用 115200 开控制台

有 log 无 nsh>？
  → Enter 唤醒；若 ew boot 已跑 → 改 @ping

NSH 有 echo，WiFi 无响应？
  → ew wifi scan 等够 130s；RTS 是否误开

显示黑屏 / 触摸？
  → 用 skill devkit-lcd-display-touch-debug（与串口正交）
```

## 6. 板上串口设备映射（应用层）

| 设备 | 用途 | 波特率 |
|------|------|--------|
| `/dev/console`（USB-UART） | NSH + `@` 遥控 | 1M |
| `/dev/ttyS1` | LD2451 雷达 | 115200 |
| `/dev/ttyS2` | ESP AT 猫 | 115200 |

**不要**把 PC 上的 115200 当成控制台波特率；115200 是雷达/ESP 外设。

## 7. 验收输出模板

完成串口调试后回复：

```markdown
## 串口调试报告

**端口**：COMx @ 1Mbps，RTS/DTR off
**模式**：NSH | @遥控
**已执行**：脚本/命令列表
**日志**：VMware_share/artifacts/xxx.txt
**结果**：PASS/FAIL + 关键回显（nsh> / [ew-ctl] / ew wifi）
**下一步**：…
```

## 8. 相关文档

| 路径 | 内容 |
|------|------|
| `app/edge_walker/README.md` | `ew` 子命令全集 |
| `scripts/README.md` | host/guest 分工 |
| `.agents/skills/devkit-lcd-display-touch-debug/` | 显示/触摸（I2C） |
| `VMware_share/scripts/AGENT_BUS.md` | host/guest 烧录仲裁 |
