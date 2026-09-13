# TASK_003 · 阶段 0 收尾 + 进入阶段 1（感知）

时间: 2026-08-12 · 主机 Windows Cursor  
依据: `docs/分工/边缘行者_异地三人MVP开工计划.md` v2.2

## 重要澄清

已烧录的 `nuttx.bin@0x12010000` **就是** openvela 板端系统（NuttX/NSH）。  
**不要**再找「另一套 openvela 系统镜像」二次烧录。

阶段 0 剩余验收 = **串口看到启动日志 / `nsh>`**。

## 当前进度

| 项 | 状态 |
|----|------|
| VM repo sync（关键路径） | 完成 |
| 编 `sf32lb52_devkit_lcd` | 完成 |
| 烧录 nuttx.bin | 完成（flash_exit=0） |
| 串口 NSH 冒烟 | **待郑/主机确认** |
| LD2451 → decision | 未开始（阶段 1） |
| alert_output | 未开始（阶段 2） |
| ai_agent + Skill | 未开始（阶段 3，可与 1 并行桩） |

## A. 主机/郑（H）立刻做

1. PuTTY：COM7，波特率先 **1000000**（乱码再试 115200），关硬件流控  
2. 按 Reset，确认有启动打印或 `nsh>`  
3. 通过后在 `mailbox/guest_to_host/REPLY_003.md` 贴 3～5 行启动日志  
4. 按接线手册接 LD2451 → **UART2**（勿占 Debug UART）；VIN 5V + 共地；TX↔RX  
5. 手机 HLKRadarTool 可先蓝牙验活

## B. Ubuntu Cursor（可与 A 并行）

1. **不要**再全量并行 `repo sync` 抢带宽  
2. 查板级 UART2 引脚：`vendor/sifli/boards/sf32lb52/sf32lb52_devkit_lcd` 内 pinmux / README  
3. 在专属仓或 apps 侧起草 F 模块骨架（可先 host 侧协议解析单测）：
   - `ld2451_parse()` → `range_m` / `speed` / `approaching`
   - `decision`：靠近且 ≤15 m → ALERT
   - `alert_output(level, reason)` 先串口打印桩
4. A 线：对照赛方 ai_agent 教程，确认示例配置能否编进下一版固件（本周可用模拟 `decision` 桩）

## C. 回传

写 `mailbox/guest_to_host/REPLY_003.md`：

- NSH 是否通（日志摘录）
- UART2 脚号定案
- 解析骨架路径 / 是否已能本地编过
- 阻塞项

## 验收（本任务）

- [ ] 串口 `nsh>` 可见  
- [ ] UART2 脚号写进 REPLY_003  
- [ ] F 解析/决策骨架落地（哪怕先打印假数据）  
