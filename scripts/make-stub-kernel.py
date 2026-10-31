#!/usr/bin/env python3
"""Hand-build the minimal ARM64 Mach-O stub kernel for flashlm M2.

DarwinBoot's ParseKernel (drivers/DarwinBoot, DarwinBoot.c) refuses
anything a stock linker emits for this purpose -- ld64.lld produces
LC_MAIN instead of the required LC_UNIXTHREAD -- so the stub is laid
out byte by byte here. The rules enforced by the parser (and re-checked
by check() below, a line-by-line port of the C code) are:

  header   magic 0xfeedfacf, cputype 0x0100000c (ARM64), cpusubtype 0
           (CPU_SUBTYPE_ARM64_ALL -- the C parser rejects anything
           else even though the mh2lm checklist omits it), filetype 2
  commands every cmdsize >= 8, 8-byte aligned, total == sizeofcmds and
           sizeofcmds must fit in the file after the 32-byte header
  segment  LC_SEGMENT_64 (0x19), cmdsize >= 72, nsects fits the
           command; segments with vmsize == 0 are skipped by the
           parser; for the rest: vmsize <= 256 MiB (fixed parser
           bound, NOT the ADT window size), no vmaddr+vmsize
           overflow, filesize <= vmsize, fileoff+filesize within the
           file, <= 64 segments, no two segments overlapping
  thread   exactly one LC_UNIXTHREAD (cmd 5), cmdsize 288, flavor 6
           (ARM_THREAD_STATE64), count 68, entry pc read at +272
  entry    must lie inside an executable segment (initprot & 4)
           within its *filesize*, and be 4-byte aligned
  span     base = min(vmaddr) must be page aligned (4 KiB);
           End - Base <= 256 MiB - 2 MiB (fixed parser bound)

Layout chosen for flashlm (all values throwaway-virtual; DarwinBoot
copies segments into the allocated window at PA = window + VA - base
and jumps to window + entry - base):

  base 0x1_0000_0000   page aligned and 32 MiB aligned, so the window
                       candidate offset (base & (32 MiB - 1)) is 0
  __TEXT  vmaddr base,        vmsize 0x2000, fileoff 0,      filesize 0x2000, prot r-x
          page 0: Mach-O header + load commands; page 1: entry code
  __DATA  vmaddr base+0x2000, vmsize 0x1000, fileoff 0x2000, filesize 0x1000, prot rw-
  entry   base + 0x1000 (== file offset 0x1000)

Entry code: store the 64-bit magic "M2STUB!!" (little-endian
0x212142555453324D) at physical 0x89B00010 -- inside the reserved
ShengBoot status block whose DT-pointer slot lives at 0x89B00000 in
the lg-flash memory map -- then spin on wfe forever. DarwinEnter has
already disabled the MMU when the stub runs, so the store goes
straight to DRAM; if the address were unusable the part would reset
right after DarwinBoot's on-screen hand-off banner, which is the
same observable M2 pass mh2lm recorded. The magic is a bonus software
marker only; M2 acceptance is DarwinBoot's own output.

Usage:
  make-stub-kernel.py OUT.macho [--check FILE]
"""
import struct
import sys

BASE = 0x1_0000_0000
PAGE = 0x1000
TEXT_VMSIZE = 0x2000
DATA_VMOFF = 0x2000
DATA_VMSIZE = 0x1000
ENTRY = BASE + 0x1000

MAGIC_ADDR = 0x89B00010
MAGIC = 0x212142555453324D          # "M2STUB!!" little-endian

WINDOW_PARSER = 0x10000000          # DarwinBoot.c: #define WINDOW_SIZE SIZE_256MB
SIZE_2MB = 0x200000
MAX_SEGMENTS = 64


# --- tiny AArch64 encoder (only what the entry stub needs) -----------

