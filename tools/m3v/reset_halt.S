// M3Z9 reset_halt: catch every kernel-side reset request in the same round.
// Each hooked site is replaced by `b stub_N`; stub_N = `mov x4,#CODE ; b rec`.
// rec writes the M3E crumb (0xFFFFFFF007F14800) and parks in wfe (no reset).
//   ESR row <- x0, ELR <- x30, FAR <- x1, CODE <- x4
rec:
msr daifset, #0xf
movz x3, #0x4800
movk x3, #0x07f1, lsl #16
movk x3, #0xfff0, lsl #32
movk x3, #0xffff, lsl #48
str x0, [x3, #0x08]
str x30, [x3, #0x10]
str x1, [x3, #0x18]
str x4, [x3, #0x20]
str x30, [x3, #0x28]
mov x5, sp
str x5, [x3, #0x30]
movz x8, #0x4d32
movk x8, #0x4352, lsl #16
movk x8, #0x4558, lsl #32
movk x8, #0x4d33, lsl #48
str x8, [x3, #0x40]
dsb sy
sub x8, x8, #1
str x8, [x3]
dsb sy
1: wfe
b 1b
.irp c, 0x60,0x61,0x62,0x63,0x64,0x65,0x66,0x67,0x68,0x69
mov x4, #\c
b rec
.endr
