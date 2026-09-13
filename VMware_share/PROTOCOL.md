# 主机 ↔ Ubuntu Cursor 协作协议（经 VMware_share）

三端（虚拟机 / 宿主机 / 组员远端）高效方案见 **`AGENT_BUS.md`**。下文为兼容旧双端流程。

## 路径
- 主机: E:\openvela\contest2026_313_bianyuanxingzhe\VMware_share
- 客人: /mnt/hgfs/VMware_share

## 目录
- mailbox/CURRENT.json    唯一真状态（动手前先读）
- mailbox/host_to_guest/  主机下发任务（TASK_NNN.md）
- mailbox/guest_to_host/  客人回传结果（REPLY_NNN.md）
- mailbox/peer_to_all/    组员远端需求/评审
- mailbox/status/         当前状态 / 请读纸条
- artifacts/              编译产物（nuttx.bin 等）

## 规则
1. 先读 CURRENT.json；`owner` 不是自己就不要开新 P0。
2. Ubuntu Cursor 读取 host_to_guest 最新 TASK 并执行。
3. 完成后写 REPLY_NNN.md，并更新 CURRENT。
4. 需要 sudo 时在虚拟机本机输入密码（主机 SSH 无 sudo）。
5. SSH: a1@192.168.126.128（密钥已配）。
6. 烧录只允许宿主机 COM7；客人不要抢 CH343。
