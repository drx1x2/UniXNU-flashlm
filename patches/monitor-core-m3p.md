# M3P — monitor-core launch single test (DIAGNOSTIC ONLY)

Firmware-side gate experiment for the monitor-core route. Baseline
firmware: M3M (== M3N firmware byte-for-byte). Kernel: M3N, unchanged
(volume KERNEL MD5 `6349ba730b91ff89412112b3fbd91f63`). Patch archive:
`darwinboot-cpuon-monitor.patch` (+95/−0 lines vs the M3M DarwinBoot.c,
two hunks: helpers + blob array after `M3KWatchdogArm`, one call block
immediately after the `M3KWatchdogArm ();` call site).

## Question under test

Does this device's EL3 accept a PSCI `CPU_ON` with a caller-chosen
entry point? Everything in M3Q (a monitor core polling the PROG
mailbox and painting row 3) depends on that single gate; M3P tests it
in isolation, with the kernel's behavior as mere background (the M3N
kernel freezes as usual and the watchdog cycles the device, so the
readout screen recurs every cycle).

## Design

- **Blob** (`m3p/monitor.S`, assembler-produced, 112 B): position-
  independent; entered with MMU/caches off (the PSCI wake state). It
  paints the row-3 first block — x [0,240), y [2940,3000) of the
  1440x3120 32bpp framebuffer — alternating `0xFFFF4000` (orange-red)
  and `0xFF000080` (navy) with a loop-count delay of 0x20000000
  iterations per color (roughly 0.4–0.6 s at Kryo 485 clocks; a busy
  loop, approximate by design). It writes nothing but the FB block,
  uses no stack, and never returns. Block PA recomputed from the
  row-1/row-2 generator parameters: 0x9C000000 + 2940*5760 =
  **0x9D025400** (row 1 y=3060 -> 0x9D0CF200 and row 2 y=3000 ->
  0x9D07AC00 cross-check against the M3L/M3N specs).
- **Residence**: slot page **0x89B00400**. Page user map: +0x00 x0
  (BootShim), +0x08/+0x10 earliest copies (BootShim/DarwinBoot),
  +0x100 SLT probe (DarwinBoot). Whole-tree grep: no other user of
  +0x400. DarwinBoot CopyMem's the blob there and cleans the range
  with `dc cvac` + `dsb sy` + `isb` before the CPU_ON (the woken core
  fetches with caches off).
- **Launch**: PSCI `CPU_ON`, 64-bit function ID **0xC4000003**;
  x1 = target MPIDR **0x700** (CPU7: flashlm ADT /cpus reg list
  `cpu_regs` in devices.py, confirmed from the live FDT; the LOS
  sm8150 DTS carries the matching cpu@700 node); x2 = entry PA
  0x89B00400; x3 = context_id 0. The SMC result is drawn with
  `CPUON %lx` at DiagDraw row 11, and Boot() proceeds to
  ExitBootServices regardless of the result.
- **Placement**: the launch is the last step before the EBS loop,
  *after* `M3KWatchdogArm ()` — if the SMC itself never returned, the
  armed watchdog would still bite ~29 s later and recover the device.
  All other firmware behavior (readbacks, probes, watchdog arm/disarm,
  BootShim) is untouched.

## Built-binary evidence

- DarwinBoot.efi (21,504 B, MD5 `a681a9537eff6558a4ed2db23d07b862`):
  blob byte-identical at file offset 16800; `CPUON %lx` exactly once;
  all retained format strings once; PSCI/CPY strings zero.
- SMC site disassembly (VA 0x2850): `dc cvac` clean loop over the
  copied range -> `dsb sy` -> `isb` -> `mov w0,#0x3` /
  `movk w0,#0xc400,lsl #16` (x0 = 0xC4000003), `mov w1,#0x700`,
  `mov w2,#0x400` / `movk w2,#0x89b0,lsl #16` (x2 = 0x89B00400),
  `mov x3,xzr`, `smc #0`, result taken from x0.
- FVMAIN.Fv: blob at offset 4894956; `CPUON %lx` once; Sheng count 0.
- stuart build: one Success (`logs/build-m3p-cpuon.log`).

## Image

`builds/lg-flash-unixnu-m3p-cpuon.img` (28,356,608 B): ramdisk slice
byte-identical to the M3N image's; whole-image diff vs M3N confined
to the firmware/header region; volume KERNEL/ADT/toml MD5s unchanged
(`6349ba73…` / `8766bcb3…` / `08ec0480…`).

## Hardware readout (gate criteria)

After flash + slot B + reboot, on the frozen hand-off frame (and on
every watchdog cycle thereafter):

- **Row-3 first block blinking orange-red/navy** -> CPU_ON accepted,
  the core runs, PA painting works: the whole M3Q route is open.
- **`CPUON` line shows a negative value** (long hex, sign-extended
  PSCI error: …FF = NOT_SUPPORTED −1, …FE = INVALID_PARAMETERS −2,
  …FD = DENIED −3, …FC = ALREADY_ON −4, …F7 = INVALID_ADDRESS −9) and
  no blinking block -> EL3 refused the launch; record the exact code.
- **`CPUON 0` but no blinking block** (absent or static) -> the core
  was released but did not run/paint as designed; separate diagnosis
  (entry state / FB address), not an EL3 refusal.
- **No `CPUON` line at all** while watchdog cycles continue -> the
  SMC itself never returned (the armed dog is doing the cycling).

## M3Q hand-off points

If the gate opens: the same launch path carries the real monitor
(same resident page or a larger carve-out — the blob will outgrow
112 B: add PROG-mailbox polling of args +0x848 with `dc cvac`
coherency on the kernel side, ID->block painting for P4/P5/P9/P10
and finer points inside [SW, banner), and a guard so the kernel's
own SMP bring-up cannot collide — CPU7 is the last core the kernel
starts; the monitor must tolerate being joined or the boot-args cpu
count must be fenced). M3P's blob, resident offset, MPIDR derivation
and SMC form carry over verbatim.

---

# M3P2 — timer-cadence blob v2 (DIAGNOSTIC ONLY)

## Hardware readout that forced v2

M3P on hardware (2026-10-31): `CPUON 0` — EL3 accepted the launch —
and the row-3 block was present in color A, **but static: Yun
confirmed it does not blink**. Two live explanations:

- **(a) delay mis-scale**: the core is alive, but v1's loop-count
  delay (0x20000000 iterations, calibrated by guessing Kryo 485
  clocks) runs far slower on the freshly woken core (low power-up
  clock / no boost), so a single delay outlasts the ~29 s watchdog
  window and the color toggle is never observed.
- **(b) parked after first paint**: the core took an exception (or
  otherwise stopped) right after the first fill and never loops.

v2 changes **only the blob** (DarwinBoot.c vs M3P: the byte array and
its length figure in the comment; the launch block, SMC form, MPIDR,
call-site placement and all other firmware behavior are byte-
identical). Kernel and payload volume: M3N, unchanged.

## Erratum — the v1 block address was off (affects M3P readout only)

