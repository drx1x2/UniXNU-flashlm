# M3V — 飞行记录仪（trace strip）：一刷看全 P4→P5 路径（DIAGNOSTIC ONLY）

**动机**：M3U2（v3.5.2）真机读侧成立，终点钉在 P4（`_pmap_bootstrap` 入口）之后、
P5（`PE_init_printf` 返回）之前。旧办法一刷只得「最后到达的一个 ID」，要一轮轮二分。
M3V 让监控核把内核依次经过的每个桩**按顺序**画成一串色块：一刷得到整条路径，
最后一格就是终点所在的调用。

## 组成

| 件 | 位置 | 作用 |
| --- | --- | --- |
| 监控 blob v3.6 | `tools/m3v/monitor36.S`（1588 B） | v3.5.2 全部保留（前导、S1–S4、row-3 五格）；新增 trace 条带 + ID 0x20–0x2F 调色板 |
| DarwinBoot | `patches/darwinboot-cpuon-monitor.patch` | 嵌 v3.6；CPU_ON 前 `ZeroMem` + `dc civac` trace 环（args PA `0xC1F14980`，0x80 B） |
| 内核桩 | `tools/m3v/patch_trace.py IN OUT` | 在 15 个点插 24 字的桩；在现役（M3U）内核上叠加 |
| 门 | `tools/m3v/gate36.py` | A 补丁 blob 一致；B v3.5.2 前导回归；C 阶段一权限走查（含环与条带）；D Unicorn 跑主循环 4 个场景 |

## trace 环（args 页 +0x980..+0x9FF）

全仓检索 `0x980`/`0x988`/`F14980` 零命中（已用：+0x800 EXC、+0x848 PROG、+0x860 PRB、
+0x868 M3N、+0x880 SIG、+0x900 M3J）。

| off | 内容 |
| --- | --- |
| +0x980 | u64 n：trace 命中计数（桩自增） |
| +0x988 + (n−1) | u8 ID（n ≤ 0x78 才写，越界只计数） |

监控核在 args 1 GiB 块上只读（AP=11），故由 DarwinBoot 在 CPU_ON 前清零。

## 内核桩（24 字，只动 x16/x17 与 NZCV）

```
x16 = PROG (args+0x848)            ; 与 M3F 同：magic、latest ID、count++ → row-3 idx1 照常显示最新 ID
x16 += 0x138                        ; → args+0x980
n = [x16] + 1 ; [x16] = n
if n <= 0x78: byte[x16 + 7 + n] = ID
dsb ish
<被替换的原指令>                     ; bl / adrp 按桩 PC 重编码（脚本校验原目标不变）
b 原址+4
```

插点全是调用返回点或循环出口：x16/x17 是调用破坏寄存器、NZCV 在调用后已死；
每点后 16 条指令内无 x16/x17/NZCV 读（已用 llvm-objdump 逐点核对）。循环体内的
`pmap_init_pte_page` 返回点刻意不用，改用两个循环的**出口**，避免一个点刷满环。

## 15 个点（ID → 颜色 = 条带上的格色）

| ID | 色 | VA | 含义 |
| --- | --- | --- | --- |
| 0x20 | 红 FF0000 | 0xFFFFFFF0073BB454 | pmap_bootstrap：SecureDTGetProperty 返回 |
| 0x21 | 橙 FF8000 | 0xFFFFFFF0073BB4F4 | pmap_bootstrap：**pmap_data_bootstrap** 返回 |
| 0x22 | 黄 FFFF00 | 0xFFFFFFF0073BB57C | pmap_bootstrap：bzero 返回 |
| 0x23 | 黄绿 80FF00 | 0xFFFFFFF0073D89C4 | arm_vm_init：pmap_bootstrap 返回 |
| 0x24 | 绿 00FF00 | 0xFFFFFFF0073D8B28 | arm_vm_init：第一个建表循环退出 |
| 0x25 | 春绿 00FF80 | 0xFFFFFFF0073D8C60 | arm_vm_init：第二个建表循环退出 |
| 0x26 | 青 00FFFF | 0xFFFFFFF0073D8CB8 | arm_vm_init：_enable_preemption 返回 |
| 0x27 | 天蓝 0080FF | 0xFFFFFFF0079A195C | arm_init：arm_vm_init 返回 |
| 0x28 | 蓝 0000FF | 0xFFFFFFF0079A1974 | arm_init：PE_consistent_debug_inherit 返回 |
| 0x29 | 紫 8000FF | 0xFFFFFFF0079A1978 | arm_init：serial_init 返回 |
| 0x2A | 品红 FF00FF | 0xFFFFFFF0079A1984 | arm_init：**kernel_startup_initialize_upto** 返回 |
| 0x2B | 玫红 FF0080 | 0xFFFFFFF0079A1990 | arm_init：第一个 kprintf 返回 |
| 0x2C | 白 FFFFFF | 0xFFFFFFF0079A1A6C | arm_init：kern_feature_override 返回 |
| 0x2D | 灰 808080 | 0xFFFFFFF0079A1A94 | arm_init：switch_to_serial_console 返回 |
| 0x2E | 棕 804000 | 0xFFFFFFF0079A1AA4 | arm_init：PE_create_console 返回 |

（P5 仍是原 M3F 桩，只走 PROG、不进环：idx1 变 P5 粉色即过了 PE_init_printf。）
坐标取自 CI run 41150570344 的 `mach.development.bcm2837`（MD5 af7a0bf2…），
对 pristine 跑 `patch_trace.py` 改动恰 375 字（15 入口 + 15×24），逐点反汇编核对
（入口 b→桩、桩尾 b→原址+4、重编码指令目标与原指令一致）。

## 画面

- **条带**：菜单区「drivers … loaded」那一带，y=2680 与 y=2736 两行，每行 15 格，
  格 80×40 px，横距 96 px，起点 x=16。启动后先全画暗灰 `#303030`（30 个空格），
  之后每命中一次就把下一格涂成该 ID 的颜色——**从左到右、先上行后下行**即执行顺序。
  只显示前 30 次命中（环里存 120 次）。
