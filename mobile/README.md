# 边缘行者手机端

## 当前测试方式：0.3.2 无硬件模拟（2026-10-26）

手机和开发板暂不接入，使用已安装的 MuMu Android12。以下命令启动有限串口/模型夹具，测试当前标准/提前敏感度原型；不打开物理串口，不调用云模型。界面明确标注“协议夹具 · 模拟设备”和模拟回复。

```powershell
python scripts/host/mobile_mumu_acceptance.py --serial 127.0.0.1:16384 --apk output/mobile_android_20261026/prototype032/edge-walker-companion-debug.apk --prototype-fixture --port 18769 --output output/mobile_simulation_20261026/prototype032
```

原型界面验收7/7通过。另运行不带 `--prototype-fixture` 的默认模拟模式，覆盖排队、服务故障及恢复；结果分别保存，不能作为实板或实体手机验收。报告见 `docs/协作/手机模拟环境验收_2026-10-26.md`。

0.3.1 APK 增加临时配对连接码。局域网原型只允许显式绑定地址、指定客户端和会话码；普通只读网关仍限制回环。实体卓易通访问鸿蒙 HDC 回环端口已出现 ECONNREFUSED，因此下方0.3.0 USB步骤保留作历史记录，不能当作已可用的手机连接方案。0.3.1实体手机经配对网络连接仍待恢复联调。

## 0.3.0 电脑转发原型（2026-10-25）

用户将当前验收收敛为敏感度调整和真实模型问答，允许电脑转发。新 APK 在 `output/mobile_android_20261025/prototype030/`，手机公共“下载”目录为 `edgewalker030.apk`；卓易通覆盖安装后使用。此路径需要电脑和 USB，不表示设备独立 Wi-Fi 服务完成。

先运行支持 `@sensitivity` 的新主固件，再用既有模型配置启动：

```powershell
& 'D:\anaconda3\python.exe' scripts/host/mobile_prototype_gateway.py --port COM7 --listen-port 8767
& './output/harmony_tools_20261025/hdc.exe' -t <已确认手机USB目标> rport tcp:18767 tcp:8767
```

原型服务只绑定电脑回环地址，不开放局域网；手机到电脑走用户已授权的 HDC USB 隧道。手机应用填写 `127.0.0.1:18767`；卓易通内部是否可访问原生鸿蒙的该回环监听，需要以实体手机结果为准。配置成功后应显示“电脑转发原型”，不能显示模拟器或设备独立直连。此前只读网关不开放配置/模型控制。

- 标准档保持原有全部门限；提前档仅将距离/TTC门限提高25%，不改速度/SNR筛选、雷达配置或告警保持。更改作用于后续真实判决，内存保存，设备重启恢复标准。应用只有收到设备回执及读回一致的最终结果后才显示“已应用”。
- 真实 MiMo 由电脑使用既有 `MIMO_API_KEY` 配置访问，当前实测可用模型为 `mimo-v2.6-flash`。请求带实际设备快照，缺测为空；没有执行设备工具的模型接口。模型密钥不传手机，不写日志。
- `origin=pc_prototype`，配置能力只允许 standard/early；告警测试保持停用。模拟夹具必须声明 `fixture_state=true`，应用明确显示模拟来源。该开发通道的信任来自本机和已授权 USB 调试，不是面向局域网部署的设备认证方案。
- 真实 TCP/实板验收：状态基线中位约329ms；敏感度修改+读回5次中位约673ms、最大约680ms；真实状态问答一例约13.6秒，短回复一例约1秒。不是手机UI或独立Wi-Fi端到端时延保证。

实现入口：`scripts/host/mobile_prototype_gateway.py`、`scripts/host/test_mobile_prototype.py`、`scripts/host/test_sensitivity.py`。物理验收和剩余事项以最新协作报告为准。下文0.2.1说明保留用于原只读路径。

当前版本 0.2.1 支持本地设备模拟器和只读 PC 串口网关，已安装到 MuMu Android12，并通过 PC 网关读取真实开发板快照。模拟器提供标明来源的演示；网关只读板端快照，不开放告警、档位或问答写操作。独立 ESP32 Wi-Fi/BLE、真实模型问答和手机实机仍待验收。

最新安装包位于 `output/mobile_android_20261025/edge-walker-companion-debug.apk`，版本0.2.1/versionCode3；以同目录验收报告判断本轮通过范围。0.1.0/0.2.0 原包保留在此前目录，作为回退参考。

## 构建与运行

在仓库根目录：

```powershell
python scripts/host/build_mobile_apk.py
python scripts/host/mobile_device_simulator.py
```

构建器使用已安装的 JDK17、Android SDK35/build-tools35，无额外下载。可用 `--jdk`、`--sdk` 指定其它安装位置。输出安装包：

`output/mobile_android/edge-walker-companion-debug.apk`

同目录 `manifest.json` 包含 APK/源码校验和、构建时间、工具版本与源码基线。可用 `--output output/mobile_android_YYYYMMDD` 留存独立交付。不同输出目录共用 `output/mobile_android/debug.keystore` 的本地开发身份，支持安装更新；构建失败不会发布替换之前的 APK。签名用于本地开发，正式发布另行配置。

