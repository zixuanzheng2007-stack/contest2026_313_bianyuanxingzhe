# 边缘行者 · Demo 脚本与验收步骤（评委 / 录像用）

> 截止 2026-09-20 · 板型 SF32LB52-DevKit-LCD · NSH 命令 `ew`  
> 固件示例：`nuttx.bin` @ `0x12010000` · 串口 COM7 @ 1 Mbps

---

## 1. 用户故事（30 秒口播）

「边缘行者」是腰后接近预警：后方有电动车靠近时，**板子本地**判断距离与速度，**不依赖云端**即可橙/红屏 + 蜂鸣；联网后可向智能体问「告警怎么工作」，靠近时系统**主动**提醒，无需用户先开口。

---

## 2. 硬件准备（录像前检查）

| 设备 | 接法 |
|------|------|
| LD2451 | VIN→5V，GND→GND，雷达 TX→板 **PA20**，雷达 RX→板 **PA27**（UART2 `/dev/ttyS1`） |
| ESP AT 猫（可选联网） | 板 **PA24**→ESP RX(GPIO16)，板 **PA25**←ESP TX(GPIO17)，共 GND |
| 蜂鸣器 | PA28（无源，方波驱动） |
| 调试串口 | 板 **USB-UART** → 电脑 COM（常见 COM7） |

---

## 3. 演示 A · 感知预警（必拍，约 2 分钟）

**开机**：上电后 `rcS.user` 自动 `ew boot`，预警页显示 **EW READY**（蓝底）。

| 步骤 | 操作 | 预期 |
|------|------|------|
| A1 | 人/反射物从雷达后方靠近（或手在雷达前挥动） | 屏变 **橙色 WARN** 或 **红色 CRIT** |
| A2 | 听蜂鸣 | 橙 ~2300 Hz，红 ~2700 Hz，持续响 |
| A3 | 目标离开 | 约 1 s 内回 **EW READY**，蜂鸣停 |
| A4（备选） | NSH：`ew alert soft` / `strong` / `crit` | 三档屏色 + 蜂鸣，无需雷达 |
| A5（备选） | NSH：`ew fake 10 2` | 控制台 `[alert_output] level=...`，有 UI 时同步变色 |

**断网说明**：拔掉 ESP 或不开 WiFi，重复 A1–A3 仍应通过（安全环离线可用）。

---

## 4. 演示 B · 智能体对话（必拍，约 1 分钟）

| 步骤 | 操作 | 预期 |
|------|------|------|
| B1 | 预警页点 **Agent**（或 NSH：`ew chat`） | 进入对话页 |
| B2 | 点快捷句 **「Who are you?」** 或 **「告警怎么工作」** | 气泡回复（本地或 MiMo） |
| B3 | NSH（可选）：`ew ask 现在后面有没有车` | 打印回复（需 WiFi + AT 通） |

**说明**：固件已内嵌思源黑体 GB2312 字库，中文候选字不依赖板端 TTF/OTF。字库外字符会显示为 `?`，不会导致整段文字渲染失败；如需扩展字符，可在 `/data/font/` 部署 OFL 授权的 Source Han Sans 或 Noto Sans CJK。

---

## 5. 演示 C · WiFi 配网（可选，约 1 分钟）

| 步骤 | 操作 | 预期 |
|------|------|------|
| C1 | 预警页点 **WiFi** | 进入扫描页 |
| C2 | 点 **Scan** 或 **+ enter SSID manually** | 列出 2.4G 热点或手输 SSID |
| C3 | 选 AP → 输密码 → Connect | 状态 **ONLINE \<ip\>** 或 **LAN ONLY \<ip\>** |
| C4 | NSH：`ew wifi ping` | `[ew-at] ... OK` |

---

## 6. 赛题「主动 + 执行」口径（答辩用）

| 能力 | 实现位置 | 状态 |
|------|----------|------|
| 接近检测 | `ew_ld2451.c` 解析 + `ew_decide` 门限 | ✅ 已落地 |
| 主动执行提醒 | `alert_output()` → 蜂鸣 + LCD | ✅ 已落地（不等人问） |
| ai_agent ≥1 Skill | `approach-warn` + `approach_alert`（`ew_agent.c`） | ✅ 已落地；录像用 `ew fake 10 20` 验链路 |
| 对话 | `ew_chat` + `ew_llm`（MiMo HTTPS） | ✅ 可用（依赖联网） |

当前：**安全环主动告警 + Skill 链已编进固件**；Demo 必拍 A（预警）+ B（Agent/Skill 日志或快捷句），C（WiFi）可选。

---

## 7. 5 分钟录像（V2 · 分段录 → 剪辑）

> 详表与 OBS 并列布局见归档的 [`拍摄指导_硬件照片与Demo视频.md`](archive/demo_work/拍摄指导_硬件照片与Demo视频.md)。

**不要一镜到底**；原始分镜已归档至 `docs/提交材料/archive/demo_work/demo_clips/`。

| 素材 | 内容 | 机位 |
|------|------|------|
| clip_A | 口播 + 硬件全貌 | 手机拍板 |
| clip_B | **分档报警** READY→SOFT/WARN→CRIT→恢复 | 手机拍屏+蜂鸣 |
| clip_C | **断网仍预警** | 手机拍屏 |
| clip_D | **Agent 对话** | **录屏：PC ew_panel/串口 ∥ 实物屏** |
| clip_E | **WiFi scan/join/ping** | **录屏并列**（勿依赖小屏触控） |
| clip_F | `ew fake 10 20` Skill 链 | 录屏 + 串口 log |
| clip_G | 架构图收尾 | 静态图 |

**PC 远控**：`scripts/host/EW_PANEL.bat` → `@mirror on` `@goto wifi|chat` `@ask …`

合成时间轴：A(0:30) → B(1:20) → C(0:30) → D(0:50) → E(0:50) → F(0:30) → G(0:20) ≈ **4:50**

---

## 8. 烧录后屏上勾选

固件：`VMware_share/artifacts/nuttx.bin`（或 `nuttx_wifiui.bin`）@ `0x12010000` · COM7 @ 1Mbps

- [ ] 开机进预警页，雷达接好时不长期卡 NO RADAR
- [ ] `ew fake 10 20` → 橙/红 + 蜂鸣；串口见 `[ew_agent]` + `[alert_output]`
- [ ] WiFi 页 scan / 手动 SSID → 状态 `WIFI ON x.x.x.x` 或失败原因
- [ ] Agent 页快捷句「Who are you?」/「告警怎么工作」（需联网时先连 WiFi）

VMware USB 透传：可移动设备 → 连接 CH343 → Guest 可烧录 `/dev/ttyACM0`。

---

## 9. 三人分工（代码归属）

| 成员 | 模块 | 代码占比（行） |
|------|------|----------------|
| 郑子轩 | 主程序、预警 UI、蜂鸣、WiFi UI/AT、`@` 遥控/镜像、硬件烧录 | 55–61% |
| 王筠昊 | LD2451 解析与策略、`host_smoke` | 10–15% |
| 韦政宇 | Agent 页、拼音、LLM、Skill/Tool | 29–35% |

*不含 `ew_font_cjk_18.c` 生成字库。*

详见 `docs/分工/工作完成情况_2026-09-11.md`。
