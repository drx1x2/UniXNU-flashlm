# M3L 判别 + 绕行（DIAGNOSTIC ONLY）

两件相互独立的事合并一刷，分别存档、互不耦合：

- **A. BootShim 最早读者拷贝**（固件线 = M3K + 本节）：
[bootshim-early-copy.patch](bootshim-early-copy.patch)（BootShim.S）、
[darwinboot-cpy-readback.patch](darwinboot-cpy-readback.patch)（DarwinBoot.c）。
- **B. locore 里程碑帧缓冲同轮标记**（内核 = M3G + 本节）：
[kernel-locore-fbmarks.md](kernel-locore-fbmarks.md)（几何、颜色表、
寄存器/映射证明、diff 总账都在那份里）。

固件相对 M3K 的 diff 仅 A；内核相对 M3G 的 diff 仅 B（各自在
assemble 阶段分开证明，见文末构建实测）。ADT/toml 与 M3C 逐字节一致。

## A 的问题设定

M3K 真机判读：`PRB NO / SLT NO / VAR NO / PSCI TEST ARMED` 数轮不变。
其中 PSCI 的现象最关键：固件亲手写下槽 0 并 `dc cvac` 清洁到 DRAM、
自发 PSCI 温复位，次轮窗口原位仍读不到——「温复位丢 DRAM」与
「次轮固件在 DarwinBoot 读回之前覆盖了窗口」两说未分。窗口 args 页
位于一块由 DXE 分配的常规内存窗口内（落点 0xC1004000），DarwinBoot
的 AllocateWindow 之前，DXE 完全可能把同一物理页先作他用再归还。
分开两说的唯一办法是把读取时刻推到固件的最前端：BootShim 入口。

## A 的机制

### BootShim 拷贝时序

```
复位 → PBL → ABL 早期初始化（DDR 训练/可能的清零 —— 嫌疑 1）
→ ABL 装载 boot.img、验签、跳入镜像头
→ BootShim _Start:

ldr [0xC1F14900] → str [0x89B00008] (窗口 PSCI 槽 0 拷贝)
ldr [0x89B00100] → str [0x89B00010] (SLT 原件拷贝)
原有: x0 → [0x89B00000]; FD 拷至 0x9FC00000; br FD
→ UEFI SEC/PEI/DXE（内存初始化与大量分配 —— 嫌疑 2：
窗口原位可在此被覆写；槽页是保留区、不可分配）
→ UniXNU 菜单 → DarwinBoot Boot():
AllocateWindow（落点仍 0xC1004000）→ 读回块读拷贝（Row 8 CPY）
与窗口原位（PRB/EXC/PROG）、SLT/VAR 原件 → ZeroMem → 各写点
→ 看门狗武装 → 交接
```

拷贝块 8 条指令（构建产物反汇编逐字验证）：`movz x6,#0x4900 /
movk x6,#0xC1F1,lsl#16`（拼 0xC1F14900）→ `ldr x7,[x6]` →
`movz/movk x6`（0x89B00000）→ `str x7,[x6,#8]` →
`ldr x7,[x6,#0x100]` → `str x7,[x6,#0x10]`。位于原 x0 槽存储
（`movz/movk/str x0,[x6]` 三字在产物中原样保留、整体移位 +32 B）
之前；只动 x6（原代码随即重装）与 x7（入口处无契约），x0/x1
不碰。BootShim 以物理地址运行、无页表依赖。BootShim.bin
128 B → 160 B，假 Linux 头魔数 `ARMd`@56 完好；组装后的最终镜像
解压流以新 shim 开头且拷贝字在偏移 64–92、原槽字在 96–104，
均已实证。

**前置条件与失效模式**：源地址是写死的 0xC1F14900 =
落点(0xC1004000) + 0xF10000(args 页) + 0x900(槽 0)。落点自
M3C 起经 WIN 行多轮实证恒定；若将来改窗口尺寸（ADT 的
darwinboot-memory-size）或内存图使落点变化，拷贝将读错页——
届时 CPY 恒 NO 而 PRB（按当轮实际落点计算）仍可工作，**CPY 与
PRB 背离即是该失效模式的签名**，须先修源地址再下结论。

### DarwinBoot 侧

- 新增 Row 8 `CPY %s %s`：第一值 = 槽 +0x08 拷贝与 PSCI 槽 0
magic `0x5053434900000000` 的比对；第二值 = 槽 +0x10 拷贝与
SLT magic `0x534C5431` 的比对。每轮必画。
- **PSCI 状态机的 k 改以拷贝值为据**：`Written = (拷贝 ==
槽 0 magic)? 1: 0`（拷贝缺失即 k=0）。异常判定保留 M3J
语义中仍可达的部分：窗口原位槽 1–7 任一持有自身 magic（乱序
写入）即 ODD；原「k≥2」分支因 k 现在至多为 1 而不可达。三个
分支本体（k=0 写窗口槽 0 + 清洁 + ARMED + 驻留 + PSCI 复位；
k=1 只画 SURVIVED、零写零复位；ODD 不复位）逐字未动；窗口槽 0
仍是武装分支的写目标——下轮 BootShim 正是从那里拷贝。
- 在最终 DarwinBoot.efi 中逐字实证：x24 拼 0x89B00008 为拷贝
基址，`ldr [x24]`（WIN 拷贝）与 PSCI magic 比较、`ldr
[x24,#8]`（SLT 拷贝）与 0x534C5431 比较、UnicodeSPrint 后以
Row 8 调 DiagDraw；M3H 的 SLT 写（[0x89B00100] ← 0x534C5431）、
PRB 写、VAR 调用与 M3K 看门狗四写序列（BARK 851890 → BITE
950185 → EN=1 → RST=1 + 回读）在新.efi 中全部原样在位。

