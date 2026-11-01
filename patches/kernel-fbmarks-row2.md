# Kernel patch (DIAGNOSTIC): FB marks row 2 — post-locore C milestones via the identity alias (M3N)

Stacks on the M3L kernel (pristine → M3L = 349 changed words, see
`kernel-locore-fbmarks.md` / `m3l-earlycopy-fbmarks.md`). Baseline for
this layer: M3L kernel MD5 `884949415562806d6df07261aa70f7fa`.
Generator: `~/workspace/unixnu-flashlm/m3n/patch_kernel.py`; packed by
`~/workspace/unixnu-flashlm/m3n/assemble.py` on the M3M image (firmware
bytes verbatim). **Not for production use.**

## Why

Round 6 starts from the M3M hardware photo: locore FB marks 5/5 lit —
the kernel completes `__start → common_start` exit and reaches the
`_arm_init` doorstep on real hardware. The death is inside the C span
`[_arm_init, ArmDTPlatform::configure)`, with `_panic` (M3D) and the
rerouted exception paths (M3E) excluded. The PROG readback channel is
dead on this hardware (M3G–M3L), so the FB color marks are the only
live channel — but from `_arm_init` on, code runs on kernel VAs and
the framebuffer PA (0x9C000000) is outside both bootstrap mappings
(the VA mapping and the window identity segment). The maneuver used
here is the **identity alias**: each stub computes its own physical
address, branches to the same code inside the identity-mapped window,
paints the framebuffer by PA with SCTLR.M cleared, restores, and
branches back to the VA continuation.

All numbers below were recomputed from the CI `.unstripped` kernel
(`llvm-objdump`/`llvm-nm` full scans) and re-verified on the patched
binary; hand-derived values are not used (house rule).

## Analysis 1 — TTBR switch timing (disassembly-proven)

Full-kernel scan for `msr tcr_el1 / ttbr0_el1 / ttbr1_el1` (patterns
generated with `llvm-mc-18` for every Rt) finds writes in exactly
four places:

| site | instructions |
|---|---|
| `common_start` (+0xC/+0x18/+0x28/+0x98/+0xC0) | `msr tcr_el1`; `bl _set_mmu_ttb` (bootstrap TTBR0); two `msr ttbr1_el1` fixups; final `msr sctlr_el1` |
| `_set_tcr` (0xFFFFFFF0073E63A8) | `msr tcr_el1; isb; ret` |
| `_set_mmu_ttb_alternate` (0xFFFFFFF0073E637C) | `dsb sy; msr ttbr1_el1; isb; ret` |
| `_set_mmu_ttb` (0xFFFFFFF0073E638C) | `dsb ish; msr ttbr0_el1; isb; ret` |

`_arm_init` (0xFFFFFFF0079A118C, size 0xBCC) contains **no** `msr`/`mrs`
at all. The only boot-path callers of the three helpers are inside
`_arm_vm_init` (0xFFFFFFF0073D7A74, size 0x1390):

| offset in `_arm_vm_init` | VA | effect |
|---|---|---|
| +0xAC8 | 0xFFFFFFF0073D853C | `bl _set_tcr` — new TCR = `get_tcr() \| 0x2000000000` (bit 37 / TBI1 only; low-half geometry untouched) |
| +0xC04 | 0xFFFFFFF0073D8678 | `bl _set_mmu_ttb_alternate` — TTBR1 ← `*_cpu_ttep & 0xFFFFFFFFFFFF` (`_cpu_ttep` @0xFFFFFFF0071646B8) |
| **+0xC18** | **0xFFFFFFF0073D868C** | **`bl _set_mmu_ttb` — TTBR0 ← `*_invalid_ttep & mask` (`_invalid_ttep` @0xFFFFFFF0071646A8): the identity mapping is deliberately abolished here** |
| +0xC1C | 0xFFFFFFF0073D8690 | `tlbi vmalle1is; dsb ish; isb` |

`_pmap_bootstrap` is called at `_arm_vm_init+0xF4C` — **after** the
switch. Execution order along the boot path (all call sites verified by
scan): P1 `_arm_init` entry → P7 `_cpu_data_init` (called at
`_arm_init+0x604`, linear, `x0 = &_percpu_slot_cpu_data`) → P2
`_PE_init_platform` first call (`+0x610`, `w0 = 0`) → timer/misc
configure → P3 `_arm_vm_init` entry (`+0x7CC`) → [set_tcr → TTBR1 swap
→ **SW: TTBR0 swap** → P4 `_pmap_bootstrap`] → `kprintf initialized`
(`+0x800`) → `PE_create_console` (`+0x914`) → P5 (`+0x920`) → P2 #2
(`+0x934`) → `machine_startup` (`+0xA00`) → `_arm_init` returns →
banner → P9 `_PE_init_iokit` → P10 → P8 `_cpu_data_alloc` (IOKit phase
only).

## Analysis 2 — first printf / banner position

- First output-family call on the path: `kernel_debug_string_early(
  "kernel_startup_bootstrap")` at `_arm_init+0x738` — early-debug sink
  only, cannot reach the panel.
