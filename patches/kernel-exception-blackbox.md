# M3E diagnostic kernel patch — exception black box (DIAGNOSTIC ONLY)

Applies to the CI-built stripped kernel `mach.development.bcm2837`
(xnu-8796.141.3, DEVELOPMENT_ARM64_BCM2837; pristine MD5
`af7a0bf21935829b5a7ef12f14800f37`, 14,917,208 B). **Diagnostic use only —
never ship in a production image.** The patch is 56 words; the file size is
unchanged. Purpose: the kernel dies silently between the DarwinBoot
hand-off and console initialisation. `_panic` rerouting (M3D) proved the
death is not a panic. This patch instruments the remaining silent exit —
the exception path itself — by rerouting the exception-vector slots that
can reach the C layer, and the three spin points inside
`check_exception_stack`, to a small recorder that stores the exception
registers into the tail of the boot-args page and resets via PSCI. The
paired firmware change (`darwinboot-crumb-readback.patch`) reads the
record back on the next boot, before the window ZeroMem, and draws it on
DiagDraw rows 3–4.

## Breadcrumb location — VERIFIED VALUE, corrects the design draft

The design draft named VA `0xFFFFFFF007B64800`. Per the draft's own
verification instruction, the value was recomputed from the segment
table by replicating DarwinBoot's `ParseKernel` exactly (segments with
`vmsize != 0`; `MAX_SEGMENTS` = 64, so all 10 such segments count,
including `__LINKINFO` and `__LINKEDIT`):

- `Kernel.Base` = `0xFFFFFFF007004000`
- `Kernel.End`  = `0xFFFFFFF007F11E58` (end of `__LINKEDIT`)
- `ALIGN(End - Base, 16K)` = `0xF10000`
- boot-args VA = Base + `0xF10000` = `0xFFFFFFF007F14000`
- **breadcrumb VA = boot-args VA + 0x800 = `0xFFFFFFF007F14800`**

The draft value implies `ALIGN(End - Base, 16K) = 0xB60000`, which
matches no walk of the flashed kernel's segment table (a walk stopping
at `__BOOTDATA` gives `0xB64000`; the full ParseKernel walk gives
`0xF10000`). The recorder below therefore assembles
`0xFFFFFFF007F14800`, the only address the firmware readback (which
computes the same formula at runtime from the real `Kernel.End`) will
ever look at. `sizeof(DARWIN_BOOT_ARGS) == 0x480 < 0x800`
(BootArgs.h static assert), so the breadcrumb never overlaps the
boot-args struct; the args page is inside the window span the kernel's
bootstrap page tables map (`MemorySize` = window size).

Breadcrumb layout (all UINT64, offsets from the breadcrumb address):

| off | field |
|---|---|
| +0x00 | MAGIC1 `0x4D33455843524D31` ("M3EXCRM1"), stored last |
| +0x08 | ESR_EL1 |
| +0x10 | ELR_EL1 |
| +0x18 | FAR_EL1 |
| +0x20 | CODE (slot id, zero-extended) |
| +0x28 | SPSR_EL1 |
| +0x30 | SP at exception |
| +0x38 | TPIDR_EL1 |
| +0x40 | MAGIC2 `0x4D33455843524D32` ("M3EXCRM2"), stored first |

## Vector-slot and check-stack reroutes (7 words)

All new encodings were produced by `llvm-mc` (never hand-derived) and
verified by disassembling the patched binary at the real VAs.

| id | file off | VA | original | new | intent |
|---|---|---|---|---|---|
| K1 | 0x3D8000 | 0x73DC000 (slot 0) | `14000400` | `14000184` | `b stub0` (CODE=0) |
| K2 | 0x3D8180 | 0x73DC180 (slot 3) | `14000406` | `14000126` | `b stub3` (CODE=3) |
| K3 | 0x3D8200 | 0x73DC200 (slot 4) | `140003f6` | `14000108` | `b stub4` (CODE=4) |
| K4 | 0x3D8380 | 0x73DC380 (slot 7) | `140003c4` | `140000aa` | `b stub7` (CODE=7) |
| K5 | 0x3D93F8 | 0x73DD3F8 | `b4000012` | `b4ff91d2` | `cbz x18, stubC4` — opcode/register/condition unchanged, only the target: was a self-loop when `cpu_data->exception_stack_top` (at `[TPIDR+0x1C8]`… loaded via x18) is 0 |
| K6 | 0x3D9404 | 0x73DD404 | `5400000c` | `54ff91ac` | `b.gt stubC5` — condition (GT) unchanged, target only (SP above stack top) |
| K7 | 0x3D9410 | 0x73DD410 | `5400000b` | `54ff918b` | `b.lt stubC6` — condition (LT) unchanged, target only (SP below stack top − 16 KiB) |

