# tools/m3u — monitor blob sources and host gates (M3U / M3U2)

| File | What |
| --- | --- |
| `monitor35.S` | v3.5 as shipped in M3U, reconstructed from the patch bytes (reassembles byte-identically) |
| `monitor351.S` | v3.5 + row-3 idx4 stage markers S1–S4 (control build, keeps the AP bug) |
| `monitor352.S` | v3.5.1 + slot-page AP fix `0x743`→`0x703` — the blob now in `patches/darwinboot-cpuon-monitor.patch` |
| `build.sh` | assemble all three (`AS=aarch64-linux-gnu-as OBJCOPY=aarch64-linux-gnu-objcopy ./build.sh` on x86) |
| `gate.py` | Gates A/B/C (`pip install unicorn`; run after `build.sh`) |

Readout and rationale: `patches/monitor-core-m3p.md`, section M3U2.
Any edit to a `.S` that changes a movz/movk chain must still pass the
numeric-evaluation discipline of HANDOVER §4.3 (Gate C re-walks the
tables the blob actually builds, so a wrong constant shows up there).
