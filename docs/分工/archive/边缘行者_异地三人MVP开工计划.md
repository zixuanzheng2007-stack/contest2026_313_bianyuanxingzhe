# 边缘行者 · 异地三人 MVP 开工计划

> v2.2 · 2026-08-12 · 板/雷达在**郑同学**处 · 仓 `contest2026_313_bianyuanxingzhe` · 截止 9/20  
> 对齐 AI 硬件赛道：**openvela + ai_agent**，可交初赛

## 目标（初赛可提交 MVP）

两条线必须同时闭环（缺 Agent 不能按该赛道交）：

```text
感知执行链：
  LD2451 ──UART──► 板端解析+门限决策 ──► alert_output（蜂鸣/LCD/LED…）

Agent 合规链（赛方硬性）：
  openvela + ai_agent 上板运行
  ├── ≥1 自定义 Skill（如 approach-warn）
  ├── ≥1「主动+执行」：雷达接近/门限触发 → Tool 调 alert_output
  └── ≥1 交互渠道（CLI / 串口对话即可）
```

- 主雷达：**LD2451**（LD2417 仅郑侧备份）  
- **硬门限决策仍在板端**（不靠 LLM 判距）；Agent 负责主动编排与执行告警 Tool，可附简短提示  
- 响应：蜂鸣 / LCD / LED / 串口提示均可；抽象 `alert_output`  
- LLM：可用赛方/MiMo 云端后端，保证基础对话能通即可  

本期可不做：IMU、导航、骨传导、双雷达主路径、端云复杂协作（作加分缓冲）。

## 环境

| 定案 | 内容 |
|------|------|
| 编译 | **Ubuntu 22.04 VM**（勿用 WSL/Docker） |
| 真机 | **仅郑处**烧录/接线/台架；他人约联调窗 |
| Win 可做 | 文档、PuTTY、烧录协助、Remote-SSH |

三人：VM → `repo sync` → `sf32lb52_devkit_lcd` + **ai_agent 示例**各编通一次。

## 分工

| 角色 | 谁 | 主责 | 初赛验收点 |
|------|----|------|------------|
| H 真机 | **郑同学** | 接线表、烧录、台架录像、回传日志 | 镜像可烧；接近告警可复现短视频 |
| F 感知 | ____ | UART 解析、门限 `decision`、`alert_output` 驱动 | 板上有距离/决策；告警可触发 |
| A Agent | ____ | ai_agent 上板、LLM 配置、**1 Skill**、主动任务接 F 的决策/事件 | CLI 能对话；接近时 Agent **主动**调 Tool 告警 |

接口先冻（改名三人同意）：

- F→全队：`decision` / `range_m` / `speed` / `approaching`  
- 输出统一：`alert_output(level, reason)`  
- A 侧 Tool 只调 `alert_output`，不重复写硬件细节  
- Skill 建议名：`approach-warn`（存放按赛方：`/data/agent/skills/`）  

门限初值：靠近且 ≤15 m → 告警（可调）。

## 阶段（对准 9/20）

| 阶段 | ~时长 | 验收 |
|------|-------|------|
| 0 环境 | 3 天 | VM+`repo sync`；示例板 + ai_agent 能编 |
| 1 感知 | 4～5 天 | 板上有距离与 `decision` |
| 2 告警 | 3～4 天 | 接近→`alert_output` 可感知 |
| 3 Agent 最小集 | 5～7 天 | Agent 上板；1 Skill；主动+执行演示通 |
| 4 提交缓冲 | 截止前 | README/场景说明、`logs/`、Demo≤5min、PR 合入 |

阶段 1～2 与 3 **可部分并行**：A 先用模拟事件/`decision` 桩调通 Agent，再换真雷达。

## 「主动+执行」最小定义（评委可看懂）

| 项 | 本队落地 |
|----|----------|
| 主动类型 | **阈值/事件主动**：`approaching && range_m≤门限` |
| 执行 | Agent 调 Tool → `alert_output`（非纯文本回复） |
| Skill | `approach-warn`：说明何时告警、如何调 Tool、用户可问状态 |
| 渠道 | 串口/CLI 可问「当前有无来车」；告警不依赖用户先开口 |

不做纯聊天机器人；LLM 不替代测距。

## 协作

1. 板不邮寄分散；联调每周 ≥2 次  
2. 只改专属仓；功能分支 + PR  
3. 每日简报：完成 / 阻塞 / 要郑测的分支与预期  
4. 关串口后再拔线；烧录中禁止拔线  
5. AI 日志：`repo sync` 后装官方 collector；提交前 `logs/` 入库  

```text
【日期】角色：H/F/A
今日完成：
阻塞：
需要郑测：分支/commit/预期：
明日：
```

## 勾选（初赛）

**郑：** 接线表+照片 · LD2451 冒烟 · 烧录回传 · 台架短视频（含接近告警）  
**F：** 解析+决策 · `alert_output` · 复现步骤  
**A：** ai_agent 上板 · LLM 通 · Skill×1 · 主动告警演示 · 场景说明段落（供 README）  
**共同：** README 作品说明 · `logs/` · 截止前 PR 合入  

## 资料

`群内分工一页纸.md` · 赛方 [AI 硬件赛道指引](https://github.com/open-vela/docs/blob/dev-ai-contest-2026/zh-cn/contest_2026/ai_hardware/ai_hardware_track_guide.md) · [ai_agent 上手](https://github.com/open-vela/docs/blob/dev-ai-contest-2026/zh-cn/contest_2026/ai_hardware/ai_agent_quickstart.md)
