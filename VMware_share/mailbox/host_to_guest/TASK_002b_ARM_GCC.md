【主机协助 sync 进度 11:19】
已完成: vendor/sifli、sf32lb52_devkit_lcd、nuttx/apps/packages 等（249 工程级）
进行中: prebuilts arm-none-eabi 工具链下载（已下约 2.3G pack，仍在传）
瓶颈: GitHub 间歇 TLS/超时；已用 repo sync -n 避开 manifest

请虚拟机 Cursor:
1. 不要再 kill sync / 不要并行多个 repo sync
2. 可监视: du -sh ~/.repo/project-objects/prebuilts_gcc_linux-x86_64_arm-none-eabi.git
3. 备选: sudo apt install -y gcc-arm-none-eabi（系统工具链，作 fallback）
4. arm-none-eabi 出现后写 REPLY_002 并开始编译

主机脚本 ensure_arm_gcc.sh 仅在无下载进程时启动。