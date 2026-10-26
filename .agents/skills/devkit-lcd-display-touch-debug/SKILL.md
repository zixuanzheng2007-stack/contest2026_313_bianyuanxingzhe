---
name: devkit-lcd-display-touch-debug
description: >-
  Diagnose and fix SF32LB52-DevKit-LCD display (CO5300 QSPI) and touch (FT6146
  I2C) issues on openvela sf32lb52_devkit_lcd. Use when the user reports black
  screen, fb0/lvgldemo problems, touch not working, I2C scan empty, FPC/J0102
  wiring, PA30/PA37 pin mismatch, or asks to troubleshoot DevKit-LCD AMOLED.
---

# DevKit-LCD 显示与触摸排查

板：**SF32LB52-DevKit-LCD** · 目标：`sf32lb52_devkit_lcd` · 屏：**390×450 CO5300** · 触摸：**FT6146 @ 0x38**

## 快速分流

| 现象 | 优先方向 |
|------|----------|
| 全黑 / 无 `fb0` | FPC/J0102、固件目标、LCD 驱动 |
| 显示正常、触摸无反应 | **软件引脚** → I2C 扫描 → FPC 18–21 脚 |
| `input0 open success` 但点屏无效 | **≠ 芯片在线**；必须 I2C 扫到 **0x38** |
| 显示正常 + I2C 全 `--` | `sifli_ap.c` PA37→PA30 补丁（见修复流程） |

显示（QSPI Pin 5–16）与触摸（I2C Pin 18–21）**独立**。显示稳定多次插拔后 I2C 仍空 → **软件配置 > FPC 接触**。

## 工作流（按序执行）

```
任务进度：
- [ ] 1. 确认硬件接线与模组
- [ ] 2. NSH 设备节点检查
- [ ] 3. 显示功能测试
- [ ] 4. 触摸 I2C 扫描（bus0 @ 0x38）
- [ ] 5. 对照 vendor 引脚/Kconfig
- [ ] 6. 应用补丁、VM 重编、烧录
- [ ] 7. 实机复测并输出报告
```

### 1. 硬件

- LCD：**22P FPC → J0102**（金手指朝下、插到底）；**40P 排针不接 LCD**
- 触摸 FPC 脚：18=PA31 INT，19=PA33 SDA，20=**PA30 SCL**，21=PA09 RST
- 非官方 1.85" AMOLED 转接板（CN3 40P 空）→ 触摸可能未进 J0102

### 2. NSH 节点（COM7 @ 1M，上电等 ≥15s）

```text
ls /dev
```

| 节点 | 含义 |
|------|------|
| `fb0`, `lcd0` | 显示驱动 OK |
| `i2c0` | 触摸总线（硬件 I2C1） |
| `input0` | FT6146 驱动节点（**存在 ≠ 芯片在线**） |

缺 `i2c0`/`input0` → 查 Kconfig：`CONFIG_I2C=y`、`CONFIG_INPUT_FT6146=y`（关 LSM6 后需显式 `CONFIG_I2C=y`）。

### 3. 显示测试

```text
fb
lvgldemo
ew screen info
ew screen
ew alert warn
```

期望：`fb` 报 **390×450**；`lvgldemo` 有 UI。`rcS` 已自启 `lvgldemo` 时再跑会报 `LVGL already initialized` — **直接点屏**。

### 4. 触摸 I2C（关键）

**扫 bus0，不是 bus1**（bus1 = 硬件 I2C2）：

```text
i2c bus
i2c dev -b 0 0x38 0x38
```

**PASS**：行 `30:` 出现 `38`。  
**FAIL**：全 `--` → 继续步骤 5–6。

