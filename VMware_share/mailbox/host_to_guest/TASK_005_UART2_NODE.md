# TASK_005 · 雷达串口读错节点

主机 2026-08-16：蓝牙正常、ttyS0 全 0x00，**优先不是接线，是读错设备**。

## 板级对照（sf32lb52_devkit_lcd README）

| 外设 | 引脚 | NuttX 节点 | 默认波特率 |
|------|------|------------|------------|
| UART1 控制台 | PA18/PA19 | `/dev/console`、**`/dev/ttyS0`** | **1000000** |
| UART2 雷达 | PA20 RX / PA27 TX | **`/dev/ttyS1`** | 板级常跟 `CONFIG_UART_BAUD`，可能也是 **1000000** |

LD2451 串口是 **115200**。

## 请 Ubuntu 立刻重测（不要再读 ttyS0）

```sh
ls /dev/ttyS*
# 必须对 /dev/ttyS1 测，115200 与 1000000 各抓一次

# 例：
stty -F /dev/ttyS1 115200 raw -echo
hexdump -C /dev/ttyS1 | head
# 再：
stty -F /dev/ttyS1 1000000 raw -echo
hexdump -C /dev/ttyS1 | head
```

期望：115200 下出现 `F4 F3 F2 F1`。  
若只有 1Mbps 才像帧、115200 是乱码 → 改 defconfig 把 UART2 设为 115200 后重编烧录。

## 接线（已冻结，模组视角）

- TX → PA20（排针脚 10）
- RX → PA27（排针脚 8）
- GND → 脚 6，VIN → 脚 2/4 的 5V

回传 REPLY_005：ttyS1 在 115200 / 1Mbps 各一段 hex。
