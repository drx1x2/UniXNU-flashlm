.text
.global _start
_start:
    // v3.5.1 stage marker S1 entry: row-3 idx4 <- 0xFFFFFFFF (MMU-off PA store, or Device identity map after S4)
    mov x15, #0x1680
    mov x16, #0x7640
    movk x16, #0x9d02, lsl #16
    mov w10, #0xffff
    movk w10, #0xffff, lsl #16
    bl L_490
    mov x0, #0x110
    movk x0, #0x89b0, lsl #16
    ldr x1, [x0]
    cbz x1, L_0f8
    add x2, x1, #1, lsl #12
    add x3, x2, #1, lsl #12
    add x13, x3, #1, lsl #12
    mov x4, x1
    add x5, x1, #4, lsl #12
L_024:
    str xzr, [x4], #8
    cmp x4, x5
    b.lo L_024
    mov x8, #0x7c1
    movk x8, #0x60, lsl #48
    orr x7, x2, #3
    str x7, [x1]
    mov x7, #0x7c1
    movk x7, #0xc000, lsl #16
    movk x7, #0x60, lsl #48
    str x7, [x2, #0x18]
    orr x7, x3, #3
    str x7, [x2, #0x10]
    orr x7, x13, #3
    str x7, [x3, #0x268]
    mov x7, #0x445
    movk x7, #0x9c00, lsl #16
    movk x7, #0x60, lsl #48
    add x4, x3, #0x700
    mov x5, #9
L_074:
    str x7, [x4], #8
    add x7, x7, #0x200, lsl #12
    subs x5, x5, #1
    b.ne L_074
    // v3.5.2: slot page AP[2:1]=00 (EL1 RW, EL0 none). 0x743 had AP=01 (EL0 RW),
    // which the ARM ARM forces to PXN at EL1 -> instruction abort on the first fetch after SCTLR.M.
    mov x7, #0x703
    movk x7, #0x89b0, lsl #16
    movk x7, #0x40, lsl #48
    str x7, [x13, #0x800]
    mov x6, x1
    bl L_424
    mov x6, x2
    bl L_424
    mov x6, x3
    bl L_424
    mov x6, x13
    bl L_424
    dsb sy
    // v3.5.1 stage marker S2 tables built: row-3 idx4 <- 0xFFFF00FF (MMU-off PA store, or Device identity map after S4)
    mov x15, #0x1680
    mov x16, #0x7640
    movk x16, #0x9d02, lsl #16
    mov w10, #0xff
    movk w10, #0xffff, lsl #16
    bl L_490
    mov x4, #0x4ff
    msr mair_el1, x4
    mov x4, #0x3510
    movk x4, #0x80, lsl #16
    movk x4, #2, lsl #32
    msr tcr_el1, x4
    msr ttbr0_el1, x1
    tlbi vmalle1
    dsb sy
    isb 
    // v3.5.1 stage marker S3 MAIR/TCR/TTBR0 loaded, TLB invalidated: row-3 idx4 <- 0xFF808080 (MMU-off PA store, or Device identity map after S4)
    mov x15, #0x1680
    mov x16, #0x7640
    movk x16, #0x9d02, lsl #16
    mov w10, #0x8080
    movk w10, #0xff80, lsl #16
    bl L_490
    mrs x4, sctlr_el1
    mov x5, #0x1005
    orr x4, x4, x5
    and x4, x4, #0xfffffffffff7ffff
    msr sctlr_el1, x4
    isb 
    // v3.5.1 stage marker S4 SCTLR.M|C|I set, first fetch under MMU survived: row-3 idx4 <- 0xFF00FF00 (MMU-off PA store, or Device identity map after S4)
    mov x15, #0x1680
    mov x16, #0x7640
    movk x16, #0x9d02, lsl #16
    mov w10, #0xff00
    movk w10, #0xff00, lsl #16
    bl L_490
L_0f8:
    mov x9, #0x6600
    movk x9, #0x9d02, lsl #16
    mov x17, #0x6a10
    movk x17, #0x9d02, lsl #16
    mov x15, #0x1680
    mov x19, #0x4848
    movk x19, #0xc1f1, lsl #16
    mov x28, #0x4880
    movk x28, #0xc1f1, lsl #16
    mrs x20, cntfrq_el0
    cbnz x20, L_12c
    mov x20, #0xf800
    movk x20, #0x124, lsl #16
L_12c:
    mov x10, #0x14
    udiv x21, x20, x10
    lsr x22, x20, #1
    add x23, x21, x21, lsl #1
    mov w24, #-1
    mov w25, #0
    mov w26, #0
    mov w29, #0
    // v3.6 trace strip: x0 = cells drawn, x1 = trace ring PA (args +0x980;
    // u64 count at +0, one ID byte per hit from +8). Paint the 30 empty
    // cells dark first so the strip's extent is visible.
    mov x1, #0x4980
    movk x1, #0xc1f1, lsl #16
    mov x3, #0
L_trinit:
    mov w10, #0x3030
    movk w10, #0xff30, lsl #16
    bl L_cell
    add x3, x3, #1
    cmp x3, #30
    b.lo L_trinit
    mov x0, #0
    mov x16, x9
    mov w10, #0x4000
    movk w10, #0xffff, lsl #16
    bl L_490
    mov x16, x17
    mov w10, #0
    movk w10, #0xff00, lsl #16
    bl L_490
    add x16, x9, #0x820
    mov w10, #0
    movk w10, #0xff00, lsl #16
    bl L_490
    add x16, x9, #0xc30
    mov w10, #0
    movk w10, #0xff00, lsl #16
    bl L_490
    mrs x27, cntpct_el0
    add x27, x27, x22
L_194:
    mrs x10, cntpct_el0
    cmp x10, x27
    b.lo L_1ec
    cmp w25, #0
    b.ne L_1c0
    mov x16, x9
    mov w10, #0x80
    movk w10, #0xff00, lsl #16
    bl L_490
    mov w25, #1
    b L_1d4
L_1c0:
    mov x16, x9
    mov w10, #0x4000
    movk w10, #0xffff, lsl #16
    bl L_490
    mov w25, #0
L_1d4:
    mrs x10, cntpct_el0
    cmp w26, #0
    b.ne L_1e8
    add x27, x10, x22
    b L_1ec
L_1e8:
    add x27, x10, x23
L_1ec:
    mrs x10, cntpct_el0
L_1f0:
    mrs x11, cntpct_el0
    sub x11, x11, x10
    cmp x11, x21
    b.lo L_1f0
    ldr x10, [x28]
    cmp x10, #0x67
    b.eq L_228
    tbz w29, #0, L_240
    and w29, w29, #0xfffffffe
    add x16, x9, #0x820
    mov w10, #0
    movk w10, #0xff00, lsl #16
    bl L_490
    b L_240
L_228:
    tbnz w29, #0, L_240
    orr w29, w29, #1
    add x16, x9, #0x820
    mov w10, #0xff00
    movk w10, #0xff00, lsl #16
    bl L_490
L_240:
    ldr x10, [x28, #8]
    cmp x10, #0x64
    b.eq L_268
    tbz w29, #1, L_280
    and w29, w29, #0xfffffffd
    add x16, x9, #0xc30
    mov w10, #0
    movk w10, #0xff00, lsl #16
    bl L_490
    b L_280
L_268:
    tbnz w29, #1, L_280
    orr w29, w29, #2
    add x16, x9, #0xc30
    mov w10, #0xceeb
    movk w10, #0xff87, lsl #16
    bl L_490
L_280:
    ldr x2, [x1]
    cmp x2, #30
    b.ls L_trloop
    mov x2, #30
L_trloop:
    cmp x0, x2
    b.hs L_trdone
    add x11, x1, #8
    ldrb w11, [x11, x0]
    bl L_pal
    mov x3, x0
    bl L_cell
    add x0, x0, #1
    b L_trloop
L_trdone:
    // v3.7 EXC readout (same boot): when the M3E crumb at args +0x800 is
    // valid (MAGIC1 at +0x00, MAGIC2 at +0x40), redraw it
    // every poll as 6 rows of 32 bit-cells, MSB left: ESR, ELR[31:0], ELR[63:32],
    // FAR[31:0], FAR[63:32], CODE[31:0]. 1 = white/yellow, 0 = dark/darker,
    // alternating per nibble.
    mov x4, #0x4800
    movk x4, #0xc1f1, lsl #16
    ldr x10, [x4]
    mov x11, #0x4d31
    movk x11, #0x4352, lsl #16
    movk x11, #0x4558, lsl #32
    movk x11, #0x4d33, lsl #48
    cmp x10, x11
    b.ne L_exdone
    ldr x10, [x4, #0x40]
    add x11, x11, #1
    cmp x10, x11
    b.ne L_exdone
    ldr x5, [x4, #8]
    mov x6, #0
    bl L_bits
    ldr x5, [x4, #16]
    mov x6, #1
    bl L_bits
    ldr x5, [x4, #16]
    lsr x5, x5, #32
    mov x6, #2
    bl L_bits
    ldr x5, [x4, #24]
    mov x6, #3
    bl L_bits
    ldr x5, [x4, #24]
    lsr x5, x5, #32
    mov x6, #4
    bl L_bits
    ldr x5, [x4, #32]
    mov x6, #5
    bl L_bits
L_exdone:
    ldr x10, [x19]
    mov x11, #0x5250
    movk x11, #0x474f, lsl #16
    cmp x10, x11
    b.ne L_194
    ldr w10, [x19, #8]
    cmp w10, w24
    b.eq L_194
    mov w24, w10
    cmp w24, #0x11
    b.eq L_328
    cmp w24, #0x12
    b.eq L_338
    cmp w24, #0x13
    b.eq L_348
    cmp w24, #0x14
    b.eq L_358
    cmp w24, #0x15
    b.eq L_368
    cmp w24, #1
    b.eq L_378
    cmp w24, #7
    b.eq L_384
    cmp w24, #2
    b.eq L_394
    cmp w24, #3
    b.eq L_3a4
    cmp w24, #4
    b.eq L_3b4
    cmp w24, #5
    b.eq L_3c4
    cmp w24, #6
    b.eq L_3d4
    cmp w24, #8
    b.eq L_3e4
    cmp w24, #9
    b.eq L_3f4
    cmp w24, #0xa
    b.eq L_404
    sub w12, w24, #0x20
    cmp w12, #0xf
    b.hi L_unk
    mov w11, w24
    bl L_pal
    mov w12, w10
    mov w26, #0
    b L_414
L_unk:
    mov w26, #1
    mov w12, #-1
    b L_414
L_328:
    mov w26, #0
    mov w12, #0
    movk w12, #0xffff, lsl #16
    b L_414
L_338:
    mov w26, #0
    mov w12, #0xff
    movk w12, #0xff00, lsl #16
    b L_414
L_348:
    mov w26, #0
    mov w12, #0xff
    movk w12, #0xffff, lsl #16
    b L_414
L_358:
    mov w26, #0
    mov w12, #0xffff
    movk w12, #0xff00, lsl #16
    b L_414
L_368:
    mov w26, #0
    mov w12, #0xff00
    movk w12, #0xffff, lsl #16
    b L_414
L_378:
    mov w26, #0
    mov w12, #-1
    b L_414
L_384:
    mov w26, #0
    mov w12, #0x8000
    movk w12, #0xffff, lsl #16
    b L_414
L_394:
    mov w26, #0
    mov w12, #0xff
    movk w12, #0xff80, lsl #16
    b L_414
L_3a4:
    mov w26, #0
    mov w12, #0xc0c0
    movk w12, #0xffc0, lsl #16
    b L_414
L_3b4:
    mov w26, #0
    mov w12, #0xd700
    movk w12, #0xffff, lsl #16
    b L_414
L_3c4:
    mov w26, #0
    mov w12, #0x69b4
    movk w12, #0xffff, lsl #16
    b L_414
L_3d4:
    mov w26, #0
    mov w12, #0x8080
    movk w12, #0xff80, lsl #16
    b L_414
L_3e4:
    mov w26, #0
    mov w12, #0x2a2a
    movk w12, #0xffa5, lsl #16
    b L_414
L_3f4:
    mov w26, #0
    mov w12, #0xff00
    movk w12, #0xff00, lsl #16
    b L_414
L_404:
    mov w26, #0
    mov w12, #0xceeb
    movk w12, #0xff87, lsl #16
    b L_414
L_414:
    mov x16, x17
    mov w10, w12
    bl L_490
    b L_194
L_424:
    ubfx x4, x6, #0x1e, #9
    cmp x4, #3
    b.eq L_48c
    cmp x4, #2
    b.eq L_448
    and x7, x6, #0xffffffffc0000000
    orr x7, x7, x8
    str x7, [x2, x4, lsl #3]
    ret 
L_448:
    ubfx x5, x6, #0x15, #9
    cmp x5, #0x4d
    b.eq L_478
    cmp x5, #0xe0
    b.lo L_468
    cmp x5, #0xe8
    b.hi L_468
    ret 
L_468:
    and x7, x6, #0xffffffffffe00000
    orr x7, x7, x8
    str x7, [x3, x5, lsl #3]
    ret 
L_478:
    ubfx x5, x6, #0xc, #9
    and x7, x6, #0xfffffffffffff000
    orr x7, x7, x8
    orr x7, x7, #2
    str x7, [x13, x5, lsl #3]
L_48c:
    ret 
L_490:
    mov x12, #0x3c
    mov x18, #0xf0
L_rect:                     // v3.6: x16 dest, w10 color, x12 rows, x18 cols, x15 stride
    mov x11, x16
L_498:
    mov x13, x11
    mov x14, x18
L_4a0:
    str w10, [x13], #4
    subs x14, x14, #1
    b.ne L_4a0
    add x11, x11, x15
    subs x12, x12, #1
    b.ne L_498
    ret 

// v3.6 L_pal: w11 = trace ID -> w10 = ARGB (0x20..0x2F palette, else white)
L_pal:
    sub w12, w11, #0x20
    mov w10, #-1
    cmp w12, #0xf
    b.hi 1f
    adr x13, L_paltab
    ldr w10, [x13, w12, uxtw #2]
1:  ret

// v3.6 L_cell: x3 = cell index (0..29), w10 = color; 80x40 cell,
// 15 per line, pitch 96 px, lines 56 px apart, origin (16, 2680)
L_cell:
    mov x13, #15
    udiv x14, x3, x13
    msub x13, x14, x13, x3
    mov x11, #0xec00
    movk x11, #0x4, lsl #16     // 56 * 5760
    mul x14, x14, x11
    mov x11, #384               // 96 px * 4 B
    mul x13, x13, x11
    mov x16, #0x8c40
    movk x16, #0x9ceb, lsl #16  // FB 0x9C000000 + 2680*5760 + 16*4
    add x16, x16, x14
    add x16, x16, x13
    mov x12, #40
    mov x18, #80
    b L_rect

// v3.7 L_bits: x5 = value (low 32 bits drawn, MSB left), x6 = row 0..5.
// Cell 32x40 px, pitch 40 px plus 8 px between nibbles; rows 50 px apart
// from y = 2380 (above the trace strip; the row-3 idx blocks sit at y 2940..3000); origin x = 16. Uses x7 (saved lr), x8 (bit index).
L_bits:
    mov x7, x30
    mov x8, #0
1:  mov x11, #31
    sub x11, x11, x8
    lsr x12, x5, x11
    lsr x13, x8, #2
    and x14, x13, #1
    tbz x12, #0, 2f
    mov w10, #-1                 // 1: white (even nibble)
    cbz x14, 3f
    mov w10, #0xff00
    movk w10, #0xffff, lsl #16   // 1: yellow (odd nibble)
    b 3f
2:  mov w10, #0x2020
    movk w10, #0xff20, lsl #16   // 0: dark (even nibble)
    cbz x14, 3f
    mov w10, #0x5050
    movk w10, #0xff50, lsl #16   // 0: grey (odd nibble)
3:  mov x11, #160                // 40 px * 4 B
    mul x16, x8, x11
    add x16, x16, x13, lsl #5    // + nibble * 8 px * 4 B
    mov x11, #50
    mul x11, x6, x11
    add x11, x11, #2380
    mov x12, #5760
    mul x11, x11, x12
    add x16, x16, x11
    mov x11, #0x9c000000
    add x16, x16, x11
    add x16, x16, #64            // x = 16 px
    mov x12, #40
    mov x18, #32
    bl L_rect
    add x8, x8, #1
    cmp x8, #32
    b.lo 1b
    mov x30, x7
    ret

    .balign 4
L_paltab:
    .word 0xFFFF0000, 0xFFFF8000, 0xFFFFFF00, 0xFF80FF00   // 0x20 red, 0x21 orange, 0x22 yellow, 0x23 lime
    .word 0xFF00FF00, 0xFF00FF80, 0xFF00FFFF, 0xFF0080FF   // 0x24 green, 0x25 spring, 0x26 cyan, 0x27 azure
    .word 0xFF0000FF, 0xFF8000FF, 0xFFFF00FF, 0xFFFF0080   // 0x28 blue, 0x29 violet, 0x2A magenta, 0x2B rose
    .word 0xFFFFFFFF, 0xFF808080, 0xFF804000, 0xFFFF80C0   // 0x2C white, 0x2D gray, 0x2E brown, 0x2F pink