Fall-through behaviour of K5–K7 (condition false) is byte-for-byte the
original path; only the taken-branch target moved from "spin here" to
"record, then reset".

## A32 slide guards (4 words)

The hole region `0x73DC600–0x73DD000` (file `0x3D8600–0x3D9000`) is pure
NOP padding in the pristine kernel. The first word of each 0x80 slot
residue in the stub/recorder half is turned into `b .` (`14000000`) so
an AArch32-style slide down the table stops at a guard instead of
falling into the recorder code:

| id | file off | VA | original | new |
|---|---|---|---|---|
| K8 | 0x3D8600 | 0x73DC600 | `d503201f` | `14000000` |
| K9 | 0x3D8680 | 0x73DC680 | `d503201f` | `14000000` |
| K10 | 0x3D8700 | 0x73DC700 | `d503201f` | `14000000` |
| K11 | 0x3D8780 | 0x73DC780 | `d503201f` | `14000000` |

## Stubs (14 words, file 0x3D8610, VA 0x73DC610)

Seven stubs, 2 words each: `movz w4, #CODE` then `b recorder`.

| stub | VA | CODE | words |
|---|---|---|---|
| stub0 | 0x73DC610 | 0 | `52800004`, `1400001f` |
| stub3 | 0x73DC618 | 3 | `52800064`, `1400001d` |
| stub4 | 0x73DC620 | 4 | `52800084`, `1400001b` |
| stub7 | 0x73DC628 | 7 | `528000e4`, `14000019` |
| stubC4 | 0x73DC630 | 0xC4 | `52801884`, `14000017` |
| stubC5 | 0x73DC638 | 0xC5 | `528018a4`, `14000015` |
| stubC6 | 0x73DC640 | 0xC6 | `528018c4`, `14000013` |

## Recorder (27 words, file 0x3D8690, VA 0x73DC690)

No stack use; clobbers x0–x8 only (x4 = CODE arrives from the stub).

```
mrs  x0, ESR_EL1          d5385200
mrs  x1, ELR_EL1          d5384021
mrs  x2, FAR_EL1          d5386002
mrs  x5, SPSR_EL1         d5384005
mov  x6, sp               910003e6
mrs  x7, TPIDR_EL1        d538d087
movz x3, #0x4800          d2890003     ; x3 = 0xFFFFFFF007F14800
movk x3, #0x07F1, lsl 16  f2a0fe23
movk x3, #0xFFF0, lsl 32  f2dffe03
movk x3, #0xFFFF, lsl 48  f2ffffe3
str  x0, [x3, #0x08]      f9000460     ; ESR
str  x1, [x3, #0x10]      f9000861     ; ELR
str  x2, [x3, #0x18]      f9000c62     ; FAR
str  x4, [x3, #0x20]      f9001064     ; CODE
str  x5, [x3, #0x28]      f9001465     ; SPSR
str  x6, [x3, #0x30]      f9001866     ; SP
str  x7, [x3, #0x38]      f9001c67     ; TPIDR
movz x8, #0x4D32          d289a648     ; x8 = MAGIC2 0x4D33455843524D32
movk x8, #0x4352, lsl 16  f2a86a48
movk x8, #0x4558, lsl 32  f2c8ab08
movk x8, #0x4D33, lsl 48  f2e9a668
str  x8, [x3, #0x40]      f9002068     ; MAGIC2 first
dsb  sy                   d5033f9f
sub  x8, x8, #1           d1000508     ; MAGIC1 = MAGIC2 - 1
str  x8, [x3]             f9000068     ; MAGIC1 last (commit word)
dsb  sy                   d5033f9f
b    tail                 14000006
```

## PSCI tail (4 words, file 0x3D8710, VA 0x73DC710)

Identical to the M3D assembler-verified sequence; issues
PSCI SYSTEM_RESET (`0x84000009`) so a recorded exception reboots the
device and the paired firmware readback can display the record.

```
movz w0, #0x9             52800120
movk w0, #0x8400, lsl 16  72b08000
smc  #0                   d4000003
b    .                    14000000
```

## Verification performed at build time

- All 11 spec'd original words matched the pristine kernel byte-for-byte
  before patching; the hole region was confirmed pure NOP
  (`0x3D8600–0x3D9000`).
- Full-file diff vs the pristine kernel: exactly the 56 words above,
  nothing else; size unchanged (14,917,208 B). Patched kernel MD5
  `4952355d688a38ef3510dda32b5a5e7a`.
- `llvm-objdump` disassembly of the patched binary at the real VAs
  confirms every branch target (slots → stubs, K5–K7 → stubC4/C5/C6
  with conditions preserved, stubs → recorder, recorder → tail) and
  the recorder's store map.
- `ParseKernel` replication on the patched kernel: header, entry
  (`0xFFFFFFF0073E0488`), Base/End unchanged.
