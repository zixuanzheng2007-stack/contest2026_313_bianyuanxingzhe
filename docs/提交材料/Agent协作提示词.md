# Agent 协作提示词（复制给队友 Cursor）

> 用法：把对应整段粘贴给 **Ubuntu 虚拟机 Cursor**（Guest），或队友本机 Agent。  
> 仓库路径：`~/openvela/contest2026_313_bianyuanxingzhe`  
> 编译：`tr -d '\r' < VMware_share/mailbox/host_to_guest/sync_and_build.sh | bash`  
> 产物拷到：`VMware_share/artifacts/nuttx.bin`，由 **郑子轩 Windows COM7** 烧录。

---

## 一、韦政宇 · P0：ai_agent Skill「接近提醒」（赛题硬性）

```
你是 openvela AI 硬件赛道助手。仓库 contest2026_313_bianyuanxingzhe，应用 app/edge_walker/。

## 目标
在 SF32LB52-DevKit-LCD 上满足赛题：**ai_agent 上板 + ≥1 Skill + 阈值/事件主动 + Tool 执行**。
Skill 名建议：`approach-warn`（接近提醒）。

## 现状（不要破坏）
- 雷达：UART2 `/dev/ttyS1`，`ew_ld2451.c` 解析，门限在 `ew_decide()`。
- 提醒出口：`alert_output(level, reason)`（alert_output.c），会驱动蜂鸣+LCD。
- 已有对话：`ew_chat.c` + `ew_llm.c`（MiMo HTTPS via ESP AT），**不是**官方 ai_agent 框架。
- 预警页：`alert_lcd.c` 每帧读雷达并调用 alert_output，已能主动橙/红+蜂鸣。
- WiFi/触摸/雷达脚：PA20/PA27 雷达，PA24/PA25 ESP AT，PA28 蜂鸣，I2C 触摸 PA30/PA37。

## 你要做的
1. 查阅 openvela 官方教程：ai_hardware 下 ai_agent / Skill / Tool 示例。
2. 在 vendor 或 apps 中启用 `CONFIG_EXAMPLES_AI_AGENT_VELA`（或赛方当前推荐配置），
   与现有 edge_walker 共存；参考 mailbox/guest_to_host/FLASH_AI_AGENT_STATUS.md。
3. 新增 Skill 描述（YAML/JSON 按官方格式）：说明「后方目标靠近时主动提醒用户」。
4. 新增 Tool：例如 `haptic_alert(level, reason)`，内部**只调用**已有 `alert_output()`，
   不要重写蜂鸣/GPIO。
5. 主动触发路径（二选一或组合）：
   - A) ai_agent 订阅/轮询 `ew_ld2451` 判断结果（读共享状态或 NSH 接口）；
   - B) 在 `alert_lcd.c` 等级变化时向 ai_agent 发事件，由 Skill 决定是否调用 Tool（需轻量胶水层）。
6. 保留 `ew chat` / `ew ask` 可用；Skill 与 chat 可并存。
7. 在 app/edge_walker/README.md 增加一节「ai_agent Skill 演示步骤」。

## 验收
- NSH 或串口日志可见：接近时 ai_agent **主动**调 Tool → `[alert_output] level=SOFT|STRONG|EMERGENCY`。
- `ew alert none` 后 Skill 仍能再次触发（或文档说明互斥策略）。
- Ubuntu 编过：`ninja -C ~/openvela/cmake_out/sf32lb52_devkit_lcd`（或 ai_agent 专用 out 目录）。
- 写回执：`VMware_share/mailbox/guest_to_host/REPLY_AI_AGENT_SKILL.md`（改了哪些文件、怎么演示）。

## 禁止
- 不要用 LLM 输出决定是否告警（测距必须本地）。
- 不要 erase_flash；不要改 ESP 到 GPIO19；不要阻塞 lv_timer_handler。
- 不要把 WiFi 密码写进 git。
```

---

## 二、韦政宇 · P1：Agent 体验补洞（字体 + 输入）

```
仓库 app/edge_walker/，任务：修复 Agent 页中文方框与边缘按键失灵。

## 问题
- CJK 字体从 /data/font/MiSans-Regular.ttf 加载，板上常缺失 → 候选字显示 □。
- g_list 绑定了 PRESSED→hide_kb，键盘边缘键（退格、1）易失焦。

## 要做
1. 在 board_overlay 或启动脚本中部署 MiSans（或 Noto Sans SC 子集）到 /data/font/，
   或在固件分区只读挂载字体；ew_chat.c 的 g_font_paths 对齐。
2. ew_chat.c：键盘可见时去掉 g_list 的 PRESSED hide_kb；键盘加 12px 安全边距；
   lv_obj_remove_flag(kb, LV_OBJ_FLAG_SCROLLABLE)。
3. 编译 sync_and_build.sh，产物 nuttx.bin，写 REPLY_AGENT_UI.md。

## 不要改
雷达 UART2、ESP UART3、alert_buzzer  worker 逻辑。
```

---

## 三、王筠昊 · P0：数据管线文档 + 回归

```
你是 edge_walker 数据负责人。仓库 app/edge_walker/ew_ld2451.c、host_smoke.c。

## 目标
提交材料需要「别人能照做」的 3～8 步复现 + 主机回归全绿。

## 要做
1. 在 docs/提交材料/ 新建 `LD2451数据与策略复现.md`，包含：
   - 协议帧格式、body[1] 报警位含义、ew_decide 门限（距离/TTC/SNR）。
   - host_smoke 编译与运行命令，预期输出 ALL PASS。
   - 真机 NSH：`ew` 读 ttyS1 时控制台应看到 distance/speed 类日志（有雷达时）。
2. 确认 host_smoke 覆盖：有效靠近帧 + 后续空帧仍保留目标（TASK_016 回归）。
3. 若改 ew_ld2451.c：Guest 跑 sync_and_build.sh，写 mailbox/guest_to_host/REPLY_DATA.md。
4. 不要改 alert_buzzer.c、ew_wifi_at.c、GPIO 脚位。

## 验收
gcc host_smoke → ALL PASS；文档可被评委独立复现主机侧测试。
```

---

## 四、郑子轩 · 本机（可选，自己执行）

```
整理 contest2026_313_bianyuanxingzhe 提交：
1. git add app/edge_walker 未提交改动；commit；push feature/host-edge-walker；PR → dev-ai-contest-2026。
2. 更新 docs/00_提交材料索引.md 勾选状态。
3. 按 docs/提交材料/Demo脚本与验收步骤.md 录 ≤5 分钟视频。
4. 冒烟表单 docs/开发板冒烟测试表单.md 填 A1/A2/A5 + 预警录像链接。
5. 9 月 Cursor 日志补进 logs/zixuanzheng2007-stack/（若官网要求）。
```

---

## 五、合流顺序（避免互相踩脚）

1. **王筠昊**：冻结 `ew_ld2451` 接口文档（可先不改码）  
2. **韦政宇 P0**：ai_agent Skill + Tool 胶水（最大风险，优先）  
3. **郑子轩**：合 PR + 烧录 + 录像  
4. **韦政宇 P1**：字体/键盘（不挡提交时可后做）
