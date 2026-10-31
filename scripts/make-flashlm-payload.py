#!/usr/bin/env python3
"""Build the flashlm FV payload image: a 512 KiB FAT12 volume labelled FLASHSP.

The LG ABL rejects boot images with large ramdisks (mh2lm hardware finding),
so the UniXNU payload travels inside the firmware volume as an FFS file and
UniXNURamDiskDxe publishes it as a block device (FV fallback).

v1 produced a valid but empty volume. v2 packed the M2 payload set with a
hand-written Python FAT12 writer. v3 keeps the v2 layout but switches the
writer to mtools -- the same tool the UniXNU core payload tool uses
(scripts/unixnu/payload.py write_volume) -- and renames the kernel files
to strict 8.3 names:

    EFI/UniXNU/unixnu.toml      menu config, xnu entry -> KERNEL
    EFI/UniXNU/KERNEL           Mach-O (real kernel or the M2 stub)
    EFI/UniXNU/KERNEL.ADT       flashlm ADT (DarwinBoot reads
                                KernelPath + ".adt")

Why the rename: "kernel.macho" (5-char extension) and "kernel.macho.adt"
(double dot) are not legal 8.3 names, so on the FAT volume they exist only
as LFN entries. On the v2 hand-written volume that LFN match failed at
runtime in the Payloads directory and DarwinBoot's open of the kernel
returned EFI_NOT_FOUND (hardware finding, M2). The control devices
(guacamole/mh2lm) ship the same names successfully -- the systematic
difference is the volume writer (mtools vs the hand-written one). Strict
8.3 names remove the LFN dependency for the kernel files entirely;
unixnu.toml keeps its LFN, which Config.c demonstrably opens fine.

v3 (M2E) applied both fixes above -- 8.3 names under Payloads/ plus the
mtools writer -- and the hardware still returned EFI_NOT_FOUND from one of
DarwinBoot's two file opens. After three rounds of forensics (path chain,
volume handle/media, volume bytes) the only unexercised variable left is
the directory depth: every depth<=2 open on this firmware (the toml
itself) succeeds every time, while the only depth-3 opens ever attempted
(through the Payloads directory) failed every time. v4 therefore moves
KERNEL and KERNEL.ADT up beside the toml, into EFI/UniXNU directly, and
the toml path becomes plain "KERNEL".

The unixnu.toml has no `initrd` in the xnu entry and the ADT carries no
RAMDisk placeholder under /chosen/memory-map; the two facts must stay
consistent or DarwinBoot refuses the boot (EFI_UNSUPPORTED /
EFI_COMPROMISED_DATA). The [boot]/[kits]/entry text mirrors the core
payload tool's template, with title/args/timeout/tools taken from
board.toml [payload].

Volume: 512 B/sector, 1024 sectors (512 KiB), FAT12, label FLASHSP,
serial 0x53484E47 ("SHNG", same as upstream payload.py). The BPB volume
label at offset 43 is "FLASHSP" and the type string at offset 54 is
"FAT12   ", which is what ShengBootMemoryDxe's IsPayloadFat() checks on
the fallback path.

Usage:
  make-flashlm-payload.py OUT.img                          # empty volume
  make-flashlm-payload.py OUT.img --kernel K --adt A       # packed payload
  make-flashlm-payload.py --verify IMG --kernel K --adt A  # re-read and check
"""
import os
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

TOTAL_SECTORS = 1024            # 512 KiB at 512 B/sector
LABEL = "FLASHSP"
SERIAL = "53484e47"             # upstream payload.py volume serial
LABEL_FIELD = b"FLASHSP    "    # 11-byte BPB volume label field
TYPE_FIELD = b"FAT12   "        # 8-byte BPB type string field
FIXED_MTIME = 1793462400        # 2026-10-30 00:00 UTC, deterministic staging


def mtools_env():
    return dict(os.environ, MTOOLS_SKIP_CHECK="1", TZ="UTC")


def run(cmd, **kw):
    subprocess.run(cmd, check=True, env=mtools_env(), **kw)


def format_volume(out):
    out.unlink(missing_ok=True)
    # Upstream's write_volume passes -F, but that flag forces FAT32 (their
    # volumes are MiB-scale); at 512 KiB it produces a FAT32 boot sector
    # (verified: type string lands at offset 82), contradicting this
    # volume's FAT12 design. Without -F, mformat picks FAT12 by size and
    # the BPB label/type land at offsets 43/54 as required.
    run(["mformat", "-C", "-T", str(TOTAL_SECTORS), "-v", LABEL,
         "-N", SERIAL, "-i", str(out), "::"])


