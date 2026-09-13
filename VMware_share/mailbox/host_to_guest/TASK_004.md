# TASK_004 · 接 LD2451 + 阶段1板上读数

时间: 2026-08-12  
前置: REPLY_003（NSH 通、UART2=PA20/PA27）

## H 真机（郑）

1. LD2451 → DevKit-LCD：
   - TX→**PA20**，RX→**PA27**，GND共地，VIN=**5V**
   - 勿动 UART1 / USB-UART 控制台
2. 拍照一张接线回传到 `artifacts/photos/`（可先放共享盘）
3. 完成后在 REPLY_004 写「已接线」

## F / Ubuntu Cursor

1. 确认 `/dev/ttyS1` 在 NSH：`ls /dev` / `echo` 探测
2. 将 `contest.../app/edge_walker` 接入 apps（或板端示例），打开 115200 读 UART2
3. 先打印原始十六进制；再按 V1.03 填 `decode_body`
4. `decision`：approaching && range≤15m → 调 `alert_output`（先串口打印）

## A（可并行）

ai_agent 教程：用模拟 decision 事件桩，不阻塞接线。

## 验收

- [ ] 接线照片  
- [ ] 板上能看到雷达原始字节或解析后的 range_m  
- [ ] 人为接近时 decision 翻转（日志即可）  