- **row 3**：与 v3.5.2 完全相同（idx4 S1–S4、idx0 心跳、idx1 最新 PROG ID——trace ID
  也按上表颜色显示、idx2/idx3 签名）。

## 预登记判读

| 条带 | 结论 |
| --- | --- |
| 全暗灰 30 格 | 没有任何 trace 桩命中：死在 P4 入口与 0x20 之间（pmap_bootstrap 前段：lck_grp_init、PE_parse_boot_argn、kprintf、lck_rw_init、DT 查找）|
| 红 橙 … 第 k 格止 | 死在第 k 格的点与表中下一个点之间的代码里 |
| 走到棕（0x2E）且 idx1 仍棕 | 死在 PE_init_printf 本体 |
| idx1 变 P5 粉 | 过了 PE_init_printf，终点在 P5 之后（与 M3U2 结论冲突，先复核） |
| 同一颜色重复多格 | 该点被重复执行（意外回环），本身就是线索 |
| 条带画面不变（连暗灰都没有）| v3.6 没跑到主循环：看 row-3 idx4 阶段色 |

## 风险/未覆盖

- 桩经 args 页内核 VA 写；P4 已证该 VA 在换根后可写。arm_vm_init 完成后若该映射
  属性变化导致写异常，M3E 黑匣子会复位——那本身也是读数（会表现为复位而非静默）。
- `patch_trace.py` 要求插点仍是 pristine 字、洞内有连续 360 字 NOP，否则拒绝、不盲写。
- **洞窗（2026-11-01 修订）**：现役 M3U 内核的 A32 洞已被 M3E/M3F/M3S 占满（最大空段
  24 字），故加第二洞窗 `0x…73E048C..0x…73E1000`：start.s 在 `__start`（`b _start_first_cpu`）
  之后、`_LowExceptionVectorBase` 之前的 `.align 12` 填充，733 字。pristine 核实：纯 NOP、
  无符号、全核无 b/bl/adr/adrp 落点；同在 `__TEXT_EXEC,__text`（本核无 `__TEXT_BOOT_EXEC`，
  不会被回收）。两端各留 1 个 NOP 守卫。唯一外部引用是 `ArmCpu::startCPU` 对
  LowResetVectorBase 起 64 KiB 做 cache 清理（副核启动，P5 之后），对桩无影响。
  **不用**：`0x…73E0004` 段（LowResetVectorBase 页，副核入口）与 `0x…73E1784` 段（异常向量表内）。
  模拟「洞一占满」后桩落在 `0x…73E0A58..0x…73E0FF8`，375 字改动、逐点反汇编核对 PASS。
- 不腾退 M3F 桩阵列：P5 判读与 idx1 依赖它；不去掉桩内 PROG 三写：idx1 显示最新 trace ID 靠它。
- Unicorn 只能跑关 MMU 的降级路径；开 MMU 后的条带写由 Gate C 权限走查覆盖。

## 真机读数 #1（2026-11-01，p4p5 点集）

用户逐格测像素：第一行 1–12 格红→玫红全亮，第 13 格 (255,246,255) = **0x2C 白**；
第 14/15 格暗值互等 = 未命中暗灰（不是 0x2D 命中灰 808080）；第二行全空。
row-3 idx1 显白 = 最新 PROG ID 0x2C（v3.5.2 旧色表外 → 白），两通道互证。

**判读**：0x20–0x2C 全部按序命中，没有重复格 → pmap_bootstrap、arm_vm_init 全尾段、
serial_init、kernel_startup_initialize_upto、kprintf、kern_feature_override 全都过了。
0x2D 未命中**不说明死在 switch_to_serial_console**：`0x…79A1A74..1A80` 三个条件分支在
非串口路径上直接跳到 `0x…79A1AA0`（`bl _PE_create_console`），而 switch_to_serial_console
本身是 5 条指令的赋值函数。0x2E（PE_create_console 返回）未命中 ⇒
**终点 = PE_create_console 内部（含它尾调的 initialize_screen）**。

**头号嫌疑**：PE_create_console 第一件事是 `ml_io_map_wcomb(0x3C0FC000, 0x4000)` 并立刻
`ldr w8, [x0]` 比对魔数（'CRTB'/'CMHS'/'KNUF'），不匹配再 bzero 整 16 KiB。0x3C0FC000 是
bcm2837（RPi3，RAM 0–1 GiB）上靠近 RAM 顶的物理地址；在 SM8150 上它不是 DRAM（DRAM
从 0x80000000 起），落在无主外设空间——高通 NoC 对无主访问常见表现是总线挂死或
异步 SError（早期 DAIF.A 屏蔽 ⇒ 静默）。与「静默停住、无复位」吻合。未证实，下一刷验证。

## M3V2：console 点集（`patch_trace.py --set console`）

ID 复用 0x20 起的调色板（监控/DarwinBoot 不变，只换内核）；**一个镜像只打一个点集**，
打在现役 M3U 内核上（不是叠在 p4p5 trace 内核上）。13 点 × 24 字 = 325 字改动，模拟
「洞一占满」时落在第二洞窗 `0x…73E0B18..0x…73E0FF8`，逐点反汇编核对 PASS；每点之后
直到下一个置标志指令/分支前，无 NZCV 读、无 x16/x17 读（脚本化核对）。

