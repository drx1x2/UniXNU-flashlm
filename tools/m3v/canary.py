#!/usr/bin/env python3
"""M3Z: cross-reset readback-channel canary (DIAGNOSTIC ONLY, one flash = one verdict).

  python3 canary.py IN_KERNEL OUT_KERNEL            # variant C: clean to PoC before reset
  python3 canary.py IN_KERNEL OUT_KERNEL --no-clean # variant N: same, dc civac -> nop

IN = current M3U kernel after fix_console_pa.py (M3W). Do NOT also run patch_trace.py
--set console (its 0x2C point is the same word) or panic_rec.py (same cave words).

The `ret` of initialize_screen (0x...73B087C, reached on device: readout #3) becomes
`b 0x...73E0500`. The 35-word canary writes a known breadcrumb in the exact M3E layout at
args VA 0xFFFFFFF007F14800, optionally cleans both lines to PoC, and jumps to the M3E
PSCI SYSTEM_RESET tail at 0x...73DC710 (present in M3U). The next boot's
darwinboot-crumb-readback draws on DiagDraw rows 3-4:

    EXC ee ESR c0ffee01      (variant N: c0ffee00)
    ELR fffffff0073b087c FAR ca4a

Verdict:
  C shows        -> kernel-written record survives warm reset when cleaned; channel OK.
                    Then flash N: N shows -> PSCI/EL3 flushes caches, (b) is false;
                    N missing -> dirty lines are lost: add dc civac to M3E recorder + PROG.
  C missing      -> firmware side (readback address / ordering / XBL-ABL scrub) is broken;
                    PROG NONE has the same cause; fix the channel before any recorder.
"""
import struct, sys
BASE, SIZE, NOP, RET = 0xFFFFFFF007004000, 14_917_208, 0xD503201F, 0xD65F03C0
SITE, BR = 0xFFFFFFF0073B087C, 0x1400BF21          # ret -> b 0x...73E0500
TAIL = (0xFFFFFFF0073DC710, [0x52800120, 0x72B08000, 0xD4000003, 0x14000000])   # M3E PSCI tail
VA = 0xFFFFFFF0073E0500
CLEAN = [0xD2890003, 0xF2A0FE23, 0xF2DFFE03, 0xF2FFFFE3, 0xD29DC020, 0xF2B81FE0,
       0xD2810F81, 0xF2A0E761, 0xF2DFFE01, 0xF2FFFFE1, 0xD2994942, 0xD2801DC4,
       0xF9000460, 0xF9000861, 0xF9000C62, 0xF9001064, 0xF900147F, 0x910003E6,
       0xF9001866, 0xD538D087, 0xF9001C67, 0xD289A648, 0xF2A86A48, 0xF2C8AB08,
       0xF2E9A668, 0xF9002068, 0xD5033F9F, 0xD1000508, 0xF9000068, 0xD5033F9F,
       0xD50B7E23, 0x91010069, 0xD50B7E29, 0xD5033F9F, 0x17FFF062]
NOCLEAN = [0xD2890003, 0xF2A0FE23, 0xF2DFFE03, 0xF2FFFFE3, 0xD29DC000, 0xF2B81FE0,
       0xD2810F81, 0xF2A0E761, 0xF2DFFE01, 0xF2FFFFE1, 0xD2994942, 0xD2801DC4,
       0xF9000460, 0xF9000861, 0xF9000C62, 0xF9001064, 0xF900147F, 0x910003E6,
       0xF9001866, 0xD538D087, 0xF9001C67, 0xD289A648, 0xF2A86A48, 0xF2C8AB08,
       0xF2E9A668, 0xF9002068, 0xD5033F9F, 0xD1000508, 0xF9000068, 0xD5033F9F,
       0xD503201F, 0xD503201F, 0xD503201F, 0xD5033F9F, 0x17FFF062]

def main():
    k = bytearray(open(sys.argv[1], 'rb').read())
    if len(k) != SIZE: sys.exit(f'size {len(k)} != {SIZE}')
    rd = lambda va: struct.unpack_from('<I', k, va - BASE)[0]
    code = NOCLEAN if '--no-clean' in sys.argv[3:] else CLEAN
    if rd(SITE) != RET: sys.exit(f'{SITE:#x}: {rd(SITE):#010x} is not ret (trace set or canary already applied?)')
    for i, w in enumerate(TAIL[1]):
        if rd(TAIL[0] + 4 * i) != w: sys.exit(f'M3E PSCI tail word {i} at {TAIL[0] + 4 * i:#x} mismatch: input lacks M3E')
    for va in range(VA - 4, VA + 4 * len(code) + 4, 4):
        if rd(va) != NOP: sys.exit(f'{va:#x} not NOP (panic_rec.py already applied?)')
    for i, w in enumerate(code): struct.pack_into('<I', k, VA - BASE + 4 * i, w)
    struct.pack_into('<I', k, SITE - BASE, BR)
    open(sys.argv[2], 'wb').write(k)
    print(f'canary {"N (no clean)" if code is NOCLEAN else "C (clean)"}: ret@{SITE:#x} -> {VA:#x}..{VA + 4 * len(code):#x} -> M3E tail; {len(code) + 1} words')

if __name__ == '__main__':
    main()
