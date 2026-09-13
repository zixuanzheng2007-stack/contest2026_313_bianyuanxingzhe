# REPLY_005 · UART2 节点重测

时间: 2026-08-16 11:36 CST  
任务: TASK_005_UART2_NODE.md  
执行: Ubuntu Cursor（经 CH343 `/dev/ttyACM0` 进板内 NSH，**没有**读虚拟机 `/dev/ttyS*`）

## 1. 板内 `ls /dev`（当前在跑的固件）

固件: `NuttX … Aug 16 2026 11:02:07 arm nsh`（UART2 波特已改 115200，但 **仍跳过把 console 注册成 ttyS0**）

```
/dev:
 … ttyACM0  ttyS0  …
```

**没有 `/dev/ttyS1`。**  
`dd if=/dev/ttyS1` → `nsh: dd: infd open failed: 2`（ENOENT）

原因：`sifli_uart.c` 注册时跳过 `CONSOLE_UART`，于是：

| 硬件 | 当前节点 | README / TASK_005 期望 |
|------|----------|------------------------|
| UART1 控制台 1Mbps | `/dev/console` only | `/dev/console` + **`/dev/ttyS0`** |
| UART2 雷达 PA20/PA27 | **`/dev/ttyS0`** | **`/dev/ttyS1`** |

因此此前读板内 `ttyS0` 实际就是 UART2，不是宿主机 Linux 空串口。

## 2. 按 TASK 要求的 hex

### `/dev/ttyS1` @ 115200 与 1Mbps

节点不存在，**无法抓帧**。NSH 无 `stty`。

```
dd if=/dev/ttyS1 of=/dev/console bs=1 count=64
nsh: dd: infd open failed: 2
```

hex: （无）

### `/dev/ttyS0`（当前固件上的 UART2，已 115200）

约 64 字节，**全 `0x00`**，无 `F4 F3 F2 F1`：

```
0000000000000000000000000000000000000000000000000000000000000000
0000000000000000000000000000000000000000000000000000000000000000
```

`dd` 在 ~0.05–0.8s 内凑满，不像在等 1s 空目标帧。

## 3. 已改源码、已编过、烧录未成功

已改 `vendor/sifli/chips/sf32lb52/sifli_uart.c`：

- UART1 → `/dev/console` + `/dev/ttyS0`
- UART2 → `/dev/ttyS1`，波特 **115200**

产物: `cmake_out/sf32lb52_devkit_lcd/nuttx.bin`（已拷到 `artifacts/nuttx.bin`，1542784 B）

`sftool write_flash --verify` **三次失败**：`Failed to download stub: Operation timed out`  
板子仍停在 11:02 固件，故 **ttyS1 尚未出现**。

请真机：**断电再上电**（或按下载键）后让客人再烧一次，即可对 `/dev/ttyS1` 抓 `F4 F3 F2 F1`。

## 4. 对「没数据 / 读错节点」

- 蓝牙有数据 ⇒ 模组活着；手册写无目标串口仍约 1s 一帧。
- 当前板内 UART2（现名 `ttyS0`）收到的是连续 0x00，**不是**空目标协议帧。
- 节点名与 README 不一致已修，但新固件还没烧进去。
