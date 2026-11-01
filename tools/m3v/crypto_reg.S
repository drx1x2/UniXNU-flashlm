.text
reg:
stp x29, x30, [sp, #-16]!
mov x29, sp
adr x0, table
bl .
ldp x29, x30, [sp], #16
ret
ctxsz:
mov x0, #256
ret
kinit:
mov w0, #0
ret
rgen:
mrs x9, cntpct_el0
orr x9, x9, #1
1:
cbz x2, 2f
eor x9, x9, x9, lsl #13
eor x9, x9, x9, lsr #7
eor x9, x9, x9, lsl #17
strb w9, [x1], #1
sub x2, x2, #1
b 1b
2:
mov w0, #0
ret
runi:
mrs x9, cntpct_el0
cbz x1, 3f
udiv x10, x9, x1
msub x0, x10, x1, x9
ret
3:
mov x0, #0
ret
trap:
mov w4, #0
b common
mov w4, #8
b common
mov w4, #16
b common
mov w4, #24
b common
mov w4, #32
b common
mov w4, #40
b common
mov w4, #48
b common
mov w4, #56
b common
mov w4, #64
b common
mov w4, #72
b common
mov w4, #80
b common
mov w4, #88
b common
mov w4, #96
b common
mov w4, #104
b common
mov w4, #112
b common
mov w4, #120
b common
mov w4, #128
b common
mov w4, #136
b common
mov w4, #144
b common
mov w4, #152
b common
mov w4, #160
b common
mov w4, #168
b common
mov w4, #176
b common
mov w4, #184
b common
mov w4, #192
b common
mov w4, #200
b common
mov w4, #208
b common
mov w4, #216
b common
mov w4, #224
b common
mov w4, #232
b common
mov w4, #240
b common
mov w4, #248
b common
mov w4, #256
b common
mov w4, #264
b common
mov w4, #272
b common
mov w4, #280
b common
mov w4, #288
b common
mov w4, #296
b common
mov w4, #304
b common
mov w4, #312
b common
mov w4, #320
b common
mov w4, #328
b common
mov w4, #336
b common
mov w4, #344
b common
mov w4, #352
b common
mov w4, #360
b common
mov w4, #368
b common
mov w4, #376
b common
mov w4, #384
b common
mov w4, #392
b common
mov w4, #400
b common
mov w4, #408
b common
mov w4, #416
b common
mov w4, #424
b common
mov w4, #432
b common
mov w4, #440
b common
common:
movz x3, #0x4800
movk x3, #0x07f1, lsl #16
movk x3, #0xfff0, lsl #32
movk x3, #0xffff, lsl #48
mov x1, #0xc0de0000
orr x1, x1, x4
str x1, [x3, #8]
str x30, [x3, #16]
str x0, [x3, #24]
str x4, [x3, #32]
movz x8, #0x4d32
movk x8, #0x4352, lsl #16
movk x8, #0x4558, lsl #32
movk x8, #0x4d33, lsl #48
str x8, [x3, #0x40]
dsb sy
sub x8, x8, #1
str x8, [x3]
dsb sy
b .
.balign 8
table:
.skip 448
