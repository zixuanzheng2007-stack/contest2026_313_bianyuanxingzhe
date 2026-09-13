# Ubuntu Cursor 交接包（主机 → 虚拟机）

> 生成时间：2026-08-12 · 主机 Windows Cursor 无法直接操控虚拟机内 Cursor，需 SSH 或粘贴本提示词。

## SSH 状态（主机已测）

| 项 | 结果 |
|----|------|
| VM | `D:\VMware\Ubuntu\Ubuntu 64 位.vmx` 运行中 |
| IP | `192.168.126.128`（vmrun / ping 一致） |
| 端口 22 | **已开放**（之前 Connection refused 已解决） |
| 登录 | **未打通**：主机无免密密钥入库；需你在 Ubuntu 写入下方公钥或提供用户名+密码 |

### 在 Ubuntu 里一键写入主机公钥（复制整段执行）

```bash
mkdir -p ~/.ssh && chmod 700 ~/.ssh
echo 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAILlbjzmMNnuQbfeOcCsyhps5xR/p933SNKyitv+hd+Vc windows-host-to-ubuntu-vm' >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
whoami
hostname -I
```

然后告诉主机侧你的 **用户名**（`whoami` 输出）。主机测试：

```powershell
ssh -i $env:USERPROFILE\.ssh\id_ed25519_openvela_vm 你的用户名@192.168.126.128
```

公钥文件也在：`E:\openvela\vm-handoff\windows_host.pub`

---

## 工作进度摘要（给 Ubuntu Cursor）

### 已完成（Windows / 真机侧）

- 专属仓：`contest2026_313_bianyuanxingzhe`，分支工作在 `feature/host-edge-walker`
- 主硬件：**SF32LB52-DevKit-LCD** + **HLK-LD2451**
- CH343 USB-UART：**COM7** 在线；`sftool -c SF32LB52` 可读 Flash（`FCES` 头）
- 雷达：手机 HLKRadarTool 已验正常；PC 用 sscom/COM；**雷达不用烧录**
- 文档/分工 v2.2：初赛 MVP = 感知闭环 + **ai_agent（Skill + 主动执行）**
- AI 日志已归档到 `logs/zixuanzheng2007-stack/`（含 openvela 母目录会话）
- Windows 上 `repo sync` **失败**（无符号链接权限）→ **必须在 Ubuntu 拉全量工程**

### 未完成 / 下一步（开发板相关，请 Ubuntu 开展）

1. `repo init/sync` 竞赛 manifest（`dev-ai-contest-2026`）
2. 编译 `sf32lb52_devkit_lcd`，产出 `nuttx.bin`
3. （可选）先编通 ai_agent 示例
4. 把 bin 拷回 Windows 或 USB 直通后烧录 COM7：`nuttx.bin@0x12010000`
5. 板端预留 UART 解析 LD2451 + `decision` + `alert_output` 骨架
6. Agent 最小集并行：Skill `approach-warn`、主动触发 Tool

### 建议工作区路径

```bash
mkdir -p ~/openvela && cd ~/openvela
repo init -u https://github.com/open-vela/contest2026_313_bianyuanxingzhe \
  -b dev-ai-contest-2026 -m contest2026_313_bianyuanxingzhe.xml \
  --repo-url=https://github.com/GerritCodeReview/git-repo --repo-rev=v2.66
repo sync -c -j$(nproc)
```

若 GitHub 慢，可用镜像；编译参考赛方 AI 硬件教程。

---

## 粘贴给 Ubuntu Cursor 的提示词（整段复制）

```text
你是边缘行者竞赛在 Ubuntu VM 上的开发助手。主机 Windows 已完成硬件冒烟与文档；请在本机开展 openvela/开发板工作。

背景：
- 仓 contest2026_313_bianyuanxingzhe，板 SF32LB52-DevKit-LCD，雷达 LD2451
- 初赛 MVP：① LD2451→门限 decision→alert_output ② ai_agent 上板+≥1 Skill+接近主动告警
- Windows 无法 repo sync（符号链接）；必须在本 Ubuntu 拉代码并编译
- 烧录在 Windows：COM7 CH343，sftool write_flash nuttx.bin@0x12010000

请立即执行：
1. 检查 git/repo/python3；没有则 sudo apt 安装
2. 在 ~/openvela 执行竞赛 repo init + repo sync（branch dev-ai-contest-2026）
3. 定位 sf32lb52_devkit_lcd 的 board config，按赛方教程 cmake/build 出 nuttx.bin
4. 汇报：同步是否成功、编译命令、nuttx.bin 路径与大小
5. 不要改主机 COM 口；编译产物路径列清楚以便 scp 回 Windows

约束：测距门限不靠 LLM；Agent 后置但环境可先编 ai_agent 示例。
```
