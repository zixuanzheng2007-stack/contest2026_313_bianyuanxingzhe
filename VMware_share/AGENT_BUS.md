# 三端 Cursor 智能体总线（Guest / Host / Peer）

操作手册（旧双端协议仍兼容）：`PROTOCOL.md`  
本文件是 **更高效的交流方案**：虚拟机 Cursor、宿主机 Cursor、组员远端桌面 Cursor **只读写共享盘，不互相抢对话窗口**。

## 三端角色（固定）

| 角色 ID | 谁 | 允许做 | 禁止做 |
|---------|----|--------|--------|
| **guest** | Ubuntu 虚拟机 Cursor | 改参赛仓、编译、写 artifacts、写回执 | 抢 CH343/COM 烧录 |
| **host** | Windows 宿主机 Cursor | COM7 烧录、真机目视/触控、串口验收、USB 归属 | 在客人编译未完成时乱烧旧 bin |
| **peer** | 组员远端桌面 Cursor | 审代码/文档、提需求、同步 CURRENT | 烧录、改板级 UART 脚、提交 WiFi/API 密钥 |

工作区：

- guest：`/home/a1/openvela/contest2026_313_bianyuanxingzhe`
- 共享盘客人：`/mnt/hgfs/VMware_share`
- 共享盘主机：`E:\openvela\contest2026_313_bianyuanxingzhe\VMware_share`（或 `\\vmware-host\Shared Folders\VMware_share`）
- peer：把同一共享盘映射到远端（VPN/共享文件夹/git 只作代码，**任务总线必须走共享盘**，避免三端 git 抢同一 commit）

## 目录约定

```
VMware_share/
  PROTOCOL.md              双端旧手册（仍有效）
  AGENT_BUS.md             本方案（三端）
  mailbox/
    CURRENT.json           【唯一真状态】每端动手前先读
    host_to_guest/         host → guest 任务  TASK_NNN_*.md
    guest_to_host/         guest → host 任务/回执
    peer_to_all/           peer → 全员（需求、评审）
    guest_to_peer/         guest → peer（需要远端协助时）
    status/                心跳与请读纸条（短文本）
  artifacts/               只放要烧的镜像与短日志
```

兼容旧路径：`host_to_guest` / `guest_to_host` **不要删**。新消息优先更新 `CURRENT.json`。

## CURRENT.json 字段

```json
{
  "ts": "ISO-8601+08:00",
  "active_id": "TASK_013",
  "blocker": "host_flash|guest_build|peer_review|none",
  "owner": "guest|host|peer",
  "guest": { "doing": "", "need": "" },
  "host":  { "doing": "", "need": "" },
  "peer":  { "doing": "", "need": "" },
  "flash": { "bin": "artifacts/nuttx_task013.bin", "port": "COM7", "ok": false },
  "do_not": ["guest flash CH343", "erase_flash", "ESP BOOT for SiFli"]
}
```

**blocker = 当前唯一执行人。** 另外两端只轮询 CURRENT，不发明并行 P0。

## 每端开聊时的固定动作（30 秒）

1. 读 `mailbox/CURRENT.json`（没有则读 `PROTOCOL.md` + 最新 TASK）。
2. 若 `owner` 不是自己：只写 `status/` 心跳，**不要**开新 TASK 抢工。
3. 若是自己：做完立刻写回执 + 改 CURRENT（`owner` 交给下一家，`blocker` 更新）。
4. 需要对方动手：写 **一份** `TASK_NNN_给谁.md`，并改 `FROM_HOST_Windows.txt` / `FROM_GUEST_Ubuntu.txt` / `mailbox/peer_to_all/PING.txt` 其中一行（文件管理器能看见的短纸条）。

## 比旧 mailbox 高效的点

| 旧问题 | 新约定 |
|--------|--------|
| REPLY 写在对方 inbox，找不见 | 回执文件名 `REPLY_NNN.md`，**同时**改 CURRENT |
| 双端互相下发 P0（012 烧触控 vs 013 烧雷达） | **同时只允许一个 active_id**；新镜像覆盖旧烧录请求 |
| 组员口头传话 | peer 只写 `peer_to_all/NOTE_*.md`，guest/host 下次开聊必读 |
| 长对话丢上下文 | 任务正文 ≤ 一屏铁律 + 验收表；细节链到参赛仓路径 |
| 轮询共享盘慢 | CURRENT.json 小于 2KB；纸条 txt 一行 |

## 烧录权

只有 **host** 烧 SF32LB52：`sftool -c SF32LB52 -p COM7 -b 1000000 --before default_reset --after soft_reset write_flash --verify <bin>@0x12010000`  
不要按 ESP32 BOOT。客人 USB 必须先断开。