- First printf-family call: `kprintf("kprintf initialized\n")` at
  `_arm_init+0x800` (0xFFFFFFF0079A198C), unconditional, **after** P4
  and **before** P5. Its sink is the serial/kprintf path; the FB
  console is created only later (`PE_create_console` at `+0x914`,
  `PE_init_printf` at `+0x91C`) → it cannot appear on the panel.
- The Darwin banner: the version string exists twice in the kernel
  (VA 0xFFFFFFF0070423A5 / 0xFFFFFFF00704240A) with 13 reference sites;
  the banner site is in `_kernel_bootstrap` (0xFFFFFFF0072A8A08): at
  +0x2C it executes `printf("%s\n", version)` as its first substantive
  statement, unconditionally. `_kernel_bootstrap` runs on the boot
  thread **after** the whole `_arm_init` body; it spawns
  `_kernel_bootstrap_thread` (ref at +0x68C), and `_PE_init_iokit`'s
  only caller is that thread (at its +0x28C). **The banner is
  therefore after P1–P5/P7 and before P9/P10 (and P8).**

Consequence for the readout: the task's hypothetical — *if the banner
preceded P7, "no banner ever" would already bound the death* — is
**false** for this kernel: the banner sits at the far end of the
fenced span. "No banner on hardware" bounds the death to before
`_kernel_bootstrap+0x2C` (with `[banner, configure)` surviving only as
the low-probability tail that requires the print to be invisible
despite a live FB console since `_arm_init+0x914`). Row 2 narrows the
span from the other end; the two bounds are consistent for every
readout (see matrix).

## Analysis 3 — identity-alias feasibility per point

The maneuver is valid at a point ⟺ at that point TTBR0 is still the
bootstrap identity root (low VAs walk the identity table) and the TCR
low half is the bootstrap value. TCR is written only in
`common_start` and at `_arm_vm_init+0xAC8` (bit-37-only change, so the
condition survives it); TTBR0 only in `common_start` and at `+0xC18`.

| point | verdict | reason |
|---|---|---|
| P1 `_arm_init` entry | ✅ | single entry (from locore); pre-switch |
| P7 `_cpu_data_init` | ✅ guarded | first call (`_arm_init+0x604`) is pre-switch; second caller `_ml_processor_register` is post-switch (IOKit) → first-call guard required |
| P2 `_PE_init_platform` | ✅ guarded | first call (`_arm_init+0x610`) pre-switch; second `_arm_init` call (+0x934) and `_arm_init_cpu` callers are post-switch → guard |
| P3 `_arm_vm_init` entry | ✅ | single caller; entry precedes the switch inside its own body |
| **SW** the `bl _set_mmu_ttb` site itself | ✅ | paint *before* executing the intercepted call; TTBR0 is still the bootstrap root at that instant |
| P4 `_pmap_bootstrap` | ❌ | called at `+0xF4C`, after `+0xC18`: TTBR0 = invalid root; an alias fetch faults immediately |
| P5 post-`PE_init_printf` | ❌ | after `_arm_vm_init` returns; TTBR0 invalid |
| P6 `_PE_initialize_console` | ❌ moot | zero callers in the whole kernel — never executes |
| P8 `_cpu_data_alloc` | ❌ | only via `ArmCpu::start/finishSecondary → _ml_processor_register` (IOKit phase) |
| P9 `_PE_init_iokit` | ❌ | `kernel_bootstrap_thread` phase |
| P10 `IOPlatformExpertDevice::init` | ❌ | IOKit phase |

The post-switch span `[SW, configure)` is physically unreachable by
this channel; if row 2 ever lights 5/5, further narrowing there needs
the monitor-core route (a permanently-mapped MMIO/debug channel
installed before the switch), noted as future work, not built here.

### Register / state contract (per point, from the disassembly)

- Stubs paint via the existing M3F PROG stubs' tails (P1/P7/P2/P3) or
  by intercepting the `bl` word itself (SW); the PROG stub bodies run
  unchanged on every call.
- Scratch: **x9–x17 only** (all caller-saved at every point). x0–x8
  (live args — at SW, x0 *is* the new TTBR0 value), x19–x30 (x30 = the
  return address at every point; SW's `bl` is re-encoded inside the
  block) and SP are never touched. The maneuver is stack-free.
- `physBase`: `_gPhysBase` (0xFFFFFFF007165100) is written only at
  `_arm_vm_init+0x44` and is 0 before that, so pre-switch stubs load
  `boot_args.physBase` from the fixed args VA **0xFFFFFFF007F14010**
  (`_arm_vm_init`'s prologue proves the layout: `[args+0x8]` virtBase,
  `[args+0x10]` physBase, `[args+0x18]` memSize).
