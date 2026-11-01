#!/usr/bin/env python3
"""M3V trace stubs for the xnu-8796.141.3 diagnostic kernel (DIAGNOSTIC ONLY).

  python3 patch_trace.py IN_KERNEL OUT_KERNEL

IN_KERNEL is the kernel the current image ships (the M3U kernel: pristine
af7a0bf2... + M3E/M3F/M3N/M3S/... layers) or the pristine CI kernel. Every
trace point below must still hold its pristine word (no earlier layer may
have touched it) and the stubs go into the highest free NOP run of the
A32 NOP-slide cave 0x...73DC600-0x...73DD000; the script refuses otherwise.

Each stub (24 words, only x16/x17 and NZCV clobbered -- dead at a call's
return point and at the loop exits used here):
  PROG slot (args+0x848): magic, latest ID, count++   -- same as M3F, so
                                                         row-3 idx1 keeps working
  trace ring (args+0x980): n++, and if n <= 0x78: byte[args+0x987+n] = ID
  dsb ish; displaced word (bl/adrp re-encoded for the stub's PC); b back
The monitor (v3.6) draws ring entries 1..30 as colour cells above row 1.
"""
import struct, subprocess, sys, tempfile, os

BASE = 0xFFFFFFF007004000          # file offset 0 <-> this VA (segment walk, kernel-milestone-prog.md)
SIZE = 14_917_208
PROG = 0xFFFFFFF007F14848
CAVE_LO, CAVE_HI = 0xFFFFFFF0073DC600, 0xFFFFFFF0073DD000
NOP = 0xD503201F

# (ID, VA, pristine word, meaning) -- pristine words read from
# mach.development.bcm2837.unstripped of CI run 41150570344 (MD5 af7a0bf2...)
POINTS = [
    (0x20, 0xFFFFFFF0073BB454, 0x7100041F, 'pmap_bootstrap: SecureDTGetProperty returned'),
    (0x21, 0xFFFFFFF0073BB4F4, 0xD0FFED55, 'pmap_bootstrap: pmap_data_bootstrap returned'),
    (0x22, 0xFFFFFFF0073BB57C, 0xD0FFED48, 'pmap_bootstrap: bzero returned'),
    (0x23, 0xFFFFFFF0073D89C4, 0x9400089A, 'arm_vm_init: pmap_bootstrap returned'),
    (0x24, 0xFFFFFFF0073D8B28, 0xB0FFEC68, 'arm_vm_init: 1st table-page loop exited'),
    (0x25, 0xFFFFFFF0073D8C60, 0xF9409B33, 'arm_vm_init: 2nd table-page loop exited'),
    (0x26, 0xFFFFFFF0073D8CB8, 0xF85A03A8, 'arm_vm_init: _enable_preemption returned'),
    (0x27, 0xFFFFFFF0079A195C, 0x90FFBDA8, 'arm_init: arm_vm_init returned'),
    (0x28, 0xFFFFFFF0079A1974, 0x97FE6EBF, 'arm_init: PE_consistent_debug_inherit returned'),
    (0x29, 0xFFFFFFF0079A1978, 0xAA0003F3, 'arm_init: serial_init returned'),
    (0x2A, 0xFFFFFFF0079A1984, 0xD0FFB6C0, 'arm_init: kernel_startup_initialize_upto returned'),
    (0x2B, 0xFFFFFFF0079A1990, 0xF0FFBE14, 'arm_init: 1st kprintf returned'),
    (0x2C, 0xFFFFFFF0079A1A6C, 0xF0FFBE08, 'arm_init: kern_feature_override returned'),
    (0x2D, 0xFFFFFFF0079A1A94, 0xB00009E8, 'arm_init: switch_to_serial_console returned'),
    (0x2E, 0xFFFFFFF0079A1AA4, 0x52800000, 'arm_init: PE_create_console returned'),
]
STUB_WORDS = 24