Windows 脚本（优先执行，勿只描述）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/touch_probe.ps1 -Port COM7
powershell -ExecutionPolicy Bypass -File scripts/full_hw_check.ps1 -Port COM7
```

### 5. 已知软件 Bug（vendor_sifli）

路径：`vendor/sifli/boards/sf32lb52/sf32lb52_devkit_lcd/`

| 问题 | 错误 | 正确（DevKit-LCD） |
|------|------|-------------------|
| I2C0 SCL | `PAD_PA37` in `sifli_ap.c` | **PA30** |
| 触摸 IRQ | `CONFIG_TOUCH_IRQ_PIN=41` | **31** (PA31) |
| IMU 抢脚 | `CONFIG_SENSORS_LSM6DSL=y` | **关闭**（占 PA30/31） |
| I2C 驱动 | 关 LSM6 后可能丢 | 显式 **`CONFIG_I2C=y`**、`CONFIG_I2C_DRIVER=y` |
| PA37 冲突 | 误作 I2C SCL | 本板 **LCD_VADD_EN** |

`bsp_pinmux.c` 的 `BSP_PIN_Touch()` 正确，但 `sifli_ap.c` bringup 会覆盖。

详表见 [reference.md](reference.md)。

### 6. 修复与烧录

VM SSH：`a1@192.168.126.128`（密钥 `~/.ssh/id_ed25519_openvela_vm`）

```bash
cd ~/openvela
sed -i 's/\r$//' /mnt/hgfs/VMware_share/patches/devkit_lcd_touch_i2c.sh
bash /mnt/hgfs/VMware_share/patches/devkit_lcd_touch_i2c.sh ~/openvela
bash /mnt/hgfs/VMware_share/build_ew_main.sh
```

验证编译配置：

```bash
grep -E '^CONFIG_I2C=|^CONFIG_INPUT_FT6146|^CONFIG_TOUCH_IRQ' \
  ~/openvela/cmake_out/sf32lb52_devkit_lcd/.config
grep 'PA30, I2C1_SCL' \
  ~/openvela/vendor/sifli/boards/sf32lb52/sf32lb52_devkit_lcd/src/sifli_ap.c
```

Windows 烧录：

```powershell
& tools/sftool/sftool.exe -c SF32LB52 -p COM7 -b 1000000 `
  --before default_reset --after soft_reset `
  write_flash VMware_share/artifacts/nuttx.bin@0x12010000
```

### 7. 验收标准

| 检查项 | PASS |
|--------|------|
| `i2c dev -b 0 0x38 0x38` | 出现 `38` |
| `ls /dev` | `i2c0`, `input0`, `fb0` |
| `lvgldemo` | UI 可点按 |
| 启动 log（可选） | `ft6146 id_h=0x..` |

补丁后 I2C 有 0x38 仍无坐标 → 查 FPC 18–21、模组是否含 FT6146。

## 报告模板

完成排查后输出：

```markdown
## DevKit-LCD 排查报告

**现象**：
**硬件**：FPC/J0102 / 模组型号
**NSH**：fb0 / i2c0 / input0 / bus0@0x38
**根因**：软件引脚 | Kconfig | 硬件线序 | 其他
**已执行**：补丁 / 重编 / 烧录
**结果**：PASS / FAIL + 下一步
```

## 仓库内资源

| 路径 | 用途 |
|------|------|
| `VMware_share/patches/devkit_lcd_touch_i2c.sh` | 触摸 I2C 补丁 |
| `VMware_share/build_ew_main.sh` | VM 编译 |
| `scripts/touch_probe.ps1` | I2C + 触摸探针 |
| `scripts/full_hw_check.ps1` | 全量硬件检查 |
| `docs/DevKit-LCD_屏幕接线与自检.md` | 接线说明 |
| `docs/DevKit-LCD_触摸I2C排查与补丁.md` | 完整根因分析 |

## 常见误判（直接否定）

- ❌ 「menuconfig 未开触摸」— defconfig 通常已开 FT6146/LVGL
- ❌ `i2c dev -b 1` 扫触摸 — 应 **bus0**
- ❌ `input0 open success` = 触摸好 — 必须 **0x38 ACK**
- ❌ 「RST 未初始化」— `bsp_lcd_tp.c` 已实现

## 延伸阅读

- openvela 驱动开发：`.claude` 仓库 `nuttx-driver-development` skill
- 官方板级 README：`vendor_sifli/.../sf32lb52_devkit_lcd/README_zh-cn.md`
