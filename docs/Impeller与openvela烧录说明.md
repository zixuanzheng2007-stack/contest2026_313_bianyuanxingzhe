# Impeller 与 openvela 烧录 / 测试说明

> DevKit-LCD · COM7 · 固件 `VMware_share/artifacts/nuttx.bin@0x12010000`

---

## 1. 我们的测试脚本有没有问题？

**没有本质问题**，但和 Impeller / 官方 Demo 测的不是同一件事：

| 工具/命令 | 测什么 | 不能代替什么 |
|-----------|--------|--------------|
| `sftool write_flash` | 烧 **openvela nuttx.bin** | Impeller 的 Solution IMG 包 |
| `lvgldemo` / `fb` | **openvela** 下显示是否正常 | 官方 SiFli 出厂 UI / 触摸校准 |
| `i2c dev -b 1` | 触摸芯片是否在总线上 | 万用表能测通断，不能测线序 |
| `touch_probe.ps1` | I2C + lvgldemo 触摸日志 | 硬件没接 I2C 时仍会「open success」 |

**结论：**

- 显示、上电自启、串口 `ew` → 脚本结果 **可信**
- 触摸：I2C 全 `--` → **硬件/接线问题**，不是脚本写错
- `lvgldemo` **本身可交互**；点不了是因为 **没有触摸输入**，不是 demo 不支持

---

## 2. Impeller 和 sftool 的区别

| 项目 | Impeller（官方 GUI） | sftool（命令行，我们在用） |
|------|----------------------|----------------------------|
| 固件格式 | 目录内需 **`downfile.ini`** 或 **`ImgBurnList.ini`** | 单文件 **`nuttx.bin@0x12010000`** |
| 典型用途 | SiFli **Solution** 产线 IMG | **openvela** NuttX 镜像 |
| 接口 | UART / JLink | UART |
| 52x 进 BOOT | 工具发串口命令；**监控上电（单次）** | `write_flash` 时自动处理 |

**openvela 竞赛固件** 用 **sftool 即可**；Impeller 需先把 `nuttx.bin` 放进带 `downfile.ini` 的目录（见下）。

---

## 3. 用 Impeller 烧 openvela（可选）

### 3.1 准备目录

已准备：

```text
VMware_share/artifacts/impeller_packet/
  downfile.ini
  nuttx.bin          ← 与上级 artifacts/nuttx.bin 同步
```

### 3.2 Impeller 设置（对照 wiki）

1. USB 线接 **USB to UART**（不是 Device 口）→ **COM7**
2. 打开 **Impeller.exe**（从 [wiki 下载](https://wiki.sifli.com/tools/%E7%83%A7%E5%BD%95%E5%B7%A5%E5%85%B7.html)）
3. **设置** → 升级包路径：选 `impeller_packet` 文件夹
4. **接口**：UART · 波特率 **1000000** · 勾选 **Verify** · 建议 **压缩**
5. **设备选择**：选与 SF32LB52 / DevKit-LCD 匹配项（与 Solution 包一致；纯 openvela 可试默认 52x UART）
6. 主界面：**监控（单次）** → 功能选 **烧录** → 点 **运行**
7. **按板子 RESET**；烧完应显示成功
8. 烧录中 **勿用** PuTTY / 我们的串口脚本占 COM7

### 3.3 与 wiki「硬件设置」的关系

官方写：Impeller + SifliTrace → **LCD 亮起、可触摸**。

那是 **SiFli Solution 出厂固件** + **官方 4.3" H043 模组**。

你们现在是 **openvela + 1.85" AMOLED**，即使用 Impeller 烧 **nuttx.bin**，行为仍与 **lvgldemo / ew** 一致，**不会 magically 恢复触摸**。

---

## 4. 「串口 log / logo」看什么？

| 含义 | 怎么看 |
|------|--------|
| **串口启动 log** | Impeller 烧录日志在 `Impeller/log/`；板子 log 用 **SifliTrace** 或 PuTTY **COM7 · 1000000** |
| **屏上 logo / UI** | openvela：上电 **lvgldemo**（已写进 rcS）；官方包：Solution 开机动画 |
| **NSH 命令** | 烧录完成后：`ew help`、`fb`、`i2c dev -b 1` |

**Windows 一键（等效 Impeller 烧录后测屏）：**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\flash_sf32.ps1 -Port COM7 -Firmware "VMware_share\artifacts\nuttx.bin@0x12010000"
powershell -ExecutionPolicy Bypass -File scripts\boot_check.ps1
```

---

## 5. J0102 22P 与触摸（对照表）

触摸只在 **18–21 脚**（INT/SDA/SCL/RST）。显示脚 **3–16** 通、触摸脚未接 → **能亮不能触**，与测试程序无关。

详见 `docs/DevKit-LCD_屏幕接线与自检.md`、`docs/模组确认_1.85_AMOLED_vs_DevKit-LCD.md`。

---

## 6. 建议验收顺序（官方 + 竞赛）

1. **Impeller 或 sftool** 烧录成功  
2. 上电 **2s 内 LVGL 自启**（当前 nuttx.bin）  
3. 串口：`ew alert warn` → 屏变色 + 日志  
4. 触摸：`i2c dev -b 1` → 有设备地址才算硬件 OK  