def off(va): return va - BASE
def movz(d, imm, hw): return 0xD2800000 | hw << 21 | imm << 5 | d
def movk(d, imm, hw): return 0xF2800000 | hw << 21 | imm << 5 | d
def str_x(t, n, o): return 0xF9000000 | (o // 8) << 10 | n << 5 | t
def ldr_x(t, n, o): return 0xF9400000 | (o // 8) << 10 | n << 5 | t
def add_i(d, n, i): return 0x91000000 | i << 10 | n << 5 | d
def cmp_i(n, i): return 0xF100001F | i << 10 | n << 5
def add_r(d, n, m): return 0x8B000000 | m << 16 | n << 5 | d
def strb(t, n, o): return 0x39000000 | o << 10 | n << 5 | t
def b(frm, to, link=False):
    d = (to - frm) // 4
    assert -(1 << 25) <= d < (1 << 25)
    return (0x94000000 if link else 0x14000000) | d & 0x3FFFFFF
def bcond(frm, to, cond):
    d = (to - frm) // 4
    return 0x54000000 | (d & 0x7FFFF) << 5 | cond
def adrp_target(pc, w):
    imm = ((w >> 5) & 0x7FFFF) << 2 | (w >> 29) & 3
    if imm & (1 << 20): imm -= 1 << 21
    return (pc & ~0xFFF) + (imm << 12)
def adrp(pc, rd, tgt):
    imm = ((tgt & ~0xFFF) - (pc & ~0xFFF)) >> 12
    assert -(1 << 20) <= imm < (1 << 20)
    imm &= (1 << 21) - 1
    return 0x90000000 | (imm & 3) << 29 | (imm >> 2) << 5 | rd

PCREL_REJECT = [(0x7C000000, 0x14000000, 'b'), (0xFF000010, 0x54000000, 'b.cond'),
                (0x7E000000, 0x34000000, 'cbz/cbnz'), (0x7E000000, 0x36000000, 'tbz/tbnz'),
                (0x3B000000, 0x18000000, 'ldr literal'), (0x9F000000, 0x10000000, 'adr')]

def relocate(entry, word, at):
    if word & 0xFC000000 == 0x94000000:                    # bl
        d = word & 0x3FFFFFF
        if d & (1 << 25): d -= 1 << 26
        return b(at, entry + d * 4, link=True)
    if word & 0x9F000000 == 0x90000000:                    # adrp
        return adrp(at, word & 31, adrp_target(entry, word))
    for m, v, name in PCREL_REJECT:
        if word & m == v: sys.exit(f'refusing {entry:#x}: displaced word {word:#010x} is PC-relative ({name})')
    return word

def stub(sid, entry, word, at):
    w = [movz(16, PROG & 0xFFFF, 0), movk(16, PROG >> 16 & 0xFFFF, 1),
         movk(16, PROG >> 32 & 0xFFFF, 2), movk(16, PROG >> 48 & 0xFFFF, 3),
         movz(17, 0x5250, 0), movk(17, 0x474F, 1), str_x(17, 16, 0),
         movz(17, sid, 0), str_x(17, 16, 8),
         ldr_x(17, 16, 0x10), add_i(17, 17, 1), str_x(17, 16, 0x10),
         add_i(16, 16, 0x138),                              # x16 = args + 0x980
         ldr_x(17, 16, 0), add_i(17, 17, 1), str_x(17, 16, 0),
         cmp_i(17, 0x78), None,                             # b.hi -> dsb
         add_r(16, 16, 17), movz(17, sid, 0), strb(17, 16, 7),
         0xD5033B9F]                                        # dsb ish
    w[17] = bcond(at + 17 * 4, at + 21 * 4, 8)              # hi
    w.append(relocate(entry, word, at + 22 * 4))
    w.append(b(at + 23 * 4, entry + 4))
    assert len(w) == STUB_WORDS
    return w

def main():
    src, dst = sys.argv[1], sys.argv[2]
    k = bytearray(open(src, 'rb').read())
    if len(k) != SIZE: sys.exit(f'size {len(k)} != {SIZE}')
    rd = lambda va: struct.unpack_from('<I', k, off(va))[0]
    for sid, va, w0, what in POINTS:
        if rd(va) != w0: sys.exit(f'point {sid:#x} {va:#x}: word {rd(va):#010x} != pristine {w0:#010x} (touched by an earlier layer?)')
    need = len(POINTS) * STUB_WORDS
    best, va, run_end = None, CAVE_HI - 4, CAVE_HI      # highest NOP run that fits (plus a guard NOP below)
    while va >= CAVE_LO:
        if rd(va) != NOP: run_end = va
        else:
            start = (va + 4 + 7) & ~7                   # keep word va as the guard NOP
            if start + need * 4 <= run_end: best = start; break
        va -= 4
    if best is None: sys.exit('no free NOP run in the cave')
    ledger = []
    for i, (sid, va, w0, what) in enumerate(POINTS):
        at = best + i * STUB_WORDS * 4
        for j, w in enumerate(stub(sid, va, w0, at)):
            struct.pack_into('<I', k, off(at + j * 4), w)
        struct.pack_into('<I', k, off(va), b(va, at))
        ledger.append((sid, va, at, what))
    open(dst, 'wb').write(k)
    print(f'stubs at {best:#x}..{best + len(POINTS) * STUB_WORDS * 4:#x} ({len(POINTS)} x {STUB_WORDS} words)')
    for sid, va, at, what in ledger:
        print(f'  {sid:#04x}  entry {va:#x} (off {off(va):#x}) -> stub {at:#x}   {what}')

if __name__ == '__main__':
    main()
