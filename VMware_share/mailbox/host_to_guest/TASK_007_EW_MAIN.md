# TASK_007 · 郑子轩主程序 ew 编进固件

签发: 2026-08-18  
执行: Ubuntu 编译机 + 郑子轩烧录

## 做什么

专属仓 `app/edge_walker/` 已有 NSH 命令 `ew`（提醒出口 + 假靠近 + 读 /dev/ttyS1）。

请编进 `sf32lb52_devkit_lcd`：

1. 打开 Kconfig：`LVX_USE_DEMO_CONTEST2026_313_EDGE_WALKER` / `ew`
2. `cmake --build` 后把 `nuttx.bin` 拷到 `/mnt/hgfs/VMware_share/artifacts/nuttx.bin`
3. 写 `mailbox/guest_to_host/REPLY_007.md`：是否编进、镜像时间

郑侧 Windows COM7 烧 `0x12010000`，NSH 测：

```text
ew alert warn
ew fake 10 2
```
