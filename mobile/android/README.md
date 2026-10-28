# 边缘行者 Android 手机控制台

当前源码版本为0.3.2。新增 `pc_prototype` 来源，允许有限的 standard/early 敏感度及电脑转发问答；告警执行保持禁用。配置必须等回执和独立读回，模拟夹具来源及模拟问答均明确标记。非空连接码只用于本次握手，不保存；配对网络原型要求服务器确认 paired_lan。模型问答等待上限60秒。下方原有 simulator/pc_gateway 规则继续适用，但两者不代表新增原型能力。

2026-10-26用户要求先用模拟环境：`mobile_mumu_acceptance.py --prototype-fixture` 测试相同APK与原型协议，不接实体串口或模型。具体命令和证据见上级README。

本目录为 **Android 原生 Java、纯平台 API、零第三方依赖**的手机应用源码。支持本地模拟器和只读 PC 串口网关，页面按握手结果区分来源。`pc_gateway` 表示数据传输通路，不表示物理开发板身份或真机测试已经验证；使用串口夹具的验收仍须标为夹具测试。模拟回复不是真实 MiMo。

## 源码与构建接口

- 包名：`com.edgewalker.companion`，启动 Activity：`.MainActivity`。
- 编译 SDK：35；`minSdkVersion=26`、`targetSdkVersion=35`。
- Java：`-source 8 -target 8 -encoding UTF-8`。依赖仅 `android.jar`（包含 `org.json`）。
- 资源目录：`res/`；Manifest：`AndroidManifest.xml`；Java：`src/com/edgewalker/companion/*.java`。
- Manifest 已包含应用标签、图标、主题、INTERNET 权限与 exported 启动 Activity。
- 使用 Java lambda，直接构建时需由 D8 处理 Java 8 脱糖；没有 Gradle/AndroidX 依赖。构建与签名脚本由仓库主流程提供。

## 使用

1. 在电脑显式启动配套模拟服务器，或使用明确指定串口的只读串口网关；两者使用不同端口时在应用中填写相应端口。
2. 打开应用，填写主机与端口并点击“连接设备”。MuMu 默认 `10.0.2.2:8765`；普通模拟器和只读网关只监听电脑回环地址；电脑转发原型的配对网络模式另见上级README，需明确配置服务地址、允许客户端与连接码。实体手机实测按独立证据记录。
3. `hello` 接受 `origin=simulator`、`origin=pc_gateway` 或受限的 `origin=pc_prototype`，并要求声明状态查询能力。模拟器仅启用已知且声明支持的操作；只读网关无论声明什么能力，都只允许 `get_state` 和 `subscribe_state`；电脑转发原型仅允许状态、标准/提前档配置和问答，告警测试保持停用。
4. 模拟器可刷新状态、测试 soft/strong 告警、切换 walk/cycle 档位、发送文字问题、查看最近事件。告警测试持续 2 秒。只读网关只提供状态查询和订阅，问答、告警测试、档位和问题输入均禁用。
5. 应用进入后台或销毁时关闭连接；返回前台需要手动重新连接。保存的只是地址/端口，不自动连接任何目标。

本地开发协议使用未加密 TCP；电脑转发接入尚不等于独立 Wi-Fi/BLE 或实机验收。只读串口网关不开放写操作；电脑转发原型仅提供顶部说明的有限配置与问答能力，不提供公网账户服务。

## 协议与执行语义

UTF-8 JSONL，协议版本 `v=1`，每个请求带唯一 `id`、`op`、`args`。已实现 `hello`、`get_state`、`get_config`、`subscribe_state`、`test_alert`、`set_profile`、`ask`。

- `accepted / stage=queued`：显示“已接收并排队，尚未执行完成”。不视为执行成功。
- `result / ok=true / stage=applied`：显示已应用；告警以返回的 `event_id` 关联日志。
- `result / ok=false`：显示服务端 `error.code` 与 `error.message`，按执行失败处理。
- 等待超时：从请求首次发送时开始按绝对期限计时（普通请求 12 秒，问答 60 秒）；`accepted / queued` 和重复 queued 均不延长期限，重复确认也只记录首次状态转换。超时显示执行结果未知，提示刷新确认；已 queued 却无最终结果时不会宣称失败或成功，也不会自动重发请求。接收回执时会先按单调时钟清理过期请求，尚未来得及由 watchdog 清理的迟到 queued/applied 也不能确认操作。截止时刻本身仍允许回执，超过截止才过期；每秒一次的 watchdog 使无回执时的超时显示通常滞后不超过约1秒，主线程繁忙时可能更晚，截止时间不会因此延长。
- `event=state` 的 envelope source 和 data origin 必须与已协商来源相同；simulator 的 envelope event_id 必须与状态 event_id 相同，pc_gateway 则必须与状态 snapshot_seq 相同。5 秒无新状态则标注过期。
- 模拟器按 event_id 排序；只读网关按每快照递增的 snapshot_seq 排序，同时保留显示真实告警 event_id。标识必须是非负 JSON 整数，不能用时钟代替顺序；新连接重置顺序标记。
- 网关快照中的 range_m/speed_kmh 可以为 null，显示为“—”；profile 必须为 null，显示“未提供（只读）”，不填入演示值。已知雷达链路 ok/waiting/no_frame/stale/error 分别显示正常、等待数据、无有效帧（与板端 NO FRAME 一致）、数据已过期、故障；未知值作为协议错误处理。
- 网关 updated_ms 属于 device_monotonic，不能当作日期。界面使用 received_at_ms 的网关墙钟，并明确显示“网关接收”；模拟器继续使用它的 epoch updated_ms。

网络连接、读取、写入均在后台线程，UI 通过主线程 Handler 更新；单条消息上限 **8192 字节**，UTF-8 严格解码，半条消息接收限时 5 秒，TCP 连接限时 5 秒，连接/握手总等待 8 秒，普通操作请求限时 12 秒、问答请求限时 60 秒；发送队列和未完成请求有上限。连接或协议错误会显式显示并停用操作。

请求绝对等待期限与 queued 幂等状态放在无 Android 依赖的 `RequestWaitState.java`。Host 覆盖测试位于 `scripts/host/RequestWaitStateTest.java` 和 `test_mobile_request_wait_source.py`，可在仓库根目录执行：

```powershell
$classes = Join-Path $env:TEMP 'mobile-request-wait-test'
New-Item -ItemType Directory -Force $classes | Out-Null
javac -encoding UTF-8 -d $classes mobile/android/src/com/edgewalker/companion/RequestWaitState.java scripts/host/RequestWaitStateTest.java
java -cp $classes com.edgewalker.companion.RequestWaitStateTest
python scripts/host/test_mobile_request_wait_source.py
```

## 官方技术依据

- [Android Java 后台线程与主线程通信](https://developer.android.com/develop/background-work/background-tasks/asynchronous/java-threads)
- [Android 15 目标 SDK 35 的 edge-to-edge 与系统 Insets](https://developer.android.com/develop/ui/views/layout/edge-to-edge)
- [Activity 生命周期](https://developer.android.com/reference/android/app/Activity#onDestroy())
- [INTERNET 权限](https://developer.android.com/reference/android/Manifest.permission#INTERNET)

界面已处理系统栏、显示缺口与软键盘 Insets；数据区在首个有效状态前显示空值。断连后保留的数据按之前来源标注为历史；开始新连接时清空数值和来源，防止前一个端点的数据被误认为新连接返回。为自动验收保留原有 ew_* 控件描述，新增 ew_capabilities、ew_radar、ew_updated、ew_profile。