| ID | 色 | VA | 含义 |
| --- | --- | --- | --- |
| 0x20 | 红 | 0x…793CBE8 | ml_io_map_wcomb(0x3C0FC000) 返回（只建映射） |
| 0x21 | 橙 | 0x…793CC10 | **第一次读 0x3C0FC000 返回** |
| 0x22 | 黄 | 0x…793CC48 | 'KNUF' 分支的 printf 返回（多半不走） |
| 0x23 | 黄绿 | 0x…793CC58 | bzero 完成 / 魔数匹配汇合，将尾调 initialize_screen |
| 0x24 | 绿 | 0x…73AFF94 | initialize_screen 入口 |
| 0x25 | 春绿 | 0x…73B018C | ml_io_map_unmappable 返回 |
| 0x26 | 青 | 0x…73B01B4 | lck_spin_lock 返回 |
| 0x27 | 天蓝 | 0x…73B0380 | lck_ticket_init 返回 |
| 0x28 | 蓝 | 0x…73B0540 | vc_progress_set 返回（第 1 处） |
| 0x29 | 紫 | 0x…73B05F4 | gc_enable 返回 |
| 0x2A | 品红 | 0x…73B06C4 | thread_call_enter_delayed 返回 |
| 0x2B | 玫红 | 0x…73B07BC | vc_progress_set 返回（第 2 处） |
| 0x2C | 白 | 0x…73B087C | initialize_screen 走到最终 ret |

initialize_screen 内分支多（按 op 走不同路径），中间点不全命中是正常的；看**最后一个命中格**。

| 条带 | 结论 / 下一步 |
| --- | --- |
| 只有红 | 死在第一次读 0x3C0FC000 ⇒ 证实嫌疑；修法：把该 PA 改指 DRAM 内一块保留区（或跳过 panic-log 魔数段），需选定安全 PA |
| 红 橙 停 | 死在 bzero 0x3C0FC000（写侧）⇒ 同上 |
| 走到黄绿/绿之后 | panic-log 段无辜；终点在 initialize_screen，按最后命中格缩小 |
| 白（0x2C）也亮 | initialize_screen 返回了 ⇒ 与读数 #1 矛盾，先复核 |

## 真机读数 #2（2026-11-01，console 点集）

第 1 格 (255,74,63) = 0x20 红，其余全暗灰；row-3 idx1 同为红（最新 ID 0x20）。
⇒ `ml_io_map_wcomb(0x3C0FC000)` 返回了，**第一次读 0x3C0FC000 再没回来**（0x21 未命中）。
嫌疑坐实：PE_create_console 用 bcm2837 遗留 panic-log 物理地址，在 SM8150 上读到非 DRAM
地址，总线挂死。这就是 M3 一路追的「静默停住、不复位」的直接原因。

## M3W：改址修复（`tools/m3v/fix_console_pa.py`）

一字修改：`0x…793CBDC` `movk w0, #0x3c0f, lsl #16`（0x72A781E0）→ `movk w0, #0x9d1f, lsl #16`
（0x72B3A3E0），PA 变 **0x9D1FC000**：

- 属 "Display Reserved"（0x9C000000 + 18 MiB，PlatformMemoryMapLib.c）最后 16 KiB——非安全
  DRAM，ABL 已为显示保留；
- 在内核托管内存之外（physBase ≈ 0xC1000000），不会与页分配器冲突；
- 在可见帧缓冲之后（0x9C000000 + 3120×5760 = 0x9D122000），bzero 不出现在屏幕上；
- 全核唯一的 0x3c0f 立即数；与 `patch_trace.py` 改动的字不相交，可叠加。

**建议下一刷**：现役 M3U 内核 → `fix_console_pa.py` → `patch_trace.py --set console`
（模拟叠加共 326 字改动，反汇编核对通过）。

| 读数 | 结论 |
| --- | --- |
| 条带过了红、橙继续亮 | 修复生效（读 0x9D1FC000 返回）；看最后命中格定位 initialize_screen 内的下一终点 |
| 白（0x2C）也亮且 idx1 变 P5 粉/更后的 M3F 里程碑 | PE_create_console 与 PE_init_printf 都过了，终点后移到 P5 之后 |
| 仍只有红 | 读 0x9D1FC000 也挂 ⇒ 不是「地址不是 DRAM」这么简单（属性/映射问题），回到反汇编 ml_io_map_wcomb |

**源码层待办**（M4 线必须做，M3 可先用二进制修复）：上游 xnu `pexpert/arm` BCM2837 路径
硬编码了这个 panic-log 地址；应在 ci/0019 的 xnu 补丁里改成按板配置（或在 flashlm 上关闭），
不能把二进制修复带进 16K 单体内核线。

## 真机读数 #3（2026-11-01，M3W + console 点集）

条带红→橙→黄绿→绿→春绿→蓝→白；row-3 idx1 紫 (168,28,244) = P2 第二次调用（P5 先亮后被覆盖）。
⇒ **M3W 修复真机生效**，PE_create_console / initialize_screen / PE_init_printf 全过；M3 原始冻结治愈。
设备「一闪而过、自动重启」并回到菜单。**更正（同日构建侧机检）**：现役内核不含 M3D（M3F 重建诊断栈时
未带入，_panic 为原版序言 0xd10083ff，0x…73E1010 全 NOP），所以复位不是 panic 改道。仍在役的复位源：
M3E 异常记录器 + PSCI 尾（0x…73DC710–71C）——快速复位首选此解释，面包屑应已写下；若配方含 M3K，
挂死（含纯 panic 自旋）约 29 s 后看门狗 bite 也会复位。用循环菜单帧第 3–4 行（EXC）和复位间隔区分。
新终点：P2 第二次之后、P9 之前（machine_startup / bootstrap 区段）。

## M3X：panic 现场记录（`tools/m3v/panic_rec.py`）

M3D 的 `_panic` 入口 `b 0x…73E1010` 改指向 0x…73E0500 的 28 字记录器，按 M3E 面包屑格式写
args VA 0xFFFFFFF007F14800，再落 M3D 的 PSCI 尾。现有 DarwinBoot crumb readback 下一轮画在
DiagDraw 第 3–4 行：