The v1 section above states the block PA as
"0x9C000000 + 2940*5760 = 0x9D025400". That equality is wrong:
2940*5760 = 16,934,400 = 0x1026600, so the true row-3 idx0 PA is
**0x9D026600**. v1's hand-computed 0x9D025400 (offset 16,929,792)
actually painted at **(x=288 px, y=2939)** — a clean 240x60 block,
just shifted right 288 px and up ~1 row from the intended idx0 spot.
This retro-explains the M3P photo, where the block appeared above
the *second* column rather than the first. The M3P gate verdict is
unaffected (the paint proved PA painting works); only its position
was off. v2's addresses are script-computed from the generator
geometry and cross-checked against the proven row-1/row-2 anchors
(0x9D0CF200 / 0x9D07AC00, both exact):
idx0 = 0x9C000000 + 2940*5760 + 0*1040 = **0x9D026600**;
idx1 = idx0 + 260*4 = **0x9D026A10**. Note for the readout: the v2
blocks appear one column to the *left* of where the v1 block sat.

## Blob v2 design (`m3p2/monitor2.S`, assembler-produced, 196 B)

Entry order — the discrimination is carried by this order:

1. **Paint idx0 = color A `0xFFFF4000` immediately.**
2. **Paint idx1 = color B `0xFF000080` immediately after**, no delay
   in between: a second completed fill proves the core executes
   continuously past the first paint (the thing (b) denies).
3. **Toggle idx0 A/B on the architectural timer**: read
   `CNTFRQ_EL0` once, half-period = freq/2 ticks (~0.5 s of real
   time at any core clock); each wait snapshots `CNTPCT_EL0` and
   polls (unsigned 64-bit difference) until the half-period has
   elapsed. If CNTFRQ reads 0 (left unprogrammed), the half-period
   falls back to this platform's QTIMER rate, 19.2 MHz / 2 =
   9,600,000 ticks — on this board identical to the CNTFRQ path.
   The first `mrs` sits *after* both paints, so a fault on the timer
   path still leaves the two-block witness on screen.

Architectural basis for the timer reads: a PSCI CPU_ON entry is
never at EL0 (the core enters at the highest implemented non-secure
EL, here EL1 or EL2). `CNTFRQ_EL0` is readable from EL1 and above;
`CNTPCT_EL0` is readable from EL1 and above unconditionally (EL0
access is the CNTKCTL_EL1-gated case). No stack, no writes outside
the two FB blocks, never returns — same constraints as v1.
Frequency derivation: ticks are architectural-time, not core
cycles; the SM8150 generic timer runs at 19.2 MHz (board QTIMER
fact), so freq/2 = 9,600,000 ticks ≈ 0.5 s regardless of the woken
core's clock state — precisely the variable that made v1's
loop-count cadence unreliable.

## Built-binary evidence (v2)

- Blob: 196 B, MD5 `2b7e7c9863aca7ff4e4d73adbc53b28a`; objdump
  confirms fill(idx0,A) -> fill(idx1,B) -> first `mrs` (CNTFRQ word
  `d53be013` at blob +0x34), CNTPCT words `d53be035`/`d53be036`,
  unsigned `b.lo` wait loop, fallback constant 0x927C00.
- DarwinBoot.c vs M3P: diff audited — 10 old / 17 new lines, all of
  them blob-array bytes or the "112-byte" -> "196-byte" figure.
  Patched source MD5 `58484572ef4ee2a753b02c8b3b12074f`.
- DarwinBoot.efi (21,504 B, MD5 `06e1b0a559593b9341f6f322499cf9de`):
  blob v2 byte-identical at offset 16800 (same slot as v1), count 1;
  `CPUON %lx` exactly once. SMC site (DEBUG dll): `dc cvac` clean
  loop -> `dsb sy` -> `mov w0,#0x3` / `movk w0,#0xc400,lsl #16`
  (x0 = 0xC4000003, split by the `isb` this build) -> `mov w1,#0x700`
  -> `mov w2,#0x400` / `movk w2,#0x89b0,lsl #16` (x2 = 0x89B00400)
  -> `mov x3,xzr` -> `smc #0` at VA 0x2850.
- FVMAIN.Fv: blob v2 count 1, `CPUON %lx` count 1, Sheng count 0.
- stuart build: one Success (`logs/build-m3p2-timer.log`).

## Image (v2)

`builds/lg-flash-unixnu-m3p2-timer.img` (28,356,608 B): ramdisk
slice byte-identical to the M3N image's (independently re-verified
on the final file); volume KERNEL/ADT/toml MD5s unchanged
(`6349ba73…` / `8766bcb3…` / `08ec0480…`); whole-image diff vs M3N
confined to the firmware/header region.

## Hardware readout (v2 discrimination)

On the frozen hand-off frame, look at **row 3** (the band directly
above row 2; the v2 blocks sit at the true idx0/idx1 columns, one
column left of where the v1 block appeared):

- **idx1 navy block present AND idx0 blinking ~0.5 s** -> the core
  is fully alive; explanation (a) confirmed (v1 was a delay
  mis-scale). The architectural-timer monitor is sound; the M3Q
  route is open with this cadence mechanism.
- **idx0 and idx1 both present but both static** -> the core
  executed both paints and then stopped in/at the timer-wait
  segment: (b)-class, localised to the `mrs` path — next diagnosis
  targets the timer registers / entry EL.
- **Only idx0 present (no idx1)** -> the core died between the
  first and second paint: (b), localised to the first fill's return
  path.
- (Unchanged from M3P: a negative `CPUON` value or a missing
  `CPUON` line re-opens the EL3/SMC questions instead.)

---

# M3Q — monitor blob v3: PROG-mailbox polling (DIAGNOSTIC ONLY)

## Hardware premises (proven, not re-tested)

M3P: `CPUON 0` — EL3 accepts the CPU_ON launch with a caller-chosen
entry. M3P2: row-3 idx1 navy present and idx0 blinking ~0.5 s — the
woken core executes continuously on the architectural-timer cadence
and paints the FB by PA; v1's static block was a loop-count delay
mis-scale (explanation (a)), closed. The M3N kernel still carries
all M3F PROG-slot write stubs P1–P10 (step-0 double proof in the
M3P round: ledger + byte-level), so v3 needs **zero kernel change**:
the firmware baseline is the M3P2 image and only the blob changes.

## Blob v3 design (`m3q/monitor3.S`, assembler-produced, 700 B)

Same resident page and launch path as v1/v2 (0x89B00400, DarwinBoot
copies + `dc cvac` + SMC `CPU_ON` 0xC4000003, MPIDR 0x700, result at
DiagDraw row 11, launch after the watchdog arming). The 700 B blob
ends at 0x89B006BC; the slot page's user map (+0x00 x0, +0x08/+0x10
earliest copies, +0x100 SLT, +0x400 blob) leaves the rest of the
4 KiB page unused (whole-tree grep: no other user at +0x400 or
above), so 2,372 B of headroom remain.

Main loop (all cadence from CNTFRQ_EL0 read once at entry, with the
v2 fallback to 19.2 MHz if CNTFRQ reads 0):

