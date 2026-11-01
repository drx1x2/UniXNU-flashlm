# M3T — coherence signatures (alpha / beta / gamma; delta CUT)

One flash, four signatures, each with its own readout bit, to
settle the silicon-coherence paradox left by M3S and to validate
a repair path for the PROG mailbox channel.

## The paradox (premises, all proven before this round)

Page-table walk audit (`m3t/M3T-AUDIT.md`, QEMU rig walk of the
shipped M3S components): the boot_args page (PA 0xC1F14000,
window 0xC1004000 + 0xF10000) is mapped by BOTH page-table
regimes with the same attribute bits — bootstrap TTBR0 identity
block `0x...601` and the post-switch TTBR1 L3 page `0x...603`
(differing only in descriptor type bits, granularity, and
PXN/XN); AttrIndx 0 = Normal WB, SH = ISH in both. The mapping
is built by `_arm_vm_init` itself; `_pmap_bootstrap` creates no
VA mappings. Yet on hardware: locore records written by pure
stores under the TTBR0 identity map (PA addressing, caches off)
always reach the monitor core's DRAM reads, while P-stub records
written under TTBR1 — even followed by `dc cvac` + `dsb sy`
(M3S) — present in DRAM only as a stale last-evicted value
(M3Q3's P5 pink and M3R/M3S's L4 yellow were both eviction
lottery outcomes, not endpoints). The remaining explanation
space is silicon coherence semantics; this round discriminates
it experimentally.

## Signature slots (occupancy proof)

SIG_A = args page +0x880 (PA 0xC1F14880), SIG_B = +0x888
(PA 0xC1F14888), two u64 in the boot_args gap. Occupancy of the
gap before this round, every item traced to its writer:
EXC record +0x800..0x847 (M3E black box, DarwinBoot reads it),
PROG record +0x848..0x85F (M3F stubs), PRB probe +0x860..0x867
(M3G, DarwinBoot-written), row-2 first-call guards
+0x868..0x87F (M3N: P7 idx1 -> +0x870, P2 idx2 -> +0x878, one
u64 each; DarwinBoot zeroes the window every boot so guards
start clear). +0x880..0x88F is the first free span after the
guards. A full-tree grep for the offset constants (0x880 /
0x888 / 0x14880) across `patches/*.md`, the product
DarwinBoot.c, all `monitor*.S` and the m3n/m3s kernel
generators returned zero hits before this round. The retired
PSCI probe array at +0x900..0x93F has had no writer since M3M
and is not touched.

## Kernel side (base: shipped M3S kernel, MD5 1c676a4f...)

Only the P1 stub changes. Its M3S tail routine (3 words at VA
0xFFFFFFF0073DCF10) is retired to NOP and a 9-word tail is built
in the cave space the M3S tails left free (VA
0xFFFFFFF0073DCF88; 30 words were free, 9 used, 21 remain):

    dsb sy                  ; the inherited M3S ordering barrier
    dc civac, x16     ALPHA ; clean+invalidate the PROG line
                            ; (x16 still holds the PROG VA)
    dsb sy                  ; alpha fully ordered
    movz/movk x17           ; gamma: identity alias = SIG_A PA
    movz x16, #0x67         ; gamma signature value
    str x16, [x17]          ; gamma: pure store, NO cache op
    sub sp, sp, #0xd0       ; displaced original word (byte-
                            ; identical to M3S)
    b FB2_P1                ; M3N tail target, unchanged

Ordering rationale: alpha sits immediately after the inherited
dsb and before the displaced word, so the clean+invalidate of
the PROG line is fully ordered before any original instruction
resumes. Gamma runs after alpha because alpha needs x16 = PROG
VA; gamma then overwrites x16/x17 freely — the FB2 block that
follows rebuilds every pointer it uses (verified in the M3N
generator: the block is self-sufficient) and the displaced word
touches neither register.

Gamma legality (premise check): P1 is `_arm_init` entry.
`_arm_vm_init` — the only builder of the post-switch tables and
the only caller of `_set_mmu_ttb` / `_set_mmu_ttb_alternate` on
the boot path — runs LATER (called from `_arm_init+0x7CC`); at
P1 the active TTBR0 is still the bootstrap identity root. The
walk audit read the bootstrap tables live: L1 -> L2 block for
the args span is `0x49E00601` (rig PA; identity, bit-identical
template to the fill code in `_start_first_cpu`), i.e. the args
page including +0x880 is identity-mapped at P1, so addressing
it by its PA is a legal VA. Alpha's premise is the same audit's
post-switch entry: WB + ISH, so clean / clean+invalidate to PoC
is the architecturally correct maintenance for that line.

