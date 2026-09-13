# TASK_001 · 环境 + openvela 拉取 + 开发板编译

签发: Windows Cursor · 2026-08-12
优先级: P0
执行方: Ubuntu Cursor（用户 a1）

## 背景
- SSH 已通: a1@192.168.126.128
- 主机无 sudo 密码，apt 请在本机完成
- 共享: /mnt/hgfs/VMware_share
- 板: SF32LB52-DevKit-LCD；烧录在 Windows COM7
- 初赛 MVP: LD2451 感知闭环 + ai_agent（Skill + 主动告警）

## A. 装依赖（sudo）
```bash
sudo apt-get update
sudo apt-get install -y git curl ca-certificates python3 python-is-python3 build-essential
mkdir -p ~/bin
curl -fsSL https://raw.githubusercontent.com/GerritCodeReview/git-repo/v2.66/repo -o ~/bin/repo
chmod +x ~/bin/repo
echo 'export PATH="$HOME/bin:$PATH"' >> ~/.bashrc
export PATH="$HOME/bin:$PATH"
git --version && python3 ~/bin/repo --version
```

## B. 拉取竞赛工程
```bash
mkdir -p ~/openvela && cd ~/openvela
repo init -u https://github.com/open-vela/contest2026_313_bianyuanxingzhe \
  -b dev-ai-contest-2026 \
  -m contest2026_313_bianyuanxingzhe.xml \
  --repo-url=https://github.com/GerritCodeReview/git-repo \
  --repo-rev=v2.66 \
  --depth=1
repo sync -c -j$(nproc)
```

## C. 编译开发板
- 定位 sf32lb52_devkit_lcd
- 按赛方教程编出 nuttx.bin
- 复制到 /mnt/hgfs/VMware_share/artifacts/nuttx.bin
- 记录完整命令与文件大小

## D. 回传
写: /mnt/hgfs/VMware_share/mailbox/guest_to_host/REPLY_001.md
（完成项、sync/编译结果、阻塞）

## 约束
测距不靠 LLM；先出固件；客人不烧录板子。