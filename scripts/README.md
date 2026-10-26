# 脚本目录

| 目录 | 运行环境 | 用途 |
|------|----------|------|
| [`guest/`](guest/) | Ubuntu 22.04 VM | 编译 openvela / edge_walker |
| [`host/`](host/) | Windows 11 | 烧录、串口冒烟、触摸探测 |
| [`patches/`](patches/) | Ubuntu | 板级补丁（触摸 I2C 等） |
| [`submission/`](submission/) | 任意 | 提交 zip 打包、日志归档 |
| [`archive/`](archive/) | — | 历史一次性脚本（勿用） |

## Git · push 前 rebase

见 [`git/README.md`](git/README.md)。`git push` 前自动 `rebase upstream/dev-ai-contest-2026`（需先 `setup_hooks`）。

## 常用命令

**无硬件统一回归（Windows / Linux）：**

先安装 GCC、Bash 和带 Tk 的 Python，再在仓库根目录运行：

```text
python -m pip install -r requirements-test.txt
python scripts/host/run_tests.py
```

覆盖雷达 host_smoke、fake 的本地 Agent/Tool 链、独立 Tool 注入幂等性，以及
镜像、输入、网络状态、扫描解析和日志脱敏。不会打开串口或调用在线模型。
另覆盖跨进程告警发布/消费、忙与写入失败，以及构建失败不替换已交付固件。
Windows 支持 MSYS2 UCRT64 GCC（bin 加入 PATH）和 MSYS2 / Git Bash。
退出码：0 全通过，1 测试失败，2 GCC 或 Python 依赖缺失。

**Ubuntu 编译主程序：**

```bash
cd ~/openvela
bash contest2026_313_bianyuanxingzhe/scripts/guest/build_ew_main.sh
```

产物拷贝到 HGFS：`/mnt/hgfs/VMware_share/artifacts/nuttx.bin`

**Windows 烧录：**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\host\flash_sf32.ps1 `
  -Port COM7 -Firmware "VMware_share\artifacts\nuttx.bin@0x12010000"
```

**Windows 串口调试（NSH / `@` 遥控）：**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\host\nsh_auto.ps1 -Port COM7 `
  -Commands "ls /dev","ew wifi ping"
python scripts/host/wifi_at_probe_once.py
```

Agent 规则：`.cursor/rules/serial-debug-devkit.mdc` · 详表：`.agents/skills/devkit-serial-debug/SKILL.md`

**提交打包：**

```bash
python scripts/submission/pack_submission.py
```

VM 交接见 [`docs/协作/UBUNTU_CURSOR_HANDOFF.md`](../docs/协作/UBUNTU_CURSOR_HANDOFF.md)。
