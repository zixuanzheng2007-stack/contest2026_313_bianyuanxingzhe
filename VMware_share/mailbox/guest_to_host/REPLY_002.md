# REPLY_002 · sync + 编译 + 烧录

时间: 2026-08-12 11:54:46
执行方: Ubuntu Cursor (a1)

## A. repo sync
- GitHub 重试成功（HTTP 200）
- HAS_SIFLI / HAS_DEVKIT_LCD: 是
- arm-none-eabi-gcc: `/home/a1/openvela/prebuilts/gcc/linux-x86_64/arm-none-eabi/bin/arm-none-eabi-gcc` (GCC 13.4.0)
- 系统备用: /usr/bin/arm-none-eabi-gcc（构建实际使用）

## B. 编译
命令:
```bash
cd ~/openvela
cmake -B cmake_out/sf32lb52_devkit_lcd -S "$PWD/nuttx" -GNinja \
  -DBOARD_CONFIG=../vendor/sifli/boards/sf32lb52/sf32lb52_devkit_lcd/configs/nsh \
  -DEXTRA_FLAGS="-Wno-cpp -Wno-deprecated-declarations"
cmake --build cmake_out/sf32lb52_devkit_lcd -j$(nproc)
```
- 产物: `~/openvela/cmake_out/sf32lb52_devkit_lcd/nuttx.bin`
- 大小: 1542776 bytes (1.5M)
- 已复制: `/mnt/hgfs/VMware_share/artifacts/nuttx.bin`
- build_exit=0

## C. 烧录
- 端口: /dev/ttyACM0 （= Windows COM7）
- 命令: `sftool -c SF32LB52 -p /dev/ttyACM0 -b 1000000 write_flash --verify nuttx.bin@0x12010000`
- 日志: artifacts/flash.log
- flash_exit 见日志末行

## 阻塞
无（若 flash 失败，按一下板子 Reset 再重试）。
