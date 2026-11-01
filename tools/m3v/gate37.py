#!/usr/bin/env python3
"""M3Z3 host-side gates for monitor v3.7 (trace strip + same-boot EXC readout). pip install unicorn.

Gate A  identity: the blob in patches/darwinboot-cpuon-monitor.patch equals
        monitor37.bin (skipped with a note until the patch carries v3.6).
Gate B  v3.5.2 preamble regression: tables built, row-3 S1->S2->S3, no
        stray / args writes (reuses tools/m3u/gate.py).
Gate C  stage-1 permission walk (reuses tools/m3u/gate.py) plus v3.6's new
        accesses: trace ring read (Normal-WB) and every trace-cell FB store
        (writable Device).
Gate D  loop run (Unicorn, MMU off = degraded path; cntpct_el0 faked): ring
        scenarios -> every cell's colour and position, idx1 colour, zero
        writes outside the FB, no read past the ring's 30 visible entries.
"""
import os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '../m3u'))
import gate as g                                           # noqa: E402
from unicorn import Uc, UcError, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_MEM_WRITE, UC_HOOK_MEM_READ, UC_HOOK_CODE
from unicorn.arm64_const import UC_ARM64_REG_PC, UC_ARM64_REG_X0

PAL = [0xFFFF0000, 0xFFFF8000, 0xFFFFFF00, 0xFF80FF00, 0xFF00FF00, 0xFF00FF80, 0xFF00FFFF, 0xFF0080FF,
       0xFF0000FF, 0xFF8000FF, 0xFFFF00FF, 0xFFFF0080, 0xFFFFFFFF, 0xFF808080, 0xFF804000, 0xFFFF80C0]
RING = 0xC1F14980
DARK = 0xFF303030
IDX1 = 0x9D026A10
CRUMB, M1 = 0xC1F14800, 0x4D33455843524D31

def bit_xy(row, i):
    return 16 + i * 40 + (i >> 2) * 8, 2380 + row * 50

def bit_col(b, i):
    odd = (i >> 2) & 1
    return (0xFFFFFF00 if odd else 0xFFFFFFFF) if b else (0xFF505050 if odd else 0xFF202020)

def mkcrumb(esr, elr, far, code, m2ok=True):
    return struct.pack('<QQQQQQQQQ', M1, esr, elr, far, code, 0, 0, 0, M1 + 1 if m2ok else 0)

def check_exc(fb, vals):
    bad = []
    for row, v in enumerate(vals):
        for i in range(32):
            x, y = bit_xy(row, i)
            want = bit_col((v >> (31 - i)) & 1, i) if v is not None else 0
            for dx, dy in ((0, 0), (31, 39)):
                if px(fb, x + dx, y + dy) != want: bad.append(f'r{row}b{i}={px(fb, x+dx, y+dy):#x}!={want:#x}')
            if v is not None and px(fb, x + 32, y) == want: bad.append(f'r{row}b{i} overruns')
    return bad

