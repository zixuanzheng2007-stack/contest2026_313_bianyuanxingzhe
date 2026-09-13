# 技术报告撰写方案 + ChatGPT 提示词

> 对照：`2026 首届 openvela AI 硬件开发者大赛 - 作品提交模板.docx`  
> 截止：**2026-09-20** · 仓库：`contest2026_313_bianyuanxingzhe`

---

## 一、文档分工（什么现在能写、什么要等人填）


| 产出物                         | 对应模板章节     | 现状           | 谁写 / 怎么写                                    |
| --------------------------- | ---------- | ------------ | ------------------------------------------- |
| **技术报告**（.docx → .pdf）      | 全文         | ❌ 未写         | **ChatGPT 出初稿** → 三人校对 → 郑子轩定稿导出 PDF        |
| `docs/技术说明文档.md`            | 3.2–3.4 素材 | ⚠️ 停在 8 月规划版 | 报告定稿后 **回写 v2.0「已实现」**，删 IMU/BLE 等未做项或标「规划」 |
| `README.md`                 | 评委入口       | ✅ 较新         | 报告摘要可抄这里；Skill 状态需改为 ✅                      |
| `app/edge_walker/README.md` | 3.4 实现细节   | ✅            | 直接引用模块表、命令表                                 |
| `Demo脚本与验收步骤.md`            | 展示效果 / 3.5 | ✅            | 录像分镜来源                                      |
| `LD2451数据与策略复现.md`          | 3.5 功能测试   | ✅            | host_smoke ALL PASS                         |
| `开发板冒烟测试表单.md`              | 3.5 测试环境   | ❌ 未填         | **郑子轩** 真机测完勾选 A1/A2/A5                     |
| `logs/` + 3.6 AI-Native     | 3.6        | ⚠️ 部分        | 如实写 Cursor 手工归档；占比可估算                       |
| Demo 视频                     | 展示效果 10 分  | ❌            | **郑子轩** 按 Demo 脚本录                          |
| 硬件照片                        | 完整度 / 可选必交 | ❌            | **郑子轩** 多角度 + 接线                            |


**原则：** 规划文档（8 月版 `技术说明文档.md`）与 **真机已实现** 分开写——报告以 **已实现 MVP** 为准，未做功能（IMU 降敏、BLE Companion、骨传导）放「不足与展望」。

---



## 二、推荐执行顺序（3 天内可出报告初稿）



### Day 1 · 素材齐套（2 小时）

- [ ] 郑子轩：填冒烟表单 A1/A2/A5 + 拍 4 张硬件图（正/侧/接线/屏显预警）
- [ ] 王筠昊：确认 `host_smoke` 截图或日志一行 `ALL PASS`
- [ ] 韦政宇：确认 Skill 演示串口日志样例（`[ew_agent] proactive` + `[alert_output]`）
- [ ] 三人：确认分工表述、作品中文名「边缘行者」、选题「AI 硬件产品创新」



### Day 2 · ChatGPT 出稿（1 小时）

- [ ] 复制下方 **「ChatGPT 提示词」** 整段到 ChatGPT（建议 GPT-4o / o3）
- [ ] 在 `[待填]` 处粘贴：COM 口、测试日期、误报次数、录像链接占位等
- [ ] 要求输出 **完整 Markdown**，章节编号对齐模板



### Day 3 · 人工校对 + 导出（2 小时）

- [ ] 核对引脚、命令、文件名与仓库一致
- [ ] 补 **2 张 ASCII/框图**（系统架构、数据流）— 可用 draw.io 或 PPT 导出 PNG 插入 Word
- [ ] 3.5 节量化数据：**不许编造**；没有实测的写「台架/走廊场景，N=__ 次」并真测后填
- [ ] 导出 PDF，命名：`边缘行者-技术报告-contest2026_313_bianyuanxingzhe.pdf`
- [ ] 更新 `docs/00_提交材料索引.md` 勾选状态

---



## 三、报告 vs 现有 `技术说明文档.md` 的差异


| 8 月规划文档写的        | 9 月真机实际                           | 报告应写               |
| ---------------- | --------------------------------- | ------------------ |
| IMU 场景降敏         | 未上板                               | 展望                 |
| BLE 手机 Companion | 未做                                | 展望                 |
| 震动马达 PWM         | **蜂鸣 PA28 + LCD 变色**              | 已实现                |
| SDIO WiFi        | **ESP UART AT 猫**                 | 已实现                |
| 5 个 Skill        | **1 个** `approach-warn`           | 已实现 1 个（满足硬性）      |
| ai_agent 独立进程    | **ew 内嵌 + 可选 nuttx_ai_agent.bin** | 两路径都写，主推 ew boot 链 |


---



## 四、ChatGPT 提示词（整段复制）