安装到已确认的模拟器（先检查实际序列号）：

```powershell
& 'C:\Program Files (x86)\Android\android-sdk\platform-tools\adb.exe' devices -l
& 'C:\Program Files (x86)\Android\android-sdk\platform-tools\adb.exe' -s emulator-5554 install -r output/mobile_android/edge-walker-companion-debug.apk
& 'C:\Program Files (x86)\Android\android-sdk\platform-tools\adb.exe' -s emulator-5554 shell am start -n com.edgewalker.companion/.MainActivity
```

MuMu 内选择地址 `10.0.2.2`、端口 `8765`，点击“连接模拟器”。模拟服务只监听电脑回环地址，当前不接受手机通过电脑局域网地址连接。进入后台会断开，回到应用后手动重连。

### 只读串口网关

需要开发板运行含 `@snapshot` 的固件，且串口没有被 PC 面板/其它工具占用。显式指定串口后，网关才会打开它；不会扫描、复位、烧录、切页或执行模型/告警命令：

```powershell
python scripts/host/mobile_serial_gateway.py --port COM7 --listen-port 8766
```

MuMu 使用 `10.0.2.2:8766`。网关必须得到匹配本次请求的新快照，才允许握手/状态成功；旧固件或串口不可用会明确返回错误。序号与设备单调时间保留，墙钟另以网关接收时间标注；空测量显示“—”。应用按能力禁用未提供的写操作。

2026-10-25已安装含快照接口的完整主固件，并读取真实COM7状态；当前测试链路仍依赖电脑网关。ESP32的AT或热点故障不会阻断此条USB串口快照链路。

真板 + MuMu 基础验收（先确认目标序列号、COM口空闲；只发只读快照，不复位或烧录）：

```powershell
python scripts/host/mobile_mumu_acceptance.py --serial 127.0.0.1:16384 --apk output/mobile_android_20261025/edge-walker-companion-debug.apk --board-port COM7 --port 8766 --output output/mobile_android_20261025/physical_board_acceptance
```

`--board-port` 与 `--gateway-fixture`互斥。真板模式记录实际快照、`fixture_state=false`和已验证的板测状态，检查新快照序号、来源、空测量、能力限制、刷新、后台断连/重连及服务停止提示。测试结束关闭自己的网关、释放COM口。首次运行有证据保存在对应目录；不要覆盖既有报告，可指定新的输出目录。

0.2.1对应网关补齐合法的 `no_frame` 雷达状态，避免将“有字节但无有效帧”误判为协议不兼容；这不代表雷达数据正常，也不生成距离/速度。

## 验证

协议回归仅需 Python 标准库：

```powershell
python scripts/host/test_mobile_device_simulator.py
python scripts/host/test_mobile_serial_gateway.py
python scripts/host/test_snapshot.py
```

应用界面自动验收需要已经启动并确认目标的 MuMu；运行前不要另行启动 8765 端口模拟服务，因为验收脚本会自行启动、停止和重启该服务：

```powershell
python scripts/host/mobile_mumu_acceptance.py --serial emulator-5554
```

验收只操作本应用。覆盖安装/冷启动、来源与状态、刷新、排队/执行区分、档位、模拟问答、后台断连、服务故障与重连。输出 JSON、UI 层级和截图到 `output/mobile_android/acceptance/`，可用 `--output` 指定独立证据目录。为兼容旧版 ADB UI 层级工具的空闲等待，界面验收使用 3 秒状态订阅；普通模拟服务仍是 1 秒。

只读网关跨层验收（需 GCC；真实 C 序列化器 + 管道串口夹具 + 真实 TCP，不打开物理串口）：

```powershell
python scripts/host/mobile_mumu_acceptance.py --serial <已确认的ADB序列号> --apk output/mobile_android_20261024/edge-walker-companion-debug.apk --gateway-fixture --port 8766 --output output/mobile_android_20261024/gateway_acceptance
```

报告始终标记 `fixture_state=true`、`board_tested=false`；`pc_gateway` 标签只表示数据路径，不能证明物理板身份。仅运行软件夹具不能算真机无线验收。

总体无硬件回归 `scripts/host/run_tests.py` 会自动纳入模拟服务的测试；它不会安装 APK 或调用 MuMu。GUI 验收脚本刻意不命名为 `test_*.py`，避免污染无硬件回归入口。

## 后续接入

下一步整合 Host/Guest/fork 的事件接口，构建可回退的完整固件，再做板端串口实测和 ESP32 常驻接收、无线连接共存与独立设备适配。新增真实控制能力前，要同步实现认证、受限命令与最终执行确认，不能用模拟握手绕过设备验收。

协议说明见 `docs/方案/手机控制协议_v0.1.md`；长期安排和本轮证据见 `docs/协作/每日推进计划_2026-10-23.md` 与 `docs/协作/手机首版验收_2026-10-23.md`。