| 行 | 内容 |
| --- | --- |
| `EXC 50 ESR <x1>` | CODE 0x50 = panic（M3E 向量码是 0/3/4/7/C4–C6，不会混）；ESR 槽放 panic 第一个参数 |
| `ELR <x30> FAR <x0>` | x30 = 调用 panic() 的返回地址；x0 = panic 格式串 VA |

与 M3E 记录器差别：不读系统寄存器；复位前对两条面包屑缓存行 `dc civac` 到 PoC，防温复位丢行。
29 字改动；`as` 汇编、补丁后反汇编核对（_panic → 0x…73E0500，尾跳 0x…73E1010）。

叠加顺序：现役 M3U → `fix_console_pa.py` → `panic_rec.py --install-m3d` → `patch_trace.py --set console`
（现役无 M3D，`--install-m3d` 同时铺 M3D 的 4 字 PSCI 尾；分支字与记录器改的是同一字，总账 359 字，模拟通过；
产物与「先装历史 M3D 再跑 panic_rec」逐字节相同）。已含 M3D 的输入不带该参数（355 字）。
panic_rec 占 cave 2 低端，patch_trace 从高端分配，不冲突；输入不含 M3D 时脚本拒绝。

**先看现有读数**：若当前循环的菜单帧第 3–4 行已经有 `EXC` 行（CODE 0/3/4/7/C4–C6），说明是
M3E 记录的异常复位，不必刷 M3X，直接按 ELR/FAR 判读。

## 无记录复位路径排查（2026-11-01，主机侧静态）

现役内核全核只有 6 处 `smc #0`、1 处 `hvc #0`：
- `ArmCpu::startCPU`（0x…795FDC4 smc / 0x…795FDCC hvc）：PSCI CPU_ON 0xC4000003，非复位。
- `ArmDTPlatform::configure` 里 **5 处直接 PSCI SYSTEM_RESET**（0x84000009），不经 `_panic`、不进异常向量，
  M3E/M3X 都钩不到，均由 boot-args 控制（`[sp,#0xc]`/`[sp,#0x8]` 先清零，未设置时不触发）：

| smc VA | 触发条件 | 位置 |
| --- | --- | --- |
| 0x…795D96C | `sheng-platform-stage=1` | hasNVRAMProxy 通过后 |
| 0x…795D9F0 | `sheng-platform-stage=2` | 下一步检查后 |
| 0x…795DBD4 | `sheng-platform-stage=3` | createDeviceNubs 成功后 |
| 0x…795DC60 | `sheng-platform-panic≠0` 或 `stage=4` | 发布前 |
| 0x…795DC40 | `sheng-platform-stage=5` | vtable+0x2A0 调用后 |

即上游 UniXNU 的「阶段到达即复位」二分开关。若 DarwinBoot/菜单传的 boot-args 含 `sheng-platform-*`，
快速无记录复位 = 内核已到 IOKit 平台 configure（大进展），而不是死亡。其余无记录类：未钩向量槽
（1/2/5/6 IRQ/FIQ、8–15 低 EL）；EL3/TZ 侧复位（XPU 违规等，非安全世界看不到）。

(b) 读回通道：M3F 的 PROG 由内核按可缓存映射写、无 `dc civac`；M3J 只证明了**固件写**的 DRAM 跨温复位存活。
本轮 monitor 相干读到 P2（idx1 紫）而读回报 `PROG NONE` ⇒ 至少 PROG 这条「内核写→温复位→固件读」链未通，
优先怀疑脏行随复位丢失（M3E 记录器同样只有 dsb）。判别：在已确认到达的点放一个「写面包屑 + dc civac + PSCI 复位」金丝雀。

## M3Z：跨复位读回通道金丝雀（`tools/m3v/canary.py`）

用户侧核实：boot-args 无 `sheng-platform-*`（mkadt /chosen 无 boot-args 属性；DarwinBoot 命令行只来自
payload toml，无 args 字段），configure 的 5 处复位未武装。(a) 余：未钩向量槽、EL3 侧复位。canary 判 (b)。

`initialize_screen` 的 `ret`（0x…73B087C，读数 #3 确认到达）→ `b 0x…73E0500`；35 字金丝雀按 M3E 格式写
args VA 0xFFFFFFF007F14800（CODE 0xEE、ESR 0xC0FFEE01/00、ELR=0x…73B087C、FAR 0xCA4A），
变体 C 对两条缓存行 `dc civac`，变体 N（`--no-clean`）同位换 nop，然后跳 M3E PSCI 尾 0x…73DC710。

配方：现役 M3U → `fix_console_pa.py` → `canary.py`（不叠 `--set console`、不叠 `panic_rec.py`，脚本门禁拒绝）。
合计 37 字。门禁：ret 原字、M3E 尾 4 字、NOP 区逐字核对；合成底稿（原版+M3E 尾）模拟、反汇编核对通过。

| 读回第 3–4 行 | 结论 |
| --- | --- |
| C：`EXC ee ESR c0ffee01` / `ELR fffffff0073b087c FAR ca4a` | 内核写 + 清到 PoC 能跨温复位；再刷 N 判缓存 |
| N 也出现 | PSCI/EL3 会刷缓存，(b) 不成立 ⇒ 回 (a)：钩剩余向量槽 / 查 EL3 复位 |
| N 不出现 | 脏行随复位丢失 ⇒ M3E 记录器与 PROG 写补 `dc civac` |
| C 不出现 | 固件侧读回通道坏（地址 / 时序 / XBL-ABL 清内存），PROG NONE 同因，先修通道 |

设备行为：每轮在 initialize_screen 返回时立即复位（数秒内回菜单），属预期。

## 金丝雀 C 读数（2026-11-01）：第 3–4 行空、PRB 恒 NO ⇒ 跨轮通道死（与 M3L 一致）