1. **Entry**: paint idx0 = heartbeat color A `0xFFFF4000`; paint
   idx1 = **black** `0xFF000000` ("no milestone yet").
2. **Poll every ~50 ms** (freq/20 ticks, relative wait in the v2
   form): `dc civac` the mailbox's 64B line (0xC1F14840) + `dsb sy`,
   then read the record at PA **0xC1F14848** (window landing
   0xC1004000 + 0xF10000 + 0x848; the args-page PROG slot). If
   [0] != magic `0x474F5250`, or [1] equals the last ID painted,
   keep the current idx1. On a **new ID**, repaint idx1 with that
   ID's color (table below) and remember it. The hit count [2] is
   not displayed.
3. **Heartbeat every ~0.5 s** (freq/2 ticks, absolute deadline):
   toggle idx0 between A `0xFFFF4000` and `0xFF000080` — the
   liveness witness separating "monitor dead" from "kernel dead".
   An **unknown ID** paints idx1 white and switches the heartbeat
   to ~0.15 s fast-blink (freq*3/20) until a known ID replaces it;
   any known ID restores the ~0.5 s cadence.

Color table — same milestone, same color as rows 1/2 where they
overlap; P4 onward are new (the post-switch points only this
channel can reach):

| ID | milestone | color |
|---|---|---|
| 0x11 | L0 `__start` | red `0xFFFF0000` |
| 0x12 | L1 `_start_first_cpu` | blue `0xFF0000FF` |
| 0x13 | L2 first_cpu tail | magenta `0xFFFF00FF` |
| 0x14 | L3b common_start (MMU on) | cyan `0xFF00FFFF` |
| 0x15 | L4 common_start exit | yellow `0xFFFFFF00` |
| 1 | P1 `_arm_init` | white `0xFFFFFFFF` |
| 7 | P7 `_cpu_data_init` | orange `0xFFFF8000` |
| 2 | P2 `_PE_init_platform` | violet `0xFF8000FF` |
| 3 | P3 `_arm_vm_init` | silver `0xFFC0C0C0` |
| 4 | P4 `_pmap_bootstrap` | gold `0xFFFFD700` |
| 5 | P5 post-`PE_init_printf` return | pink `0xFFFF69B4` |
| 6 | P6 `_PE_initialize_console` | gray `0xFF808080` |
| 8 | P8 `_cpu_data_alloc` | brown `0xFFA52A2A` |
| 9 | P9 `_PE_init_iokit` | green `0xFF00FF00` |
| 10 | P10 `IOPlatformExpertDevice::init` | sky `0xFF87CEEB` |
| other | unknown | white + ~0.15 s fast heartbeat |

Constraints (disassembly-verified on the built blob): the only
store instruction in the blob is the fill loop's `str w10`; the
only other outward operation is the mailbox line's `dc civac`; no
`sp` reference anywhere (no stack); no return except the fill
helper's. Register contract: permanents live in x9/x15/x17/x19–x28,
the fill helper's scratch is x11–x14, so no live value crosses a
fill call in a clobbered register.

Disassembly spot-checks (llvm-objdump on the assembled object):
constants x9 = 0x9D026600, x17 = 0x9D026A10, x19 = 0xC1F14848;
`sub x10, x19, #8` -> `dc civac, x10` (word `d50b7e2a`) -> `dsb sy`
-> `ldr x10, [x19]`; magic assembled as 0x5250 | 0x474F<<16 =
0x474F5250; compare chain immediates in execution order
0x11,0x12,0x13,0x14,0x15,1,7,2,3,4,5,6,8,9,10; all fifteen color
stubs load the table value and clear the fast flag; the unknown-ID
fallthrough sets the fast flag and loads 0xFFFFFFFF; poll wait
compares against freq/20, heartbeat scheduling selects freq/2 or
freq*3/20 by the fast flag. Blob MD5 `a2504ead1cf0e3a655c155148fa07c1e`.

## Firmware delta and identity

- DarwinBoot.c vs M3P2: **only the blob byte array (196 -> 700 B)
  and its length figure** in the M3P comment — patch-script diff
  audit: 13 old / 55 new lines, every one an array byte line or the
  length figure. Patched source MD5 `6b84c2dd037c88b50f8fa57223c0cf52`.
  CPU_ON call site, SMC form, watchdog, readbacks: byte-identical
  to M3P2. (The DarwinBoot launch helper cleans `sizeof(blob)`
  bytes at the resident address, so the longer blob needs no
  firmware-side size change.)
- stuart build: one Success (`logs/build-m3q-monitor.log`).
  DarwinBoot.efi (22,016 B): blob v3 byte-identical at offset
  16800 (the same slot as v1/v2), count 1; `CPUON %lx` count 1.
  FVMAIN.Fv: blob count 1, `CPUON %lx` count 1, Sheng count 0.
- Image `builds/lg-flash-unixnu-m3q-monitor.img` (**28,360,704 B**
  — one page larger than the M3N/M3P2 images: the +504 B array
  pushed the packed FV across a 4 KiB boundary, so the bootpayload
  occupies one more page and the ramdisk starts at 3,194,880
  instead of 3,190,784; the boot partition is 96 MiB, so this is
  immaterial). MD5 `812253b4022ee12d2bb2c13e25e50bfe`,
  SHA-256 `f42e34374428254c9780afe6846b4700bbc05bb7bf84ee046bc82a612c26289b`
  (measured on the final disk file; two independent assembly runs
  produced byte-identical output). Identity: ramdisk slice
  byte-identical to the M3N image's; volume KERNEL/ADT/toml MD5s
  unchanged (`6349ba73…` / `8766bcb3…` / `08ec0480…`); BootShim
  prefix and slot words verified in the new bootpayload.

## Hardware readout

Flash + slot B + reboot; after the hand-off freeze, read **row 3**:

- **idx0 blinking ~0.5 s** = the monitor is alive and polling.
  idx0 frozen (either color) or absent = the monitor itself died;
  fall back to rows 1/2 (which are independent of the monitor).
- **idx1's frozen color = the last milestone the kernel reached**
  (the monitor tracks the latest ID within ~50 ms and the frozen
  frame keeps the final repaint). Bracket by the table: gold (P4)
  = death inside `_pmap_bootstrap` or between it and the next
  writing milestone; pink (P5) = past the console-printf return,
  before P8's phase; green (P9) = `_PE_init_iokit` entered, death
  before P10; sky (P10) = the platform-expert `init` was entered —
  the QEMU death neighborhood, now observable on hardware; black =
  no stub ever wrote the mailbox, which would contradict rows 1/2
  (locore stubs write it from L0 on) — if rows 1/2 are lit while
  idx1 stays black, suspect the mailbox path (landing/coherency),
  not the kernel.
- **idx1 white with a fast (~0.15 s) heartbeat** = an unknown ID
  value was written (white with the normal ~0.5 s heartbeat is the
  legitimate P1 color — the cadence is the discriminator).
