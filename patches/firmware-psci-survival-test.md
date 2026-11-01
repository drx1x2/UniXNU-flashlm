# M3J 固件 PSCI 温复位存活自测试（firmware-psci-survival-test）

诊断专用，**不得带入正式镜像**。源码补丁：[darwinboot-psci-survival-test.patch](darwinboot-psci-survival-test.patch)
（对 DarwinBootPkg/Driver/DarwinBoot.c 的纯新增 diff，基线 = M3H 构建树；
DarwinBoot.inf 不动）。内核与 payload 沿 M3G 逐字节不变。

## 背景与目的

至此全部跨轮记录通道均已被真机证伪，但证伪都发生在**长按电源+音量−
强制重启**之后：窗口内记录页（M3F–M3G，分支 B 实锤）、BootShim 保留
槽页与 UEFI 非易失变量（M3H，两轮强启后 SLT NO / VAR NO）。长按复位
是 PMIC 层面的深度复位；**PSCI SYSTEM_RESET（温复位）后 DRAM 是否
存活从未在真机测过**。该前提是看门狗读回路线与一切复位型记录通道
（包括 M3E 黑匣子记录器隐含依赖的「记录器经 PSCI 复位、次轮固件
读回」）的共同地基。本实验由固件单方完成自测，不依赖内核行为。

## 探针布局（槽位复核实证）

位置：boot_args 页（ArgsAddress = 窗口内 `ALIGN(Address + Kernel.End
- Kernel.Base, 16K)`，与既有读回块同一公式）**+0x900 起 8 个 u64
子槽**，共 64 B（+0x900..+0x93F）。

该页实际占用边界（构建前逐项核对，零重叠）：

| 区段 | 偏移 | 依据 |
| --- | --- | --- |
| DARWIN_BOOT_ARGS 结构 | +0x000..+0x47F | BootArgs.h `sizeof == 0x480`（STATIC_ASSERT） |
| M3E EXC 记录 | +0x800..+0x847 | 读回代码以 Crumb[8]（+0x840）为 MAGIC2，清除 0x48 B |
| M3F/M3G PROG 槽 | +0x848..+0x85F | 读回代码清除 0x18 B |
| M3G PRB 探针 | +0x860..+0x867 | 读/写点均为单个 u64 |
| **M3J 子槽** | **+0x900..+0x93F** | 全 workspace 规格与暂存目录检索 `0x900`/`F14900` 零命中，无其它使用者 |

子槽 magic 每槽不同：槽 k 的期望值 = `0x5053434900000000 | k`
（高 4 字节 'PSCI'）。**k 定义**：自槽 0 起连续持有各自 magic 的
槽数（首个非 magic 槽的序号）。

异常定义（须与 DRAM 垃圾区分）：未被固件写过的窗口在首轮读到的是
任意 DRAM 残值，随机残值与 64 位 magic 精确相等的概率可忽略，故
**非零垃圾不算已写、仍按 k=0 处理**；异常只认两种结构性证据——
k ≥ 2，或引导段之后某槽持有其自身 magic（乱序/撕裂写入）。异常时
画 `PSCI ODD k=%d`、不复位、正常交接。

## 状态机（位于读回块末尾、窗口 ZeroMem 之前）

- **k=0（首轮）**：写槽 0；`dc cvac` 清洁该 64 B 至一致性点 +
  `dsb sy`/`isb`（防记录只停留在脏缓存行被复位丢弃）；DiagDraw
  Row 9 画 `PSCI TEST ARMED`；`gBS->Stall` **驻留 15 秒**（读屏与
  按键介入窗口，沿用 DbFail 的 15 秒惯例）；随后自发 PSCI 复位：
  `M3JPsciSystemReset()` 内联汇编 `movz w0,#0x9 / movk w0,#0x8400,
  lsl #16 / mov x1..x3,xzr / smc #0`（w0 合成 `0x84000009` =
  PSCI SYSTEM_RESET；指令字 `52800120`/`72b08000`/`d4000003` 与
  M3D 内核桩的汇编器定版逐字一致，构建前以 clang 单独汇编复验；
  SMC 调用约定的 caller-saved 区 x0–x17 全部声明 clobber）。
  若 SMC 返回（未复位）：Row 10 画 `PSCI NOFIRE`，改走
  `gRT->ResetSystem(EfiResetWarm)` 兜底；兜底也返回则正常继续交接。