写侧已到可验证极致（哨兵、契约、提交字最后、两行 civac、PSCI 尾确实执行），次轮仍空；PRB（固件同公式
自写自读）从未 OK。这与既有裁决完全一致：M3K PSCI 自测试 ARMED 循环、M3L `CPY NO NO`（BootShim 在镜像入口、
早于全部 UEFI 拷出的探针也空）——跨轮 DRAM 在本机死于复位本身或 ABL 早期初始化（m3m-flow.md 已关闭此线）。
M3X/M3Z 依赖跨轮读回是我方失误；3273151 的 readback-hold 补丁无意义，已删。

此后只用**同轮**通道（M3V 监控色带）。下一步 M3Z2 `tools/m3v/halt_tail.py`：把现役 M3E PSCI 尾首字
`mov w0,#9` 改 `b .`（1 字），M3E 记录器（审计后内核唯一武装的复位路径）改为原地停住，色带留屏。

    python3 tools/m3v/fix_console_pa.py M3U_KERNEL M3W_KERNEL
    python3 tools/m3v/halt_tail.py M3W_KERNEL HALT_KERNEL

| 现象 | 裁决 |
|---|---|
| 不再复位，停在色带 | 复位来自内核自身 M3E 异常尾：P2#2..P9 之间有异常；下一步同轮给异常上色（ESR EC/ELR 低位编码进色带） |
| 仍在数秒内复位 | 复位不经内核武装路径：EL3/XPU/看门狗类外部复位；查 M3K 看门狗是否在位（应为 ~29 s）及 XPU 违例 |

## M3Z2 真机（2026-11-01）：秒级复位消失 ⇒ 内核异常经 M3E 尾；idx1 天蓝 (201,255,252) = P10

死点在 IOPlatformExpertDevice::init（P9 PE_init_iokit 之后），即 generatePlatformUUID 所在类。_panic 未被调用。
停住期间本轮 args 页 +0x800 的 M3E 面包屑仍在 ⇒ 同轮读出。

## M3Z3：监控 v3.7 同轮 EXC 读出（tools/m3v/monitor37.S，1872 B）

v3.6 + 每轮询检查 args+0x800 MAGIC1 / +0x840 MAGIC2，双匹配则在 y=2380 起画 6 行×32 位格（MSB 在左，
格 32×40 px、间距 40 px、每 4 位多 8 px；行距 50 px）：

| 行 | 内容 |
|---|---|
| 0 | ESR[31:0] |
| 1 | ELR[31:0] |
| 2 | ELR[63:32]（内核应为 fffffff0） |
| 3 | FAR[31:0] |
| 4 | FAR[63:32] |
| 5 | CODE[31:0]（M3E 向量槽号） |

颜色：1 = 白（偶数半字节）/黄（奇数半字节）；0 = 深灰 0x20 / 灰 0x50 交替。无记录则该区不画。
门禁 `gate37.py` A–E 全 PASS（E：有效/MAGIC2 坏/无记录三场景逐格比色、无越界）。
补丁 blob 已用 `swap_blob.py monitor37.bin` 换入 `darwinboot-cpuon-monitor.patch`（首 hunk +23 行）。

配方：固件 = 更新后的 cpuon-monitor 补丁重建 DarwinBoot；内核 = M3U → fix_console_pa.py → halt_tail.py（不变）。
拿到照片后按行读 32 位转十六进制；ELR 用 nm.txt/all.s 落函数，ESR EC 判类型。

## M3Z3 读数（2026-11-01）与 M3Z4

ESR 0x96000005（EL1 数据中止，读，L1 翻译故障），ELR 0xFFFFFFF00786AA40，FAR 0x28，CODE 0。
未剥离反汇编：ELR = `_sha1_init+0x34`：`ldr x20, [x22, #0x28]`，x22 = `g_crypto_funcs`（0xFFFFFFF0071AF598）= NULL。
不是设备树查找失败：调用者 `IOPlatformExpertDevice::generatePlatformUUID` 已经成功取到 `/chosen` 的
`unique-chip-id`（8 B）与 `chip-id`（4 B），于是走 SHA-1（v5 UUID）分支；而内核里没有任何代码调
`register_crypto_functions`——它的调用者是 com.apple.kec.corecrypto kext，M3 诊断内核不加载 kext，
故 corecrypto 函数表为空，+0x28（sha1 项）取空。ADT 是对的（M4 的 IOPlatformUUID 需要它们），不改。

M3Z4 `tools/m3v/uuid_skip.py`：0x...78D2DFC `b.ne`（0x54000941）→ `b`（0x1400004A），恒走「无 chip id」出口
（x21=0、释放 /chosen、不设 IOPlatformUUID），1 字。配方：M3U → fix_console_pa → halt_tail → uuid_skip，
固件沿 v3.7（保留同轮 EXC 读出）。

预期：越过 P10。风险：`g_crypto_funcs` 在内核中有 166 处引用（cpx AES、mptcp/ipsec HMAC、in6_cga 等），
后续任一被调用都会以同一形态（FAR 为小偏移、ELR 在 cc*/sha*/aes* 包装里）再死；届时根治是让 corecrypto
注册（M3 侧：内核内建表 + 调 register_crypto_functions；M4 的 iOS kernelcache 预链接 corecrypto kext，应不受影响——待验证）。

## M3Z4 读数与 M3Z5（corecrypto 表注册）

M3Z4 真机：越过 UUID；ESR 0x96000005、FAR 0x150、ELR 0x...786xxxx。按 xnu-8796.101.5 register_crypto.h，
+0x150 = `random_kmem_ctx_size_fn`，调用链 `kmem_crypto_init → crypto_random_kmem_ctx_size`（0x...786BFAC）。

