#!/usr/bin/env python3
"""UniXNU ADT step for flashlm.

The UniXNU payload driver passes the generic ADT flags (chip-id,
owned-memory-size, root-match UUID, CPU registers, PSCI method, trust cache,
...). The flashlm hardware profile in mkadt.py owns those values; accept the
flags and generate the D22AP/flashlm tree with the requested DRAM size.
"""
import argparse
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--output", required=True)
    parser.add_argument("--dram-size", default="0xc0000000")
    parser.add_argument("--owned-memory-size", type=lambda value: int(value, 0))
    known, _unknown = parser.parse_known_args()
    tool = Path(__file__).resolve().parent / "mkadt.py"
    command = [sys.executable, str(tool), known.output, "--device", "flashlm",
               "--dram-size", known.dram_size]
    if known.owned_memory_size is not None:
        command += ["--owned-memory-size", str(known.owned_memory_size)]
    subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
