#!/usr/bin/env python3
"""M3U2 host-side gates for the monitor blobs (pip install unicorn).

Gate A  identity: the blob embedded in patches/darwinboot-cpuon-monitor.patch
        equals monitor352.bin byte for byte.
Gate B  preamble run (Unicorn, MMU off, EL1h): execute from 0x89B00400 up to
        the SCTLR_EL1 write; record the row-3 paint sequence, the tables the
        blob built, and every store outside {table pages, FB}. The args page
        must receive zero writes.
Gate C  stage-1 walk of the built tables with the ARMv8 EL1&0 permission
        rules (ARM ARM D8.4.1), including the rule that a location writable
        at EL0 is treated as PXN at EL1 regardless of the descriptor's PXN
        bit. Checks: every body instruction fetch is executable at EL1, the
        mailbox/signature reads are readable, the row-3 FB stores are
        writable Device.

Unicorn 2.1 cannot be used past SCTLR.M=1 here (even a minimal hand-built
identity map prefetch-aborts in it), so Gate C replaces emulation for the
MMU-on half. Expected: monitor35/monitor351 FAIL Gate C on the first fetch
after SCTLR.M (implicit PXN on the slot page), monitor352 PASSes.
"""
import re, struct, sys, os
from unicorn import Uc, UcError, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_MEM_WRITE, UC_HOOK_CODE
from unicorn.arm64_const import UC_ARM64_REG_CP_REG

HERE = os.path.dirname(os.path.abspath(__file__))
SLOT, RES, CELL = 0x89B00000, 0x89B00400, 0x89B00110
FB, FBSZ, ARGS = 0x9C000000, 0x1200000, 0xC1F14000
ROW3, STRIDE = 0x9D026600, 0x1680
MAILBOX, SIG = 0xC1F14848, 0xC1F14880
NAMES = {0xFFFFFFFF: 'white(S1)', 0xFFFF00FF: 'magenta(S2)', 0xFF808080: 'gray(S3)',
         0xFF00FF00: 'green(S4)'}

def gate_a():
    p = open(os.path.join(HERE, '../../patches/darwinboot-cpuon-monitor.patch')).read()
    s = p.index('mM3PMonitorBlob[] = {'); e = p.index('};', s)
    b = bytes(int(x, 16) for x in re.findall(r'0x([0-9a-f]{2})', p[s:e]))
    ok = b == open(os.path.join(HERE, 'monitor352.bin'), 'rb').read()
    print(f'Gate A  patch blob == monitor352.bin: {"PASS" if ok else "FAIL"} ({len(b)} B)')
    return ok

def preamble(blob, B):
    uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    for a, s in ((SLOT, 0x1000), (B, 0x4000), (FB, FBSZ), (ARGS, 0x1000)):
        uc.mem_map(a, s)
    uc.mem_write(B, b'\xA5' * 0x4000)                    # garbage: zeroing is exercised
    uc.mem_write(RES, blob); uc.mem_write(CELL, struct.pack('<Q', B))
    paints, stray = [], []
    def wr(uc, acc, addr, size, val, ud):
        if FB <= addr < FB + FBSZ:
            off = addr - ROW3
            if 0 <= off < 60 * STRIDE:
                key = ((off % STRIDE) // 4 // 260, val & 0xFFFFFFFF)
                if not paints or paints[-1] != key: paints.append(key)
        elif not (B <= addr < B + 0x4000): stray.append(addr)
    uc.hook_add(UC_HOOK_MEM_WRITE, wr)
    # stop right before the SCTLR_EL1 write (msr sctlr_el1, x4 = d5181004)
    stop = RES + blob.index(bytes.fromhex('041018d5'))
    try: uc.emu_start(RES, stop, count=200000)
    except UcError as e: return None, paints, stray, str(e)
    return bytes(uc.mem_read(B, 0x4000)), paints, stray, None

def walk(tables, B, va):
    rd = lambda pa: struct.unpack_from('<Q', tables, pa - B)[0] if B <= pa < B + 0x4000 else None
    tab = B
    for lvl, sh in ((0, 39), (1, 30), (2, 21), (3, 12)):
        d = rd(tab + ((va >> sh) & 511) * 8)
        if d is None or not d & 1: return None
        if lvl < 3 and d & 2: tab = d & 0xFFFFFFFFF000; continue
        if lvl == 3 and not d & 2: return None
        out = d & ~((1 << sh) - 1) & 0xFFFFFFFFF000 | (va & ((1 << sh) - 1))
        return dict(pa=out, attr=(d >> 2) & 7, ap=(d >> 6) & 3, af=(d >> 10) & 1,
                    pxn=(d >> 53) & 1, uxn=(d >> 54) & 1)
    return None

def gate_c(tables, B, blob):
    mair = {0: 'Normal-WB', 1: 'Device-nGnRE'}
    fails = []
    body0 = RES + blob.index(bytes.fromhex('041018d5')) + 8     # first fetch after msr+isb
    for va in range(body0, RES + len(blob), 4):
        w = walk(tables, B, va)
        if not w or w['pa'] != va or not w['af']: fails.append(f'fetch {va:#x}: translation'); break
        pxn_eff = w['pxn'] or w['ap'] == 1                   # EL0-writable => PXN at EL1
        if pxn_eff:
            fails.append(f'fetch {va:#x}: permission (AP={w["ap"]:02b}, PXN={w["pxn"]}, '
                         f'{"implicit PXN: EL0-writable" if w["ap"] == 1 else "PXN"})'); break
    for va in (MAILBOX, MAILBOX + 8, SIG, SIG + 8):
        w = walk(tables, B, va)
        if not w or w['pa'] != va or mair[w['attr']] != 'Normal-WB': fails.append(f'read {va:#x}')
    for idx in range(5):
        va = ROW3 + idx * 0x410
        w = walk(tables, B, va)
        if not w or w['pa'] != va or w['ap'] & 2 or mair[w['attr']] != 'Device-nGnRE': fails.append(f'FB {va:#x}')
    return fails

def main():
    ok = gate_a()
    for name in ('monitor35', 'monitor351', 'monitor352'):
        blob = open(os.path.join(HERE, name + '.bin'), 'rb').read()
        for B in (0xB0000000, 0x89A00000, 0x9F000000):      # table bases: plain, slot's 2 MiB neighbour, near FB
            tables, paints, stray, err = preamble(blob, B)
            seq = ' -> '.join(f'idx{i}:{NAMES.get(c, hex(c))}' for i, c in paints) or '(none)'
            if err: print(f'{name} B={B:#x}: Gate B FAIL {err}'); ok = False; continue
            argsw = [a for a in stray if ARGS <= a < ARGS + 0x1000]
            fails = gate_c(tables, B, blob)
            print(f'{name} B={B:#x}: Gate B paints [{seq}] stray-writes={len(stray)} args-writes={len(argsw)}; '
                  f'Gate C {"PASS" if not fails else "FAIL: " + "; ".join(fails)}')
            if name == 'monitor352' and (fails or stray): ok = False
    print('M3U2 gates:', 'PASS' if ok else 'FAIL')
    return 0 if ok else 1

if __name__ == '__main__':
    sys.exit(main())
