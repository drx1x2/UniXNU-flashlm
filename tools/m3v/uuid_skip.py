#!/usr/bin/env python3
"""M3Z4 (DIAGNOSTIC ONLY): skip the SHA-1 branch of generatePlatformUUID.

M3Z3 readout: ESR 0x96000005 (EL1 data abort, read, L1 translation fault),
ELR 0xFFFFFFF00786AA40 = _sha1_init+0x34 `ldr x20, [x22, #0x28]`, FAR 0x28.
x22 = g_crypto_funcs (0xFFFFFFF0071AF598) = NULL: nothing in this kernel calls
register_crypto_functions (its caller is the com.apple.kec.corecrypto kext,
which the M3 diagnostic kernel never loads), so g_crypto_funcs->sha1 (+0x28)
faults. Caller: IOPlatformExpertDevice::generatePlatformUUID, which takes the
SHA-1 path because our ADT /chosen carries unique-chip-id (8 B) and chip-id
(4 B) -- both correct and needed for M4 (IOPlatformUUID), so the ADT stays.

Patch: 0x...78D2DFC `b.ne +0x128` (0x54000941, unique-chip-id length != 8)
-> `b +0x128` (0x1400004A): always take the "no chip id" exit (x21 = 0,
release /chosen, no IOPlatformUUID). 1 word.

Usage: uuid_skip.py IN OUT   (M3U -> fix_console_pa -> halt_tail -> this)
"""
import struct, sys
BASE, SIZE = 0xFFFFFFF007004000, 14_917_208
SITE, OLD, NEW = 0xFFFFFFF0078D2DFC, 0x54000941, 0x1400004A

def main():
    k = bytearray(open(sys.argv[1], 'rb').read())
    if len(k) != SIZE: sys.exit(f'size {len(k)} != {SIZE}')
    w = struct.unpack_from('<I', k, SITE - BASE)[0]
    if w == NEW: sys.exit('uuid skip already applied')
    if w != OLD: sys.exit(f'{SITE:#x}: {w:#010x} != b.ne {OLD:#010x}')
    struct.pack_into('<I', k, SITE - BASE, NEW)
    open(sys.argv[2], 'wb').write(k)
    print(f'uuid skip: {SITE:#x} b.ne -> b (generatePlatformUUID SHA-1 path bypassed); 1 word')

if __name__ == '__main__':
    main()
