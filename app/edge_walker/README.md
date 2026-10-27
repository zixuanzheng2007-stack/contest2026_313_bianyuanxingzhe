# 边缘行者板上应用

映射到 openvela 后作为 NSH 命令 `ew`。板子上由 `rcS` 启动 `ew boot`，其余子命令只用于台架调试。

## 模块划分

| 文件 | 职责 | 负责人 |
|------|------|--------|
| `ew_main.c` | 命令行入口，只做参数分派 | 郑子轩 |
| `alert_output.*` | 提醒出口：日志 + 蜂鸣 + 屏色，一处调用三处生效 | 郑子轩 |
| `alert_buzzer.*` | PA28 无源蜂鸣，后台 worker 持续发波 | 郑子轩 |
| `alert_lcd.*` | 预警页与 LVGL 启动 | 郑子轩 |
| `ew_ld2451.*` | LD2451 帧解码 + `ew_decide` 门限 | 王筠昊 |
| `ew_chat.*` | UI 主循环 + 智能体对话页 | 韦政宇 |
| `ew_wifi_at.*` | ESP AT 猫：扫描 / 连接 / 凭证 / HTTPS | 郑子轩 |
| `ew_wifi_ui.*` | WiFi 配网页 | 郑子轩 |
| `ew_llm.*` | 走 AT HTTPS 问大模型 | 韦政宇 |
| `ew_net_status.*` | 联网 / LLM 稳定故障码、HTTP 与 AT 分类、日志脱敏 | 角色 B |
| `ew_agent.*` | Skill `approach-warn` + Tool `approach_alert` | 韦政宇 |
| `skills/` | Skill 文档模板 | 韦政宇 |
| `ai_agent_ext/` | ai_agent 进程侧 Tool 注入 | 韦政宇 |
| `host_smoke.c` | 主机侧解码与策略回归，不上板 | 王筠昊 |

## 三个页面

`ew_ui_loop()` 是唯一的 LVGL 主循环，页面靠 `ew_ui_goto()` 切换，各页只实现
`build / tick / teardown` 三个钩子：

| 页面 | 进入方式 | 钩子 |
|------|----------|------|
| 预警 `EW_PAGE_WARN` | 开机默认；其他页点「预警」；Esc 键 | `alert_lcd_attach_warn_ui` / `alert_lcd_warn_tick` / `alert_lcd_detach_warn_ui` |
| 对话 `EW_PAGE_CHAT` | 预警页点屏幕或「Agent」；回车键 | `build_ui` / `poll_reply` / `hide_kb` |
| 配网 `EW_PAGE_WIFI` | 预警页点「WiFi」或左上角网络状态；W 键 | `ew_wifi_ui_*` |

每帧最长睡 `EW_UI_FRAME_MS`（8 ms），保证雷达变色跟得上。新建页面后
`EW_UI_GATE_MS`（400 ms）内忽略切页请求，避开上一页松手时的触摸抖动。

## 联网

外挂 ESP AT 猫走 `/dev/ttyS2` @115200。凭证保存在板上 `/data/ew_wifi.conf`，
**不做编译期硬编码**，换网络不用重新编译。

屏上操作：预警页点「WiFi」→ 自动扫描 → 点一行 → 输密码 → connect。
开放网络直接连；连上后状态栏显示 `ONLINE <ip>`（公网可达）或 `LAN ONLY <ip>`
（连上了路由器但出不了公网）。已保存的那个网络在列表里带 `*`。

开机时 `ew_wifi_bringup()` 先问模组自己是不是已经连着（ESP 会记住上次的 AP），
没连再用 `/data/ew_wifi.conf` 里的凭证连一次；都没有就显示 `NO WIFI`，等人去配网页。

命令行等价操作：

```text
ew wifi                     链路状态 + 已保存的 SSID
ew wifi scan                列出周边网络（含定向补扫 hint）
ew wifi probe <ssid>        只扫一个 SSID（华为热点漏扫时用）
ew wifi join <ssid> [pass]  连接并记住（SSID 含空格用引号）
ew wifi forget              断开并清除凭证
ew wifi fault               显示最近一次联网故障码
ew wifi ping                AT 握手
ew at AT+CIFSR              原始 AT
```

## 阶段二：联网故障与对话隔离

