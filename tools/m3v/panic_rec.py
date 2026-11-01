#!/usr/bin/env python3
"""M3X: record the panic caller before the M3D panic->PSCI reset (DIAGNOSTIC ONLY).

  python3 panic_rec.py IN_KERNEL OUT_KERNEL      # IN = a kernel carrying M3D (e.g. current M3U)

M3D turned `_panic` entry into `b 0x...73E1010` (PSCI SYSTEM_RESET tail), so a panic
reboots with no trace. M3W moved the death past PE_init_printf and the device now
reset-loops: a panic. This retargets that one branch to a 28-word recorder at
0x...73E0500 (start.s NOP padding, low end of patch_trace.py cave 2; patch_trace
allocates from the top, so the two compose) which writes the M3E breadcrumb at the
fixed args VA 0xFFFFFFF007F14800 in the exact M3E layout, then jumps to the M3D tail.
The existing DarwinBoot crumb readback (darwinboot-crumb-readback.patch) draws it on
the next boot, DiagDraw rows 3-4:

    EXC 50 ESR <x1>          CODE 0x50 = panic (M3E vector codes are 0/3/4/7/C4-C6)
    ELR <x30> FAR <x0>       x30 = return address into the function that called panic()
                             x0  = panic format string VA (look it up in the kernel)
    (SPSR slot = x2, SP, TPIDR as in M3E)

Differences from the M3E recorder: no system registers (they describe no exception
here), and the two breadcrumb lines are cleaned to PoC (dc civac) before the reset so a
warm reset cannot drop them from the cache. Encodings come from GNU as and are checked
against a disassembly of the patched file by the caller.
"""
import struct, sys
BASE, SIZE, NOP = 0xFFFFFFF007004000, 14_917_208, 0xD503201F
PANIC = 0xFFFFFFF00796F3B4
M3D_BR, NEW_BR = 0x17E9C717, 0x17E9C453           # b 0x...73E1010 -> b 0x...73E0500
TAIL = (0xFFFFFFF0073E1010, [0x52800120, 0x72B08000, 0xD4000003, 0x14000000])
REC_VA = 0xFFFFFFF0073E0500
REC = [0xD2890003, 0xF2A0FE23, 0xF2DFFE03, 0xF2FFFFE3,   # x3 = 0xFFFFFFF007F14800
       0xF9000461, 0xF900087E, 0xF9000C60,               # ESR<-x1 ELR<-x30 FAR<-x0
       0xD2800A04, 0xF9001064, 0xF9001462,               # CODE=0x50, SPSR<-x2
       0x910003E6, 0xF9001866, 0xD538D087, 0xF9001C67,   # SP, TPIDR
       0xD289A648, 0xF2A86A48, 0xF2C8AB08, 0xF2E9A668,   # MAGIC2
       0xF9002068, 0xD5033F9F, 0xD1000508, 0xF9000068, 0xD5033F9F,  # MAGIC2, dsb, MAGIC1, dsb
       0xD50B7E23, 0x91010069, 0xD50B7E29, 0xD5033F9F,   # dc civac both lines, dsb
       0x140002A9]                                       # b 0x...73E1010 (M3D tail)

def main():
    k = bytearray(open(sys.argv[1], 'rb').read())
    if len(k) != SIZE: sys.exit(f'size {len(k)} != {SIZE}')
    rd = lambda va: struct.unpack_from('<I', k, va - BASE)[0]
    if rd(PANIC) == NEW_BR: sys.exit('already patched')
    if rd(PANIC) != M3D_BR: sys.exit(f'_panic entry {rd(PANIC):#010x}: input lacks M3D (want {M3D_BR:#010x})')
    for i, w in enumerate(TAIL[1]):
        if rd(TAIL[0] + 4 * i) != w: sys.exit(f'M3D tail word {i} mismatch')
    for va in range(REC_VA - 4, REC_VA + 4 * len(REC) + 4, 4):    # one guard NOP each side
        if rd(va) != NOP: sys.exit(f'{va:#x} not NOP (run panic_rec.py before patch_trace.py)')
    for i, w in enumerate(REC): struct.pack_into('<I', k, REC_VA - BASE + 4 * i, w)
    struct.pack_into('<I', k, PANIC - BASE, NEW_BR)
    open(sys.argv[2], 'wb').write(k)
    print(f'_panic -> recorder {REC_VA:#x}..{REC_VA + 4 * len(REC):#x} ({len(REC)} words) -> M3D tail; 29 words changed')

if __name__ == '__main__':
    main()
