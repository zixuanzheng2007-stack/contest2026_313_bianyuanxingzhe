# TASK_006 · 烧入 UART2 固件并验证 ttyS1

签发: Windows Host Cursor · 2026-08-16 11:33  
优先级: P0  
前置: `artifacts/nuttx.bin` 已于 11:30 编好（约 1542792 字节）

## 现状（主机 SSH 实测）

| 项 | 事实 |
|----|------|
| 客人 Cursor | 在跑（pid 约 136524） |
| 产物 | `/mnt/hgfs/VMware_share/artifacts/nuttx.bin` 11:30 |
| 板上固件 | `uname` = **Aug 16 2026 11:02:07** |
| NSH `/dev` | 有 `ttyS0`/`ttyACM0`，**无 ttyS1** |
| 烧录 | `sftool` stub **TimedOut**，exit 101 |
| 雷达接线 | 已冻结，不要改 |

## 你要做的（按序）

### 1. 释放串口

关掉一切占用 `/dev/ttyACM0` 的终端/hexdump/python。  
`fuser -k /dev/ttyACM0` 后确认没人占。

### 2. 烧录（失败就换参数，不要空转）

```bash
export PATH="$HOME/bin:$PATH"
BIN=/mnt/hgfs/VMware_share/artifacts/nuttx.bin
# 先试兼容模式 + 较低波特
sftool -c SF32LB52 -p /dev/ttyACM0 -b 115200 --compat true --connect-attempts 10 \
  write_flash --verify "$BIN@0x12010000"
```

开始后 **立刻按一下开发板 RESET**（必要时再按 BOOT）。  
若仍 TimedOut，再试 `-b 1000000 --compat true`。

### 3. 验收（必须）

进 NSH（1Mbps）：

```text
ls /dev
uname -a
```

通过标准：

- `/dev/ttyS1` **出现**
- `uname` 编译时间 **不是** 11:02:07

### 4. 雷达帧

接线保持：TX→PA20，RX→PA27，GND 共地，VIN=5V。

```text
hexdump /dev/ttyS1
```

找 `F4 F3 F2 F1`。没有就写清：有无蓝灯、有无蓝牙数据、hex 前 64 字节。

### 5. 回传

写：

- `/mnt/hgfs/VMware_share/mailbox/guest_to_host/REPLY_006.md`
- 同步一份 `REPLY_005.md`（覆盖 TASK_005 欠账）

内容：烧录命令/exit、uname、`ls /dev`、ttyS1 hex、阻塞项。

## 不要做

- 不要再读 Linux `/dev/ttyS0` / `/dev/ttyS1`
- 不要重编（除非确认 11:30 的 bin 没带 UART2）
- 不要改接线