- **k=1（温复位后次轮）**：Row 9 画 `PSCI SURVIVED`，**不写新槽、
  不复位**，正常交接。
- **k≥2 或异常**：Row 9 画 `PSCI ODD k=%d`，不复位，正常交接。

既有读回行（WIN/EXC/PROG/PRB/SLT/VAR）与全部写点保留不动；
DarwinBoot.c 相对 M3H 的 diff 只有本探针一块（PSCI 助手函数 +
Boot 内一块），纯新增零删改。

## 防循环论证

固件自发复位只发生在 k=0 分支，且该分支至多写入槽 0。若复位后
记录存活，次轮必为 k=1 分支——该分支无任何写、无复位，正常交接
（其后本轮主流程的 ZeroMem 会按基线行为清掉该页，但结论已在屏
上给出；再次武装需要人工长按强启后的新一轮，不构成自动循环）。
若记录未存活，次轮再见 k=0 而重新武装复位——这是**预期的诊断
签名**（见判读），且每圈都有 15 秒 ARMED 驻留可供介入；止损路径
为 fastboot 切回 A 槽（ABL 阶段按键可进，与历轮止损相同）。

## 真机判读

- 次轮 Row 9 见 `PSCI SURVIVED` ⇒ **温复位保 DRAM 成立**，看门狗
  读回与复位型通道的地基可用。
- 设备自发复位成循环、每轮只见 `PSCI TEST ARMED` ⇒ **温复位同样
  丢 DRAM**，槽恒空；长按进 fastboot `set_active a` 止损并回报。
- ARMED 驻留后不复位 ⇒ PSCI 未触发：有 `PSCI NOFIRE` 行且随后
  正常交接 = SMC 与 ResetSystem 兜底均返回未复位；无 NOFIRE 行
  而设备自行重启 = 兜底（ResetSystem）生效。
- `PSCI ODD k=%d` ⇒ 槽内容结构异常（乱序写入），不复位、正常
  交接，拍照回报 k 值另议。

## 构建实测（2026-10-31）

- 构建前隔离复核：产品树 DarwinBoot EL 门仍 `(DarwinCurrentEl()
  != 4)` 单条件、DarwinBoot.c/Entry.S 中 EL2 字样 0；产品 FDF
  （SurfaceDuo1.fdf）含 FvSimpleFileSystemDxe；台架改动未混入；
  emptyramdisk 仍 6 B 占位（MD5 `f02e326f…`）。
- stuart 全量重建一次 Success（logs/build-m3j-pscitest.log）。
- DarwinBoot.efi：21,504 B（M3H 版 20,992 B，+512 B），MD5
  `44f6efc5…`；`PSCI TEST ARMED`/`PSCI SURVIVED`/`PSCI NOFIRE`/
  `PSCI ODD k=%d` 各恰 1 次，既有读回格式串各仍恰 1 次；
  `movz 52800120`/`movk 72b08000`/`smc d4000003` 在 .efi 代码中
  各恰 1 次。UTF-16 字符串集相对 M3G 版 .efi 的增量恰为 M3H 的
  `M3Probe`、`SLT %s VAR %s` 与 M3J 的四条 PSCI 串，零删除。
- FVMAIN.Fv：Sheng 计数 ASCII/UTF-16 均为 0；PSCI 两主串各 1 次。
  bootpayload 解压流：偏移 56 `ARMd`、偏移 64 槽位三字
  `d2800006/f2b13606/f90000c0` 与 M3G 一致；解压流与 M3G 的 diff
  跨越 FV 区，系 .efi 增大 512 B 引起 FV 内布局移位所致，尾部
  DTB 段之后逐字节相同。
- 最终镜像（m3j/assemble.py，M3G 成品原位换固件段）：ramdisk 区
  与 M3G 逐字节相同，整镜像 diff 全部落在 ramdisk 起点之前；
  卷内 KERNEL MD5 `850602e628a864e6deea38b7d6c47a94`（M3G 补丁
  件）、KERNEL.ADT `8766bcb3…`、unixnu.toml `08ec0480…`。
  产物 `builds/lg-flash-unixnu-m3j-pscitest.img`，28,356,608 B，
  MD5 `95fb40a8082bb9d81f11ec2fd9c40cdd`，SHA-256
  `0a40f7c5061c2b9a0a6f6bc7605d4a2e2f9325294af1a6680d0de052ac94c8cf`。
