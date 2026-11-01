# M3S diagnostic kernel patch — PROG stubs writer-side self-clean (DIAGNOSTIC ONLY)

Stacks on the M3N kernel (pristine → M3N = 552 changed words, see
`kernel-milestone-prog.md` / `kernel-fbmarks-row2.md`). Baseline: M3N
kernel MD5 `6349ba730b91ff89412112b3fbd91f63`. Generator:
`~/workspace/unixnu-flashlm/m3s/patch_kernel.py`; packed by
`~/workspace/unixnu-flashlm/m3s/assemble.py` on the M3Q3 image
(firmware bytes verbatim — monitor blob v3.2, see
`monitor-core-m3p.md`). **Diagnostic use only — never ship in a
production image.**

## Why: the mailbox's DRAM value was an eviction lottery

The monitor core (M3P–M3R) reads the PROG record (args `+0x848`, VA
`0xFFFFFFF007F14848`, PA `0xC1F14848`) straight from DRAM. The boot
CPU's stubs, however, *write* it through the kernel VA mapping with
caches on, so a write lands in DRAM only when its line is evicted.
Two hardware rounds proved the resting DRAM value is therefore not
the last value written:

- M3Q3 (direct read): idx1 **pink = P5**.
- M3R (monitor issues `dc civac` + `dsb sy` before every read):
  idx1 **yellow = L4** (photo-adjudicated against row 1's own L4
  block) — the reader-side clean, issued by a core running with
  caches off, never reaches the boot CPU's caches; the value
  regressed to the last *cache-off PA write* (the locore stubs),
  while the P-stub writes sat in the boot CPU's cache, invisible.

The only deterministic fix is writer-side: the writer cleans its own
line, through the same mapping and shareability attributes its
stores used, immediately after storing. That is this patch. The five
locore stubs (M3G) are **not** touched: they write by PA with caches
off, so their values are already in DRAM when written.

## The change (per P stub, words numbered within the 14-word stub)

Stub bodies live at VA `0xFFFFFFF0073DC790` + (n−1)·0x38 (M3F).
Words 0–11 are **byte-identical** to M3N (address build, the three
stores magic/ID/count, unchanged semantics). Then:

| word | M3N content | M3S content |
|---|---|---|
| 12 | displaced original word0 | `dc cvac, x16` (`d50b7a30`) |
| 13 | tail branch (entry+4, or M3N's `b` FB2 block for P1/P2/P3/P7) | `b tramp_Pn` |

with one 3-word trampoline per stub in the free cave tail
(`0xFFFFFFF0073DCF10` + (n−1)·0xC, P1..P10; 30 of the 60 NOP words
M3N left, re-measured all-NOP before writing):

```
tramp_Pn:  dsb sy                          ; d5033f9f
           <displaced original word0>      ; verbatim copy of M3N word 12
           b <M3N word-13 target>          ; FB2 block VA for P1/P2/P3/P7,
                                           ; entry+4 for the rest
```

Execution order per stub hit is therefore: three stores → `dc cvac`
→ tail branch → `dsb sy` → displaced word0 → original continuation.
The displaced word still executes exactly once per hit, before the
function's second instruction, exactly as in M3F–M3N; the four
M3N-hooked stubs still reach their FB2 blocks, whose paint sections
and first-call guards (P2/P7) are unmodified. No other diagnostic
component changes: the M3E exception blackbox, the M3G locore
stubs/FB marks, the M3L BootShim copies and the M3N row-2 blocks are
untouched (the diff ledger below is the proof).

### Why `dc cvac`, why `dsb sy`

- `dc cvac, x16`: x16 still holds the record VA at word 12 (built by
  words 0–3; no intervening word touches it — verified per stub).
  The record (`+0x848..+0x85F`) lies inside the single 64B line
  VA `0xFFFFFFF007F14840` / PA `0xC1F14840`, so one clean by VA to
  the Point of Coherency covers all three fields. `cvac` (clean
  only), not `civac`: the writer needs its dirty data written back;
  invalidation buys nothing — the monitor holds no cached copy
  (caches off) and re-reads DRAM every poll. This is the standard
  clean-before-noncoherent-read sequence, executed by the writer
  through its own cacheable, inner-shareable kernel mapping — the
  exact path the stores took — so it cannot miss the cache levels
  involved the way the reader-side attempt did (M3R).
- `dsb sy` (full system), not `dsb ish`: the observer is a core
  running with caches off, outside any shareability domain the
  writer can rely on; `sy` is the barrier whose completion orders
  the clean with respect to *all* agents. Its cost (nanoseconds, ten
  stubs on a diagnostic path) is irrelevant.
- Register contract: the clean reads x16 and clobbers no register;
  the trampoline adds no stack use and no `bl` (x30 is the
  function's return address at every stub and is never touched) —
  the M3F x16/x17-only clobber contract is preserved.

Note: P6's stub is patched identically for uniformity although
`_PE_initialize_console` has zero callers in this kernel and the
stub never executes (round-6 analysis).

## Diff ledger (word-level, exact offset sets asserted by the generator)

| step | changed words |
|---|---|
| M3N → M3S | **50** = 10 stubs × (word 12, word 13) + 30 trampoline words (previously NOP) |
| pristine → M3S | **582** = 552 (the full M3N set) + the same 30 trampoline words (the 20 stub words were already non-pristine in M3N) |

Size unchanged (14,917,208 B). M3S kernel MD5
`1c676a4f7bc018d64c3c5ac21fa58242`.

Verification on the final bytes, beyond the generator's own gates:
numerical evaluation of every stub's words 0–3 movz/movk chain
(m3r-gate style) yields `0xFFFFFFF007F14848` for all ten stubs, so
the cvac target line evaluates to VA `0xFFFFFFF007F14840` / PA
`0xC1F14840` — the same line the monitor side pinned in M3R — and an
independent `llvm-objdump-18` pass over the stub and trampoline
spans shows `dc cvac, x16` in every stub and
`[dsb sy][displaced word][b original target]` in every trampoline,
with the branch targets resolving to the M3N continuations (FB2
blocks for P1/P2/P3/P7; `_pmap_bootstrap+4`, `_arm_init+0x924`,
`_PE_initialize_console+4`, `_cpu_data_alloc+4`,
`_PE_init_iokit+4`, `IOPlatformExpertDevice::init+4` for the rest).

## Readout (with the M3Q3 firmware / monitor blob v3.2)

The monitor is unchanged (direct DRAM read every ~50 ms), but every
PROG value is now in DRAM the moment its stub returns, so row 3
idx1 is a per-write deterministic truth, no longer an eviction
sample:

| idx1 resting color | verdict |
|---|---|
| pink (P5) | death between P5 and the P2-second-call stub — a span of a few instructions in `_arm_init` |
| violet (P2) | the second `_PE_init_platform` call was entered; death inside it or before `machine_startup` completes its next stub-visible point |
| green (P9) | `_PE_init_iokit` entered |
| sky blue (P10) | `IOPlatformExpertDevice::init` entered — the QEMU death neighborhood, first exactly observable on hardware |
| any other color | read against the standing color table (gold P4, gray P6, brown P8, …) |