def movz(rd, imm16, shift=0):
    return 0xD2800000 | ((shift // 16) << 21) | (imm16 << 5) | rd


def movk(rd, imm16, shift=0):
    return 0xF2800000 | ((shift // 16) << 21) | (imm16 << 5) | rd


def str_u64(rt, rn, imm12=0):
    return 0xF9000000 | (imm12 << 10) | (rn << 5) | rt


def load_imm64(rd, value):
    words = [movz(rd, value & 0xFFFF)]
    for shift in (16, 32, 48):
        chunk = (value >> shift) & 0xFFFF
        if chunk:
            words.append(movk(rd, chunk, shift))
    return words


def entry_code():
    words = []
    words += load_imm64(9, MAGIC_ADDR)          # x9 = &status block + 0x10
    words += load_imm64(10, MAGIC)              # x10 = "M2STUB!!"
    words.append(str_u64(10, 9))                # str x10, [x9]
    words.append(0xD5033F9F)                    # dsb sy
    words.append(0xD503205F)                    # 1: wfe
    words.append(0x17FFFFFF)                    # b 1b (offset -4)
    return b"".join(struct.pack("<I", w) for w in words)


# --- Mach-O construction ----------------------------------------------

def segment_64(name, vmaddr, vmsize, fileoff, filesize, maxprot, initprot):
    cmd = struct.pack(
        "<II16sQQQQIIII",
        0x19, 72, name.encode().ljust(16, b"\0"),
        vmaddr, vmsize, fileoff, filesize, maxprot, initprot, 0, 0,
    )
    assert len(cmd) == 72
    return cmd


def unixthread(pc):
    state = bytearray(272)                      # ARM_THREAD_STATE64 (68 u32)
    struct.pack_into("<Q", state, 256, pc)      # __pc at state offset 256
    cmd = struct.pack("<IIII", 5, 288, 6, 68) + bytes(state)
    assert len(cmd) == 288
    return cmd


def build():
    cmds = b"".join([
        segment_64("__TEXT", BASE, TEXT_VMSIZE, 0, TEXT_VMSIZE, 5, 5),
        segment_64("__DATA", BASE + DATA_VMOFF, DATA_VMSIZE,
                   DATA_VMOFF, DATA_VMSIZE, 3, 3),
        unixthread(ENTRY),
    ])
    header = struct.pack(
        "<IIIIIIII",
        0xFEEDFACF,                             # magic MH_MAGIC_64
        0x0100000C,                             # cputype CPU_TYPE_ARM64
        0,                                      # cpusubtype ARM64_ALL (parser demands 0)
        2,                                      # filetype MH_EXECUTE
        3,                                      # ncmds
        len(cmds),                              # sizeofcmds
        0x100000,                               # flags MH_PIE (parser ignores flags)
        0,                                      # reserved
    )
    img = bytearray(DATA_VMOFF + DATA_VMSIZE)   # 0x3000 bytes total
    img[0:32] = header
    img[32:32 + len(cmds)] = cmds
    code = entry_code()
    img[0x1000:0x1000 + len(code)] = code
    return bytes(img)


# --- ParseKernel port: the self-check ----------------------------------
# Mirrors ParseKernel() in DarwinBoot.c statement by statement; raises
# AssertionError on the first rule the C code would reject.

def check(data, window=None):
    u32 = lambda o: struct.unpack_from("<I", data, o)[0]
    u64 = lambda o: struct.unpack_from("<Q", data, o)[0]
    size = len(data)
    assert size >= 32, "file smaller than mach_header_64"
    assert u32(0) == 0xFEEDFACF, "bad magic"
    assert u32(4) == 0x0100000C, "cputype != CPU_TYPE_ARM64"
    assert u32(8) == 0, "cpusubtype != 0 (parser rejects, checklist omits this)"
    assert u32(12) == 2, "filetype != MH_EXECUTE"
    assert u32(20) <= size - 32, "sizeofcmds overruns file"
    count = u32(16)
    end = 32 + u32(20)
    offset = 32
    segments = []
    entry = None
    for _ in range(count):
        assert end - offset >= 8, "load command header truncated"
        command, length = u32(offset), u32(offset + 4)
        assert length >= 8 and length % 8 == 0 and length <= end - offset, \
            "bad cmdsize"
        if command == 0x19:                     # LC_SEGMENT_64
            assert length >= 72, "segment cmdsize < 72"
            assert u32(offset + 64) <= (length - 72) // 80, "nsects overrun"
            if u64(offset + 32) != 0:           # vmsize == 0: parser skips it
                seg = dict(addr=u64(offset + 24), size=u64(offset + 32),
                           foff=u64(offset + 40), fsize=u64(offset + 48),
                           prot=u32(offset + 60))
                assert len(segments) < MAX_SEGMENTS, "too many segments"
                assert seg["size"] <= WINDOW_PARSER, "segment vmsize > 256 MiB"
                assert seg["addr"] <= (1 << 64) - 1 - seg["size"], "vmaddr overflow"
                assert seg["fsize"] <= seg["size"], "filesize > vmsize"
                assert seg["foff"] <= size, "fileoff past EOF"
                assert seg["fsize"] <= size - seg["foff"], "file data past EOF"
                segments.append(seg)
        elif command == 5:                      # LC_UNIXTHREAD
            assert entry is None, "duplicate LC_UNIXTHREAD"
            assert length == 288, "LC_UNIXTHREAD cmdsize != 288"
            assert u32(offset + 8) == 6, "thread flavor != ARM_THREAD_STATE64"
            assert u32(offset + 12) == 68, "thread count != 68"
            entry = u64(offset + 272)
        offset += length
    assert offset == end, "commands do not exactly fill sizeofcmds"
    assert entry is not None, "no LC_UNIXTHREAD"
    assert segments, "no non-empty segment"
    base = min(s["addr"] for s in segments)
    seg_end = max(s["addr"] + s["size"] for s in segments)
    executable = any(
        s["addr"] <= entry and entry - s["addr"] < s["fsize"] and s["prot"] & 4
        for s in segments)
    assert executable, "entry not inside an executable segment's filesize"
    for i, s in enumerate(segments):
        for o in segments[:i]:
            assert not (s["addr"] < o["addr"] + o["size"]
                        and o["addr"] < s["addr"] + s["size"]), "segments overlap"
    assert entry % 4 == 0, "entry not 4-byte aligned"
    assert base & 0xFFF == 0, "base not page aligned"
    assert base <= (1 << 64) - 1 - WINDOW_PARSER, "base + window overflows"
    assert seg_end - base <= WINDOW_PARSER - SIZE_2MB, \
        "span exceeds parser window - 2 MiB"
    if window is not None:
        # The runtime window comes from the ADT (darwinboot-memory-size);
        # DarwinBoot additionally needs Used <= WindowSize - 2 MiB.
        assert seg_end - base <= window - SIZE_2MB, \
            "span exceeds ADT window - 2 MiB"
    return dict(base=base, end=seg_end, entry=entry, segments=len(segments))


def main():
    argv = sys.argv[1:]
    if argv[:1] == ["--check"]:
        data = open(argv[1], "rb").read()
        info = check(data)
        print(f"{argv[1]}: ParseKernel OK "
              f"(base {info['base']:#x}, entry {info['entry']:#x}, "
              f"span {info['end'] - info['base']:#x}, {info['segments']} segments)")
        return
    out = argv[0] if argv else "kernel.macho"
    data = build()
    info = check(data, window=0xC0000000)       # flashlm ADT window: 3 GiB
    with open(out, "wb") as f:
        f.write(data)
    print(f"{out}: {len(data)} bytes, base {info['base']:#x}, "
          f"entry {info['entry']:#x}, self-check OK")


if __name__ == "__main__":
    main()