- Rows 1/2 remain the independent evidence for locore and the
  pre-switch span; row 3 extends the same color language past the
  TTBR0 switch for the first time.

## v3.1 ablation (M3Q2)

M3Q hardware readout: row-3 idx0 frozen in heartbeat color A (the
heartbeat never toggled even once) and idx1 black (the mailbox was
never serviced). Blob v3 painted its two entry blocks and then
died or hung inside the FIRST main-loop iteration, in one of the
mechanisms v3 added over the hardware-proven v2 loop: (1) the
mailbox line's `dc civac` + `dsb sy` -- the only new instruction
class; (2) the absolute-deadline heartbeat arithmetic/scheduling.
The kernel is not implicated (byte-identical to M3N). M3Q2 is a
two-point ablation of v3; everything else is v3 verbatim:

1. **Cache maintenance removed.** The service block's
   `sub x10, x19, #8` / `dc civac, x10` / `dsb sy` is deleted; the
   loop reads the mailbox directly by PA (`ldr x10, [x19]` is the
   first service instruction). The blob now contains NO `dc`
   instruction at all. If the kernel's dirty lines never reached
   DRAM, idx1 stays black this round -- an expected verdict, not
   a build error.
2. **Heartbeat moved to the loop top.** Each iteration FIRST
   compares CNTPCT against the absolute deadline and (when due)
   toggles idx0 and schedules the next deadline, and only then
   runs the poll wait and the mailbox service. "The loop is
   turning" and "the mailbox service is fatal" become separable
   on screen.

Source `m3q2/monitor31.S` -> blob **688 B** (12 B shorter than v3),
MD5 `4d3b81639a27f069a10c8599aab08c8e`, resident
0x89B00400-0x89B006B0 (slot-page spare 2,384 B). Verification
(llvm-objdump on the assembled object; the build pipeline first
reproduced monitor3.bin from monitor3.S byte-identically): the
`dc civac` word `d50b7e2a` count is 0, dc-family words 0, `dsb sy`
0; the loop order in the disassembly is heartbeat check (offset
0x74) -> poll wait (0xCC) -> direct mailbox read (0xE0); the
compare-chain immediates run 0x11,0x12,0x13,0x14,0x15,1,7,2,3,4,5,
6,8,9,10 exactly as v3; a normalized instruction-stream diff vs
v3 shows only the two ablations plus branch-displacement
re-encoding from the size change and the block relocation.

Firmware delta: DarwinBoot.c vs M3Q -- **only the blob byte array
(700 -> 688 B) and its length figure** (patch-script diff audit:
48 old / 47 new lines, all array bytes or the figure). Patched
source MD5 `24e790dea33e3b59f3c0f0bb1a423b2c`. stuart one Success
(`logs/build-m3q2-ablate.log`). DarwinBoot.efi (22,016 B): blob
v3.1 byte-identical at offset 16800 (same slot as v1/v2/v3), count
1; `CPUON %lx` (UTF-16) count 1. FVMAIN.Fv: blob 1, CPUON 1,
Sheng 0.

Image `builds/lg-flash-unixnu-m3q2-ablate.img` (**28,356,608 B**
-- the bootpayload fell back one page vs M3Q, so the ramdisk
starts at 3,190,784 again, as in M3N). MD5
`a50196e260fe9220ec3502e92ea868d0`, SHA-256
`43324013897f18a83c84312d5b9b23a7a365d7b74903556f2e5d9685708e3975`
(measured on the final disk file; two independent assembly runs
produced byte-identical output). Identity: ramdisk slice
byte-identical to the M3N image's; volume KERNEL/ADT/toml MD5s
unchanged (`6349ba73...` / `8766bcb3...` / `08ec0480...`);
BootShim prefix and slot words verified in the new bootpayload.

## Hardware readout (M3Q2)

Flash + slot B + reboot; after the hand-off freeze, read row 3:

- **idx0 blinking ~0.5 s AND idx1 colored** = `dc civac` was the
  killer AND direct PA reads are coherent. Read the death bracket
  straight off idx1's color (the v3 table above).
- **idx0 blinking AND idx1 black** = the monitor is healthy; the
  mailbox's dirty lines never reached DRAM. Next step: kernel
  stubs clean their own line (`dc cvac` stub-side) after writing
  the PROG slot.
- **idx0 still frozen in A** = the hang is in the loop arithmetic
  itself (the civac is gone, so it cannot be the cause): the poll
  wait or the loop control flow. Fall back to the host-side audit
  of v3's wait/deadline logic (see the M3Q2 build report) and an
  instruction-level host simulation of one loop iteration.

## v3.2 fix (M3Q3)

M3Q2's hardware readout was identical to M3Q's (idx0 frozen in A,
idx1 black) -- the ablation changed nothing, which acquitted the
`dc civac`: the fault sat upstream of both variants. Host-side
instruction-level simulation (m3q2/sim/, Unicorn; blob mapped
verbatim at 0x89B00400, architectural timer supplied by a code
hook) pinned it: the mailbox pointer chain in monitor3.S and
monitor31.S,

    movz x19, #0x4848 ; movk x19, #0xf148, lsl #16 ;
    movk x19, #0x00c1, lsl #32

evaluates to 0xC1F1484848, not 0xC1F14848 -- the hex string
"C1F14848" was split 4848 | F148 | 00C1 instead of 4848 | C1F1.
The first mailbox read (v3.1 blob offset 0xE0) hit a
physical-address hole, took a data abort, and the woken core
parked silently (no usable exception vectors), before the first
0.5 s heartbeat deadline -- the exact M3Q/M3Q2 symptom. v3's
civac operated on x19-8, the same wrong address: a scapegoat,
not the cause. Every other mechanism (poll wait, heartbeat
deadlines, magic/ID compare chain, color table) was proven alive
in the same simulation.

The fix is exactly two words against v3.1, with both v3.1
ablations retained (direct PA mailbox reads; heartbeat check at
the loop top):

    movz    x19, #0x4848
    movk    x19, #0xc1f1, lsl #16       // x19 = 0xC1F14848

(the third movk is deleted). Source `m3q3/monitor32.S` -> blob
**684 B**, MD5 `374862c2ab95dc20b0aa75b5a28b78d9`, resident
0x89B00400-0x89B006AC (slot-page spare 2,388 B).

**New hard gate (from this build on):** `m3q3/check_mov_chains.py`
numerically evaluates EVERY movz/movk/movn immediate chain in the
shipped blob from the raw encodings (the eval_mov_chain prototype
in m3q2/sim/sim_monitor.py, generalized) and asserts: (a) the
pinned chains x9 = 0x9D026600, x17 = 0x9D026A10, x19 = 0xC1F14848;
(b) the (width, register, value) chain sequence equals v3.1's
except exactly one element -- x19, 0xC1F1484848 -> 0xC1F14848;
(c) the bug value appears as no chain's value; (d) all 25
source-declared constants match the binary in order. Result: 50
chains, ALL GATES PASSED. The branch machine check
(`m3q3/check_branches.py`, the check_branches.py method rerun on
the new binary): linear decode 684/684 with no data region, all
branch targets in-blob / aligned / on instruction boundaries,
dc-family count 0, the blob embedded in DarwinBoot-m3q3.c
byte-identical to monitor32.bin. A normalized instruction-stream
diff vs v3.1 (branch targets masked) is identical except the one
movk immediate and the deleted word. The shipped 684-byte blob
itself -- not the sim scratch copy -- was then run through the
Unicorn harness (m3q3/sim_product.log): 53 empty-mailbox services
with the heartbeat toggling, inject ID=4 -> idx1 gold 0xFFFFD700,
inject ID=9 -> idx1 green 0xFF00FF00, repeat services deduped,
no fault in any phase.