Ledger (asserted by the generator, `m3t/patch_kernel_m3t.py`):
vs M3S kernel exactly 13 words (P1 stub word 13 re-pointed,
3 retired-tail words NOP-restored, 9 new-tail words); vs the
pristine CI kernel 588 words (582 M3S - 3 + 9). Shipped kernel
MD5 `02a1bdbe15b057bcc507dae3bdf224c7`, size unchanged
14,917,208 B. In the shipped bytes the signatures sit at:
alpha `dc civac, x16` = word 0xD50B7E30 at kernel file offset
0x3D8F8C (VA 0xFFFFFFF0073DCF8C); gamma chain words at
0x3D8F94/0x3D8F98 (evaluate to 0xC1F14880 — asserted), value
word `movz x16, #0x67` at 0x3D8F9C, store at 0x3D8FA0.

## Delta — CUT after rig validation (does not ship)

Design (as tasked): in a 15-word P5 tail, load
`*_physmap_base` (global at VA 0xFFFFFFF007165028, populated by
P5 time), add the SIG_B PA, store 0x64 through the resulting
physmap VA, `dc cvac` + `dsb sy`. Admission rule set by the
task: the derivation must validate end-to-end in the QEMU rig
(write by the formula, read back by PA) or delta is cut.

Rig evidence (structural-twin variant kernel, rig args PA
0x49F14000; two runs, two boots): the delta store FAULTED both
times. EXC: ESR 0x96000046 (data abort, translation fault),
ELR 0xFFFFFFF0073DCFD4 — the `str` word of the P5 tail —
FAR = *_physmap_base + 0x49F14888 exactly (boot A:
0xFFFFFFF040E4B000 + 0x49F14888 = 0xFFFFFFF08AD5F888 = FAR;
boot B likewise with its slid base 0xFFFFFFF01532C000 ->
0xFFFFFFF05F240888). PROG stopped at ID 5, CNT 11 (5 locore +
P1/P7/P2/P3/P4/P5); SIG_B stayed 0. The dumped physmap globals
page explains the miss: the region table `_phystokv` consults
has, at that point, region[0] = {pa_base 0x49F1C000, va_base =
slide + 0x49F1C000-ish, size 0x1F0E8000} — the args page PA
(0x49F14888 rig / 0xC1F14888 hw) lies BELOW region[0]'s start,
in the gap between the kernel-image fallback span and the
physmap region, and `*_physmap_base + PA` is not the region
formula for any region covering it. The naive slide derivation
is therefore wrong for this PA at P5; per the admission rule
delta was cut rather than iterated on speculation. The P5 stub
in the shipped kernel is byte-identical to M3S.

(Gamma mechanism, by contrast, validated in the same runs:
SIG_A read back 0x67 by PA at every stop.)

## Monitor side (blob v3.4, 868 B, MD5 6f9a0ccf...)