def build(kernel=None, adt=None, toml_text=None, out=None):
    """Write the volume to `out` (a Path) via a staging tree + mtools."""
    format_volume(out)
    if kernel is None:
        return
    with tempfile.TemporaryDirectory() as td:
        stage = Path(td) / "EFI" / "UniXNU"
        stage.mkdir(parents=True)
        files = {
            stage / "unixnu.toml": toml_text.encode(),
            stage / "KERNEL": kernel,
            stage / "KERNEL.ADT": adt,
        }
        for path, data in files.items():
            path.write_bytes(data)
            os.utime(path, (FIXED_MTIME, FIXED_MTIME))
        # Copy the staged EFI tree in one recursive pass (upstream style).
        run(["mcopy", "-i", str(out), "-s", "-Q", "-m",
             str(Path(td) / "EFI"), "::/"])


# --- unixnu.toml ------------------------------------------------------------

def make_toml(board_path):
    board = tomllib.loads(Path(board_path).read_text())
    spec = board["payload"]
    args = " ".join(spec.get("kernel_args", []))
    text = (
        "version = 1\n"
        "[boot]\n"
        f"timeout = {spec.get('timeout', 3)}\n"
        'default = "xnu"\n'
        "[kits]\n"
        "autoload = false\n"
        "[[entry]]\n"
        'id = "xnu"\n'
        f"title = \"{spec.get('title', 'UniXNU')}\"\n"
        'type = "xnu"\n'
        'path = "KERNEL"\n'
        f"args = \"{args}\"\n"
        "[[entry]]\n"
        'id = "reset"\n'
        'title = "Restart"\n'
        'type = "action"\n'
        'action = "reset"\n'
        "[[entry]]\n"
        'id = "shutdown"\n'
        'title = "Power off"\n'
        'type = "action"\n'
        'action = "shutdown"\n'
    )
    if spec.get("tools"):
        text += (
            "[[entry]]\n"
            'id = "tools"\n'
            'title = "Tools"\n'
            'type = "action"\n'
            'action = "tools"\n'
        )
    return text


# --- volume reading / verification (mtools) -----------------------------------

def mtype(img, vol_path):
    return subprocess.run(
        ["mtype", "-i", str(img), vol_path],
        check=True, env=mtools_env(), capture_output=True).stdout


def mdir_listing(img):
    return subprocess.run(
        ["mdir", "-i", str(img), "-s", "::"],
        check=True, env=mtools_env(), capture_output=True, text=True).stdout


def verify(img, kernel, adt, toml_text):
    data = Path(img).read_bytes()
    assert len(data) == TOTAL_SECTORS * 512, "volume is not 512 KiB"
    assert data[43:54] == LABEL_FIELD, "BPB volume label is not FLASHSP"
    assert data[54:62] == TYPE_FIELD, "BPB type string is not FAT12"
    expect = {
        "::/EFI/UniXNU/unixnu.toml": toml_text.encode(),
        "::/EFI/UniXNU/KERNEL": kernel,
        "::/EFI/UniXNU/KERNEL.ADT": adt,
    }
    for vol_path, want in expect.items():
        got = mtype(img, vol_path)
        assert got == want, f"content mismatch for {vol_path}"
    return mdir_listing(img)


def main():
    args = sys.argv[1:]
    opt = {}
    positional = []
    i = 0
    while i < len(args):
        if args[i] in ("--kernel", "--adt", "--board", "--verify"):
            opt[args[i]] = args[i + 1]
            i += 2
        else:
            positional.append(args[i])
            i += 1
    here = Path(__file__).resolve().parent
    board = opt.get("--board", str(here.parent / "board.toml"))
    kernel = Path(opt["--kernel"]).read_bytes() if "--kernel" in opt else None
    adt = Path(opt["--adt"]).read_bytes() if "--adt" in opt else None

    if "--verify" in opt:
        assert kernel is not None and adt is not None
        print(verify(opt["--verify"], kernel, adt, make_toml(board)))
        print(f"{opt['--verify']}: payload verified (toml + KERNEL + KERNEL.ADT byte-identical)")
        return

    out = Path(positional[0]) if positional else Path("payload.img")
    assert (kernel is None) == (adt is None), "--kernel and --adt go together"
    toml_text = make_toml(board) if kernel is not None else None
    build(kernel, adt, toml_text, out)
    assert out.stat().st_size == TOTAL_SECTORS * 512
    if kernel is not None:
        print(verify(out, kernel, adt, toml_text))
    kind = "packed payload (toml + KERNEL + KERNEL.ADT)" if kernel is not None else "empty volume"
    print(f"{out}: {out.stat().st_size} bytes, FAT12 volume 'FLASHSP', {kind}")


if __name__ == "__main__":
    main()