M3Z5 `tools/m3v/crypto_reg.py`（源 crypto_reg.S）：initialize_screen 的 ret（0x...73B087C，P2 两次均先于 P9；
第二次注册返回 -1 无害）→ 0x...73E0500 桩调 `register_crypto_functions(&table)`。表 56 槽：
0x140 random_generate = cntpct 播种 xorshift64（**非安全随机**），0x148 uniform = cntpct % bound，
0x150 kmem_ctx_size = 256，0x158 kmem_init = 0；其余每槽独立陷阱：写 M3E 面包屑 CODE = 槽偏移、
ESR = 0xC0DE0000|槽、ELR = 调用者 x30、FAR = x0，再进 halt 尾停住 ⇒ v3.7 第 5 行直接报出下一个缺的槽
（对表：0x00–0x18 ccdigest_*，0x28 sha1_di，0x48–0x60 cchmac_*，0x160–0x1B8 digest/hmac 新接口）。
Unicorn 实跑：g_crypto_funcs = 0x...73E0780，四个活槽返回值正确，陷阱槽 0x28 记录 CODE 0x28 / ESR c0de0028 / 双 magic 后停在尾。

配方：M3U → fix_console_pa → halt_tail → uuid_skip → crypto_reg，固件 v3.7。与 canary/panic_rec/trace console 互斥。
下一步若陷阱报 digest/hmac 槽：内核自带 ccdigest_init/update、ccsha1_di、ccsha256_di、cchmac*，可逐槽接真实现。

## M3Z5 读数与 M3Z6（记录 LR）

M3Z5 真机：ESR 0x86000005（EC 0x21 取指中止，L1 翻译故障），ELR 0，FAR 0，CODE 0；陷阱未触发
（否则 ESR 为 c0de00xx）⇒ random_kmem 已越过，新死点是**经 NULL 函数指针的调用/跳转**。ELR/FAR 无信息，调用者只在 x30。
M3Z6 `tools/m3v/lr_rec.py`：把 M3E 记录器 0x...73DC6C0 的 `str x2,[x3,#0x18]`（FAR）改为 `str x30,[x3,#0x18]`（f9000c7e），
v3.7 第 4/5 行改读 LR（lo/hi）。配方：…→ crypto_reg → lr_rec，固件 v3.7 不变。LR−4 即 blr 处（若为 br 尾调用则 LR 是上一层返回点）。

## M3Z6 读数与 M3Z7（cckprng 函数表）

M3Z6 真机：LR = 0x...73B63A8 ⇒ blr @0x...73B63A4 在 `read_random`：`blr [prng+0x20]`（0x...7164480，cckprng refresh）为 NULL。
prng 全局 @0x...7164460：+0 initialized，+8..+0x30 = cckprng_funcs{init, initgen, reseed, refresh, generate(ctx,cpu,n,out), init_with_getentropy}，
ctx 指针 @0x...7B082B0；正常由 corecrypto kext 调 register_and_init_prng 填（M3 无此 kext）。
M3Z7 = crypto_reg.py 增补（不再调用 register_and_init_prng，避开早期 entropy_init 的 lck_mtx_init）：
reg 桩注册 crypto 表后直接写 funcs（generate→xorshift，其余 no-op 返回 0）、ctx=&table、initialized=1。
表移至 0x...73E07D0（代码 0x2D0 B，共 1168 B）。Unicorn：真实 read_random(buf,300) 跨 256 分块正确填充且不越界，random_cpu_init(1) 返回。
**全部随机数为非安全占位，仅用于诊断推进。** 配方不变：… → uuid_skip → crypto_reg → lr_rec（v3.7 第 4/5 行仍为 LR）。

## M3Z7 读数与 M3Z8（panic 同轮截停）

M3Z7 真机：所有旧死点一闪而过，然后秒级复位，M3E 没有记录；sheng 复位点未武装，M3E 尾仍停住 ⇒ 是新的复位路径。
首要嫌疑是真 panic 走了原厂路径：M3U 系没有 M3D，panic 的终点就是复位。
M3Z8 `tools/m3v/panic_halt.py`（源 panic_halt.S，23 字 @0x...73E0A00）：`_panic_trap_to_debugger` 入口（0x...726AC2C，panic/Assert/panic_with_options 共用）
→ 写 M3E 面包屑：CODE 0x50、ESR=x2(reason)、ELR=x6(panic 调用者)、FAR=x0(格式串 VA)，然后 wfe 死循环，不复位。
Unicorn：经 _panic 进入，面包屑字段正确，停在循环。配方 … → crypto_reg → lr_rec → panic_halt，固件 v3.7。
判读：CODE 50 ⇒ panic，按 FAR 查格式串、按 ELR 查调用者；如果仍然秒复位且没有记录 ⇒ 排除 panic，转向非 panic 复位源（PEHaltRestart / PSCI 直呼，或者记录器之外的异常）。

## M3Z9 / M3Z10：复位截停命中 stage-1，查 CommandLine 供值

M3Z9 `reset_halt.py`（d0789e3）真机读数 **CODE 0x63** = `ArmDTPlatform::configure` 第一处
`sheng-platform-stage==1` SYSTEM_RESET（0x…795D96C）。前置门：/cpus /arm-io /defaults /options
四节点齐 + `hasNVRAMProxy`（/chosen 的 CHRP NVRAM proxy）为真——它只是门，不供值。

供值链（反汇编 + 上游 UniXNU 文档 docs/xnu/boot-arguments.md 互证）：`PE_parse_boot_argn` →
`PE_boot_args()` = `PE_state.bootArgs + 0x6C` = `boot_args->CommandLine`；**不读 ADT /chosen**。
DarwinBoot 把菜单条目 `args`（+ 选中的 `confirm_args`）原样拷进 CommandLine。本仓 board.toml
`kernel_args` = `debug=0xc serial=3 cpus=8 keepsyms=1 rd=ufsroot0 wdt=-1`，不含 sheng；上游
`./unixnu payload` 还会合并 `unixnu.local.toml [build] kernel_args` 与 `--kernel-arg`。
注意：裸 token `sheng-platform-stage`（无 `=`）也解析为 1。之前「payload toml 无 args 字段」的结论有误：
make-flashlm-payload.py 会写 `args = "<kernel_args>"`。

