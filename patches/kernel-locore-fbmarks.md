# M3L diagnostic patch — locore framebuffer marks (DIAGNOSTIC ONLY)

Stacks on M3G (`kernel-locore-prog.md`): the five PA-addressed locore
milestone stubs (L0–L4, IDs 0x11–0x15) additionally paint a solid
color block into the framebuffer **in the same boot**, so the
milestone readout no longer depends on any cross-boot record channel
(the channel whose death M3F–M3K spent six rounds establishing).
Generator: `m3l/patch_kernel.py` (all encodings produced by
`llvm-mc-18`, never hand-derived). Kernel MD5:
pristine `af7a0bf21935829b5a7ef12f14800f37` → M3G
`850602e628a864e6deea38b7d6c47a94` → **M3L
`884949415562806d6df07261aa70f7fa`**, size unchanged (14,917,208 B).
**Diagnostic use only — never ship in a production image, never fold
into `ci/0019`.**

## Mechanism (diff-minimal over M3G)

Each M3G stub is 9 PROG body words + tail (1–2 words). M3L changes
**exactly one word per stub**: the first tail word (stub+9) becomes
`b FB_<point>` into a per-point block placed in the previously free
NOP span. The block is `[FB fill section][original tail]`, with any
branch in the tail re-encoded from its new address; the displaced
words (L1 `msr OSLAR_EL1, xzr`, L3b `mov x0, #0x300000`) are carried
verbatim (position-independent; executing them after the fill is
harmless — nothing in the fill touches the debug lock or x0). The L1
and L3b stubs keep their original second tail word (the `b entry+4`)
in place behind the redirect; it is unreachable padding, left there
to keep the diff minimal. The PROG writes themselves are byte-identical
to M3G, so the cross-boot PROG slot keeps working as a second channel.

| point | stub VA | redirect word (was) | FB block VA | block words |
|---|---|---|---|---|
| L0 | 0x73DC9C0 | `1400002b` (was `1400159e`, b _start_first_cpu) | 0x73DCA90 | 14 = 13 fill + 1 tail b |
| L1 | 0x73DC9E8 | `1400002f` (was `d510109f`, displaced msr) | 0x73DCAC8 | 15 = 13 fill + displaced + tail b |
| L2 | 0x73DCA14 | `14000033` (was `14001616`, b common_start) | 0x73DCB04 | 14 = 13 fill + 1 tail b |
| L3b | 0x73DCA3C | `14000037` (was `d2a00600`, displaced mov) | 0x73DCB3C | 22 = 20 fill + displaced + tail b |
| L4 | 0x73DCA68 | `14000042` (was `d65f03c0`, ret) | 0x73DCB94 | 21 = 20 fill + ret |

