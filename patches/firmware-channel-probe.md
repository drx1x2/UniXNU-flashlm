# M3H 固件侧通道存活实验（firmware-channel-probe）

诊断专用，**不得带入正式镜像**。源码补丁：[darwinboot-channel-probe.patch](darwinboot-channel-probe.patch)
（对 DarwinBootPkg/Driver/DarwinBoot.c 与 DarwinBoot.inf 的纯新增 diff，基线 = M3G 构建树）。

## 背景与目的

M3G 真机判读为 PRB NO + PROG NONE：窗口内记录页（boot_args 页尾的
EXC/PROG/PRB 区）在真机上熬不过「长按电源+音量−强制重启」（分支 B 实锤）。
M3H 只回答一个问题：**两个窗口外候选通道，哪个能在同一强制重启流程下存活**，
供后续把里程碑/黑匣子记录迁出窗口时选址。固件-only 改动；内核与 payload
与 M3G 逐字节一致（见文末同一性证明）。

## 通道一：SLT（BootShim 保留槽页）

| 项 | 值 |
| --- | --- |
| 地址 | 物理 `0x89B00100`（保留槽页 `0x89B00000` 的 +0x100） |
| magic | u64 `0x534C5431`（'SLT1'） |
| 读点 | `Boot()` 读回块内（PROG 块之后、窗口 ZeroMem 之前），volatile 直读该 PA（UEFI 恒等映射） |
| 写点 | `Boot()` 底部、PRB 写点同段（本轮窗口填充后、DarwinEnter 前），volatile 直写 |

独占性复核（构建前全树检索）：字面 `0x89B00100` 在 unixnu-core /
aloha-full Platforms / MU_BASECORE 中零命中（本补丁引入后唯一使用者即
DarwinBoot）；槽页其余使用者只有 BootShim.S（`str x0,[x6]` 单次 8 字节写
+0x00）与 UniXNURamDiskDxe.c（`DTB_POINTER_SLOT` 只读 +0x00）；
PlatformMemoryMapLib.c 只有区域描述、无写访问。故 +0x100 无其它写者。

## 通道二：VAR（UEFI 非易失变量）

| 项 | 值 |
| --- | --- |
| 变量名 | `L"M3Probe"` |
| VendorGuid | `8d0451b3-add8-4e53-8197-d7846ae14131` = `{ 0x8d0451b3, 0xadd8, 0x4e53, { 0x81, 0x97, 0xd7, 0x84, 0x6a, 0xe1, 0x41, 0x31 } }`（本轮生成、固化于 DarwinBoot.c 的 `mM3ProbeVariableGuid`，读写共用） |
| 属性 | `EFI_VARIABLE_NON_VOLATILE \| EFI_VARIABLE_BOOTSERVICE_ACCESS \| EFI_VARIABLE_RUNTIME_ACCESS`（0x7） |
| 载荷 | 8 字节，u64 `0x56415231`（'VAR1'） |
| 读点 | 同 SLT 读点：`gRT->GetVariable`，成功且长度 8 且载荷等于 magic 才记 OK |
| 写点 | 同 SLT 写点：`gRT->SetVariable`，返回值丢弃 |

服务可用性：本固件构建含 MdeModulePkg 的 `VariableRuntimeDxe`
（M3G BUILD_REPORT 在册），变量服务在静态层面存在；DarwinBoot.inf 为此
新增 `UefiRuntimeServicesTableLib` 以取 `gRT`。全路径防御式：`gRT`/函数
指针为空、GetVariable 任何错误（NotFound/长度不符/载荷不符）一律记 NO，
SetVariable 失败静默忽略，**任何错误不得影响启动流程**。变量后备存储
是否真非易失（FVB 是否落盘到 UFS 分区）正是本实验要测的未知项。

## 上屏

读回块新增 Row 7 一行，每轮必画：

```
SLT %s VAR %s      （%s ∈ {OK, NO}）
```

既有行（Row 0 DB 0、Row 2 WIN、Row 3/4 EXC、Row 5 PROG、Row 6 PRB）
位置与行为全不动。`SLT %s VAR %s` 与 `M3Probe` 在 DarwinBoot.efi 中各恰 1 次。

## 真机判读（流程与 M3G 相同，两轮）

1. 刷入 M3H、切 B 槽、重启：第一轮 Row 7 必为 `SLT NO VAR NO`
   （两个通道此前从未写过），内核照常冻结；
2. 等 30 秒，长按电源+音量−强制重启回 B 槽；
3. 第二轮读 Row 7：
   - `SLT OK` ⇒ 保留槽页在强制重启后存活，可作迁出窗口的记录通道；
   - `VAR OK` ⇒ UEFI 变量存储真非易失且跨轮可读，可作记录通道；
   - 两者皆 NO ⇒ 两候选均不可用，通道选址需另议（更早的固件阶段
     留痕或其它保留区）。

## 同一性证明（M3H 构建实测）

- stuart 全量重建一次 Success（logs/build-m3h-channel.log）；构建前基线
  复核：产品树 DarwinBoot EL 门仍 `!= 4` 单条件、EL2 字样 0；产品 FDF
  含 FvSimpleFileSystemDxe；台架（qemu-debug）改动未混入；
  emptyramdisk 仍 6 B 占位（MD5 `f02e326f…`）。
- DarwinBoot.efi：尺寸与 M3G 版同为 20,992 B；MD5 由 `e2d272b5…` 变
  `ccfa2df7…`；UTF-16 字符串集与 M3G 版之差恰为新增的
  `SLT %s VAR %s` 与 `M3Probe` 两条（29 → 31 条），其余诊断格式串
  各恰 1 次；变量 GUID 字节在 .efi 中恰 1 次；FVMAIN.Fv 内
  Sheng 计数 ASCII/UTF-16 均为 0。
- bootpayload 解压流指纹与 M3G 一致：偏移 56 `ARMd`、偏移 64 三字
  `d2800006/f2b13606/f90000c0`（BootShim 槽位存储）；尾部 DTB 段与
  M3G 逐字节相同。
- 最终镜像由 M3G 成品原位换固件段组装（m3h/assemble.py）：payload
  卷取自 M3G 镜像原样，整镜像与 M3G 的 diff 全部落在 ramdisk 起点
  之前（头页 + bootpayload 区），ramdisk 区逐字节相同；卷内 KERNEL
  MD5 `850602e628a864e6deea38b7d6c47a94`（M3G 补丁件）、KERNEL.ADT
  `8766bcb3…`、unixnu.toml `08ec0480…`，均与 M3C/M3G 一致。