Firmware delta: DarwinBoot.c vs M3Q2 -- **only the blob byte
array (688 -> 684 B) and its length figure** (patch-script diff
audit: 57 old / 56 new lines, all array bytes or the figure).
Patched source MD5 `b01a91b222b4b7cacde512d2be094a74`. stuart one
Success (`logs/build-m3q3-fix.log`). DarwinBoot.efi (22,016 B,
MD5 `7ba50d49f857e00a82352f959d14e287`): blob v3.2 byte-identical
at offset 16800, count 1; `CPUON %lx` (UTF-16) count 1.
FVMAIN.Fv: blob 1 (offset 4894956), CPUON 1, Sheng 0.

Image `builds/lg-flash-unixnu-m3q3-fix.img` (**28,356,608 B**;
bootpayload 3,186,458 B, ramdisk starts 3,190,784 as in
M3N/M3Q2). MD5 `12509da7dadb654c7e170ac25c6a0dcd`, SHA-256
`d5ef32f79f022659b5ebb9dc61738332b703c395ed1fccbc0311c96a51aef7c0`
(measured on the final disk file). Identity: ramdisk slice
byte-identical to the M3N image's; volume KERNEL/ADT/toml MD5s
unchanged (`6349ba73...` / `8766bcb3...` / `08ec0480...`);
BootShim prefix and slot words verified in the new bootpayload;
the bootpayload stream differs from M3Q2's (decompressed length
unchanged, 3,145,888 B).

## Hardware readout (M3Q3)

Flash + slot B + reboot; after the hand-off freeze, read row 3:

- **idx0 blinking ~0.5 s AND idx1 colored** = the monitor lives
  and the direct mailbox reads are coherent: idx1's color is the
  last milestone the kernel reached (the v3 table above -- gold
  P4, pink P5, gray P6, brown P8, green P9, sky P10, white P1,
  silver P3, ...). The death is bracketed between that milestone
  and the next one.
- **idx0 blinking AND idx1 black** = the monitor is healthy but
  the kernel's dirty mailbox lines never reached DRAM (the
  v3.1-retained direct reads are not coherent on hardware). Next
  step: kernel stubs clean their own line (`dc cvac` stub-side)
  after writing the PROG slot.
- **idx0 still frozen in A** = contradicts the simulation proof
  on the shipped bytes: stop and re-audit before building
  anything new.

## v3.3 civac restoration (M3R)

M3Q3 hardware readout: idx0 blinking ~0.5 s (the monitor lives),
idx1 **pink = P5** (the post-`PE_init_printf` return point). That
proved the channel end-to-end -- but v3.2's service reads the
mailbox by PA with the monitor's caches off, i.e. it reads DRAM.
The boot CPU's PROG stubs write the record through its write-back
caches, so the newest record can sit dirty in the writer's cache
and reach DRAM only on eviction: **P5 is a lower bound, not
necessarily the endpoint** -- the writes of P2's second call, P9
or P10 may already have happened invisibly. M3R removes that
ambiguity by restoring the poll-time clean, on the corrected
address.

Semantics: `dc civac` (clean and invalidate data cache by VA to
the Point of Coherency) with an inner-shareable VA is broadcast
across the inner-shareable domain -- it forces any dirty copy of
the line, including the boot CPU's, to be cleaned to the PoC and
invalidates the other copies, so the monitor's subsequent reads
return the newest record rather than an eviction-timed snapshot.
`dsb sy` completes the maintenance before the reads. This is the
mechanism v3 had; the M3Q/M3Q2 inquest and the host simulation
proved it innocent (v3 died of the mis-split x19 chain, and its
civac merely operated on the same wrong address). v3.2 kept the
direct-read ablation only because the ablation was still in force
when the address was fixed; M3R retires the ablation half
deliberately, as its own single-variable round. The other v3.1
ablation (heartbeat check at the loop top) is retained.

The ONLY code delta vs v3.2 is three words inserted in the
mailbox service, between the poll wait and the magic read
(disassembly-verified on the assembled blob, offsets relative to
the blob base):

    0xDC  and     x10, x19, #0xffffffffffffffc0   // bic x10, x19, #63
    0xE0  dc      civac, x10                      // word d50b7e2a,
                                                  // as in v3
    0xE4  dsb     sy
    0xE8  ldr     x10, [x19]                      // magic (was 0xDC)

Source `m3r/monitor33.S` -> blob **696 B**, MD5
`faac1813b4e9c933ef221d824cedc975`, resident
0x89B00400-0x89B006B8 (slot-page spare 2,376 B).

Hard gates (all green): the mov-chain gate, extended with a
civac section (`m3r/check_mov_chains.py`) -- 50 chains, sequence
**identical** to v3.2's (zero deltas; the restoration adds no mov
chain), pinned x9/x17/x19 unchanged (x19 = 0xC1F14848), bug value
absent, source cross-check 25/25, and the civac target line
numerically evaluated from the feeder instruction and the x19
chain: 0xC1F14848 & ~63 = **0xC1F14840**. Branch machine check
(`m3r/check_branches.py`): every target in-blob/aligned/on a
boundary; dc inventory exactly 1 (civac); dsb exactly 1.

Shipped-byte simulation regression (`m3r/sim_product.py`, the
M3Q2 Unicorn harness; log `m3r/sim_product.log`): phase 1 (empty
mailbox) 53 services, heartbeat toggling, no fault; ID=4 -> idx1
gold 0xFFFFD700; ID=9 -> green 0xFF00FF00, dedup correct. Unicorn
has no multi-core cache model and executes `dc civac` natively
as a harmless pass-through (proven by a separate no-hook probe:
10 services, fault=None), so no instruction skipping was needed;
the run validates the logic, not the coherency (hardware decides
that).

Firmware delta: DarwinBoot.c vs M3Q3 -- **only the blob byte
array (684 -> 696 B) and its length figure** (patch-script diff
audit: 9 old / 10 new lines, all array bytes or the figure).
Patched source MD5 `7db4dff421683b3ff0864bedd65092cb`. stuart one
Success (`logs/build-m3r-civac.log`). DarwinBoot.efi (22,016 B,
MD5 `685c065f323cf58fe4a07b918cb36e5e`): blob v3.3 byte-identical
at offset 16800, count 1; `CPUON %lx` (UTF-16) count 1.
FVMAIN.Fv: blob 1 (offset 4894956), CPUON 1, Sheng 0. Build note:
this round's packaging landed ~10 s after the main build
(bootpayload.bin mtime 07:58:47 vs DarwinBoot.efi 07:58:37) -- an
immediate content check read the previous round's efi and failed
loudly on the blob count; re-verified green once the artifacts
settled. Content checks must wait for artifact mtimes to settle.

