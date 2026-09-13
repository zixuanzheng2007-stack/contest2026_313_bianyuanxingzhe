# ai_agent 烧录状态 2026-08-29T11:37:38+08:00

- 固件: `/home/a1/openvela/cmake_out/sf32lb52_devkit_lcd_ai_agent/nuttx.bin` (2287568 B)
- 配置: `configs/ai_agent`, `CONFIG_EXAMPLES_AI_AGENT_VELA=y`
- 烧录: **待 USB 直通**（VM 需出现 CH343 `1a86:55d3` → `/dev/ttyACM0`）

## VMware 操作
1. 板子 USB 插好，Windows 不要独占 CH343
2. VMware: **虚拟机 → 可移动设备 → QinHeng/CH343 → 连接到虚拟机**
3. 本机验证: `lsusb | grep 1a86` 与 `ls /dev/ttyACM0`

## 烧录+NSH
```bash
bash /tmp/flash_ai_agent_nsh.sh /dev/ttyACM0
```
