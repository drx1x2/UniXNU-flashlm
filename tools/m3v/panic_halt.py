#!/usr/bin/env python3
"""M3Z8 (DIAGNOSTIC ONLY): catch panics in the same round (no reset).

M3Z7 readout: device flashes past every old death point and resets with no M3E
record => leading suspect is a real panic going down the stock path (the M3U line
has no M3D, so panic -> reset). Hook `_panic_trap_to_debugger` entry (0x...726AC2C,
common to panic/Assert/panic_with_options; x6 = caller) with `b` to a 23-word
recorder at 0x...73E0A00 (start.s NOP hole, after crypto_reg's 0x73E0500..0x73E0990):
M3E crumb at 0xFFFFFFF007F14800, CODE 0x50, then wfe loop (no reset).
v3.7 rows: ESR = x2 (panic reason), ELR = x6 (caller of panic), FAR = x0 (format
string VA -> look up in kernel), CODE = 0x50. Do NOT combine with lr_rec reading
(lr_rec only touches the M3E exception recorder, so it may stay applied).
Usage: panic_halt.py IN OUT  (apply after crypto_reg.py / lr_rec.py).
"""
import struct, sys
BASE, SIZE, NOP = 0xFFFFFFF007004000, 14_917_208, 0xD503201F
SITE, PROLOGUE = 0xFFFFFFF00726AC2C, 0xD10203FF        # sub sp, sp, #0x80
VA = 0xFFFFFFF0073E0A00
REC = bytes([0x03, 0x00, 0x89, 0xd2, 0x23, 0xfe, 0xa0, 0xf2, 0x03, 0xfe, 0xdf, 0xf2, 0xe3, 0xff, 0xff, 0xf2, 0x62, 0x04, 0x00, 0xf9, 0x66, 0x08, 0x00, 0xf9, 0x60, 0x0c, 0x00, 0xf9, 0x04, 0x0a, 0x80, 0xd2, 0x64, 0x10, 0x00, 0xf9, 0x7e, 0x14, 0x00, 0xf9, 0xe5, 0x03, 0x00, 0x91, 0x65, 0x18, 0x00, 0xf9, 0x48, 0xa6, 0x89, 0xd2, 0x48, 0x6a, 0xa8, 0xf2, 0x08, 0xab, 0xc8, 0xf2, 0x68, 0xa6, 0xe9, 0xf2, 0x68, 0x20, 0x00, 0xf9, 0x9f, 0x3f, 0x03, 0xd5, 0x08, 0x05, 0x00, 0xd1, 0x68, 0x00, 0x00, 0xf9, 0x9f, 0x3f, 0x03, 0xd5, 0x5f, 0x20, 0x03, 0xd5, 0xff, 0xff, 0xff, 0x17])

def main():
    k = bytearray(open(sys.argv[1], 'rb').read())
    if len(k) != SIZE: sys.exit(f'size {len(k)} != {SIZE}')
    rd = lambda va: struct.unpack_from('<I', k, va - BASE)[0]
    if rd(SITE) != PROLOGUE: sys.exit(f'{SITE:#x} = {rd(SITE):#010x}, not pristine prologue')
    for va in range(VA - 4, VA + len(REC) + 4, 4):
        if rd(va) != NOP: sys.exit(f'{va:#x} not NOP (hole in use)')
    k[VA - BASE:VA - BASE + len(REC)] = REC
    struct.pack_into('<I', k, SITE - BASE, 0x14000000 | (((VA - SITE) >> 2) & 0x3FFFFFF))
    open(sys.argv[2], 'wb').write(k)
    print(f'panic_halt: _panic_trap_to_debugger -> {VA:#x} ({len(REC) // 4} words), halts with CODE 0x50')

if __name__ == '__main__':
    main()
