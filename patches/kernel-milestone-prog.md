# M3F diagnostic kernel patch — milestone progress slot (DIAGNOSTIC ONLY)

Stacks on the M3E patch (`kernel-exception-blackbox.md`): pristine kernel
MD5 `af7a0bf21935829b5a7ef12f14800f37` → M3E 56 words → **M3F +150 words**
(206 total vs pristine). File size unchanged (14,917,208 B). M3F kernel MD5
`64160485520521ad5be22a070da4f40f`. **Diagnostic use only — never ship in a
production image.** Purpose: M3D/M3E proved the silent death is neither a
panic nor a vector-table exception. M3F brackets the death inside
`_arm_init`'s call chain: ten entry trampolines record progress into a slot
in the boot-args page; the paired firmware readback
(`darwinboot-crumb-readback.patch`, M3F extension) draws the last reached
milestone (`PROG %lx CNT %lx`, DiagDraw row 5) on the next boot, before the
window ZeroMem. Patch generator: `m3f/patch_kernel.py` (all new encodings
produced by `llvm-mc-18`, never hand-derived).

## ⚠️ Two spec corrections (evidence-backed, same class as M3D/M3E)

1. **PROG slot base: `+0x840` → `+0x848`.** The M3F spec placed the PROG
   slot at boot-args `+0x840`, asserting the M3E exception record occupies
   `+0x800..+0x83F`. It does not: the record's last field MAGIC2 is stored
   by the recorder at `[crumb, #0x40]` (word `f9002068`), i.e. at
   args `+0x840..+0x847`, and the firmware validates `Crumb[8]` and clears
   `0x48` bytes — the record spans `+0x800..+0x847`. A PROG magic at
   `+0x840` would have collided head-on with EXC MAGIC2 (each channel
   corrupting the other in exactly the exception case where the last
   milestone matters most). PROG therefore starts at the first free byte,
   **`+0x848`** — which is what the spec's "right past the EXC record,
   non-overlapping" intent describes. Both sides (kernel stubs, firmware
   readback) use the corrected base, so the channel is self-consistent.
2. **P9 displaced word: `D101C3FF`, not the spec's `D10103FF`.**
   `_PE_init_iokit` at VA `0xFFFFFFF00793C44C` begins `sub sp, sp, #0x70`
   (`d101c3ff`), proven by `llvm-objdump` against the symbol in
   `mach.development.bcm2837.unstripped` and by the bytes of both shipped
   kernels. The spec value belongs to P2 (`_PE_init_platform`,
   `sub sp, sp, #0x40`) — a copy error in the spec table. The byte in both
   kernels is the ground truth; the trampoline displaces `D101C3FF`.

## PROG slot (boot-args page, VA recomputed via ParseKernel replication)

Segment walk of the shipped kernel (vmsize ≠ 0, 10 segments):
Base `0xFFFFFFF007004000`, End `0xFFFFFFF007F11E58`,
`ALIGN(End−Base, 16K) = 0xF10000`, boot-args VA `0xFFFFFFF007F14000`.
**PROG slot VA = `0xFFFFFFF007F14848`** (args + 0x848). EXC record stays at
args + 0x800 (`0xFFFFFFF007F14800`), untouched.

| off (from PROG base) | field |
|---|---|
| +0x00 | magic u64 `0x474F5250` ('PROG', zero-extended) |
| +0x08 | latest milestone ID (1..10) |
| +0x10 | cumulative milestone hit count |

Slot spans args `+0x848..+0x85F`; firmware clears exactly those 0x18 bytes
after drawing.

## Stub template (14 words per milestone)

Only x16/x17 are clobbered (IPA0/IPA1; every displaced word0 was verified
to read neither, and none is PC-relative):

```
movz  x16, #0x4848                 ; x16 = 0xFFFFFFF007F14848
movk  x16, #0x07F1, lsl #16
movk  x16, #0xFFF0, lsl #32
movk  x16, #0xFFFF, lsl #48
movz  x17, #0x5250                 ; x17 = 0x474F5250
movk  x17, #0x474F, lsl #16
str   x17, [x16]                   ; magic
movz  x17, #ID
str   x17, [x16, #8]               ; latest ID
ldr   x17, [x16, #0x10]
add   x17, x17, #1
str   x17, [x16, #0x10]            ; count++
.word <displaced original word0>   ; verbatim copy of the entry word
b     <entry VA + 4>
```

The entry word0 is replaced by `b stub_Pn` (assembler-produced).

## Milestone points

