【紧急协调 11:32】请 Ubuntu Cursor 立刻停止一切并行 repo sync！

主机正在单独完成关键工具链克隆:
  git clone --depth 1 .../prebuilts_gcc_linux-x86_64_arm-none-eabi
  日志: /mnt/hgfs/VMware_share/artifacts/arm_manual_clone.log

当前进度约数百 MB，多个 repo sync 会抢带宽导致失败。

请只做:
1. 不要再启动 repo sync / finish_repo*
2. 监视: bash /mnt/hgfs/VMware_share/poll_arm_manual.sh
3. 看到 GCC_OK / arm-none-eabi-gcc 后再编译

不要 kill 名为 arm_manual_clone 的进程。