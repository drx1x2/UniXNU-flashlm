# M3G diagnostic patch — locore milestones + firmware survival probe (DIAGNOSTIC ONLY)

Stacks on M3F (`kernel-milestone-prog.md`): pristine kernel MD5
`af7a0bf21935829b5a7ef12f14800f37` → M3E 56 words → M3F +150 → **M3G +57
words (263 total vs pristine)**. File size unchanged (14,917,208 B).
**Diagnostic use only — never ship in a production image, never fold
into `ci/0019`.** Patch generator: `m3g/patch_kernel.py` (all new
encodings produced by `llvm-mc-18`, never hand-derived).

Purpose: M3F on hardware read back `PROG NONE` twice — either the kernel
dies before the first M3F milestone (`_arm_init` entry) in the locore
prologue (branch A), or the cross-boot record channel itself is broken
on this device (branch B: PMIC cold reset / ABL / DXE overwriting the
record page). M3G decides both in one flash: five PA-addressed
milestones cover `__start` → `_arm_init`, and the paired firmware
(`darwinboot-crumb-readback.patch`, M3G extension) plants a survival
probe in a page offset the kernel never writes.

## ⚠️ Spec correction (byte-proven, same class as M3D/M3E/M3F)

**L0 file offset: `0x3DC488`, not the task table's `0x3E0488`.** The
table's offset holds `d10173a3` (an unrelated `sub sp`). `__start`'s
true offset is entry VA `0xFFFFFFF0073E0488` − `__TEXT` base
`0xFFFFFFF007004000` = `0x3DC488`, which holds exactly `140006f5`
(`b _start_first_cpu`, target verified = `0xFFFFFFF0073E205C`). The
other four points matched the table byte-for-byte. Bytes are ground
truth (M3F P9 precedent).

## Addressing proof (unstripped disassembly, boot-CPU path)

- `x20 := args PA` at `_start_first_cpu+0x08` (`mov x20, x0`,
  `0x73E2064`). A destination-operand grep over the whole span
  `__start`…`common_start` end finds **no other write to x20**;
  `common_start` reads it once (`add x0, x20, x22` before its `ret`).
  So x20 = args PA at L2, L3b and L4.
- **x16/x17 are never mentioned anywhere in the locore span** — the
  stubs' clobber set is provably dead on this path.
- L0/L1 run before the `mov x20, x0` executes, so their stubs take the
  base from **x0** (entry args PA). L0's stub never writes x0; L4's
  stub never writes x30 (`b` in, displaced `ret` out).
- Pre-MMU points (L0/L1/L2): caches are off (DarwinEnter cleared
  M/C/I), stores go straight to DRAM. Post-MMU points (L3b/L4) use the
  same PA value as a VA: the bootstrap tables map the window as a
  VA==PA identity segment (TTBR0), and the args page lies inside the
  window, so PA-as-VA resolves to the same physical page.
- PROG slot PA = args PA + 0x848; layout identical to M3F
  ([+0] magic `0x474F5250`, [+8] latest ID, [+0x10] hit count).

## Locore milestone points

Stub shape (9 fixed words + tail): `add x16, <x0|x20>, #0x848`;
`movz/movk x17, 'PROG'`; `str x17, [x16]`; `movz x17, #ID`;
`str x17, [x16, #8]`; `ldr/add/str` count at `[x16, #0x10]`; tail per
point. All five stubs were disassembly-verified word-by-word on the
final binary (base register, ID, displaced word, branch targets).

| ID | point | entry VA | file off | orig word | base | stub VA | words | tail |
|---|---|---|---|---|---|---|---|---|
| 0x11 | `__start` | 0xFFFFFFF0073E0488 | **0x3DC488** ⚠️ | `140006F5` b _start_first_cpu | x0 | 0xFFFFFFF0073DC9C0 | 10 | re-encoded `b _start_first_cpu` |
| 0x12 | `_start_first_cpu` entry | 0xFFFFFFF0073E205C | 0x3DE05C | `D510109F` msr OSLAR_EL1, xzr | x0 | 0xFFFFFFF0073DC9E8 | 11 | displaced word + `b entry+4` |
| 0x13 | `_start_first_cpu` tail (tables filled) | 0xFFFFFFF0073E228C | 0x3DE28C | `14000001` b common_start | x20 | 0xFFFFFFF0073DCA14 | 10 | re-encoded `b common_start` |
| 0x14 | `common_start`, post-VBAR/SCTLR (MMU on) | 0xFFFFFFF0073E2370 | 0x3DE370 | `D2A00600` mov x0, #0x300000 | x20 | 0xFFFFFFF0073DCA3C | 11 | displaced word + `b entry+4` |
| 0x15 | `common_start` exit (ret → _arm_init) | 0xFFFFFFF0073E2388 | 0x3DE388 | `D65F03C0` ret | x20 | 0xFFFFFFF0073DCA68 | 10 | displaced `ret` |

Entry words after patching (assembler-produced): L0 `17FFF14E`,
L1 `17FFEA63`, L2 `17FFE9E2`, L3b `17FFE9B3`, L4 `17FFE9B8` — each a
`b` to its stub, confirmed by disassembly.

## Cave layout delta (A32 NOP slide, VA 0x73DC600–0x73DD000)

