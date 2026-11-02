// M3Z10 cmdline_peek: replaces configure's stage-1 SYSTEM_RESET (0x...795D96C) with a
// same-round dump of where `sheng-platform-stage` sits in boot_args->CommandLine.
// Tail-jumps to reset_halt's recorder (0x...73E0B00, must already be applied):
//   ESR  = (strlen(CommandLine) << 16) | match offset   (0xffff = not found)
//   ELR  = 8 bytes right after the 20-char name (e.g. "=1 debug"), little-endian ASCII
//   FAR  = first 8 bytes of CommandLine, little-endian ASCII
//   CODE = 0x6A
peek:
msr daifset, #0xf
movz x8, #0x41f0
movk x8, #0x071f, lsl #16
movk x8, #0xfff0, lsl #32
movk x8, #0xffff, lsl #48
ldr x8, [x8]            // PE_state.bootArgs
add x9, x8, #0x6c       // CommandLine
adr x10, needle
mov x11, #0
1: ldrb w12, [x9, x11]
cbz w12, 2f
add x11, x11, #1
cmp x11, #1024
b.lo 1b
2: mov x13, #0
mov x0, #0xffff
3: add x14, x13, #20
cmp x14, x11
b.hi 6f
mov x15, #0
4: add x16, x13, x15
ldrb w12, [x9, x16]
ldrb w17, [x10, x15]
cmp w12, w17
b.ne 5f
add x15, x15, #1
cmp x15, #20
b.lo 4b
mov x0, x13
b 6f
5: add x13, x13, #1
b 3b
6: mov x30, #0
mov x17, #0xffff
cmp x0, x17
b.eq 8f
add x16, x9, x0
add x16, x16, #20
mov x15, #7
7: ldrb w12, [x16, x15]
orr x30, x12, x30, lsl #8
subs x15, x15, #1
b.ge 7b
8: orr x0, x0, x11, lsl #16
mov x1, #0
mov x15, #7
9: ldrb w12, [x9, x15]
orr x1, x12, x1, lsl #8
subs x15, x15, #1
b.ge 9b
mov x4, #0x6a
b .                     // patched by .py: b rec (0x...73E0B00)
needle: .ascii "sheng-platform-stage"
.balign 4
