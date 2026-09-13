# 组员远程连接本虚拟机

## 当前环境（已自动配置）
- Ubuntu SSH: 已启用（端口 22，支持公钥）
- GNOME Remote Desktop: 3389（图形桌面）
- Tailscale: 已安装，需机主完成一次登录授权

## 推荐：Tailscale + SSH（公网最稳）

### 机主（本 VM）一次性授权
```bash
sudo tailscale up
# 浏览器打开打印的 https://login.tailscale.com/... 登录
tailscale ip -4
```

### 组员电脑
1. 安装 Tailscale 并登录**同一账号/邀请进同一 Tailnet**
2. SSH：
```bash
ssh a1@<VM的Tailscale-IP>
```
3. Cursor：安装 Remote-SSH，连 `a1@<Tailscale-IP>`
4. 图形桌面（可选）：Windows「远程桌面」连 `<Tailscale-IP>:3389`

## 备选：仅局域网（同 WiFi / 已端口转发）
```bash
ssh a1@192.168.126.128
```
（NAT 地址，公网直连无效）

## 安全建议
- 优先把组员公钥追加到 VM 的 `~/.ssh/authorized_keys`
- 公网不要裸暴露 22；走 Tailscale 或 frp
- 机主可用：`sudo tailscale status` 查看在线设备

## 公钥登记（组员发来后机主执行）
```bash
mkdir -p ~/.ssh && chmod 700 ~/.ssh
echo 'ssh-ed25519 AAAA... comment' >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

## 本机实时信息 (2026-08-12 19:31:03)
- LAN IP: 192.168.126.128
- Tailscale IP: 待授权后生成
- 授权链接: 请在VM执行 sudo tailscale up 获取
- SSH 用户: a1
- RDP 端口: 3389