FB blocks occupy 0x73DCA90–0x73DCBE8 (86 words); 0x73DCBE8–0x73DD000
of the cave remains free NOP (262 words of headroom — the "stop if it
does not fit" gate did not trigger). Placement was gated on every
target word being NOP in the M3G kernel.

Diff ledger (word-level, verified on the built files):

| step | changed words |
|---|---|
| pristine → M3G | 263 (M3E 56 + M3F milestones + M3G locore, see earlier specs) |
| M3G → M3L | **91** = 5 redirect words + 86 FB block words, exactly the expected offset set |
| pristine → M3L | **349** = 263 + 86 (the 5 redirects rewrite words already counted in the 263) |

## Framebuffer geometry (recomputed from parameters, not by hand)

Panel 1440×3120, 32bpp, stride 5760 B. FB base **0x9C000000**:
`PlatformMemoryMapLib.c` "Display Reserved" (18 MiB), cross-checked
against the ABL DTB splash region (NOTES.md), and it is the same base
the GOP hands DarwinBoot (`DarwinBootVideoFromGop` → `Video[0]`) —
DiagDraw text and DarwinEnter's green bar (pixel 0xFF00FF00, BGRA)
render through it on hardware with pitch 5760 (a wrong pitch would
skew the bar and the text; both photograph clean). Bottom band
y ∈ [3060, 3120); block *i* is 240×60 at x = *i*·260 (20 px gaps;
last block ends at x = 1280 < 1440). Start PA = 0x9C000000 +
3060·5760 + *i*·1040:

| point | x | start PA | color (u32) | name |
|---|---|---|---|---|
| L0 | 0 | 0x9D0CF200 | 0xFFFF0000 | red |
| L1 | 260 | 0x9D0CF610 | 0xFF0000FF | blue |
| L2 | 520 | 0x9D0CFA20 | 0xFFFF00FF | magenta |
| L3b | 780 | 0x9D0CFE30 | 0xFF00FFFF | cyan |
| L4 | 1040 | 0x9D0D0240 | 0xFFFFFF00 | yellow |

All five differ from each other and from the green top bar
(0xFF00FF00). Fill loop per block: `str w17, [x16], #4` ×240 per row,
row step +4800 (encoded +4096/+704), 60 rows — 14,400 stores, all by
physical address.

## Addressing and register proofs (unstripped disassembly)

**Pre-MMU points (L0/L1/L2).** DarwinEnter clears SCTLR_EL1 bits
M(0)/C(2)/I(12) before branching to the kernel (Entry.S), and SCTLR
is first written inside common_start — past L2. With the MMU off,
stores go straight to DRAM (the same regime in which the M3G PROG
writes and the M2 stub's slot write already work).

**Post-MMU points (L3b/L4) — why a toggle is required.** The
bootstrap tables built by `_start_first_cpu` map exactly two
MemorySize spans (fill loops at 0x73E2144–0x73E2280): the kernel VA
range (TTBR1) and the window identity range (TTBR0,
[0xC1004000, +512 MiB)). The FB PA 0x9C000000 lies in neither, so a
PA-as-VA store there would take a translation fault *inside the
marker itself* and poison the readout. The L3b/L4 fill sections
therefore wrap the fill: `mrs x11, sctlr_el1; bic x12, x11, #1;
msr sctlr_el1, x12; isb` … fill … `dsb sy; msr sctlr_el1, x11; isb`
— only bit 0 (M) is cleared, every other bit is preserved and
restored. This is safe here because the executing PC sits in the
identity segment (VA == PA), so instruction fetch is seamless
across the toggle, interrupts are masked (DAIFSet at
`_start_first_cpu` entry), and with the MMU off data accesses are
Normal Non-cacheable (straight to DRAM). No TLB maintenance is
needed: no FB translation is ever created while M is on.

**Registers.** Fill uses x16 (cursor) / x17 (color) — the pair M3G
proved dead across the whole locore span — plus x9 (row counter)
and x10 (pixel counter); the toggle adds x11 (saved SCTLR) and x12
(scratch). Liveness for x9–x12, from the unstripped disassembly:
after every stub point, the first access to each is a **write**
(fill loops: x10 ← `mov #0x200` @0x73E215C, x11 ← `mov #3`
@0x73E2184, x12 ← `and` @0x73E2188, x9 ← `and` @0x73E21EC), or there
is no access at all before `_arm_init` — common_start and its tail
(0x73E2290–0x73E23A0) touch only x0/x1/x19/x20/x21/x22/x23/x25/x30.
`_arm_init` takes no input contract on caller-saved registers: a
stock boot reaches it with fill-loop residue in x9–x12, values that
already vary with memory size and args. The entry contracts are
preserved exactly as in M3G: L0's section never writes x0, L4's
never writes x30 (`b` in, the original `ret` out, at the block end).

## Verification (built files)

- Generator asserts: every relocated original word matches the M3G
  file byte-for-byte (entry/tail encodings decoded and targets
  checked); every FB block word lands on a NOP; the final diff vs
  M3G equals the expected 91-word set.
- Post-build disassembly of all five stubs and blocks confirms:
  PROG bodies unchanged; redirects target the right blocks; block
  constants are the table's PAs/colors; loop branches close within
  each block; L1/L3b displaced words appear verbatim in the blocks;
  tail branches land on `_start_first_cpu`, `_start_first_cpu+4`,
  `common_start`, `common_start+0xE4` (L3b entry+4) and the L4 block
  ends in the original `ret` (0xD65F03C0).

## Readout (hardware)

After the hand-off freeze, count the colored blocks in the bottom
band of the frozen frame: *n* blocks lit (they appear left to right
in milestone order) means the kernel passed the *n*-th locore point
and died before the next one — in the **same** boot, with no
dependence on resets, ABL, or firmware allocations. Zero blocks =
death in the hand-off tail before `__start` (or the FB itself is
unreachable pre-MMU, which would contradict the M2/M3G DRAM-write
evidence). The blocks persist in the frozen frame alongside the
DarwinBoot readback rows.