| ID | point | entry VA | file off | displaced word0 | stub VA | entry `b` word | stub ret `b` word |
|---|---|---|---|---|---|---|---|
| 1 | `_arm_init` entry | 0xFFFFFFF0079A118C | 0x99D18C | `D10343FF` sub sp,sp,#0xD0 | 0x73DC790 | `17E8ED81` | `14171273` |
| 2 | `_PE_init_platform` entry | 0xFFFFFFF00793C870 | 0x938870 | `D10103FF` sub sp,sp,#0x40 | 0x73DC7C8 | `17EA7FD6` | `1415801E` |
| 3 | `_arm_vm_init` entry | 0xFFFFFFF0073D7A74 | 0x3D3A74 | `D10583FF` sub sp,sp,#0x160 | 0x73DC800 | `14001363` | `17FFEC91` |
| 4 | `_pmap_bootstrap` entry | 0xFFFFFFF0073BB344 | 0x3B7344 | `D10243FF` sub sp,sp,#0x90 | 0x73DC838 | `1400853D` | `17FF7AB7` |
| 5 | after `bl _PE_init_printf` in `_arm_init` | 0xFFFFFFF0079A1AAC | 0x99DAAC | `52800020` movz w0,#0x1 | 0x73DC870 | `17E8EB71` | `14171483` |
| 6 | `_PE_initialize_console` entry | 0xFFFFFFF00793C304 | 0x938304 | `D100C3FF` sub sp,sp,#0x30 | 0x73DC8A8 | `17EA8169` | `14157E8B` |
| 7 | `_cpu_data_init` entry | 0xFFFFFFF0073D38C8 | 0x3CF8C8 | `7900041F` strh wzr,[x0,#2] | 0x73DC8E0 | `14002406` | `17FFDBEE` |
| 8 | `_cpu_data_alloc` entry | 0xFFFFFFF0073D4B94 | 0x3D0B94 | `D10103FF` sub sp,sp,#0x40 | 0x73DC918 | `14001F61` | `17FFE093` |
| 9 | `_PE_init_iokit` entry | 0xFFFFFFF00793C44C | 0x93844C | `D101C3FF` sub sp,sp,#0x70 ⚠️ | 0x73DC950 | `17EA8141` | `14157EB3` |
| 10 | `IOPlatformExpertDevice::init` entry | 0xFFFFFFF0078D3F4C | 0x8CFF4C | `A9BE4FF4` stp x20,x19,[sp,#-0x20]! | 0x73DC988 | `17EC228F` | `1413DD65` |

**P5 measured coordinates**: `_arm_init` (VA 0xFFFFFFF0079A118C, 2852 B)
contains exactly one `bl _PE_init_printf`: at VA 0xFFFFFFF0079A1AA8
(word `97FE64D4`, target 0xFFFFFFF00793ADF8). The marked word is the next
one, VA **0xFFFFFFF0079A1AAC** / file offset **0x99DAAC**, original
`52800020` (`movz w0, #0x1` — the first argument setup of the following
call; immediate move, non-PC-relative, reads no register).

## Cave layout (A32 NOP slide, VA 0x73DC600–0x73DD000, measured on the M3E kernel)

| span | contents |
|---|---|
| 0x73DC600 | M3E guard K8 (`b .`) |
| 0x73DC604–0x73DC60C | NOP ×3 |
| 0x73DC610–0x73DC648 | M3E exception stubs ×7 (14 words) |
| 0x73DC648–0x73DC67C | NOP ×14 (free) |
| 0x73DC680 | M3E guard K9 (`b .`) |
| 0x73DC684–0x73DC68C | NOP ×3 |
| 0x73DC690–0x73DC6FC | M3E recorder (27 words) |
| 0x73DC6FC | NOP ×1 |
| 0x73DC700 | M3E guard K10 (`b .`) |
| 0x73DC704–0x73DC70C | NOP ×3 |
| 0x73DC710–0x73DC720 | M3E PSCI tail (4 words) |
| 0x73DC720–0x73DC77C | NOP ×24 (free) |
| 0x73DC780 | M3E guard K11 (`b .`) |
| 0x73DC784–0x73DC78C | NOP ×3 |
| **0x73DC790–0x73DC9C0** | **M3F milestone stubs P1–P10 (10 × 14 words, contiguous, stride 0x38)** |
| 0x73DC9C0–0x73DCFFC | NOP (free) |

No M3F word overlaps any M3E guard/stub/recorder/tail word; placement was
gated on the target span being pure NOP in the M3E kernel.

## Diff ledger (word-level, verified on the built files)

| step | changed words |
|---|---|
| pristine → M3E | 56 (untouched by M3F; subset of the M3F set) |
| M3E → M3F | **150** = 10 entry words + 10 × 14 stub words, exactly the expected offset set |
| pristine → M3F | 206 |

Size unchanged at every step (14,917,208 B). ParseKernel replication on
the M3F kernel: magic/Base/End identical to pristine. All 11 patch points
(10 entries + P5) and all 10 stubs were disassembly-verified on the final
binary (entry→stub target, PROG VA/magic construction, ID, displaced word,
return→entry+4).

## Firmware side

`darwinboot-crumb-readback.patch` now also draws DiagDraw row 5 after the
EXC rows: reads the PROG slot at `ArgsAddress + 0x848`; magic `0x474F5250`
and ID in 1..10 → `PROG %lx CNT %lx`, otherwise `PROG NONE`; clears the
0x18-byte slot after drawing. DarwinBoot.c vs the M3B-pristine file is a
single hunk (+68 lines) containing exactly the WIN marker (M3C), the EXC
readback (M3E) and this PROG extension — nothing else.

## Later layers on these stubs

- M3N (`kernel-fbmarks-row2.md`) hooked the tails of P1/P2/P3/P7 to
  row-2 FB blocks; the stub bodies and this slot layout are unchanged
  there.
- M3S (`kernel-prog-selfclean.md`) adds a writer-side `dc cvac` +
  `dsb sy` to each of the ten stubs (word 12 slot + a 3-word cave
  trampoline per stub) so every write reaches DRAM deterministically
  for the monitor-core reader (`monitor-core-m3p.md`); words 0–11 and
  the displaced-word semantics here are unchanged.
