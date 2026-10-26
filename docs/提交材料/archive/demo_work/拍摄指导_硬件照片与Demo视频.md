# 边缘行者 · 硬件照片与 Demo 视频拍摄指导（V2）

> **队伍**：边缘行者 · **板型**：SF32LB52-DevKit-LCD  
> **截止**：2026-09-20  
> **修订**：2026-09-18 — 按导师意见：**分段录制 → 剪辑合成**；WiFi/Agent **录屏远控 + 板屏并列**，避免小屏触控拍摄困难。  
> **关联**：[`Demo脚本与验收步骤.md`](../../Demo脚本与验收步骤.md) · [`技术报告排版定稿指南.md`](../report_work/技术报告排版定稿指南.md)

---

## 1. 导师意见与对策

| 意见 | 本队对策 |
|------|----------|
| 文档格式偏简陋 | Word 定稿按 [`技术报告排版定稿指南.md`](../report_work/技术报告排版定稿指南.md) 做封面/目录/三线表/图注 |
| 现视频仅 6s 片段 | **6 段素材分开录**，剪映/CapCut 合成 ≤5 min 成片 |
| WiFi、对话、分档报警要分开展示 | 每段独立文件 `clip_A`～`clip_F`，见 §4 |
| 小屏操作难拍 | **B/C/D 段用 PC 远控**（`ew_panel` + 串口 `@`）与 **实物屏左右并列** |

---

## 2. 产出清单

| 类型 | 路径 | 说明 |
|------|------|------|
| 硬件照片 | `docs/提交材料/photos/` | ≥4 张；补 **橙 WARN / 红 CRIT** |
| **分镜素材** | `docs/提交材料/archive/demo_work/demo_clips/`（不进 zip） | `clip_A.mp4` … `clip_F.mp4` |
| **成片** | `边缘行者-Demo-contest2026_313_bianyuanxingzhe.mp4` | ≤5 min，官网必交 |
| 技术报告 PDF | 同名 pdf | 定稿后打包 |

```powershell
mkdir docs\提交材料\archive\demo_work\demo_clips -Force
python scripts/submission/pack_submission.py
```

---

## 3. 拍摄前准备

### 3.1 硬件与串口

| 项 | 要求 |
|----|------|
| 调试口 | 板 **USB to UART** → COM7 @ **1 Mbps** |
| 固件 | 含 `ew boot`；上电 **EW READY** 蓝底 |
| 雷达/蜂鸣 | LD2451 + PA28 蜂鸣已接（见 `docs/硬件/DevKit-LCD.md`） |
| ESP AT | WiFi/Agent 段需要；断网段 A 可拔模块或关热点 |

### 3.2 PC 远控工具（WiFi / Agent 必装）

| 工具 | 用途 | 启动 |
|------|------|------|
| **ew_panel** | COM7 镜像 + `@goto` `@tap` `@ask` 遥控 | `scripts/host/EW_PANEL.bat` |
| **OBS / Win11 录屏** | 采集「左：PC 控制台 / 右：实物屏」 | 见 §5.2 |
| 串口（备用） | NSH / `@ping` | `nsh_cmd.ps1` |

`ew_panel` 连接 COM7 后发送 `@mirror on` 可在 PC 侧看到屏镜像；发送 `@goto wifi`、`@ask …` 无需手指点 390×450 小屏。

### 3.3 环境

- 实物屏：三脚架固定，横屏 16:9，1080p
- 桌面纯色；画面无密码、SSID 全名（WiFi 列表可打码）
- 每段 **单独录**：失败只重录该段，不重拍全长

---

## 4. 分镜素材表（先分段，后剪辑）

**原则**：一段一文件，文件名固定，便于剪辑对表。

