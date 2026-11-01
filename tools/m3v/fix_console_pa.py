#!/usr/bin/env python3
"""M3W: repoint PE_create_console's hardcoded bcm2837 panic-log PA (DIAGNOSTIC FIX).

  python3 fix_console_pa.py IN_KERNEL OUT_KERNEL

xnu-8796 BCM2837 PE_create_console does
    ml_io_map_wcomb(0x3C0FC000, 0x4000); ldr w8, [x0]  (magic check); else bzero 16 KiB
0x3C0FC000 is RAM on a RPi3 (1 GiB at 0) but not DRAM on SM8150; M3V2 readout #2
(2026-11-01) showed the first read never returns (bus hang).

Fix: one word. `movk w0, #0x3c0f, lsl #16` at 0x...793CBDC -> `movk w0, #0x9d1f, lsl #16`,
so the PA becomes 0x9D1FC000 = the last 16 KiB of "Display Reserved"
(0x9C000000 + 18 MiB, PlatformMemoryMapLib.c): non-secure DRAM, outside the kernel's
managed RAM (physBase ~0xC1000000), and past the visible framebuffer
(0x9C000000 + 3120 * 5760 = 0x9D122000), so the bzero is invisible. It is the only
0x3c0f immediate in the kernel. Composable with patch_trace.py (disjoint words).
"""
import struct, sys
BASE, SIZE = 0xFFFFFFF007004000, 14_917_208
SITE = 0xFFFFFFF00793CBDC
PREV = (0xFFFFFFF00793CBD8, 0x52980000)       # movz w0, #0xc000
OLD, NEW = 0x72A781E0, 0x72B3A3E0             # movk w0,#0x3c0f,lsl16 -> movk w0,#0x9d1f,lsl16
assert NEW == 0x72A00000 | 0x9D1F << 5 and OLD == 0x72A00000 | 0x3C0F << 5

def main():
    src, dst = sys.argv[1], sys.argv[2]
    k = bytearray(open(src, 'rb').read())
    if len(k) != SIZE: sys.exit(f'size {len(k)} != {SIZE}')
    rd = lambda va: struct.unpack_from('<I', k, va - BASE)[0]
    if rd(PREV[0]) != PREV[1]: sys.exit(f'{PREV[0]:#x}: {rd(PREV[0]):#010x} != {PREV[1]:#010x}')
    if rd(SITE) == NEW: sys.exit('already patched')
    if rd(SITE) != OLD: sys.exit(f'{SITE:#x}: {rd(SITE):#010x} != {OLD:#010x}')
    struct.pack_into('<I', k, SITE - BASE, NEW)
    open(dst, 'wb').write(k)
    print(f'{SITE:#x}: {OLD:#010x} -> {NEW:#010x}  (PE_create_console panic-log PA 0x3C0FC000 -> 0x9D1FC000)')

if __name__ == '__main__':
    main()
