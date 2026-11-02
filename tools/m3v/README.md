# tools/m3v — 飞行记录仪（monitor v3.6 + 内核 trace 桩）

规格与判读见 `patches/m3v-trace.md`。

```sh
sh tools/m3v/build.sh                         # monitor36.bin（1588 B）
python3 tools/m3v/gate36.py                   # Gate A–D 全 PASS（pip install unicorn）
python3 tools/m3v/patch_trace.py KIN KOUT     # KIN = 现役 M3U 镜像里的内核（或 pristine CI 内核）
```

出镜像（在产品树）：打上更新后的 `patches/darwinboot-cpuon-monitor.patch`，KERNEL 换成
`KOUT`，其余照 M3U 配方；记录大小/MD5；按 boot_b 回路刷（或先试 `fastboot boot`）。
