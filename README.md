# 边缘行者（Bian Yuan Xing Zhe）

队伍专属仓：`contest2026_313_bianyuanxingzhe` · 截止 **2026-09-20**

## 一、作品简介

面向骑行/步行场景的**后方来车接近预警**原型：毫米波雷达感知接近目标，在 **SF32LB52-DevKit-LCD（openvela）** 上完成本地解析与门限决策，并给出可感知告警（蜂鸣 / LCD / LED 等，输出抽象为 `alert_output`）。

最小闭环：

```text
LD2451 ──UART──► 板端解析 + 本地门限决策 ──► alert_output（可感知响应）
```

初赛 MVP 双线：① LD2451→板端门限→`alert_output`；② openvela **ai_agent** 上板 + ≥1 Skill + ≥1「主动+执行」（接近触发告警 Tool）。测距不靠 LLM。分工见 `docs/分工/`。

## 二、选题方向

**AI 硬件产品创新**（参考官方指南，非排他命题）。

理由：真实边缘感知 + 板端门限 + ai_agent「主动告警执行」，贴近腰戴安全产品，并满足赛道 Agent 硬性要求。

## 三、目录结构

```text
contest2026_313_bianyuanxingzhe/
├── README.md                 # 本作品说明（评委入口）
├── contest2026_313_bianyuanxingzhe.xml / openvela.xml
├── app/edge_walker/          # ★ 板端主应用（NSH 命令 ew）
├── app/hello_app/            # 模板骨架（保留）
├── board_overlay/sf32lb52_devkit_lcd/  # rcS.user → ew boot
├── board/contest_board/      # 模板板级骨架
├── quickapp/hello_quickapp/  # 快应用模板（本作品暂不依赖）
├── docs/                     # 方案、选型、接线、分工、冒烟记录
├── scripts/                  # Windows 检测/冒烟/烧录辅助脚本
├── tools/                    # 本机工具缓存（驱动/雷达APP/sftool；大文件默认不入仓）
└── logs/                     # AI Coding 日志（必须提交）
    └── zixuanzheng2007-stack/
```

详细文档索引见 [`docs/00_提交材料索引.md`](docs/00_提交材料索引.md)。

## 四、运行方式

### 1. 拉取 openvela 全量工程（Ubuntu 22.04 推荐）

```bash
repo init -u https://github.com/open-vela/contest2026_313_bianyuanxingzhe \
  -b dev-ai-contest-2026 -m contest2026_313_bianyuanxingzhe.xml
repo sync -c -j8
```

同步后：本仓位于工作区 `contest2026_313_bianyuanxingzhe/`，全量源码在外层（`nuttx/`、`apps/`、`vendor/` 等）。

### 2. 编译目标板

`repo sync` 后 `app/edge_walker` 通过 manifest 链到  
`packages/demos/contest2026_313_edge_walker`。

在 openvela 工作区根目录：

```bash
# menuconfig 中打开：
#   Contest 2026 team 313 edge_walker
#   LVGL / FreeType（若需 Agent 中文）

./build.sh vendor/sifli/boards/sf32lb52_devkit_lcd --cmake -j8
# 路径以 vendor 实际目录为准；亦可用已配置的 cmake_out 增量：
# ninja -C cmake_out/sf32lb52_devkit_lcd
```

产物：`cmake_out/sf32lb52_devkit_lcd/nuttx.bin`，烧录地址 **`0x12010000`**。

### 3. 烧录（Windows 真机站）

- 接口：DevKit **USB-to-UART**（CH343），本机当前枚举为 **COM7**
- 工具：`tools/sftool/sftool.exe` 或思澈 Impeller（Interface=UART）

```powershell
powershell -ExecutionPolicy Bypass -File scripts\flash_sf32.ps1 `
  -Port COM7 -Firmware "nuttx.bin@0x12010000"