M3E guards/stubs/recorder/tail and M3F stubs P1–P10 unchanged
(0x73DC600–0x73DC9C0, see `kernel-milestone-prog.md`). M3G adds, in the
previously free span, contiguously from `0x73DC9C0`:
L0 0x73DC9C0–0x73DC9E8, L1 0x73DC9E8–0x73DCA14, L2 0x73DCA14–0x73DCA3C,
L3b 0x73DCA3C–0x73DCA68, L4 0x73DCA68–0x73DCA90. Placement was gated on
every target word being NOP (`D503201F`) in the M3F kernel; the span
0x73DCA90–0x73DD000 remains free NOP.

## Firmware survival probe (DarwinBoot, M3G extension)

Probe slot: args page **+0x860** (past EXC record +0x800..+0x847 and
PROG slot +0x848..+0x85F; no kernel code writes this offset). Magic:
u64 value `0x0000000050524231` (little-endian bytes `31 42 52 50` =
'1','B','R','P'; both sides use the u64 constant, so the channel is
value-consistent).

- **Read**: first in the readback block (before EXC/PROG reads, hence
  before this boot's window ZeroMem): Row 6 draws `PRB OK` when the
  slot equals the magic, else `PRB NO` — every boot, on its own row.
- **Write**: after this boot's window ZeroMem and segment fills,
  before the ExitBootServices/DarwinEnter sequence:
  `*(volatile UINT64 *)(ArgsAddress + 0x860) = magic`.
- **PROG validity range extended**: IDs 1..10 (M3F) **or 0x11..0x15**
  (locore) draw `PROG %lx CNT %lx`; anything else draws `PROG NONE`.

DarwinBoot.c vs the M3B-pristine file: exactly two hunks — the readback
region (WIN marker + PRB read + EXC readback + PROG readback) and the
PRB write before the EBS loop. Format strings `PRB OK`, `PRB NO`,
`PROG %lx CNT %lx`, `PROG NONE`, `EXC %lx ESR %lx`, `ELR %lx FAR %lx`,
`WIN %lx SZ %lx` each occur exactly once in the built DarwinBoot.efi.

## Diff ledger (word-level, verified on the built files)

| step | changed words |
|---|---|
| pristine → M3E | 56 (subset of M3G set, verified still patched) |
| pristine → M3F | 206 (subset of M3G set, verified still patched) |
| M3F → M3G | **57** = 5 entry words + 52 stub words (10+11+10+11+10), exactly the expected offset set |
| pristine → M3G | **263** |

Size unchanged at every step (14,917,208 B). Segment tables of the M3G
kernel are byte-identical to pristine (Base `0xFFFFFFF007004000`,
End `0xFFFFFFF007F11E58`, args VA `0xFFFFFFF007F14000`).

## Readout matrix (hardware)

Flash, boot slot B (expected same freeze, wait 30 s), force-reboot
with **power + volume-down** back into slot B, read rows 5–6 on the
second boot:

| PRB (row 6) | PROG (row 5) | verdict |
|---|---|---|
| OK | 0x11–0x15 | (A) proven: kernel dies inside locore, bracketed after the shown milestone |
| OK | NONE | channel alive, kernel never reached `__start` — death is in the hand-off tail (DarwinEnter/exit-boot-services path) |
| NO | any | (B) proven on this device: cross-boot records in the window do not survive; channel must move out of the window (e.g. BootShim slot page) |
| OK | 1..10 | contradicts M3F's NONE — re-examine (would imply M3F-era channel failure, not kernel position) |

## Delivery (2026-10-31 build)

- Firmware: stuart full rebuild, one Success
  (`logs/build-m3g-locore.log`, BUILD_EXIT=0). Baseline/isolation sweep
  passed: product DarwinBoot EL gate still `!= 4` only, zero EL2 text
  in DarwinBoot.c/Entry.S (rig changes confined to qemu-debug),
  FvSimpleFileSystemDxe present in the product FDF, Sheng count 0 in
  FVMAIN.Fv, BootShim slot store (`movk x6, #0x89B0, lsl #16`,
  BootShim.S:44; `ARMd` + slot words verified in the built
  BootShim.bin), RamDiskDxe `DTB_POINTER_SLOT 0x89B00000`, menu
  physical-keys symbol `CollectTextInputs` in the built UniXNU app.
  New bootpayload 3,185,615 B (`m3g/bootpayload-m3g.bin`).
- Kernel: M3G patched file MD5 `850602e628a864e6deea38b7d6c47a94`
  (`m3g/kernel-m3g.bin`, generator `m3g/patch_kernel.py`, disassembly
  log in the build report).
- Payload: M3F image's ramdisk with KERNEL replaced in place along its
  cluster chain; ramdisk diff vs M3F = 225 bytes, **all inside KERNEL
  clusters, 0 outside**; KERNEL.ADT MD5 `8766bcb3571f2b70dc03a4295c7ad824`
  and unixnu.toml MD5 `08ec0480941c9efea566189c6f6ff77e` byte-identical
  to M3C. Header taken from this build's packed image with
  ramdisk_size restored and the v0 id recomputed (AOSP SHA-1; layout
  verified byte-equal in convention to the M3F final image).
- Image: `builds/lg-flash-unixnu-m3g-locore.img`, 28,356,608 B,
  MD5 `be454dc549e031e22206cb156424f104`,
  SHA-256 `98a91f63931466edd1f883691300f63029139bfde3e7e1127c7dff737ca88323`.
  Independent readback: kernel segment == new bootpayload, ramdisk
  segment == assembled ramdisk, in-image KERNEL == M3G patched kernel.
