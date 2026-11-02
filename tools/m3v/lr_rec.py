#!/usr/bin/env python3
"""M3Z6 (DIAGNOSTIC ONLY): M3E recorder stores x30 instead of FAR_EL1.

M3Z5 readout: ESR 0x86000005 (EC 0x21 instruction abort, L1 translation),
ELR 0, FAR 0 => a branch/call through a NULL function pointer. ELR/FAR carry no
information there; the caller is in x30 (the recorder clobbers only x0-x8).
One word: recorder `str x2,[x3,#0x18]` (FAR) at 0x...73DC6C0 -> `str x30,[x3,#0x18]`.
Monitor v3.7 rows 4/5 (FAR lo/hi) then show LR. NOTE: on later data aborts those
rows are LR too, not FAR.
Usage: lr_rec.py IN OUT  (apply last, after crypto_reg.py).
"""
import struct, sys
BASE, SIZE = 0xFFFFFFF007004000, 14_917_208
VA, OLD, NEW = 0xFFFFFFF0073DC6C0, 0xF9000C62, 0xF9000C7E
k = bytearray(open(sys.argv[1], 'rb').read())
if len(k) != SIZE: sys.exit(f'size {len(k)} != {SIZE}')
cur = struct.unpack_from('<I', k, VA - BASE)[0]
if cur != OLD: sys.exit(f'{VA:#x} = {cur:#010x}, expected {OLD:#010x} (no M3E recorder?)')
struct.pack_into('<I', k, VA - BASE, NEW)
open(sys.argv[2], 'wb').write(k)
print(f'lr_rec: {VA:#x} str FAR -> str x30')
