# 扩盘后黑屏修复（根分区仍 20G 且 100% 满）

虚拟机其实已开机，SSH 正常。黑屏是因为磁盘写满，桌面起不来。
虚拟磁盘已是 128G，但分区 sda2 还是 20G，需要扩展分区。

## 在 Windows PowerShell 执行（会要一次 Ubuntu 密码）

ssh openvela-vm

然后在 Ubuntu 里执行：

sudo bash /mnt/hgfs/VMware_share/fix_disk_expand.sh

完成后：

df -h /
sudo reboot

回来应能进桌面。若仍黑屏，开机时狂按 Esc 进 GRUB → Advanced → recovery。