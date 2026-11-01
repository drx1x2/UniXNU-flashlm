#!/bin/sh
# Assemble monitor v3.6 (AArch64 GNU as + objcopy; on x86 use aarch64-linux-gnu-*).
set -e
cd "$(dirname "$0")"
AS=${AS:-as}; OBJCOPY=${OBJCOPY:-objcopy}
$AS -o monitor36.o monitor36.S
$OBJCOPY -O binary -j .text monitor36.o monitor36.bin
rm -f monitor36.o
echo "monitor36.bin $(wc -c < monitor36.bin) B  md5 $(md5sum monitor36.bin | cut -d' ' -f1)"
