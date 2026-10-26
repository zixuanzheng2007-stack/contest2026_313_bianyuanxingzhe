#!/bin/bash
set -e
echo "BEFORE:"; lsblk; df -h /
# Grow partition 2 to fill disk
sudo growpart /dev/sda 2
# Resize filesystem (ext4 typical on Ubuntu)
FS=$(findmnt -n -o FSTYPE /)
echo "FSTYPE=$FS"
if [ "$FS" = "ext4" ] || [ "$FS" = "ext3" ]; then
  sudo resize2fs /dev/sda2
elif [ "$FS" = "xfs" ]; then
  sudo xfs_growfs /
else
  sudo resize2fs /dev/sda2 || sudo xfs_growfs /
fi
echo "AFTER:"; lsblk; df -h /
# free a bit of space emergency if growpart tools missing
df -h /