Wi-Fi、TLS、HTTP、配置和模型回复错误会归一到稳定短码，例如
`no_modem`、`bad_password`、`lan_only`、`http_auth`、`http_rate_limit`。
配网页和对话页显示可执行提示，串口可用 `ew wifi fault` 查询最近故障。

网络问答在后台线程执行。每次提问带页面代数；离开或重进对话页后，旧请求
即使晚到也不会写入新页面。网络失败只影响问答，本地雷达测距、判决、蜂鸣和
屏色告警保持原路径。

本阶段不修改 A 侧距离、TTC、门限和告警等级，也不覆盖已有的
`ew_safety`、`ew_snapshot`、`ew_esp_stream` 和单槽告警 ACK 架构。

详细交付说明和实板验收表见
[`docs/复赛/阶段二_联网故障与对话隔离.md`](../../docs/复赛/阶段二_联网故障与对话隔离.md)。

## 阶段三：封版交付

封版脚本把主固件、可选独立 Agent 固件、回退镜像、源码输入和工具打成
带 SHA256 的版本包。主机生成与校验命令：

```bash
ROLLBACK_BIN=/path/to/known_good/nuttx.bin \
VERSION=ew-final-20261027 \
bash scripts/guest/build_stage3_release.sh
```

烧录后连续三次演示可用
`python scripts/host/stage3_demo_acceptance.py --port COM7 --runs 3`。
脚本只判定软件事件链；屏幕、蜂鸣、真实雷达和长稳仍需人工验收。详细说明见
[`docs/复赛/阶段三_封版交付.md`](../../docs/复赛/阶段三_封版交付.md)。

## 其他命令

```text
ew                          读 /dev/ttyS1 雷达并走判断→提醒
ew boot                     LVGL UI 主循环（rcS 用）
ew chat                     直接进对话页
ew alert none|soft|strong|crit [reason]
ew fake [range_m] [speed]   假目标走完整条链
ew buzz [freq_hz] [ms]      PA28 蜂鸣点测
ew screen [info]            屏色自检 / 分辨率
ew ask <text>               不开 UI 问一次大模型
```

`ew alert` 在没有常驻 UI 的进程里跑时，会把请求写到 `/data/ew_alert.req`，
由 `ew boot` 那边的预警页下一拍取走。

## ai_agent Skill 演示

```text
ew boot                  # 安装 /data/ai_agent/skills/approach-warn.md
ew fake 10 20            # 应见 [ew_agent] proactive … [alert_output] …
ew alert strong test     # 直接测试告警出口（不经过 Agent/Tool）
```

`ew fake`、PC 遥控 `@fake` 与真实雷达共用本地 `ew_agent_proactive_alert` → Tool →
`alert_output` 路径，每次调用打印同一 `event_id` 的 decision、agent、tool、
alert_output、complete 五段日志。编号在当前 ew 运行实例内递增，重启后重置；
`complete result=0` 表示调用返回成功，仍需真机确认声音、屏幕和 IPC 消费。
fake 只模拟目标判决，不覆盖 UART 解码和连续帧保持。

这条本地调用链不代表独立 `ai_agent` 注册表已经执行 Tool。
独立固件用 `sync_and_build.sh` 构建，输出为
`cmake_out/sf32lb52_devkit_lcd_ai_agent/nuttx.bin`；脚本会校验 Tool 注入并保存
`.ew_agent_patch_stamp` 文件哈希。设置 `EW_PATCH_ONLY=1` 可仅校验注入。

独立 Agent 的 `approach_alert` 必须提供合法 `level`，可选 `reason` 和
`event_id`。Tool 返回 `status=queued` 只表示请求完整发布；预警页消费请求、
调用蜂鸣和 UI 后，才记录 `[ew_ipc] stage=applied` 和 `stage=ack`，并写入
`/data/ew_alert.req.ack`。这些记录证明软件调用完成，持续画面与声音仍需真机验证；
雷达刷新会继续更新预警页。单槽忙时明确返回 `busy`，不会覆盖前一请求；
必须等待相同 `event_id` 的 ACK 后再发送下一条。

