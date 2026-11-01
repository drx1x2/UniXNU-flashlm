# kernel-panic-psci-reroute — M3D 诊断补丁规格（仅诊断用）

把 CI stripped 内核（`mach.development.bcm2837`，xnu-8796.141.3
DEVELOPMENT_ARM64_BCM2837，MD5 `af7a0bf21935829b5a7ef12f14800f37`，
14,917,208 B）的 `_panic` 入口改道到一段 PSCI SYSTEM_RESET 代码桩：
任何走到 `_panic` 的路径不再静默挂死，而是经 SMC 请求 EL3/PSCI 复位整机。

用途是**判别实验**：在控制台（kprintf/帧缓冲）建立之前的极早期阶段，
panic 与同步异常在屏幕上同为"冻结、无输出"，无法区分。本补丁让 panic
自带可观测签名——真机自复位循环 ⇔ 存在 panic 被触发；仍冻结 ⇔ panic
出局。**仅供 M3D 一轮诊断，不是修复，不得带入后续正式镜像。**

## 五处修改（文件偏移，32 位小端字，长度不变）

| # | 文件偏移 | VA | 原字 | 新字 | 指令 |
|---|----------|----|------|------|------|
| A | `0x96B3B4` | `0xfffffff00796f3b4`（`_panic` 入口，符号表实证） | `d10083ff`（sub sp, sp, #0x20） | `17e9c717` | `b 0xfffffff0073e1010`（imm26 = −1456361，×4 = −0x58E3A4，落点 = 洞首字 +0x10） |
| B1 | `0x3DD010` | `0xfffffff0073e1010`（`_LowExceptionVectorBase+0x10`，低向量槽 0 的 NOP 填充区） | `d503201f`（nop） | `52800120` | `movz w0, #0x9` |
| B2 | `0x3DD014` | `0xfffffff0073e1014` | `d503201f`（nop） | `72b08000` | `movk w0, #0x8400, lsl #16` |
| B3 | `0x3DD018` | `0xfffffff0073e1018` | `d503201f`（nop） | `d4000003` | `smc #0` |
| B4 | `0x3DD01C` | `0xfffffff0073e101c` | `d503201f`（nop） | `14000000` | `b .`（SMC 万一返回则原地自旋，不落入后续 NOP 区乱跑） |

合成效果：`w0 = 0x84000009` = PSCI SYSTEM_RESET，经 `smc #0` 发出。
B 点选址说明：向量槽首字（`0x3DD000`）是既有的 `b .` 低向量陷阱，不动；
桩放在其后的 NOP 填充内（`+0x10` 起），不改变任何向量入口语义。

## 编码复验（硬门，2026-10-31 执行，全过）

五条新字均由汇编器（llvm-mc/clang 18，aarch64）实际汇编产出后逐字比对：

- A：以 `.space 0x58E3A4` 拉开与 A 点完全相同的 PC 相对距离汇编 `b Ltgt`，
  产出 `17e9c717`，与规格一致；imm26/位移/落点验算闭合。
- B1 `movz w0, #0x9` → 编码字节 `20 01 80 52` = `52800120` ✓
- B2 `movk w0, #0x8400, lsl #16` → 编码字节 `00 80 b0 72` = `72b08000` ✓
- B3 `smc #0` → 编码字节 `03 00 00 d4` = `d4000003` ✓
- B4 `b .`（自标签对象级汇编）→ `14000000` ✓

**修正来源**：初版诊断规格中 B1/B2 两字为手工编码，imm16 位段放错
（movz/movk 把立即数错位编码）。第一轮构建在编码复验硬门停工，改以
llvm-mc 汇编 + llvm-objdump 反汇编双证定版，即上表 B1/B2。其余三字
初版即正确。教训：指令字一律以汇编器产出为准，不手工编码。

## 补丁后验证（M3D 构建实测）

- 补丁件与 CI 原件全文件 diff 恰好 5 字 / 20 字节；大小不变。
- 补丁件 MD5 `2351695f9be65a4fc451914d980cebd7`。
- 反汇编实证：`_panic` 首指令 `b 0xfffffff0073e1010`；洞内依次
  `mov w0, #0x9` / `movk w0, #0x8400, lsl #16` / `smc #0` / `b .`。
- ParseKernel 结构复核与原件一致：magic `0xfeedfacf`、cputype
  `0x100000c`、cpusubtype 0、filetype 2、ncmds 25、LC_UNIXTHREAD entry
  `0xfffffff0073e0488`；五处偏移均位于 `__TEXT_EXEC` 段内。
- 打包为 M3C 镜像原位换件：整镜像与 M3C 的 diff 恰为上述 20 字节；
  固件区 MD5 与 M3C 相同（`3b8326fb166d017af97a791133ca0594`），
  KERNEL.ADT / unixnu.toml / PAD.BIN 与 M3C 逐字节一致。
  M3D 镜像：`builds/lg-flash-unixnu-m3d-panicreroute.img`，
  MD5 `249a8c1d4fa5574f0c27a3a6395ef1a2`。
