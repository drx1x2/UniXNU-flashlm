#!/usr/bin/env python3
"""M3Z2 halt tail (DIAGNOSTIC ONLY): same-boot reset discriminator.

Cross-boot DRAM records are dead on this device (M3L CPY NO NO, M3G PRB NO,
canary C empty), so nothing written before a reset can be read after it.
This turns the live M3E PSCI SYSTEM_RESET tail at 0x...73DC710 into a
self-loop: word 0 `mov w0,#9` (0x52800120) -> `b .` (0x14000000). The M3E
exception recorder (the only armed kernel-side reset route left by the
6971a5d audit) then parks the CPU instead of resetting, so the M3V trace band
the monitor draws stays on screen.

Usage: halt_tail.py M3W_KERNEL HALT_KERNEL   (M3U -> fix_console_pa.py -> this)

Reading: device now freezes with the band up => the reset was the kernel's
own M3E exception tail (an exception fires between P2#2 and P9; next step is
same-boot exception colouring). Device still resets within seconds => reset
comes from outside the kernel's armed paths (EL3/XPU/watchdog), not M3E.
"""
import struct, sys
BASE, SIZE = 0xFFFFFFF007004000, 14_917_208
TAIL = (0xFFFFFFF0073DC710, [0x52800120, 0x72B08000, 0xD4000003, 0x14000000])
HALT = 0x14000000

def main():
    k = bytearray(open(sys.argv[1], 'rb').read())
    if len(k) != SIZE: sys.exit(f'size {len(k)} != {SIZE}')
    rd = lambda va: struct.unpack_from('<I', k, va - BASE)[0]
    if rd(TAIL[0]) == HALT: sys.exit('halt already applied')
    for i, w in enumerate(TAIL[1]):
        if rd(TAIL[0] + 4 * i) != w: sys.exit(f'M3E PSCI tail word {i} at {TAIL[0] + 4 * i:#x} mismatch: input lacks M3E')
    struct.pack_into('<I', k, TAIL[0] - BASE, HALT)
    open(sys.argv[2], 'wb').write(k)
    print(f'halt: {TAIL[0]:#x} mov w0,#9 -> b . ; 1 word')

if __name__ == '__main__':
    main()
