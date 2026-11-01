#!/bin/sh
# Assemble the M3U monitor blobs (needs an AArch64 GNU as + objcopy;
# on an x86 host use aarch64-linux-gnu-as / aarch64-linux-gnu-objcopy).
# monitor35.S is the v3.5 blob as shipped in M3U, reconstructed from the
# patch bytes; it must reassemble byte-identically (checked by gate.py).
set -e
cd "$(dirname "$0")"
AS=${AS:-as}; OBJCOPY=${OBJCOPY:-objcopy}
for v in monitor35 monitor351 monitor352; do
  $AS -o $v.o $v.S
  $OBJCOPY -O binary -j .text $v.o $v.bin
  rm -f $v.o
  echo "$v.bin $(wc -c < $v.bin) B  md5 $(md5sum $v.bin | cut -d' ' -f1)"
done