def cell_xy(i):
    return 16 + (i % 15) * 96, 2680 + (i // 15) * 56

def px(fb, x, y):
    return struct.unpack_from('<I', fb, y * 5760 + x * 4)[0]

def run(blob, ring_ids, ring_n, prog_id, crumb=None, steps=12_000_000):
    uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    for a, s in ((g.SLOT, 0x1000), (g.FB, g.FBSZ), (g.ARGS, 0x1000)):
        uc.mem_map(a, s)
    uc.mem_write(g.RES, blob)                              # CELL stays 0 -> degraded (MMU-off) path
    uc.mem_write(g.MAILBOX, struct.pack('<QQQ', 0x474F5250, prog_id, 1))
    uc.mem_write(RING, struct.pack('<Q', ring_n) + bytes(ring_ids))
    if crumb: uc.mem_write(CRUMB, crumb)
    stray, reads = [], []
    uc.hook_add(UC_HOOK_MEM_WRITE, lambda u, a, addr, s, v, d: None if g.FB <= addr < g.FB + g.FBSZ else stray.append(addr))
    uc.hook_add(UC_HOOK_MEM_READ, lambda u, a, addr, s, v, d: reads.append(addr) if RING <= addr < g.ARGS + 0x1000 else None)
    clk = [0]
    def code(u, addr, size, d):                            # mrs xN, cntpct_el0 / cntfrq_el0 -> fake
        w = struct.unpack('<I', u.mem_read(addr, 4))[0]
        if w & ~31 in (0xD53BE020, 0xD53BE000):
            clk[0] += 50_000
            u.reg_write(UC_ARM64_REG_X0 + (w & 31), clk[0] if w & ~31 == 0xD53BE020 else 19_200_000)
            u.reg_write(UC_ARM64_REG_PC, addr + 4)
    uc.hook_add(UC_HOOK_CODE, code)
    try: uc.emu_start(g.RES, 0, count=steps)
    except UcError as e: return None, stray, reads, str(e)
    return bytes(uc.mem_read(g.FB, g.FBSZ)), stray, reads, None

def gate_d(blob):
    ok = True
    for name, ids, n, prog in (('7 hits', list(range(0x20, 0x27)), 7, 0x26),
                               ('skip+unknown', [0x20, 0x23, 0x55], 3, 0x23),
                               ('overflow n=200', [0x20 + (i % 15) for i in range(0x78)], 200, 0x2E),
                               ('empty', [], 0, 4)):
        fb, stray, reads, err = run(blob, ids, n, prog)
        if err: print(f'Gate D [{name}] FAIL {err}'); ok = False; continue
        bad = []
        vis = min(n, 30)
        for i in range(30):
            x, y = cell_xy(i)
            want = (PAL[ids[i] - 0x20] if 0x20 <= ids[i] < 0x30 else 0xFFFFFFFF) if i < vis else DARK
            for dx, dy in ((0, 0), (40, 20), (79, 39)):
                if px(fb, x + dx, y + dy) != want: bad.append(f'cell{i}({dx},{dy})={px(fb, x+dx, y+dy):#x}!={want:#x}')
            if px(fb, x + 80, y) == want and want != 0: bad.append(f'cell{i} overruns width')
        w1 = PAL[prog - 0x20] if 0x20 <= prog < 0x30 else None
        got1 = struct.unpack_from('<I', fb, IDX1 - g.FB)[0]
        if w1 is not None and got1 != w1: bad.append(f'idx1={got1:#x}!={w1:#x}')
        maxread = max(reads) if reads else RING
        if maxread >= RING + 8 + 30: bad.append(f'read past ring view {maxread:#x}')
        res = 'PASS' if not (bad or stray) else 'FAIL ' + '; '.join(bad[:4]) + (f' stray={len(stray)}' if stray else '')
        print(f'Gate D [{name}] cells={vis} idx1={got1:#x}: {res}')
        ok &= not (bad or stray)
    esr, elr, far, code = 0x96000045, 0xFFFFFFF0073B1234, 0xFFFFFFE0DEADBEE8, 0x14
    for name, cr, exp in (('exc valid', mkcrumb(esr, elr, far, code), [esr, elr & 0xFFFFFFFF, elr >> 32, far & 0xFFFFFFFF, far >> 32, code]),
                          ('exc magic2 bad', mkcrumb(esr, elr, far, code, False), [None] * 6),
                          ('exc none', None, [None] * 6)):
        fb, stray, reads, err = run(blob, [0x20, 0x21], 2, 0x21, cr)
        if err: print(f'Gate E [{name}] FAIL {err}'); ok = False; continue
        bad = check_exc(fb, exp)
        res = 'PASS' if not (bad or stray) else 'FAIL ' + '; '.join(bad[:4]) + (f' stray={len(stray)}' if stray else '')
        print(f'Gate E [{name}]: {res}')
        ok &= not (bad or stray)
    return ok

def main():
    blob = open(os.path.join(HERE, 'monitor37.bin'), 'rb').read()
    p = open(os.path.join(HERE, '../../patches/darwinboot-cpuon-monitor.patch')).read()
    import re
    s = p.index('mM3PMonitorBlob[] = {'); e = p.index('};', s)
    pb = bytes(int(x, 16) for x in re.findall(r'0x([0-9a-f]{2})', p[s:e]))
    ok = pb == blob
    print(f'Gate A  patch blob == monitor37.bin: {"PASS" if ok else "FAIL"} ({len(pb)} B vs {len(blob)} B)')
    for B in (0xB0000000, 0x89A00000, 0x9F000000):
        tables, paints, stray, err = g.preamble(blob, B)
        if err: print(f'Gate B B={B:#x} FAIL {err}'); ok = False; continue
        seq = ' -> '.join(g.NAMES.get(c, hex(c)) for _, c in paints)
        fails = g.gate_c(tables, B, blob)
        w = g.walk(tables, B, RING)
        if not w or w['pa'] != RING or w['attr'] != 0: fails.append('ring read')
        for i in range(30):
            x, y = cell_xy(i)
            for va in (g.FB + y * 5760 + x * 4, g.FB + (y + 39) * 5760 + (x + 79) * 4):
                w = g.walk(tables, B, va)
                if not w or w['pa'] != va or w['ap'] & 2 or w['attr'] != 1: fails.append(f'cell{i} {va:#x}'); break
        w = g.walk(tables, B, CRUMB)
        if not w or w['pa'] != CRUMB or w['attr'] != 0: fails.append('crumb read')
        for row in range(6):
            for i in (0, 31):
                x, y = bit_xy(row, i)
                for va in (g.FB + y * 5760 + x * 4, g.FB + (y + 39) * 5760 + (x + 31) * 4):
                    w = g.walk(tables, B, va)
                    if not w or w['pa'] != va or w['ap'] & 2 or w['attr'] != 1: fails.append(f'bit r{row} {va:#x}')
        print(f'Gate B B={B:#x} [{seq}] stray={len(stray)}; Gate C {"PASS" if not fails else "FAIL " + "; ".join(fails[:3])}')
        ok &= not (fails or stray)
    ok &= gate_d(blob)
    print('M3Z3 monitor v3.7 gates:', 'PASS' if ok else 'FAIL')
    return 0 if ok else 1

if __name__ == '__main__':
    sys.exit(main())