## 动态监听 + 自动执行（推荐）

共享盘 hgfs **没有可靠 FileSystemWatcher**，用轮询指纹 + Cursor 唤醒行。

### 宿主机（Windows · 郑子轩 Cursor）

```powershell
# 后台监听（每 8s）；有 TASK/CURRENT 变化 → 自动烧录(若 pending) + 打印唤醒行
powershell -ExecutionPolicy Bypass -File VMware_share\scripts\start_host_bus_loop.ps1

# 停止
powershell -ExecutionPolicy Bypass -File VMware_share\scripts\stop_host_bus_loop.ps1
```

| 脚本 | 作用 |
|------|------|
| `scripts/mailbox_bus_loop.ps1` | 轮询指纹 → `mailbox_exec_host.ps1` → `AGENT_LOOP_WAKE_hostbus {...}` |
| `scripts/mailbox_exec_host.ps1` | `owner=host` 且 `blocker=host_flash` 时自动 sftool 烧录并写 REPLY |
| `scripts/mailbox_watch_host.ps1` | 仅唤醒、不执行（旧版） |

**Cursor Agent 本对话** 应用 `notify_on_output` 监控 stdout 行：`^AGENT_LOOP_WAKE_hostbus`，收到后读 JSON 内 `prompt` 并执行。

日志：`mailbox/status/HOST_EXEC.log`

### 虚拟机（Ubuntu · 王筠昊 / 韦政宇 Cursor）

```bash
bash /mnt/hgfs/VMware_share/scripts/mailbox_watch.sh
# 或 INTERVAL=8 bash .../mailbox_watch.sh
```

Guest 侧输出 `AGENT_LOOP_WAKE_guestbus`；`owner=guest` 时自动编译/烧录（见下表）。**CH343 在 VM 时**用 `guest_flash` + `/dev/ttyACM0`；在 Windows 时交 `host_flash` + COM7。

| blocker | 自动脚本 |
|---------|----------|
| `guest_build_wifi` | `run_ew_wifiui_build.sh` → 链式 `guest_flash` |
| `guest_build` | `run_ew_agent_build.sh` 或按 `flash.bin` 选 wifiui |
| `guest_flash` | `/home/a1/bin/sftool` @ `/dev/ttyACM0` |

### 宿主机 SSH 直发 Guest 任务（郑子轩 → 队友 VM）

VM 已通：`a1@192.168.126.128`（密钥 `~/.ssh/id_ed25519_openvela_vm`）。

```powershell
# 交互 SSH
powershell -File VMware_share\scripts\ssh_guest.ps1

# 下发 TASK + 改 CURRENT + 启动 Guest 监听
powershell -File VMware_share\scripts\dispatch_guest_task.ps1 `
  -TaskId TASK_020 -Title "ai_agent_build" -Blocker guest_build `
  -TaskBodyFile VMware_share\mailbox\host_to_guest\TASK_020_AI_AGENT_BUILD.md `
  -StartGuestLoop

# 立即触发一轮 Guest 自动编译（不等待轮询）
powershell -File VMware_share\scripts\dispatch_guest_task.ps1 ... -RunExecNow
# 或
powershell -File VMware_share\scripts\ssh_guest.ps1 `
  "bash /mnt/hgfs/VMware_share/scripts/mailbox_exec_guest.sh"
```

队友在 **同一 VM 的 Cursor** 里应开聊：**「读 CURRENT.json，owner=guest 则执行 active TASK」**（见下方 Guest 提示词）。

Guest 监听：`bash /mnt/hgfs/VMware_share/scripts/start_guest_bus_loop.sh`  
日志：`mailbox/status/GUEST_EXEC.log`、`guest_bus_loop.out`

---

## 给 Cursor 的提示词（直接粘贴）

**Guest：**「读 `/mnt/hgfs/VMware_share/mailbox/CURRENT.json` 与 `AGENT_BUS.md`。若 owner=guest 则执行 active 任务；不要抢 CH343。完成后写 REPLY 并更新 CURRENT。」

**Host：**「读 `VMware_share\mailbox\CURRENT.json`。若 owner=host 且 blocker=host_flash，按 CURRENT.flash.bin 烧 COM7，写 REPLY_*_FLASH.md，把 owner 交回 guest 或 peer。」

**Host（自动唤醒后）：**「收到 AGENT_LOOP_WAKE_hostbus。读 CURRENT + 最新 guest_to_host TASK。若 owner=host 执行 host.need；烧录可能已在 HOST_EXEC.log 完成。」

**Peer：**「读 CURRENT.json。只评代码/文档。不要烧录。意见写 `mailbox/peer_to_all/`。」
