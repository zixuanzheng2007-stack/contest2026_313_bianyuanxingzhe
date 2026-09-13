# TASK_002 · 补全 repo sync + 编译 sf32lb52_devkit_lcd

签发: Windows Host Cursor · 2026-08-12 10:52
优先级: P0
前置: 磁盘已扩到 ~126G；git/repo 已装；~/openvela 有骨架但 **sync 不完整**（缺 vendor/sifli、大量 prebuilts）

## A. 补同步（必须）
```bash
export PATH="$HOME/bin:$PATH"
cd ~/openvela
repo sync -c -j$(nproc) 2>&1 | tee /mnt/hgfs/VMware_share/artifacts/repo_sync.log
```
验收:
```bash
test -d vendor/sifli && echo HAS_SIFLI
find vendor/sifli -iname '*devkit_lcd*' | head
ls prebuilts/gcc/linux-x86_64/arm-none-eabi/*/bin/arm-none-eabi-gcc
```

## B. 编译开发板
找到 board config 后（常见类似）:
`vendor/sifli/boards/sf32lb52/sf32lb52_devkit_lcd/...`
按赛方教程执行，例如:
```bash
cd ~/openvela
./build.sh <board-config-path> -j$(nproc)
# 或 cmake 流程，以目录内 README / 赛方 AI 硬件教程为准
```
把 `nuttx.bin` 复制到:
`/mnt/hgfs/VMware_share/artifacts/nuttx.bin`

## C. 回传
写 `/mnt/hgfs/VMware_share/mailbox/guest_to_host/REPLY_002.md`：
- sync 是否出现 HAS_SIFLI
- 使用的完整编译命令
- nuttx.bin 路径与 size
- 失败则贴日志尾部 50 行

## 说明
主机已尝试 nohup 后台 sync；你可 `tail -f /mnt/hgfs/VMware_share/artifacts/repo_sync.log` 或自己重跑。
烧录仍在 Windows COM7，客人只负责出 bin。