- Interrupts: DAIF is saved, masked (`daifset #0xf`) for the paint,
  and restored — defensively: in fact DAIF is still fully masked at
  all five points (masked in `_start_first_cpu`; `_arm_init` has no
  `msr` at all; the timer is not configured before P2#1).
- MMU toggle: only SCTLR bit 0 is cleared/restored, the saved value
  restored verbatim — the exact form hardware-proven by the M3L
  L3b/L4 marks.
- Guards: one flag word per guarded point in the free args-page gap at
  `args+0x868+8·idx` (P7 idx 1 → VA 0xFFFFFFF007F14870; P2 idx 2 →
  0xFFFFFFF007F14878). DarwinBoot zeroes the window (hence the args
  page) on every boot, so flags start clear; the first executed call
  paints, post-switch re-entries skip the paint (the PROG write of the
  underlying stub still runs, unchanged).

## The patch

Five FB2 blocks in the remaining NOP cave (0xFFFFFFF0073DCBE8–
0xFFFFFFF0073DCF10; 202 of the 262 free words; cave ends
0xFFFFFFF0073DD000). Each block: [guard] + 12-word prologue (physBase
load, alias compute, continuation VA, `br` alias) + 24-word paint
section + continuation (1 word `b` back to `entry+4`; SW: re-encoded
`bl _set_mmu_ttb` + `b _arm_vm_init+0xC1C`). Five hook words replaced:
the four M3F stub tails (P1 @0xFFFFFFF0073DC7C4 `14171273`, P7
@0xFFFFFFF0073DC914 `17ffdbee`, P2 @0xFFFFFFF0073DC7FC `1415801e`, P3
@0xFFFFFFF0073DC834 `17ffec91`) and the SW call word @0xFFFFFFF0073D868C
`94003740`. All encodings produced by llvm-mc-18 and disassembly-
verified on the patched binary (prologue constants, guard targets,
paint PAs/colors, loop closure, SW `bl` target = `_set_mmu_ttb`).

### Row-2 geometry and colors

Row 2 sits directly above row 1: y ∈ [3000, 3060), blocks 240×60 px at
x = idx·260, stride 5760 B — computed by the generator from the panel
parameters (row 1 starts 0x9D0CF200 at y=3060; row 2 idx0 =
0x9D07AC00). No overlap with row 1 or with any menu element (menu
elements live in the upper screen area; row 1 already occupies the
bottom band).

| idx | point | FB PA | color |
|---|---|---|---|
| 0 | P1 `_arm_init` entry | 0x9D07AC00 | white `0xFFFFFFFF` |
| 1 | P7 `_cpu_data_init` (1st call) | 0x9D07B010 | orange `0xFFFF8000` |
| 2 | P2 `_PE_init_platform` (1st call) | 0x9D07B420 | violet `0xFF8000FF` |
| 3 | P3 `_arm_vm_init` entry | 0x9D07B830 | silver `0xFFC0C0C0` |
| 4 | SW TTBR0 switch point | 0x9D07BC40 | dark green `0xFF008000` |

All five differ from the row-1 colors (red/blue/magenta/cyan/yellow)
and from the DarwinBoot green bar (0xFF00FF00).

### Diff ledger

- M3L → M3N: **207 words** (5 hook words + 202 block words), exact-set
  asserted by the generator; all original words re-verified.
- pristine → M3N: **552 words** (349 + 202 + 1 new SW site; the four
  stub-tail hooks rewrite already-counted words).
- M3N kernel: size 14,917,208 B (unchanged), MD5
  `6349ba730b91ff89412112b3fbd91f63`.
- Image: M3M firmware bytes verbatim; whole-image diff vs M3M confined
  to the KERNEL clusters plus the recomputed v0 header id (method
  validated against the M3M image itself before use).

## Hardware readout matrix (row 2, left → right = execution order)

Blocks light strictly in order (single CPU, each paint unconditional
at its point). "k lit, k+1 dark" brackets the death between milestone
k and milestone k+1:

| lit | bracket for the death |
|---|---|
| 0 | inside the hand-off tail / `_arm_init`'s first instructions, before P1's paint — or the row-2 mechanism itself is broken (distinguish on the host rig) |
| 1 (white) | `_arm_init` opening segment (kc header fixups, memmove) before `_cpu_data_init` |
| 2 (+orange) | inside `_cpu_data_init`'s first call, or the 3-instruction gap to P2 |
| 3 (+violet) | inside `_PE_init_platform`'s first call subtree (platform-expert early init) |
| 4 (+silver) | inside `_arm_vm_init`'s table-building phase, before the TTBR switch |
| 5 (+dark green) | the switch was **reached**; death is at/after `set_mmu_ttb` execution — the post-switch span: `_pmap_bootstrap`, `_arm_vm_init` tail, `_arm_init` late body (kprintf-init, console creation, P5, P2#2, `machine_startup`), or the `_arm_init → _kernel_bootstrap` transition |

Cross-check with the banner bound: outcomes 0–4 lie strictly inside
`[_arm_init, _kernel_bootstrap)` and are fully consistent with "no
banner ever". Outcome 5's bracket extends to the banner; if a photo
ever shows 5/5 **and** banner text, the fence collapses to
`[banner, configure)` at once; 5/5 without banner text means the death
is in `[SW, banner)` or the print path itself failed.
