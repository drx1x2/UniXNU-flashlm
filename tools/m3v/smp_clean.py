#!/usr/bin/env python3
"""M3Z14 smp_clean: fix the secondary-CPU CPU_ON wedge (DIAGNOSTIC kernel, 5 in-place words, no cave).

  python3 smp_clean.py IN_KERNEL OUT_KERNEL

A secondary starts at LowResetVectorBase with MMU and caches OFF and reads, by physical address:
  ResetHandlerData (0x...7176180), const_boot_args (0x...71647F8), sysreg_restore.tcr_el1
  (0x...71647A8 -> TCR_EL1), cpu_ttep (0x...71646B8 -> TTBR1_EL1), bootstrap_pagetables
  (0x...7166000..0x...7176000 -> TTBR0 V=P map), its cpu_data and CpuDataEntries.
ArmCpu::startCPU cleans only LowResetVectorBase+64K, ResetHandlerData+4K and 0x...71647F8+4K
(dc civac from 0x...71647C0): the cache lines holding sysreg_restore (0x...7164780) and cpu_ttep
(0x...7164680) and the bootstrap tables are never cleaned to PoC. cpu_data/CpuDataEntries are
flushed by cpu_start's flush_dcache. A secondary that reads a stale TCR/TTBR1 turns the MMU on over
garbage tables; on SM8150 the resulting walk into protected/unbacked PA can stall the NoC for every
core (same class as the 0x3C0FC000 console read). The ios-raphael SM8150 port (8/8 CPUs) cleans
exactly these objects to PoC before CPU_ON (0065-sweet-smp-psci.patch, cpu.c) and adds dsb;isb after
the secondary's TLB/I-cache invalidation before SCTLR.M=1 (start.s).

Patch:
 1. ArmCpu::startCPU 3rd clean loop: base 0x...71647F8 -> 0x...7164000, length 4K -> 0x13000, so it
    cleans 0x...7164000..0x...7177000 (cpu_ttep, sysreg_restore, const_boot_args, BootArgs,
    bootstrap_pagetables, ResetHandlerData). All of it is __DATA_CONST,__const (mapped; DC CIVAC is a
    read-permission operation).
 2. common_start: `add x0,x0,#0` (no-op) -> `dsb sy`; `movk x0,#0,lsl#48; movk x0,#0,lsl#32` ->
    `isb; movz x0,#0` (same SCTLR value 0x3454593D), i.e. dsb sy + isb between tlbi/ic iallu and
    SCTLR_EL1.M=1. Harmless on the boot CPU.
Test with cpus=7: CPU7 (MPIDR 0x700) runs the v3.x monitor and must not be CPU_ON'ed by the kernel.
"""
import struct, sys
BASE = 0xFFFFFFF007004000
SIZE = 14_917_208
EDITS = [  # (VA, pristine, new, what)
    (0xFFFFFFF00795FD6C, 0x911FE16B, 0x9100016B, 'startCPU clean#3 base: add x11,x11,#0x7f8 -> #0'),
    (0xFFFFFFF00795FD74, 0x9140056B, 0x91404D6B, 'startCPU clean#3 end: +0x1000 -> +0x13000'),
    (0xFFFFFFF0073E2330, 0x91000000, 0xD5033F9F, 'common_start: add x0,x0,#0 -> dsb sy'),
    (0xFFFFFFF0073E2340, 0xF2E00000, 0xD5033FDF, 'common_start: movk x0,#0,lsl#48 -> isb'),
    (0xFFFFFFF0073E2344, 0xF2C00000, 0xD2800000, 'common_start: movk x0,#0,lsl#32 -> movz x0,#0'),
]
def main():
    src, dst = sys.argv[1:3]
    k = bytearray(open(src, 'rb').read())
    if len(k) != SIZE: sys.exit(f'size {len(k)} != {SIZE}')
    for va, w0, w1, what in EDITS:
        cur = struct.unpack_from('<I', k, va - BASE)[0]
        if cur != w0: sys.exit(f'{va:#x}: {cur:#010x} != pristine {w0:#010x} (touched by an earlier layer?)')
    for va, w0, w1, what in EDITS:
        struct.pack_into('<I', k, va - BASE, w1)
        print(f'  {va:#x}: {w0:#010x} -> {w1:#010x}  {what}')
    open(dst, 'wb').write(k)
if __name__ == '__main__':
    main()