M3Z10 `cmdline_peek.py`：把该 smc 改指 0x…73E0C00 的 57 字扫描器，尾跳 reset_halt 记录器：

| v3.7 行 | 含义 |
| --- | --- |
| CODE | 0x6A |
| ESR | 高 16 位 = strlen(CommandLine)，低 16 位 = `sheng-platform-stage` 偏移（0xFFFF = 没找到） |
| ELR | 名字后 8 字节，小端 ASCII（`=1 c…` 读作 `…63 20 31 3d`） |
| FAR | CommandLine 头 8 字节，小端 ASCII（正常应为 `debug=0x` = `0x7830 3d67 7562 6564`） |

判读：找到 ⇒ 供值在命令行，看 FAR/长度确认是哪份 toml（board / unixnu.local / confirm_args），从源头删；
没找到但仍到 0x63 ⇒ `PE_state.bootArgs` 指向的不是 DarwinBoot 那页或 CommandLine 被覆写，转查 bootArgs 指针。
配方：… → panic_halt → reset_halt → cmdline_peek，固件 v3.7。Unicorn：四种命令行（带 `=1`、裸 token、无、空）字段全对。

## M3Z11：P10 之后的色带二分（`patch_trace.py --set p10root`）

M3Z10 后 sheng 复位消失；约 29 s 后无记录复位 = M3K APSS 看门狗 bite（DarwinBoot 交接前武装，
`darwinboot-cpuon-monitor.patch` 里 `M3KWatchdogArm()` 仍在；内核从不喂狗）。**所以只要跑满 29 s
就一定被咬，bite 本身不代表挂死**——可能是正常进展到无 UFS 驱动的根设备等待（`rd=ufsroot0`）。
用色带看 29 s 内走到哪：v3.7 的色带是同轮实时画的，**在 bite 前（约 20–25 s）拍照**。

| ID | 色 | VA | 点 |
| --- | --- | --- | --- |
| 0x20 | (调色板 0x20) | 0x…793C7DC | PE_init_iokit：InitIOKit 返回 |
| 0x21 | | 0x…793C7E0 | PE_init_iokit：ConfigureIOKit 返回（平台专家已起） |
| 0x22 | | 0x…795FDD0 | ArmCpu::startCPU：CPU_ON 返回（每个副核一次，可连出多格） |
| 0x23 | | 0x…79797D4 | kernel_bootstrap_thread：PE_init_iokit 返回 |
| 0x24 | 绿 | 0x…7696434 | bsd_init 入口 |
| 0x25 | 春绿 | 0x…7696A68 | bsd_init：IOKitBSDInit 返回 |
| 0x26 | 青 | 0x…7916B48 | IOFindBSDRoot 入口（其后是根设备等待） |
| 0x27 | 天蓝 | 0x…745ECC0 | vfs_mountroot 入口 |

判读：末格停在 0x26 ⇒ 内核在等根设备，M3 的内核侧目标基本达成（下一步是 UFS/ramdisk 根）；
停在 0x20/0x21 之间 ⇒ IOKit 平台启动里挂（configure 之后的 start/匹配）；0x22 出现后不再前进 ⇒ 副核上线等待；
0x23→0x24 之间 ⇒ kernel_bootstrap_thread 中段（vm_commpage / mac_policy / startup 子系统）。
8 点 × 24 字 = 192 字：start.s 洞窗在 crypto_reg/panic_halt/reset_halt/cmdline_peek 之后约剩 197 字，刚好装下。
配方：… → reset_halt → [cmdline_peek 可留可去] → `patch_trace.py --set p10root`，固件 v3.7。
Unicorn：8 桩各自写 PROG 最新 ID、环 n=8 / `20…27`、回跳 entry+4 全对。
可选：固件去掉 `M3KWatchdogArm()` 一行，让终点画面常驻，不用卡时间拍照。

### M3Z11 真机（2026-11-02）
- cpus=8 两轮：`20 21 22` 停、`20 21 23` 停（7 个副核只回 1 个 CPU_ON 或 0 个）⇒ 首个副核上线即全停，副核 CPU_ON wedge。
- A/B `cpus=1`（ml_parse_cpu_topology 读 "cpus"）：`20 21 23 24` 停（无 22、无 25）⇒ 单核前沿进入 bsd_init，IOKitBSDInit 返回之前。

## M3Z12：bsd_init 内二分（`patch_trace.py --set bsdinit`，替换 p10root，二者只能选一）
保持 `cpus=1`。ID 0x20–0x27 依次：mac_policy_initbsd 返回 / bsd_bufferinit 返回 / vfsinit 返回 /
第 1、2、3 个 OSKextLoadKextWithIdentifier 返回（有条件加载，跳过会留空，以**末格**为准）/
dlil_init 返回（mbinit…nwk_wq 已过）/ 即将调用 IOKitBSDInit（网络、memorystatus、kminit 已过）。
末格 0x27 ⇒ 卡在 IOKitBSDInit 内；0x22→0x23 之间 ⇒ 卡在 kext 加载（预链接 kext 缺失时的等待）。
Unicorn：8 桩 ID、环、bl/adrp 重定位目标、回跳全对。副核 CPU_ON wedge 另案（startCPU / LowResetVector 入口）。

### M3Z12 真机：bsdinit 全暗；bsd_simul_execs 断言嫌疑复核（2026-11-02）
全暗 ⇒ 死在 bsd_init 入口与 mac_policy_initbsd 返回之间（构建与桩已由交付字节 Unicorn 复执排除）。
朋友嫌疑：0x…76965A4 `cbz` 断言 `bsd_simul_execs != 0`。复核（未剥离反汇编）：`_bsd_exec_setup` 虽无 `bl`
调用者，但 `_bsd_scale_setup` 在 0x…743CD3C **尾调用**（`b`）它，`_scale_setup` 又在 0x…72A9230 尾调用
`_bsd_scale_setup`，`_scale_setup` 由 startup 表（指针在 0x…7C4BE20）登记，在 bsd_init 之前的
kernel_startup_initialize_upto 中运行。写入值来自表 0x…7022DA0 = {33,33,65,65,129,129,257,257}，大于 7 时为 513，
**不可能为 0**。Unicorn 需种子是因为从 bsd_init 中途起跑、没跑 startup。断言嫌疑因此偏弱，但不排除 startup 未登记/未跑。