| 文件 | 内容 | 机位 | 时长 | 优先级 |
|------|------|------|------|--------|
| **clip_A_intro.mp4** | 口播 + 硬件全貌 | 手机俯拍板子 | 25–35 s | P0 |
| **clip_B_alert_ladder.mp4** | **分档报警**：READY → SOFT/WARN → CRIT → 恢复 | 手机侧拍屏+蜂鸣器 | 60–90 s | P0 |
| **clip_C_offline.mp4** | **断网仍预警**（拔 ESP 或关 WiFi 后再靠近/`ew fake`） | 同 B | 30–45 s | P0 |
| **clip_D_agent.mp4** | **Agent 对话** | **录屏：左 ew_panel/串口，右实物屏** | 45–60 s | P0 |
| **clip_E_wifi.mp4** | **WiFi 扫描/连接/ping** | **录屏并列**（同上） | 45–60 s | P0 |
| **clip_F_skill.mp4** | Skill 链：`ew fake 10 20` + 串口 `[ew_agent]` | 录屏或串口+屏 PiP | 30–40 s | P1 |
| **clip_G_outro.mp4** | 架构图 / 三人分工字幕 | 静态图 + 配音 | 15–20 s | P1 |

**成片时长目标**：4:30～4:50（留 10 s 余量）

---

## 5. 各段操作脚本

### 5.1 clip_A · 开场（手机拍）

**口播参考**（可字幕）：

> 「边缘行者」：腰后自行车（含共享单车）或静音电动车接近时，板端 LD2451 本地判距，橙/红屏与蜂鸣主动提醒；联网后可问 Agent；安全判决不依赖云端。

**画面**：EW READY + 雷达 + 蜂鸣 + ESP 入镜，缓慢平移一圈。

---

### 5.2 clip_B · 分档报警（手机拍 · 必拍清楚四态）

| 步骤 | 触发方式 | 屏幕预期 | 音频 |
|------|----------|----------|------|
| B1 | 上电稳定 | **EW READY** 蓝底 | 环境音 |
| B2 | `ew alert soft` 或 `@alert soft demo` 或真机慢靠近 | **SOFT/WARN 黄或橙** | 较低频蜂鸣 |
| B3 | `ew alert crit` 或 `@alert strong` / 更近距离 | **CRIT 红** | 更高频蜂鸣 |
| B4 | 离开 / `@alert none` | 回 **READY**，蜂鸣停 | 强调「约 1 s 恢复」 |

**NSH 保底**（雷达难触发时口播「模拟接近事件」后执行）：

```text
ew alert soft test
ew alert strong test
ew alert crit test
```

**照片同步**：补拍 `photos/03_预警橙.jpg`、`04_预警红.jpg` 供报告插图。

---

### 5.3 clip_C · 断网预警（手机拍）

1. 口播：「关闭 WiFi / 拔掉 ESP，安全环仍本地工作」
2. 展示预警页无 ONLINE（或拔掉 ESP）
3. 重复 B2–B4 任一档，或 `ew fake 10 20`

---

### 5.4 clip_D · Agent 对话（录屏 · 并列布局）

**推荐布局（OBS 场景「EdgeWalker_Dual」）**：

```text
┌─────────────────────┬─────────────────────┐
│  PC：ew_panel        │  实物：DevKit 屏     │
│  - 镜像窗 @mirror on │  （三脚架同角度）     │
│  - 或 Cursor 终端    │  Agent 气泡需清晰     │
│    发 @ask / @goto   │                      │
└─────────────────────┴─────────────────────┘
```

**步骤**：

| 步 | PC 操作 | 实物屏预期 |
|----|---------|------------|
| D1 | `@goto chat` 或面板点 Agent | 进入对话页 |
| D2 | `@ask Who are you?` 或点快捷句 | 出现回复气泡 |
| D3 | `@ask 告警怎么工作`（或英文） | 第二条回复 |

**说明**：LAN ONLY 仍可能对话（HTTPS）；若失败，保留英文快捷句 + 口播「需联网时由 MiMo 回答，判距仍在板端」。

**ew_panel 快速命令**：

```text
@mirror on
@goto chat
@ask Who are you?
```

---

### 5.5 clip_E · WiFi（录屏 · 并列布局）

**勿依赖手指点小屏 Scan**，用 PC：

| 步 | PC（ew_panel 或 NSH） | 状态栏预期 |
|----|----------------------|------------|
| E1 | `@goto wifi` | WiFi 页 |
| E2 | NSH：`ew wifi scan`（录终端输出，≥60 s 可剪） | 列表出现 AP |
| E3 | `@join "热点名" "密码"` 或屏上 Connect | **WIFI ON ip** 或 **LAN ONLY ip** |
| E4 | `ew wifi ping` | MODEM/WIFI/LAN/ONLINE 四层 log |