Image `builds/lg-flash-unixnu-m3r-civac.img` (**28,356,608 B**;
bootpayload 3,186,628 B, ramdisk starts 3,190,784 as in M3N).
MD5 `350307b7b17351b0f79b287a7df278e4`, SHA-256
`155775a7aa668bbf4649eb990ffa799ee7b986a744879b5b5721fa824210023c`
(measured on the final disk file, twice independent). Identity:
ramdisk slice byte-identical to the M3N image's; volume
KERNEL/ADT/toml MD5s unchanged (`6349ba73...` / `8766bcb3...` /
`08ec0480...`); BootShim prefix and slot words verified in the
new bootpayload; the bootpayload stream differs from M3Q3's
(decompressed length unchanged, 3,145,888 B). Patch archive
`patches/darwinboot-cpuon-monitor.patch` regenerated as the full
M3M -> M3R diff and replay-verified byte-identical.

## Hardware readout (M3R)

Flash + slot B + reboot; after the hand-off freeze, read row 3:

- **idx1 past pink** (violet = P2 second call entered, green =
  P9, sky = P10) = the M3Q3 read WAS a stale snapshot; the death
  bracket moves to the new color (the v3 table above).
- **idx1 still pink** = under a forced clean every ~50 ms, P5 is
  the exact endpoint: the death is bracketed into the tiny
  interval (P5, next writing stub) -- between the
  post-`PE_init_printf` return point in `_arm_init` and the next
  PROG write (P2's second call site). Next step: host-side close
  reading of that span, not another monitor round.
- **idx0 frozen** = the monitor itself died this time; with the
  address proven, that would implicate the civac's execution
  environment (entry EL/state), not the address -- stop and
  re-audit.

# M3U — monitor blob v3.5: coherent reader (DIAGNOSTIC ONLY)

## Why

M3T's hardware verdict fixed the empirical law of the mailbox
channel: writes made through the TTBR0 identity path always reach
a caches-off DRAM reader; writes made through the kernel's TTBR1
mapping never do, even followed by `dc cvac` / `dc civac` + `dsb
sy` in the writer (signatures: gamma landed, alpha failed, beta
neutral). The surviving hypothesis is that the boot CPU's TTBR1
dirty lines stay inside the cache fabric and are never forced to
DRAM, while the caches-off monitor reads outside the coherency
domain. M3U changes only the reader: the monitor core turns its
own MMU and data cache on and maps the args page Normal WB /
Inner-Shareable, joining the coherency domain so hardware
coherence can snoop the dirty lines. If the hypothesis holds,
every in-service stub (plain store + `dc cvac`, already shipped
since M3S) becomes exactly readable with zero kernel changes.
The kernel in the M3U image is byte-identical to M3T's.

## Firmware delta (DarwinBoot only)

- `M3PLaunchMonitor` first calls `gBS->AllocatePages
  (AllocateAnyPages, EfiLoaderData, 4, &TablePages)`. On failure
  it does NOT launch: `M3UDegradedPaintIdx0Black()` paints the
  row-3 idx0 block black directly in the framebuffer (base and
  row bytes read from the GOP via the forward-declared
  `ReadBootVideo`, block geometry identical to the blob's), the
  result slot receives `0xFFFFFFFFFFFFFFFF`, and the hand-off
  proceeds. The degradation path never blocks the boot.
- On success the table base PA is written to the slot-page cell
  at +0x110 (PA 0x89B00110; audited free: the page's other users
  are +0x00 x0 stash, +0x08/+0x10 BootShim earliest copies,
  +0x100 SLT probe, +0x400 the blob itself). The cell's cache
  line is cleaned (`dc cvac`) next to the blob copy, which is
  cleaned as before, all before the SMC.
- Page count disclosure: the task sketch said 3 pages (L1/L2/L3)
  with T0SZ=16. A 48-bit VA with 4 KiB granule walks FOUR levels
  (L0 root -> L1 -> L2 -> L3), so the build allocates 4 pages;
  the geometry below is the shipped truth.
- Everything else (watchdog arming, CPU_ON target/entry, the
  CPUON row-11 draw, call-site placement) is unchanged from M3T.
  `M3PPsciCpuOn` is carried verbatim.

## Blob v3.5 (`m3u/monitor35.S`, assembler-produced, 1212 B)

Resident at 0x89B00400 as before. Layout: preamble at offsets
0x000-0x0F7, the v3.4 body from offset 0xF8 (VA 0x89B004F8), the
table-page insertion routine `.Ltins` at offset 0x424, the FB
fill loop `.Lfill` at offset 0x490; the blob ends at 0x89B008BC
(1860 B of the slot page spare). No stack is used anywhere.

Preamble (entered with MMU off; plain PA loads/stores only):
read the table-PA cell (0 => fall through to the body with the
MMU off; defensive only, DarwinBoot launches only on success);
zero all 4 pages; store the static entries; call `.Ltins` once
per table page so every table page is itself mapped; `dsb sy`;
load MAIR/TCR/TTBR0; `tlbi vmalle1`; `dsb sy`; `isb`; SCTLR_EL1
read-modify-write (set M|C|I, clear WXN); `isb`; fall into the
body. Identity mapping: every address the body uses keeps its
M3T numeric value.

Body: v3.4 instruction-for-instruction, with exactly one
deletion -- the beta `dc ivac` on the mailbox line (meaningless
and unwanted once the reader is cached). Mailbox and signature
reads are ordinary loads through the cached WB mapping. CNTPCT
heartbeat cadence, idx0-idx3 painting and colors, re-paint on
signature loss, and the ~50 ms poll are unchanged.

### Page-table geometry (base PA = B, from the cell)

- L0 at B+0x0000: L0[0] -> L1 (table descriptor).
- L1 at B+0x1000: L1[3] = 1 GiB block, Normal WB, EL1 RO,
  covering [0xC0000000, 0x100000000) -- the args page
  (0xC1F14000) is read through this block; L1[2] -> L2.
- L2 at B+0x2000: L2[77] -> L3; L2[224..232] = nine 2 MiB blocks,
  Device-nGnRE, RW, covering the framebuffer span
  [0x9C000000, 0x9D200000).
- L3 at B+0x3000: L3[256] = the slot page 0x89B00000 as a 4 KiB
  Normal WB page, RW, executable (the blob executes from it).
- `.Ltins` maps each table page itself: a page inside L1[3]'s
  block or inside the FB span is already covered; a page under
  L1[2]/L2[77] becomes the L3 page entry; any other page gets
  its own 2 MiB (under L1[2]) or 1 GiB WB block at its L2/L1
  index. All dynamic entries are EL1 RO. Entry offsets: L1[3]
  +24, L1[2] +16, L2[77] +616, L2[224] +1792, L3[256] +2048.

Device-nGnRE was chosen for the framebuffer over Normal-NC:
with the MMU off the blob's stores had Device-nGnRnE semantics;
nGnRE is the closest mapped equivalent (no gathering, no
reordering, early acknowledgement), so the painting semantics
the hardware rounds M3P-M3T validated carry over unchanged.

### Constants (script-recomputed from the ARM ARM, pinned by gate)

- MAIR_EL1 = 0x04FF (attr0 Normal WB 0xFF; attr1 Device-nGnRE
  0x04).
- TCR_EL1 = 0x0000000200803510 (T0SZ=16, IRGN0/ORGN0 WB,
  SH0=Inner-Shareable, EPD1 set, IPS 40-bit).
- WB block template 0x00600000000007C1 (AttrIndx0, AP=0b11 RO,
  SH=ISH, AF, PXN+UXN); WB page RO = template|2; args 1 GiB
  block 0x00600000C00007C1; FB block 0x006000009C000445
  (AttrIndx1, AP RW, SH=0); slot-page entry 0x0040000089B00743
  (AP RW, PXN=0, UXN=1).
- SCTLR set-mask 0x1005 (M|C|I), WXN clear-mask 0x80000.

### Read-only guarantee for the args page

The blob must never write the args page or any memory outside
the table pages and the framebuffer window. Machine-checked two
ways: (a) static store inventory of the shipped binary -- 11
store instructions, none based on the mailbox (x19) or
signature (x28) pointers; (b) dynamic write-range assertion in
the Unicorn runs below -- across all phases and all geometry
variants the only written regions were the table region and the
FB window; zero writes into the args page.

## Verification gates (all host-side, all passed)

- `m3u/check_mov_chains35.py`: linear decode 303/303; 67
  movz/movk chains evaluated; body pointer pins and every
  preamble constant pinned equal to the ARM-ARM recomputation;
  the historical bug value 0xC1F1484848 absent; no v3.4
  (register, value) tuple lost multiplicity; source cross-check
  39/39; system-register inventory exact (0 `dc`, 1 `tlbi
  vmalle1`, msr {mair,tcr,ttbr0,sctlr}_el1 once each, mrs sctlr
  once, 2 `dsb sy`, 2 `isb`); the normalized body instruction
  stream equals v3.4 minus beta, instruction-for-instruction.
- `m3u/check_branches35.py`: every branch target inside the
  blob, aligned, on an instruction boundary; the blob embedded
  in DarwinBoot-m3u.c is byte-identical to monitor35.bin.
- `m3u/sim35.py` (Unicorn; system operations are hook-skipped
  passthrough -- the msr/tlbi sequence itself is not modelled,
  but the page tables are really built in emulated RAM by the
  preamble's own stores and then decoded by the checker): the
  exact nonzero-entry set matches for five table-base geometry
  variants (base in the args block, base colliding with the L3
  page's own indices, base covered by L1[3], base in the FB
  span, base needing its own L2 block); body phases 1-5 pass
  (entry paints, SIG service, ID colors, re-paint on loss,
  poll accounting); two poison reruns reproduce identical fill
  sequences.
- Firmware audit (`m3u/patch_darwinboot_m3u.py` +
  `m3u/check_efi_m3u.py`): product tree asserted byte-identical
  to the M3T snapshot first; the whole monitor section replaced
  by construction; difflib audit shows 8 hunks, all inside the
  old monitor section; the built DarwinBoot.efi (23,040 B)
  contains the blob exactly once, `CPUON %lx` once, the cell
  chain 0x89B00110, and an SMC site materializing x0=0xC4000003,
  x1=0x700, x2=0x89B00400; Sheng count 0.
- Image identity: the M3U image's ramdisk slice differs from
  M3T's in exactly 0 bytes (kernel byte-identical by
  construction; volume KERNEL MD5 02a1bdbe15b057bcc507dae3bdf224c7
  and ADT MD5 8766bcb3571f2b70dc03a4295c7ad824 re-verified);
  the whole-image diff vs M3T is 2,293,223 B, all inside the
  header page and the payload region.

## QEMU rig investigation (mechanism NOT decidable in this rig)

The full-stack rig was asked to witness the mechanism (monitor
runs with its MMU on; idx1 shows the rig endpoint ID 0xA in sky,
idx2 green, idx0 toggling, cpu7 PC inside the blob). It cannot:
the rig's TF-A (v2.15.0 debug, SPMC build, in the prebuilt
SECURE_FLASH0.fd) accepts PSCI CPU_ON but never delivers a
secondary core to the normal-world entry point, for ANY blob.
Evidence chain, all with virtualization=on:

- v3.5 runs against MPIDR targets 0x700, 0x100 and 0x7 (the
  rig's FDT encodes affinities in Aff0; cpu@N reg = N) fail
  identically: FB row 3 all zeros, cpu7 PC in secure RAM
  (0x0E089C18..0x0E1016D0, EL3h per `info registers`).
- DarwinBoot-side forensics: the blob copy at 0x89B00400 is
  byte-identical to monitor35.bin and the table-PA cell holds a
  live allocation (0xBD392000), but the four table pages still
  contain stale UEFI data -- the blob's preamble, whose second
  act is zeroing them, never executed.
- A gdb-stub probe (Z1 breakpoints) shows the SMC return site
  hit with x0 = 0 (PSCI_SUCCESS) while the blob-entry
  breakpoint never fires.
- Control: the same rig firmware with the blob array swapped
  for monitor34.bin (v3.4, proven on hardware across M3P-M3T)
  fails identically. The failure is blob-independent.
- The sabotage variant (TCR T0SZ 16->25) formally "passes" its
  FB-all-zeros check in this rig -- vacuously, because nothing
  ever runs. The normal/sabotage pair therefore does NOT
  discriminate the mechanism here and is not evidence either
  way.
- virtualization=off is not a fallback: BL31 reproducibly
  hangs at "Initializing BL32" on an idle host, before BL33
  starts; unrelated to this code.

The mechanism evidence for v3.5 thus rests on the Unicorn gate
above (tables really constructed and decoded, body regression
in full) plus the static gates; the coherency question itself
is decidable only on hardware, which is the flash below. The
rig's DarwinBoot source was restored to its pristine baseline
(md5 f3134097cb0cb9ef9783b2b525ebd2a0) after the investigation.

## Built-binary evidence (v3.5)

- monitor35.bin: 1212 B, MD5 a811303475e5e5b830e4e8ac147bb6ad,
  SHA-256 5a65f6b661678c2e07377f4b63a0152ac0cfb47e5c5de9da11daf9fa0a02f1fe.
- DarwinBoot-m3u.c: MD5 328e8635d2557f74d10ffc084a36f504;
  DarwinBoot.efi 23,040 B, MD5 588193d5f98ccd2cc657672e138e41d8.
- Patch archive `patches/darwinboot-cpuon-monitor.patch`
  regenerated as the full M3M -> M3U diff and replay-verified
  byte-identical (baseline md5 d403bee550a36ebc667cec37bb506ad9,
  recovered by reverse-applying the M3M -> M3T patch and
  forward-verified; generator `m3u/regen_patch.py`).

## Image (v3.5)

`builds/lg-flash-unixnu-m3u-cohread.img`, 28,356,608 B,
MD5 ff9fcf5d01954d17a4a80634f8f14e38,
SHA-256 00f17b45a55c5bdc176995f8e2b4dfc3946c57de14e7a0db5b3baa2c2260c846
(hashes measured from the disk file, twice).

## Hardware readout (M3U)

Flash + slot B + reboot; in the freeze phase read row 3:

- **idx1 shows a later milestone color unrelated to the old
  eviction values** (gold = P4, pink = P5, green = P9, sky =
  P10) = the coherent read WORKS: the channel is fixed and the
  death endpoint is pinned on the spot.
- **idx1 still lemon-yellow L4** = the read-side entry into the
  coherency domain also fails; switch to the write-side plan
  (pre-switch stubs identity-double-write, a separate scheme
  for post-switch stubs).
- idx2 must stay green (the gamma control) and idx0 must keep
  flashing, idx3 black, as before.

# M3U2 — monitor blob v3.5.2: slot-page PXN fix + idx4 stage markers (DIAGNOSTIC ONLY)

## Root cause of the M3U black row (host-side finding, not yet hardware-confirmed)

The v3.5 slot-page L3 entry is `0x0040000089B00743`. Bits [7:6] of
`0x743` are `01`, i.e. **AP[2:1] = 0b01 = read/write at EL1 _and_
EL0** (the M3U text called it "AP RW", but the EL1-only RW encoding
is `00`). In the EL1&0 stage-1 regime the ARM ARM treats any location
that is writable at EL0 as **PXN at EL1 regardless of the descriptor's
PXN bit** (DDI 0487, D8.4.1 "Stage 1 permissions"; the same rule is
why Linux never maps EL0-writable pages as kernel text). The blob
executes from that very page, so the first instruction fetch after
`msr sctlr_el1` + `isb` (VA/PA `0x89B004F8`, the body's first
instruction) takes a Permission-fault instruction abort. VBAR_EL1 on
a freshly CPU_ON'd core is not set up, so the core parks silently,
having painted nothing — exactly M3U's "row 3 all black", i.e. death
cause (a) of HANDOVER §4.5, at the last step of the preamble.

All other v3.5 constants re-check correct: MAIR `0x04FF`, TCR
`0x0000000200803510`, the WB/RO block template, the args 1 GiB block,
the Device FB blocks (`0x445`: AP `00`), the table indices (L1[2],
L1[3], L2[77], L2[224..232], L3[256]).

## Changes (blob)

- **v3.5.2 = the fix:** slot-page entry `0x743` → `0x703`
  (AP[2:1] = 00: EL1 RW, EL0 none; PXN = 0, UXN = 1, AF, ISH, attr0
  unchanged). One immediate in the preamble.
- **Stage markers (v3.5.1 and v3.5.2):** row-3 **idx4** (x 1040–1280,
  y 2940–3000, PA `0x9D027640`) is painted by the existing `.Lfill`
  routine at four points, all symmetric colors so an R/B swap in the
  pixel format cannot change the reading:

  | idx4 | painted after | MMU |
  | --- | --- | --- |
  | white `FFFFFFFF` | entry (S1) | off |
  | magenta `FFFF00FF` | tables built + `dsb sy` (S2) | off |
  | gray `FF808080` | MAIR/TCR/TTBR0 + `tlbi` + `isb` (S3) | off |
  | green `FF00FF00` | SCTLR M\|C\|I + `isb` (S4), via the Device identity map | on |

- The v3.4 body follows unchanged (relative branches only; same
  idx0–idx3 semantics). v3.5.1 is v3.5.2 without the AP fix (control
  build; expected to stop at gray). Blob size 1212 → 1308 B.

## Changes (DarwinBoot, same patch file)

- Allocation-failure path additionally paints idx4 **purple
  `FF800080`**, so "no launch" is distinct from every blob marker.
- Before CPU_ON, the four table pages are `dc civac`'d from the boot
  core. The blob writes them with its MMU off (straight to DRAM) and
  then walks them with cacheable (IRGN/ORGN WB) walks; a stale or dirty
  line of a previous owner in the boot core's caches or the shared L3
  could otherwise be snooped by the walker or written back over the
  tables. The boot core never touches the pages again.

## Verification gates (`tools/m3u/`, all host-side)

- `build.sh`: `monitor35.S` (reconstructed from the shipped bytes)
  reassembles **byte-identically** to the v3.5 blob; v3.5.1/v3.5.2 are
  assembler-produced from it.
- `gate.py` Gate A: the patch's blob array == `monitor352.bin`.
- Gate B (Unicorn, MMU off, three table bases incl. one inside the
  slot page's own 2 MiB): paint order white → magenta → gray, zero
  stores outside the table pages and the FB, zero stores to the args
  page.
- Gate C (stage-1 walk of the tables the blob actually built, with the
  EL0-writable ⇒ PXN rule): **v3.5 and v3.5.1 FAIL at the first fetch
  after SCTLR.M (`implicit PXN: EL0-writable`); v3.5.2 PASSES** — every
  body fetch executable, mailbox/SIG reads Normal-WB, row-3 FB
  Device-RW.
- Not covered: Unicorn 2.1 aborts even a minimal hand-built identity
  map once SCTLR.M=1, so the MMU-on half is checked by Gate C only, and
  CPU_ON still needs the real device (the QEMU rig cannot deliver it).

## Hardware readout (M3U2, flash v3.5.2)

Pre-registered reading of row 3 in the freeze phase:

- **idx4 green + idx0 heartbeat** → the PXN fix is the whole story; the
  cached reader runs. Then read **idx1** as in the M3U readout above
  (a milestone color other than the old eviction values = the coherent
  read works and pins the endpoint; still L4 yellow = the read side
  fails, go to the write side, HANDOVER §5 甲 1).
- **idx4 gray, idx0 black** → still dies at SCTLR/first fetch: next
  suspects are the WB walk attributes (try IRGN0/ORGN0 = NC) and the
  1 GiB args block (shrink to a 2 MiB block).
- idx4 magenta → MAIR/TCR/TTBR0/TLBI step; white → table build;
  **purple** → `AllocatePages` failed (no launch); idx4 untouched →
  CPU_ON never reached the blob (compare row-11 `CPUON` text).


## M3U2 真机结果（2026-11-01）

v3.5.2 一刷：idx4 明绿（S4）、idx0 A 相心跳、idx2 绿、idx3 黑、一二排 10/10 ⇒
隐式 PXN 根因确认，开缓存相干读侧成立。idx1 金色 (252,213,17)，G/R 0.845（同帧 L4
柠檬黄 1.000）⇒ 精确终点 P4（`_pmap_bootstrap`）。死点区间：P4 之后、P5
（`PE_init_printf` 返回）之前。M3Q3 的 P5 读数为淘汰假象。
