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