**字幕解释 LAN ONLY**：「已连热点有 IP；公网 ping 可能因手机热点策略失败，Agent 以 HTTPS 实测为准。」

---

### 5.6 clip_F · Skill（录屏）

终端执行：

```text
ew fake 10 20
```

窗口同时显示：串口 `[ew_agent] proactive …` + 屏变 WARN/CRIT（PiP 实物屏或 `@mirror`）。

---

## 6. 剪辑合成（CapCut / 剪映）

> **已有四段源素材**（PC 录屏 ×2 + 手机 ×2）时，剪辑者直接按 [`demo_clips/剪辑指导_四段素材.md`](demo_clips/剪辑指导_四段素材.md) 操作：其中 §4 为 **一律删除的等待/废片**，§5 为 **分文件剪留清单**。

### 6.1 时间轴模板

| 时间 | 素材 | 字幕 |
|------|------|------|
| 0:00–0:30 | clip_A | 作品名 + 一句话 |
| 0:30–1:50 | clip_B | 分档报警 |
| 1:50–2:20 | clip_C | 断网仍预警 |
| 2:20–3:10 | clip_D | Agent 对话 |
| 3:10–4:00 | clip_E | WiFi 配网 |
| 4:00–4:30 | clip_F | Skill 主动告警 |
| 4:30–5:00 | clip_G | 架构图 + 致谢 |

### 6.2 剪辑规范

- 转场：**硬切**为主；段首加 0.5 s 黑场 + 段标题字卡（如「二、分档预警」）
- 字体：思源黑体/微软雅黑，白字黑描边
- 保留 **1～2 s** 真实响应时间，勿快剪掩盖延迟
- 蜂鸣段 **不要静音**
- 导出：**H.264 · 1080p · 30fps · AAC**，≤5:00

### 6.3 导出路径

```text
docs/提交材料/边缘行者-Demo-contest2026_313_bianyuanxingzhe.mp4
```

---

## 7. 硬件照片（与 V1 相同 + 补拍）

| 文件 | 内容 | 状态 |
|------|------|------|
| `01_正面.jpg` | 整体接线 | ✅ 已更新 |
| `02_接线.jpg` | LD2451↔ESP | ✅ |
| `03_预警橙.jpg` | **橙/黄 WARN** | ⚠️ 待补（现 03 为 SOFT） |
| `04_预警红.jpg` | **CRIT 红** 或 EW READY 对照 | ⚠️ 待补 |
| `extra/06_Agent页.jpg` | Agent 页 | ✅ |

---

## 8. 拍完后检查

### 8.1 成片

- [ ] 时长 ≤ 5:00
- [ ] 含 **READY / WARN或SOFT / CRIT** 至少三态
- [ ] 含 **断网预警** 一段
- [ ] 含 **Agent 对话**（录屏并列）
- [ ] 含 **WiFi**（录屏并列或 ping log）
- [ ] 含 **AI/Skill**（fake 或 agent log）
- [ ] 文件名正确

### 8.2 报告与打包

- [ ] Word 按排版指南定稿 PDF
- [ ] `python scripts/submission/pack_submission.py`

---

## 9. 常见问题

| 现象 | 处理 |
|------|------|
| 小屏点不准 | 改用 **ew_panel** `@tap x y` / `@goto` |
| COM7 无数据 | 确认 USB-UART 口；关 sscom；按 RESET |
| LAN ONLY | 见 §5.5 字幕说明；E4 仍录 ping 四层 |
| 镜像卡顿 | `@mirror fast`；录屏以 **实物屏** 为准 |
| 单段拍砸 | 只重录对应 `clip_*.mp4`，不必全长重拍 |

---

## 10. 赛题能力 ↔ 视频段对照

| 能力 | 视频段 | 代码 |
|------|--------|------|
| 本地判距告警 | B、C | `ew_ld2451` + `alert_output` |
| 分档输出 | B | `alert_lcd` + 蜂鸣 |
| Agent 对话 | D | `ew_chat` + `ew_llm` |
| WiFi | E | `ew_wifi_at` |
| Skill 主动 | F | `ew_agent` + `approach-warn` |

---

*V2 · 2026-09-18 · 郑子轩（集成/提交）*