## M3Z13：bsd_init 头段二分（`--set bsdhead`，替换前两组，保持 cpus=1）
0x20 platform_stall_panic_or_spin 返回 / 0x21 throttle_init 返回 / 0x22 第 1 个 printf 返回（控制台路径）/
0x23 kauth_init 返回 / 0x24 proc_ro_alloc 返回 / 0x25 fdt_init 返回（锁初始化已过）/
0x26 第 2 个 printf 返回（zalloc_permanent 已过）/ **0x27 = 断言着陆点 0x…7696E40**（bsd_simul_execs==0，下一步 panic）。
同一刀既二分又直接检验断言：出现 0x27 ⇒ 断言坐实；0x26 后无 0x27 ⇒ 断言排除，死在 current_uthread/mac_policy_initbsd。
Unicorn：8 桩 ID、环 `20…27`、bl/adrp 重定位、回跳全对。

## M3Z14：副核 CPU_ON 卡死——对照 ios-raphael 的修复（`smp_clean.py` + `--set smp1`，一次刷机）

对照对象：github.com/marnov999/raphael-ios-gpu（K20 Pro，SM8150，XNU 自编，已实测 8/8 核：
`PSCI CPU_ON rc=0, SGI1 OK`）。逐项对照：

| 项 | raphael | 本仓（预编 bcm2837 诊断核） | 结论 |
| --- | --- | --- | --- |
| ADT cpu reg | MPIDR Aff1:Aff0（0x000…0x700） | 同（devices.py `cpu_regs`） | 一致 |
| reset_vector MPIDR 掩码 | 改成 `and #0xFFFF`（原 `#0xFF` 会把所有核认成 cpu0） | 本核已是 `#0xffff`（0x…73E0420） | 不是原因 |
| kryo 名字匹配 | SweetCPU 的 IONameMatch 由 kryo470 改为 kryo485 | ArmCpu 已 start、已走到 CPU_ON | 不是原因（ArmCpu 已匹配） |
| CPU_ON 入口 | 自带入口桩（DAIF、EL2→EL1 降级）→ LowResetVectorBase | 直接用 LowResetVectorBase 的 PA | EL1 入口时等价 |
| **MMU 关时读的数据清到 PoC** | 强制清 CpuDataEntries、cpu_data、ResetHandlerData、BootArgs、**sysreg_restore**、**cpu_ttep**、**bootstrap_pagetables** | ArmCpu 只清 LowResetVector+64K、ResetHandlerData+4K、0x…71647F8+4K；cpu_start 的 flush_dcache 清 cpu_data/CpuDataEntries。**sysreg_restore（0x…71647A8 所在行 0x…7164780）、cpu_ttep（0x…71646B8）、bootstrap_pagetables 没清** | **头号嫌疑** |
| 开 MMU 前屏障 | tlbi/ic iallu 后加 `dsb sy; isb` | common_start：`ic iallu` 后直到 SCTLR 之前没有 dsb | 次嫌疑，一并修 |
| CPU7 | 8 核全给内核 | CPU7（0x700）被 v3.x 监控占用 | 测试用 cpus=7 |

机理：副核以 MMU 和缓存关闭的状态读 TCR（sysreg_restore）和 TTBR1（cpu_ttep）。这两个值是开缓存后写的，可能还脏在 L3/LLCC 里，
DRAM 里是旧值，副核于是在垃圾页表上开 MMU；页表遍历打到受保护或无后备的 PA，会把 NoC 挂死，所有核一起停。
这和 0x3C0FC000 那次属于同一类。读数吻合：首个 CPU_ON 返回 0 次或 1 次后全停，cpus=1 时不停。

`smp_clean.py`（原位改 5 个字，不占洞窗；原字不符就拒绝）：
1. startCPU 第 3 段清缓存：0x…71647F8+4K 改成 0x…7164000..0x…7177000，共 1216 行（全在 __DATA_CONST,__const）。
2. common_start：0x…73E2330 的空操作 `add x0,x0,#0` 改成 `dsb sy`；0x…73E2340/44 的两条 `movk #0`
   改成 `isb; movz x0,#0`，SCTLR 值仍是 0x3454593D。

`--set smp1`（替换其他组）：0x20 CPU_ON 返回（cpus=7 时应有 6 格）/ 0x21 PE_init_iokit 返回 / 0x22 bsd_init 入口 /
0x23 platform_stall 返回 / 0x24 printf#1 返回 / 0x25 kauth_init 返回 / 0x26 fdt_init 返回 / 0x27 mac_policy_initbsd 返回。
一次刷机同时回答两件事：0x20 的格数 = SMP 修复是否生效；0x22 之后的末格 = bsd_init 头段死点。

配方（固件 v3.7，**不加 `--stop-cpuon`**，kernel_args `cpus=7`）：
… → panic_halt → reset_halt → [cmdline_peek] → `smp_clean.py` → `patch_trace.py --set smp1`。
Unicorn：清缓存段 1216 行，覆盖 ttep/TCR/const_boot_args/BootArgs/bootstrap/ResetHandlerData；SCTLR 值不变；8 桩全对。
判读：6 格 0x20 且后面走到 0x21 ⇒ SMP 修复成立；仍只有 0–1 格 ⇒ 缓存清理不是全部原因，下一嫌疑是副核的入口 EL / reset_vector 未匹配（旋在 0x…73E0484）。
