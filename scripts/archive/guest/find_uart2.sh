#!/bin/bash
BOARD=~/openvela/vendor/sifli/boards/sf32lb52/sf32lb52_devkit_lcd
OUT=/mnt/hgfs/VMware_share/artifacts/uart2_pins.txt
{
  echo "==== $(date -Iseconds) ===="
  echo "--- README_zh-cn UART ---"
  grep -n -i -E 'UART|串口|引脚|pin|PA|PB|TX|RX' "$BOARD/README_zh-cn.md" | head -60
  echo "--- README ---"
  grep -n -i -E 'UART|pin|PA[0-9]|PB[0-9]|TX|RX' "$BOARD/README.md" | head -60
  echo "--- src ---"
  grep -RIn -E 'UART|USART|pinmux|PA[0-9]+|PB[0-9]+' "$BOARD/src" "$BOARD/include" 2>/dev/null | head -80
  echo "--- configs defconfig serial ---"
  grep -n -iE 'UART|SERIAL|USART|CONSOLE' "$BOARD/configs/nsh/defconfig" | head -40
  echo "--- board.h ---"
  find "$BOARD" -iname '*board*.h' -o -iname '*pin*' | head
  find "$BOARD" -name '*.h' | while read f; do grep -l -iE 'UART2|USART2' "$f" 2>/dev/null; done
} | tee "$OUT"