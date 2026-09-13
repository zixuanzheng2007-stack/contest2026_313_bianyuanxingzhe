#!/bin/bash
export PATH="$HOME/bin:$PATH"
cd ~/openvela
DEF=vendor/sifli/boards/sf32lb52/sf32lb52_devkit_lcd/configs/nsh/defconfig
OUT=/mnt/hgfs/VMware_share/artifacts/uart2_kconfig.txt
{
  echo "==== $(date -Iseconds) ===="
  echo "--- defconfig UART ---"
  grep -n -iE 'UART|USART|TTYS|SERIAL|115200|1000000' "$DEF" | head -80
  echo "--- built .config ---"
  grep -n -iE 'UART|USART|TTYS|SERIAL' cmake_out/sf32lb52_devkit_lcd/.config 2>/dev/null | head -80
  echo "--- Kconfig names ---"
  grep -RIn -E 'BSP_USING_UART2|USART2|ttyS1|UART2' vendor/sifli --include='*Kconfig*' --include='*.h' 2>/dev/null | head -40
} | tee "$OUT"