```

等价：

```text
sftool -c SF32LB52 -p COM7 -b 1000000 write_flash nuttx.bin@0x12010000
```

### 4. 雷达接线（LD2451）

- VIN→5V，GND→GND，TX↔RX 交叉接板端业务 UART（勿占用 Debug UART）
- 手机 **HLKRadarTool** 可先蓝牙验活；量产路径以 UART 协议解析为准

更细的接线见 [`docs/三款毫米波雷达综合选型与接线手册.md`](docs/三款毫米波雷达综合选型与接线手册.md)。

### 5. 板上演示（评委 / 录像）

上电自动进入预警页（`ew boot`）。完整分镜见  
[`docs/提交材料/Demo脚本与验收步骤.md`](docs/提交材料/Demo脚本与验收步骤.md)。

**最小验收（30 秒）：**

```text
# 串口 COM7 @ 1Mbps，RTS/DTR 关
ew alert soft      → 橙屏 + 蜂鸣
ew alert crit      → 红屏 + 高频蜂鸣
ew alert none      → 回 EW READY
```

**雷达实机：** 后方靠近 → 橙/红 + 蜂鸣 → 离开约 1s 恢复（**断网仍可用**）。

**智能体：** 点 **Agent** → 快捷句「Who are you?」/「告警怎么工作」；NSH：`ew ask <问题>`（需 WiFi）。

| 模块 | 负责人 |
|------|--------|
| 主程序 / 预警 UI / 蜂鸣 / WiFi | 郑子轩 |
| LD2451 数据与策略 | 王筠昊 |
| Agent 对话 / LLM / Skill+Tool | 韦政宇 |

**赛题 Agent（已实现）：** `ew boot` 安装 Skill `approach-warn`（`/data/ai_agent/skills/`），雷达越限经 `ew_agent_proactive_alert` → Tool `approach_alert` → `alert_output()`。演示：`ew fake 10 20`，串口见 `[ew_agent]`、`[alert_output]`。详见 [`app/edge_walker/README.md`](app/edge_walker/README.md)。

**提交进度：** 代码在 [`feature/host-edge-walker`](https://github.com/zixuanzheng2007-stack/contest2026_313_bianyuanxingzhe/tree/feature/host-edge-walker) → [PR #4](https://github.com/open-vela/contest2026_313_bianyuanxingzhe/pull/4) 合入 `dev-ai-contest-2026`（CLA ✅）。技术报告见 [`docs/提交材料/边缘行者_技术报告_V1.0.md`](docs/提交材料/边缘行者_技术报告_V1.0.md)。

## 六、AI Coding 使用说明

本阶段主要使用 **Cursor Agent** 完成：赛题解读、硬件选型、仓库/PR/CLA、文档精简、雷达与串口冒烟、sftool 连通 SF32、提交材料整理等。

| 会话 | 说明 |
|------|------|
| `6e5f1783-…` | openvela **母目录**会话：竞赛页/硬件资料与选型分析（2026-07-19 起） |
| `c06c0b41-…` | 专属仓 fork / `dev-ai-contest-2026` 分支确认 |
| `df773b3a-…` | 主开发会话：方案、文档、雷达、板端检测烧录至提交整理 |

完整对话见 [`logs/zixuanzheng2007-stack/`](logs/zixuanzheng2007-stack/)：

- 转换后的竞赛 schema JSONL：`cursor__<sid>.jsonl`
- **原始 Cursor transcript**：同日目录下 `raw/<sid>.jsonl`

> **合规说明**：官方自动采集工具支持 Claude Code / OpenCode / Codex / AIoT-IDE。Cursor 不在官方自动采集列表。本仓已将 Cursor 全过程原始日志按手册 schema **手工归档**，便于评委追溯。完成 `repo sync` 后请安装 `contest-log-collector`，后续优先在官方支持工具内开发，使有效工时自动入仓。

## 七、官方必读（组委会）

| 文档 | 用途 |
|------|------|
| [大赛总览](https://github.com/open-vela/docs/blob/dev-ai-contest-2026/zh-cn/contest_2026/contest_overview.md) | 赛道、流程、评分 |
| [参赛代码提交指南](https://github.com/open-vela/docs/blob/dev-ai-contest-2026/zh-cn/contest_2026/code_submission_guide.md) | 仓库与 PR |
| [AI Coding 日志手册](https://github.com/open-vela/docs/blob/dev-ai-contest-2026/zh-cn/contest_2026/ai_coding_log_guide.md) | `logs/` 格式 |
| [AI 硬件赛道教程](https://github.com/open-vela/docs/blob/dev-ai-contest-2026/zh-cn/contest_2026/ai_hardware/ai_hardware_guide_index.md) | 编译烧录 / Agent / Skill |

提交方式：fork → PR 回专属仓 → 自行合入；首次贡献需签署 [CLA](https://openvela.com/#/community/cla)。

**开源协议：** 本作品遵循 [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0)（与 openvela 生态一致）。
