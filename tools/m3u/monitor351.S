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
    mov x7, #0x743
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
    mov x11, x16
    mov x12, #0x3c
L_498:
    mov x13, x11
    mov x14, #0xf0
L_4a0:
    str w10, [x13], #4
    subs x14, x14, #1
    b.ne L_4a0
    add x11, x11, x15
    subs x12, x12, #1
    b.ne L_498
    ret 