```text
如：三页 LV你是 openvela AI 硬件大赛技术报告撰写助手。请根据以下「已核实事实」撰写一份完整的中文技术报告，严格对齐官方提交模板章节（信息表、摘要、3.1–3.7），输出 Markdown，便于粘贴到 Word。

## 写作约束
1. 语言：简体中文，技术报告体，避免口语和夸大。
2. 只写「已实现或已验证」的内容；IMU、BLE Companion、骨传导、多 Skill 等未实现项放入 3.7「不足与展望」。
3. 3.5 测试数据：已知数据直接写；标注 [待填] 的占位不得编造数字，用表格留空或写「待路测补充」。
4. 3.6 AI-Native：如实说明主开发使用 Cursor Agent，日志手工归档至 logs/；官方采集器因无 .repo 工作区未启用。
5. 摘要 ≤300 字；含量化成果（GL UI、LD2451  UART 解析、host_smoke ALL PASS、断网可告警等）。
6. 每个大节下用二级/三级标题；关键列表用表格。
7. 文末附「修订记录」表。

---

## 作品基本信息（必须使用）

| 项目 | 内容 |
|------|------|
| 作品名称 | 边缘行者 |
| 队伍名称 | 边缘行者（bianyuanxingzhe） |
| 专属仓库 | contest2026_313_bianyuanxingzhe |
| 选题方向 | AI 硬件产品创新 |
| 截止提交 | 2026-09-20 |

### 团队分工
| 成员 | 职责 | 代码占比（约） |
|------|------|----------------|
| 郑子轩 | 硬件接线、主程序、预警 UI、蜂鸣、WiFi AT、烧录演示 | 48–51% |
| 王筠昊 | LD2451 帧解析、ew_decide 门限、host_smoke 回归 | 15% |
| 韦政宇 | Agent 对话页、LLM(MiMo)、Skill approach-warn、Tool approach_alert | 34–37% |

---

## 产品与技术事实（必须使用，勿改引脚）

### 1.1 问题与场景
- 城市步行时，侧后方静音电动车接近，行人难察觉。
- 产品形态：竞赛阶段为 DevKit-LCD + 外挂 LD2451 雷达的原型（未来腰戴环状）。
- 边界：不替代盲杖/导盲犬/车端开门预警。

### 1.2 创新点（写 3 条）
- 端侧毫米波 + 本地门限，断网仍可橙/红预警 + 蜂鸣。
- openvela 上 LVGL 三页 UI（预警 / Agent / WiFi）+ NSH 命令 ew 统一入口。
- ai_agent Skill「接近提醒」：雷达越限主动调用 Tool approach_alert → alert_output，LLM 不参与测距判决。

### 2.1 系统架构（请用文字 + 建议 ASCII 框图）
```

LD2451 ──UART2(/dev/ttyS1, PA20/PA27)──► ew_ld2451 解析 + ew_decide 门限
                                              │
                                              ▼
                                    alert_output() ──► PA28 蜂鸣 + LVGL 预警页变色
                                              ▲
                         ew_agent 主动 Tool approach_alert（Skill: approach-warn）
                                              │
ESP AT 猫 ──UART3(PA24/PA25)──► ew_wifi_at ──► ew_llm(MiMo HTTPS) ──► Agent 对话页