跨进程请求使用 `/data/ew_alert.req.lock/` 临时目录和原子重命名，拒绝非法
等级、坏 JSON、过长原因及写入错误。预警页未运行时，请求保持排队。
进程异常退出或 ACK 写入失败可能保留占槽文件；恢复时先停止相关进程，
再移除 `/data/ew_alert.req`、`.mutex`，以及 `.lock` 目录中的
staging/processing/consumer/ack.tmp 和空的 `.lock` 后重启，勿在活跃事务中清锁。
NuttX flat 构建中，本地 JSON 入口为
`ew_agent_tool_execute`，独立 IPC 注册入口为 `tool_approach_alert_execute`。

`scripts/guest/build_ew_main.sh` 支持 `OPENVELA`、`CONTEST`、`BUILD_DIR`、
`ARTIFACT_DIR` 路径覆盖，保留现有增量构建和配置。只有编译成功且镜像非空时
才导出 `nuttx.bin`、`nuttx.bin.sha256` 与 `nuttx.build.txt`；构建失败保留原交付物。
烧录前确认 SHA256 与元数据一致，未提交源码的来源另记为 source_sha256。

MiMo Token Plan 使用中国集群端点
`token-plan-cn.xiaomimimo.com:443/v1/chat/completions` 和模型 `mimo-v2.5`。
密钥格式为 `tp-...`；不要把 API key 写入仓库或固件。Windows Host
设置临时环境变量后执行（脚本会先验证 Windows 直连，再写入开发板）：

```powershell
$env:MIMO_API_KEY = "<本机密钥>"
python scripts/host/mimo_configure.py --port COM7
Remove-Item Env:MIMO_API_KEY
```

也可用 `[Environment]::SetEnvironmentVariable('MIMO_API_KEY','<本机密钥>','User')`
供调试助手在后续进程读取，验收后从用户环境删除。脚本通过 `@mimo-set` 写入板端
`/data/ai_agent/config/config.json`，只保存脱敏日志。
`@mimo-rollback` 可恢复首次更新前的 `config.json.bak`。

## 开发辅助（非赛题必测）

| 模块 | 说明 |
|------|------|
| `ew_serial_ctl.c` | 串口 `@goto` / `@fake` / `@join` 等遥控（PC 调试） |
| `ew_mirror.c` | LVGL 快照经串口输出 RGB565 帧（PC `ew_panel.py` 可选） |

## 改完代码怎么验

仓库根目录执行 `python -m pip install -r requirements-test.txt`，再执行
`python scripts/host/run_tests.py`，统一运行 host_smoke 和全部无硬件 Python 回归。
需要 GCC、Bash、Python Tk 支持；Windows 可使用 MSYS2 UCRT64 GCC 并将其 bin 加入 PATH，
Bash 使用 MSYS2 或 Git for Windows。
环境依赖缺失返回 2，测试失败返回 1，全通过返回 0。

```bash
# 主机侧回归，不需要板子
gcc -O2 -Wall -Wextra -o /tmp/host_smoke host_smoke.c ew_ld2451.c && /tmp/host_smoke

# 增量编译
ninja -C ~/openvela/cmake_out/sf32lb52_devkit_lcd
```

产物 `cmake_out/sf32lb52_devkit_lcd/nuttx.bin`，烧录地址 `0x12010000`。

屏接线说明见 [`docs/硬件/DevKit-LCD.md`](../../docs/硬件/DevKit-LCD.md)。

## 只读手机状态接口（2026-10-24 新增）

含本次实现的固件在 UI 运行时支持 `@snapshot <request_id>`。ID 为 1—48 个 ASCII 字母、数字、下划线或连字符，不接受截断、额外参数或控制字符。回复为 `[ew-snapshot] ` 前缀后的单行 JSON。

接口复制独立安全线程的状态后再序列化，不调用网络 AT、不修改门限/告警，也不让安全线程写控制台。缺少、无效或过期测量为 null；告警保持等级单独保留。`event_id` 是原告警事件，`snapshot_seq` 是快照序号；`updated_ms` 是设备单调时钟，不能作为日期。

PC 入口为 `scripts/host/mobile_serial_gateway.py`，仅回环网络监听和只读 `hello/get_state/subscribe_state`。它使用每会话随机请求前缀匹配新响应，设备重启时关闭旧会话；不会自动扫描/复位/烧录或执行模型、配置和告警命令。

本次完成主机回归和真实 ARM 对象编译，尚无新完整固件的链接、烧录及真机验收。软件证据见 `docs/协作/手机只读网关验收_2026-10-24.md`。

