# TASK_008 · 界面怎么处理（主机已点亮 EW READY）

签发: 2026-09-04  
执行: Ubuntu 虚拟机 Cursor / 编译机  
回执: `mailbox/guest_to_host/REPLY_008.md`

真机 **SF32LB52-DevKit-LCD + CO5300** 已确认：`lvgldemo widgets` 能亮能滑；自研开机 **深蓝底 + 白字 `EW READY`** 已点亮。接线没问题。

---

## 0. 你是谁、改哪里

全量工程：`~/openvela`  
界面代码：`~/openvela/contest2026_313_bianyuanxingzhe/app/edge_walker/`  
（与 Windows 仓可能不是同一份，改完用 scp/共享盘对齐）  
开机脚本（会当 C 预处理，**禁止 `#` 注释**）：

`~/openvela/vendor/sifli/boards/sf32lb52/sf32lb52_devkit_lcd/src/etc/init.d/rcS`

编完把 `cmake_out/sf32lb52_devkit_lcd/nuttx.bin` 拷到  
`/mnt/hgfs/VMware_share/artifacts/nuttx.bin`  
Windows COM7 烧 `@0x12010000`。

---

## 1. 铁律（违反就会全黑）

这块屏 **不是** 写完 `/dev/fb0` 就亮。必须和官方 `lvgldemo` 同一条链：

1. `boardctl(BOARDIOC_INIT, 0)`（`CONFIG_NSH_ARCHINIT` 未开时 **必须**；内部 once，不和 NSH 冲突）
2. `usleep(200000)` 等 CO5300
3. 确认能 `open("/dev/lcd0")`
4. `lv_init()` → `lv_nuttx_dsc_init` → **`info.fb_path = "/dev/lcd0"`**（不要当主路径用 fb0）
5. `lv_nuttx_init`；`result.disp == NULL` 必须打日志并返回
6. 改 `lv_screen_active()` 上的控件
7. **`for (;;) { lv_timer_handler(); usleep(...); }` 常驻**，进程不能退出

对照模板：`~/openvela/apps/examples/lvgldemo/lvgldemo.c`

禁止：

- 开机只 `fb_fill` / 填完 `return`
- `rcS` 里 `#` 注释（预处理当 C，会编不过）
- 开机再拉 `lvgldemo widgets`（会 `LVGL already initialized`）
- 栈小于 **65536**、优先级建议 **100**（与 lvgldemo 同级）
- `DEPENDS lvgl`

当前已验证可亮的 `rcS`（前台，崩溃才能打到 console）：

```text
echo rcS_start > /dev/console
sleep 5
ew boot
```

不要加 `&`，除非已经能稳定亮屏且还要 NSH。

---

## 2. 现有入口（不要另起一套 init）

| 文件 | 做什么 |
|------|--------|
| `ew_main.c` | `ew boot` → `alert_lcd_boot_splash()`，入口打 `[ew-boot] start` |
| `alert_lcd.c` | 全部 LCD/LVGL 初始化 + 待机画面 |
| `alert_lcd.c` `alert_lcd_show()` | 告警填色；**LVGL 占着 lcd0 时 fb 填色可能看不见**，告警应改 LVGL 对象颜色/文字 |
| `CMakeLists.txt` | `NAME ew` `PRIORITY 100` `STACKSIZE 65536` `DEPENDS lvgl` |

诊断日志前缀 `[ew-boot]`，每行后 `fflush(stdout)`。

---

## 3. 界面怎么演进（按这个做）

**待机（已有）**：底 `0x082060`，居中 `"EW READY"`。

**告警（下一刀）**：不要再写 fb0。在 splash 里保存 `lv_obj_t *`（底、标签），提供：

- `alert_lcd_show(WARN)` → 橙底 + 字 `WARN`
- `CRIT` → 红底 + `CRIT`
- `NONE` → 回到深蓝 + `EW READY`

`ew alert warn/crit` 必须改这些对象，然后依赖已有的 `lv_timer_handler` 刷新。

**雷达数字（再下一刀）**：同一块 label 显示距离，例如 `R 8.2m`。解码仍在 `ew_ld2451.c`。注意：`ew boot` 若占着主线程循环，雷达要 **另开 pthread/任务**，或把 `lv_timer_handler` 和读 `/dev/ttyS1` 放进同一个循环（短读、非阻塞）。

**不要做**：再编一套 QuickApp / 再调 `lv_demos_create("widgets")` 当产品 UI。

---

## 4. 编译

```bash
export PATH="$HOME/bin:$HOME/openvela/prebuilts/gcc/linux-x86_64/arm-none-eabi/bin:$HOME/openvela/prebuilts/build-tools/linux-x86_64/bin:$PATH"
cd ~/openvela
# rcS 无 # 注释
cmake --build cmake_out/sf32lb52_devkit_lcd
cp -f cmake_out/sf32lb52_devkit_lcd/nuttx.bin /mnt/hgfs/VMware_share/artifacts/nuttx.bin
```

`genromfs` 必须在 PATH。Windows 烧录 1M；stub 超时再 `115200 --compat true`。

本仓 UART1 控制台是 **1000000**（不是飞书模板里的 115200）。CH343 打开 COM 可能拉 DTR 复位，PC 侧常读不到 log，**以屏为准**。

---

## 5. 回执 REPLY_008 写清

- 是否已按「lcd0 + boardctl + 常驻 timer」理解，有无改告警 UI
- `nuttx.bin` 时间与是否已拷 artifacts
- 编错贴 **完整 error:** 行
