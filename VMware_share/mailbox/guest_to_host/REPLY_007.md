# REPLY_007 · edge_walker (ew) 编进固件

时间: 2026-08-18 16:22 CST  
任务: TASK_007_EW_MAIN.md  
执行: 主机 SSH 触发 Ubuntu 编译机

## 结果

- **已编进**: `CONFIG_LVX_USE_DEMO_CONTEST2026_313_EDGE_WALKER=y`
- **NSH 命令**: `ew`（含 `alert` / `fake` / 读 `/dev/ttyS1`）
- **符号确认**: `ew_main`, `alert_output` 在 System.map
- **产物**: `cmake_out/sf32lb52_devkit_lcd/nuttx.bin` → `artifacts/nuttx.bin`
- **大小**: 1550088 B（较上一版 1542784 B +7304 B）
- **编译时间**: 2026-08-18 16:22 CST

## 集成方式

- 源码: `contest2026_313_bianyuanxingzhe/app/edge_walker/`
- 链接: `apps/packages/demos/contest2026_313_edge_walker` → 上述目录
- defconfig 已追加 `CONFIG_LVX_USE_DEMO_CONTEST2026_313_EDGE_WALKER=y`
- 全量 reconfigure 后增量 build（需 `prebuilts/build-tools/.../genromfs` 在 PATH）

## 郑侧烧录验收

Windows COM7 烧 `artifacts/nuttx.bin` @ `0x12010000`，NSH：

```text
ew alert warn
ew fake 10 2
ew
```

期望: 控制台打印 `[alert_output]`；`fake` 触发 approaching 判断；`ew` 打开 `/dev/ttyS1` 循环。

## 日志

- `artifacts/build_ew_main.log`