```

### 2.2 硬件
| 组件 | 型号/接口 | 说明 |
|------|-----------|------|
| 主控 | SF32LB52-DevKit-LCD | openvela + LVGL AMOLED |
| 雷达 | HLK-LD2451 | 24G 毫米波，UART 115200，TX→PA20 RX→PA27 |
| 联网 | ESP8266/32 AT 固件 | PA24→ESP RX, PA25←ESP TX |
| 告警 | PA28 无源蜂鸣 + LCD | 橙 ~2300Hz，红 ~2700Hz |
| 调试 | USB-UART | 常见 COM7 @ 1Mbps |

### 2.3 软件模块（app/edge_walker/）
| 模块 | 文件 | 职责 |
|------|------|------|
| 入口 | ew_main.c | NSH 命令 ew |
| 雷达 | ew_ld2451.c | 协议解析 + ew_decide |
| 提醒出口 | alert_output.c | 日志 + 蜂鸣 + 屏色一处调用 |
| 预警 UI | alert_lcd.c | EW READY / WARN / CRIT |
| WiFi | ew_wifi_at.c, ew_wifi_ui.c | 扫描、配网、/data/ew_wifi.conf |
| Agent | ew_chat.c, ew_llm.c | 对话页 + MiMo |
| Skill/Tool | ew_agent.c, ew_agent_tool.c, skills/approach-warn.md | 主动 approach_alert |
| 回归 | host_smoke.c | 主机侧 ALL PASS |

### 2.4 openvela 能力落地（模板 3.3/3.4 必写）
- **图形**：LVGL 三页 UI，CO5300 QSPI 屏，FT6146 触摸。
- **AI**：ai_agent Skill + Tool；云端 MiMo 仅用于对话/简报，不参与告警判决。
- **多媒体**：未用音视频；可说明预留。
- 组件：NuttX NSH、LVGL、vendor/sifli BSP、Contest Kconfig `CONFIG_LVX_USE_DEMO_CONTEST2026_313_EDGE_WALKER`。
- 编译：./build.sh 或 ninja -C cmake_out/sf32lb52_devkit_lcd；烧录 nuttx.bin @ 0x12010000。

### 2.5 Skill 硬性要求
- 名称：approach-warn
- 路径：/data/ai_agent/skills/approach-warn.md（ew boot 时安装）
- 触发：ew_decide 输出 SOFT/STRONG/EMERGENCY → ew_agent_proactive_alert → tool approach_alert → alert_output
- 演示：ew fake 10 20 或真机靠近；串口应见 [ew_agent] 与 [alert_output]

---

## 测试与数据（3.5 节）

### 已验证项（可写「通过」）
| 测试项 | 方法 | 结果 |
|--------|------|------|
| 主机回归 | gcc host_smoke.c ew_ld2451.c && ./host_smoke | ALL PASS |
| 手动三档告警 | ew alert soft/strong/crit | 屏色 + 蜂鸣 OK |
| 假目标链路 | ew fake 10 20 | alert_output 日志 OK |
| 断网预警 | 不连 WiFi，雷达/ fake 触发 | 本地告警仍可用 |
| WiFi AT | ew wifi ping / scan | [待填：郑子轩补一次结果] |
| Agent 对话 | 快捷句 Who are you? / ew ask | [待填：需 ONLINE 时结果] |

### 量化数据（不得编造，用占位）
| 指标 | 实测值 |
|------|--------|
| UI 帧循环周期 | EW_UI_FRAME_MS = 8 ms |
| 告警恢复延迟 | 约 1 s（目标离开后回 EW READY）[待填：录像实测] |
| host_smoke 用例数 | [待填：host_smoke 输出条数] |
| 走廊接近测试次数 / 误报 / 漏报 | [待填] |
| 连续运行时长 | [待填：如 30 min 无崩溃] |
| 固件大小 | nuttx_wifiui.bin 约 1601812 B（含 WiFi UI + serial_ctl）[可选] |

---

## AI-Native 开发说明（3.6 节，必须如实）

| 指标 | 内容 |
|------|------|
| AI Coding 代码占比 | 约 70–85%（估算：核心 C 模块多数由 Cursor Agent 起草，人工校对引脚/门限/联调） |
| 使用工具 | **Cursor Agent**（主）；队友 Ubuntu VM 协作编译 |
| 未使用 | 官方 contest-log-collector（本机无 .repo 全量工作区）；Claude Code/Codex 自动采集 |
| 日志 | logs/zixuanzheng2007-stack/ 手工归档 3+ 会话，schema 1.0，含 raw/ |
| MCP | 未使用 VelaJS MCP / Figma MCP |
| Skills | 新增 approach-warn（仓库 skills/approach-warn.md） |
| Token | [待填：MiMo 控制台用量，若无则写「对话次数约 __ 次」] |
| 效率与问题 | AI 加速文档/驱动骨架/协议解析；难点在真机引脚、UART 多字节 TX、LVGL 触摸边距，需人工示波与实机迭代 |

---

## 商业与展望（3.7 节）
- 受众：城市通勤行人、听障用户（震动为主）。
- 商业：腰戴安全辅具、可与导航 App 未来 BLE 联动（当前未实现）。
- 不足：无 IMU 降敏、无正式路测数据集、中文字体需 MiSans 部署、日志非官方采集。

---

## 演示与提交（简短提及）
- Demo 视频 ≤5 分钟：感知预警 → Agent → WiFi（可选）。
- 源码 + logs 在 GitHub 专属仓；PR 至 dev-ai-contest-2026。
- 压缩包命名：边缘行者-边缘行者-contest2026_313_bianyuanxingzhe.zip

---

## 输出格式要求
请按以下顺序输出完整 Markdown：

# 边缘行者 · 技术报告

## 1、信息表
（表格）

## 2、摘要
（≤300 字）

## 3、正文
### 3.1 绪论
### 3.2 系统方案设计
### 3.3 核心算法与技术原理
### 3.4 系统实现
### 3.5 系统测试与结果分析
### 3.6 AI-Native 开发说明
### 3.7 总结与展望

## 修订记录

并在 3.2 节末给出「评审维度自检表」：技术难度/创新性/完整度/AI 开发/商业潜力/展示效果 各对应哪些章节。
```

---



## 五、ChatGPT 之后的人工必改清单

1. **3.5 所有 [待填]**：必须换成真机数据或删除该指标。
2. **框图**：ChatGPT 的 ASCII 可保留，建议另做 1 张正式系统框图插入 Word。
3. **照片**：Word 里插入硬件图（模板序号 3「作品展示照片」可单独文件夹，也可精选进报告）。
4. **与代码一致**：命令、引脚以 `app/edge_walker/README.md` 为准。
5. **Skill 状态**：勿再写「待韦政宇合入」——`ew_agent.c` 已在主固件。
6. **导出 PDF** 后把路径记入 `docs/00_提交材料索引.md`。

---



## 六、可选：第二轮提示词（润色/缩摘要）

```text
下面是一份 openvela 大赛技术报告 Markdown 初稿。请：
1. 将摘要压缩到 300 字以内且保留量化数字；
2. 3.5 节把空洞形容词改成「测试项 | 步骤 | 预期 | 实际」四列表格；
3. 删除所有「可能」「也许」；未测数据改为「待测」而非编造；
4. 输出修订后的完整 Markdown。

[粘贴初稿]
```

