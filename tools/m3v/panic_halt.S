// M3Z8 panic_halt: hooked at _panic_trap_to_debugger entry (covers panic/Assert/panic_with_options).
// Writes M3E crumb (CODE 0x50) and stops with `b .` -> same-round v3.7 readout.
//   ESR row <- x2 (reason), ELR <- x6 (caller passed by panic*), FAR <- x0 (format string VA)
movz x3, #0x4800
movk x3, #0x07f1, lsl #16
movk x3, #0xfff0, lsl #32
movk x3, #0xffff, lsl #48
str x2, [x3, #0x08]
str x6, [x3, #0x10]
str x0, [x3, #0x18]
mov x4, #0x50
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