Base v3.2 (the M3Q3 direct-read build; v3.3's civac retired —
the reader is cache-off, its broadcasts demonstrably do not
reach the writer's caches, and the ablation line is cleaner).
Three deltas, nothing else (source: `m3t/monitor34.S`):

- BETA (negative control): once per mailbox service, before
  the first read, the mailbox line address (x19 - 8) is
  invalidated with `dc ivac` + `dsb sy`. A cache-off core holds
  no lines, so this must be a no-op; if idx1's behaviour
  changes versus the v3.2 rounds, the reader-side model is
  wrong and the round's other readings are suspect. The blob
  contains exactly one `dc` (this ivac) and one `dsb` —
  asserted by the mov-chain gate.
- SIG service (every poll cycle, before the mailbox service):
  SIG_A == 0x67 paints row-3 idx2 green 0xFF00FF00;
  SIG_B == 0x64 would paint idx3 sky 0xFF87CEEB (no writer
  ships — the bit stays black by construction and now serves
  as a second negative control). A slot that loses its value
  is repainted black, so the bits are live, not latched.
  idx2/idx3 are also painted black at entry.
- Address chain x28 = 0xC1F14880 built once at entry
  (movz/movk, two words — the decomposition that the M3Q3 gate
  style proves by evaluation); SIG_B is [x28, #8].

Row-3 geometry (script-computed, cross-checked against rows
1–2 anchors): idx0 0x9D026600, idx1 0x9D026A10, idx2
0x9D026E20, idx3 0x9D027230 (block stride 0x410). Blob resides
at slot page 0x89B00400..0x89B00764; 2,204 B of the page
remain free.

Gates run on the blob: mov-chain evaluation (58 chains; pins
x9/x17/x19/x28; bug value 0xC1F1484848 absent; every value in
the v3.2 set + {0xC1F14880}; no v3.2 chain tuple lost
multiplicity; 32/32 source-declared constants matched in
order); branch machine check (all targets in-blob, aligned,
on instruction boundaries; embedded copy in DarwinBoot.c
byte-identical); Unicorn regression, five phases, all passing
on the measured run (`m3t/sim34.py`): entry paints exact
(idx0 A, idx1/2/3 black); empty-mailbox phase reached its
stop rule at 2M instructions with 33 mailbox services and 33
SIG reads, heartbeat toggling; SIG_A injection paints idx2
green at the geometric PA 0x9D026E20, SIG_B injection paints
idx3 sky at 0x9D027230, SIG_A removal repaints idx2 black
with w29 = 0b10; PROG ID 4 -> gold, ID 9 -> green; 103
services / 103 SIG reads over the full 6M-instruction run,
no fault anywhere; register-poison reruns (0xAAAA... and a
seeded random pattern) reproduce the clean phase-1 fill
sequence exactly. (Two harness bugs of mine were caught and
fixed during this gate — a fill-list slicing error and an
asymmetric poison comparison; the blob bytes never changed,
MD5 6f9a0ccf... throughout.)

Firmware diff discipline: product DarwinBoot.c vs the M3R
snapshot differs only in blob-array lines and the length
comment (135 lines, audited). In the built firmware the blob
sits verbatim once in DarwinBoot.efi (offset 16800) and once
in FVMAIN.Fv (offset 4894956); CPUON string once; Sheng zero;
the SMC call site materializes x0 = 0xC4000003 / x1 = 0x700 /
x2 = 0x89B00400 (disassembly-verified). BootShim not rebuilt
(words verified in the new payload stream).

## Rig regression of the shipped configuration

Rig-twin (no-delta variant, MD5 960dd430...), full-stack run:
PROG = {MAGIC 0x474F5250, ID 0xA, CNT 14} — the whole span,
identical to the M3S baseline; EXC = the known QEMU-only UUID
signature (ESR 0x96000005 / ELR 0xFFFFFFF00786AA40 / FAR 0x28);
SIG_A = 0x67 at every stop. The alpha civac and gamma store in
the P1 tail do not disturb the flow.

The shipped hardware kernel itself, run on the rig for the
record, dies at gamma as predicted by the layout difference:
ELR 0xFFFFFFF0073DCFA0 (the gamma store word), FAR
0xC1F14880, ESR 0x96000045, PROG ID 1 / CNT 6 — the rig's
bootstrap identity span does not cover the hardware args PA.
On hardware the walk audit proves the identity coverage
(above); gamma's legality rests on that audit, not on the rig.

## Assembly

`builds/lg-flash-unixnu-m3t-sig.img`: header page from this
round's packed lg-flash.img (ramdisk_size restored, v0 id
recomputed; convention first validated against the M3S image),
this round's bootpayload, M3S ramdisk with KERNEL
cluster-swapped (ramdisk diff vs M3S = 40 bytes, all inside
KERNEL clusters; ADT MD5 8766bcb3... and toml unchanged).
Whole-image diff vs M3S confined to header page + payload
region + KERNEL clusters. 28,356,608 B, MD5
2de39add02816c145a96b713279f5ad1, SHA-256
5fe53a041207b8ee99abf9810a11fb572716781005787bf300bb2b023d18a148.

## Readout matrix (frozen period, row 3)

- idx0 blinking ~0.5 s: monitor alive (and beta inert if the
  blink cadence matches the v3.2 rounds).
- idx1 (main PROG record, alpha-treated): if it moves PAST
  the L4 yellow — at least to P1 white — alpha works: the
  PROG line can be forced to DRAM with clean+invalidate, the
  main channel becomes per-write deterministic, and the
  endpoint can be pinned exactly. If idx1 still shows the
  lemon yellow, alpha failed too.
- idx2 green: gamma landed — identity-map pure stores at P1
  reach DRAM (repair path for all pre-switch stubs: write via
  the identity alias). Black: even the identity store at P1
  did not land, which would contradict the locore evidence
  and reopen the channel model entirely.
- idx3: black by construction (delta cut). Any colour here is
  an anomaly to report, not data.
- Nothing changes at all (idx1 yellow, idx2 black): all
  kernel-side paths fail to reach the monitor; the paradox
  escalates back to host-side analysis.
