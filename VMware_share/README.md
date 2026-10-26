# VMware HGFS 共享目录

Win：`E:\openvela\contest2026_313_bianyuanxingzhe\VMware_share`  
Ubuntu：`/mnt/hgfs/VMware_share`

**用途：** 仅作 Win ↔ Ubuntu **固件与日志交换**（`artifacts/`）。  
编译脚本、烧录脚本已迁至 [`../scripts/`](../scripts/README.md)。

## artifacts/

| 文件 | 说明 |
|------|------|
| `nuttx.bin` | 最新 openvela 镜像（`build_ew_main.sh` 输出） |
| `*.log` | 编译/探测日志 |

目录已 gitignore；Ubuntu 编译后 Windows 用 `scripts/host/flash_sf32.ps1` 烧录。