### A 的判读矩阵

判读自**第二轮**起（首轮 CPY 反映的是 M3K→M3L 的 fastboot
刷机过渡，不作数）：

| CPY WIN | PSCI 行（Row 9） | 裁决 |
|---|---|---|
| OK | 次轮 SURVIVED | 记录活过复位 + ABL、BootShim 时刻已安全：**拷贝通道成立**，即为今后正道（状态机已改读拷贝）。若同轮窗口原位类读数（PRB 等）仍为 NO，则覆盖者在本轮固件内部（BootShim 之后、DarwinBoot 之前）一并坐实 |
| NO | 持续 ARMED 循环 | 上轮写值在 BootShim 入口已不存在：**记录死于复位本身或 ABL 早期初始化**（UEFI 代码运行之前）——跨轮 DRAM 在本机判死，后续定位只走同轮通道（B） |
| SLT 字段 OK / NO | — | 同理对 SLT 原件：CPY SLT OK 而 Row 7 的 SLT（DXE 后读原位）NO ⇒ 保留槽页在 DXE 阶段被覆写（出乎预期，指向 ABL 晚期或二次 shim）；CPY SLT NO ⇒ SLT 写值在 shim 前已死，与 M3H 的 NO 在温复位下互相印证 |

注：看门狗在位时，SURVIVED 轮交接后约 29 s 咬合复位，其次轮的
窗口槽 0 已被 SURVIVED 轮的 ZeroMem 清掉，故 ARMED 与 SURVIVED
将隔轮交替出现——这是预期节律，不是新故障；每轮的 CPY/PROG/
EXC 读数与 B 的屏上色块不受影响。

## B 的判读（摘要，全文见 kernel-locore-fbmarks.md）

交接冻结的同一帧里数屏幕**底部横带**的彩色块（左→右 =
红/蓝/品红/青/黄 = L0/L1/L2/L3b/L4）：亮起 n 个 ⇒ 内核已过第 n
个 locore 点、死在下一点之前；0 个 ⇒ 死在 `__start` 之前的交接
尾巴。此通道不依赖任何跨轮存活，与 A 的结论互不牵连。

## 构建实测（2026-10-31）

- 构建前基线/隔离：产品树 DarwinBoot.c 经「m3k 存档 M3J 源 +
看门狗补丁」重构与现状 MD5 逐字等合（M3K 态）；EL 门仍
`(DarwinCurrentEl()!= 4)` 单条件；DarwinBoot.c/Entry.S 中
EL2 字样 0；产品 FDF 含 FvSimpleFileSystemDxe；emptyramdisk
仍 6 B 占位（f02e326f…）；台架改动未混入。
- BootShim：`build_boot_shim.sh -b 0x9FC00000 -s 0x00300000`
重建（产物反汇编见上）；stuart 全量构建一次 Success
（logs/build-m3l-earlycopy.log，BUILD_EXIT=0）。
- DarwinBoot.efi：22,016 B，MD5 `2b20c944…`；`CPY %s %s` 在
.efi 与 FVMAIN.Fv 中各恰 1 次；既有全部诊断格式串各仍恰
1 次；FVMAIN 中 Sheng 计数（ASCII/UTF-16）为 0。
- bootpayload：gzip 流以新 160 B BootShim 开头；新 bootpayload
3,186,115 B。
- 内核：M3L MD5 `884949415562806d6df07261aa70f7fa`；与 M3G 的
diff 恰 91 词（5 重定向 + 86 FB 块词），与 pristine 的 diff
349 词（账目见 kernel-locore-fbmarks.md）。
- 组装（m3l/assemble.py）：ramdisk 取自 M3K 镜像、KERNEL 沿簇
链原位换 M3L 件；ramdisk 与 M3K 的 diff 全部落在 KERNEL 簇
内、簇外 0；整镜像与 M3K 的 diff 仅固件区 + KERNEL 簇；
KERNEL.ADT（8766bcb3571f…）与 unixnu.toml（08ec0480941c…）
与 M3C 逐字节一致；最终镜像卷内 KERNEL MD5 独立回读复验。
- 产物 `builds/lg-flash-unixnu-m3l-earlycopy.img`，28,356,608 B，
MD5 `e67e91eaa2939b1e99792ee29b742732`，SHA-256
`3fde6fc02b0a567798756a15ad840b91b2416b96dfc09024d8484c008a7be5e0`。

## 真机流程

刷入、切 B 槽、重启 → 首轮 ARMED 后约 15 秒自发复位（首轮 CPY
不作数）→ **次轮起**重点看三处并整屏拍照：Row 8 的 `CPY` 两值、
Row 9 的 PSCI 行（SURVIVED 即拷贝通道成立）、以及交接冻结帧
**底部横带**亮起的彩色块个数（0–5）。若次轮仍 ARMED 循环，
拍下含 Row 8 的整屏后长按止损——CPY 读数即为 A 的裁决。
