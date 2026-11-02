# HANDOVER — UniXNU-flashlm 交接文档

> **交接说明（2026-11-01）**：本项目由原维护者移交。本文是给接手工程师的冷启动
> 文档：读完它，你应能独立复现构建、刷机，并接续 M3 的死点定位。仓库内只保存
> 可复现的输入与结论；全部构建工件、证据与诊断资产在开发工作区
> `~/workspace/unixnu-flashlm/`（见 §8 索引），不在 git 内。
> 本文所有哈希与大小均为 2026-11-01 从磁盘实测。
>
> 仓库硬规则先读 [AGENTS.md](AGENTS.md)：Apple 产物不入库、不改 mkadt 节点语义
> 绕检查、内核补丁与 `ci/0019` 同步。另注意：AGENTS.md 的「只 fastboot boot」
> 是 format 1 的通用规则；**本项目的真机测试回路以 Yun 既定的 flash boot_b
> 流程为准**（见 §2），那是设备所有者亲自定立并一直在用的流程。

## 1. 设备与目标

| 项 | 值 |
| --- | --- |
| 设备 | LG V50 ThinQ，**LM-V500N**（韩版），代号 **flashlmdd**，板级目标 `flashlm` |
| SoC | SM8150（骁龙 855），面板 1440×3120 |
| RAM | **6 GiB**（真机 `/proc/meminfo` 实测 MemTotal 5,546,868 kB；8 GiB 是 V50S，勿混） |
| 状态 | bootloader 已解锁；闲置测试机，设备所有者已明示可刷砖 |
| 分区 | boot_a / boot_b 各 96 MiB；sda ≈ 125.9 GiB；出厂 Android 12 |

**目标分两条线，严禁混用：**

- **M4 用户态线（最终目标）**：iOS **16.7.16**（build 20H392，iPhone10,3 / d22ap，
  chip_id 0x8015，board_id 6）用户态，走 **16 KiB 单体（monolithic）内核线**
  ——与 guacamole / cepheus 同线（Apple 出货 kernelcache 的 prelink 路线）。
  版本三角是硬约束：iOS 16 用户态必须配 16K 单体内核。
- **M3 诊断线（当前）**：**4 KiB** 页、源码构建的 **xnu-8796.141.3**
  （`DEVELOPMENT_ARM64_BCM2837`，GitHub Actions 产物）。它只用来验证启动链、
  ADT 语义与观测通道；其内核二进制、prelink 假设**不可**带进 M4。地址、桩位、
  ADT 语义类结论可迁移。

CI 内核基线：Actions run `41150570344`（workflow `kernel-8796`），产物
`mach.development.bcm2837`（stripped 14,917,208 B，MD5
`af7a0bf21935829b5a7ef12f14800f37`；`.unstripped` 兄弟文件留作符号化），
版本串 `Darwin Kernel Version 22.6.0 … DEVELOPMENT_ARM64_BCM2837`。
工件在工作区 `ci-artifacts/run1/`，不在 git。

## 2. 已闭合：M1 菜单、M2 交接

- **M1（UEFI 菜单真机点亮）**：Aloha `lg-flash` 目标 + UniXNU 菜单。
  基线镜像 `builds/lg-flash-baseline-uefi.img`（3,158,016 B，MD5
  `a75132e7a314b1c36bd71e0eb03a50a4`）。
  **ShengBootMemoryDxe 在本板造成黑屏，已永久绕开——flashlm 的任何构建都不许
  带 Sheng**，每轮构建前复核基线补丁集。
- **M2（DarwinBoot 交接闭环）**，收官镜像 **M2I**：`builds/lg-flash-unixnu-m2i-window.img`
  （28,356,608 B，MD5 `d61545de1972a443ac1ca5760bc91eb2`）＝最后已知良好的
  「stub 交接」基线。验收标志：交接时屏幕顶部绿条 + `DB 0 ENTER`。
  M2 的三个关键修复（细节在 `patches/`）：
  1. **initrd/FDT 交接断裂**：SEC PrePi 覆写 x0 且从不建 entry-arg HOB。修复＝
     BootShim 把 x0 存入保留槽 `0x89B00000`，UniXNURamDiskDxe 改走「HOB→槽→FV」
     槽源（`ramdisk-slot-source.patch`）。
  2. **AllocateWindow NO WINDOW**：ADT 声明窗口 3 GiB，而低 bank 只有 1 GiB、
     高 bank 2 GiB，无连续段可放。窗口改为 **1 GiB** 治本（M3 诊断系列实际以
     512 MiB 窗运行，落点见 §6）。
  3. **菜单交互**：按键轮询全部 SimpleTextIn 句柄（音量+＝SCAN_UP、音量−＝
     SCAN_DOWN、电源＝SCAN_SUSPEND，确认键接受 SUSPEND）；payload 采用 v4 布局
     （`KERNEL` / `KERNEL.ADT` 与 toml 同放 `\EFI\UniXNU\`，`path = "KERNEL"`），
     修掉 DarwinBoot 三层深度打开文件失败。触控无驱动，已关闭此路；Tools 菜单
     为空是设计（AdvancedLogDxe 不在本固件）。

**刷机回路（既定流程，A 槽永不动）：**

```sh
fastboot flash boot_b <img>
fastboot set_active b
fastboot reboot        # 回退：set_active a（A 槽是原 Android + 其 boot 内的 TWRP）
```

一个启动周期的解剖：菜单倒计时 → DarwinBoot 装内核（顶绿条 + `DB 0 ENTER` /
`WIN …` 行）→ **冻结**（屏幕全静、按键无反应、约 29 s；只有监控第三排心跳在闪）
→ 看门狗咬合自动重启 → 循环。**冻结画面保留菜单的末帧（含倒计时文字）是合法的
冻结期证据**——交接后无人重绘屏幕，照片即冻结相位，不要误判为「菜单期残影」。
挂死时强重启：**电源＋音量减长按**（单长按电源无效；这是 PMIC 硬断电，
也是 §4 跨重启记录全灭的原因）。

## 3. M3 现状：死点已被围栏

- **真机已过（两刷独立证据，10/10 色块）**：整个 locore
  （`__start` → `_start_first_cpu` → `common_start` 出口）＋切换前里程碑
  P1（`_arm_init`）、P7（`_cpu_data_init`）、P2 首呼（`_PE_init_platform`）、
  P3（`_arm_vm_init`）、SW（TTBR0 换根点）。色块机制见 §4。
- **死点区间**：[**TTBR0 换 invalid 根**（`_arm_vm_init+0xC18` 经 `_set_mmu_ttb`），
  **`_kernel_bootstrap` 横幅 printf**) 之间。区间内含 `_pmap_bootstrap`、
  `_arm_vm_init` 尾段、`_arm_init` 后段（`kprintf` 初始化、`PE_create_console`、
  `PE_init_printf`）、`machine_startup` 与向 `_kernel_bootstrap` 的过渡。
  「没有横幅」只能把死点压到横幅之前，压不进更细——这正是 §4 通道存在的理由。
- **P5 已证执行**：P5＝`PE_init_printf` 返回点（`_arm_init+0x920`，
  VA `0xFFFFFFF0079A1AAC`）。M3Q3 监控在真机读到 P5 的里程碑值，即内核确已走完
  `_arm_vm_init`（含 `_pmap_bootstrap`）、kprintf 初始化、建控制台。
  但该读数经缓存淘汰通道（见 §4 相干律），它证明「P5 执行过」，**不**证明
  「终点就是 P5」——终点至今未钉死。
- **三条线已排除（不要重开）**：
  1. **panic 排除**：`_panic` 入口改道到 PSCI SYSTEM_RESET 码洞，真机无复位
     （M3D）。注：区间整体在 `PE_init_printf` 之前，panic 本就不可见，只能靠改道验。
  2. **异常向量排除**：异常黑匣子（槽 0/3/4/7 与三处 check 自旋改道为
     「记录 ESR/ELR/FAR 后 PSCI 复位」）真机无复位（M3E）；静态分析亦证明所有
     到达 C 的向量槽都汇入 `_panic`，唯一自旋点在 TPIDR=0 期被跳过。
  3. **数据消费排除**：对区间根做传递闭包审计——**344 个函数**逐项反汇编，
     DT/boot-args 消费者全部 fail-soft 带默认值，DT 遍历有界，区间内内存叙事
     只来自 boot_args（无人读 `/memory`）。同一份 ADT 在 QEMU 全程走完区间＋
     横幅＋进入 `PE_init_iokit`。
- **QEMU 假象（已证伪，勿再追）**：QEMU 全栈曾复现同签名冻结并定位到
  `IOPlatformExpertDevice::generatePlatformUUID` 读 `/chosen` 的
  `unique-chip-id`/`chip-id` 时同步异常。对照实验决定性：改道内核在 QEMU 立即
  复位、在真机不复位 ⇒ QEMU 的 panic 不是真机死点；事后审计证明 ADT 里
  ecid/chip-id 长度精确合规，QEMU 之死是其注册表层空指针的模拟器假象。
  此点作为 **M4 注意事项**保留（§6），不是 M3 死点。

- **🎯 终点已钉死（2026-11-01，M3U2 v3.5.2 真机）**：第三排 idx4＝明绿（S4，监控
  开 MMU+缓存后在跑，PXN 修复真机成立）；idx2 绿对照正常；idx0 A 相心跳；idx3 黑
  合设计；一、二排 10/10。**idx1＝金色**，实测 RGB (252,213,17)、G/R=0.845（同帧
  L4 柠檬黄 1.000）⇒ 相干读出的精确终点是里程碑 **P4（`_pmap_bootstrap`）**，不是
  旧淘汰值。结论：内核走过 P4、死在 **P4 之后、P5（`PE_init_printf` 返回）之前**，
  区间涵盖 `pmap_bootstrap` 本体、`_arm_vm_init` 尾段、kprintf 初始化、
  `PE_create_console`、`PE_init_printf` 本体。上文「P5 已证执行」据此**撤销**：
  M3Q3 的粉色 P5 读数定性为缓存淘汰抽奖假象，真终点一直在 P4。

## 4. 观测通道与相干律（核心资产）

M3 的全部难度在「怎么看见」。以下每条都是真机或走查实证，不是推测。

### 4.1 跨重启通道：全灭，勿再试

窗口 args 页、保留槽页、UEFI 变量三条「写后复位回读」通道均已证伪：
镜像内最早执行的 BootShim 在复位后读到的已是空拷贝——记录死于复位本身或
ABL 早期初始化（强重启是 PMIC 硬断电，疑 DRAM 保持丢失）。UEFI 变量通道是
**架构性缺失**：本平台固件没有 FVB 驱动（FD 是 RAM 加载镜像，无闪存 NV 区，
厂商 VariableDxe 在 DXE.inc 里被注释）。
仍有效的推论纪律：「无复位 ⇒ 某事未发生」类推断成立，其依据是复位的**可见
缺席**，不依赖回读。

### 4.2 同轮 FB 色块（第一、二排）

帧缓冲 PA `0x9C000000`（Display Reserved 18 MiB），行宽 5760 B，块 240×60、
列 x = idx·260：

- **第一排**（y 3060–3120，基址 `0x9D0CF200 + idx·0x410`）：locore 五标
  L0–L4，按 PA 直写，MMU 开关两侧均可达（L3b/L4 的填色自带 SCTLR.M 开关包裹，
  因为 FB 不在任何已映射段内）。
- **第二排**（y 3000–3060，基址 `0x9D07AC00 + idx·0x410`）：P1 / P7 / P2 首呼 /
  P3 / SW，经 TTBR1 写、首呼守卫（守卫旗在 args+0x868 起，每桩 8 B）；
  其 PROG 桩体在每次进入时都运行，守卫只挡填色。
- 关键推论：TTBR0 身份映射在 SW 点被**故意废除**，故第二排之后 PA-as-VA 直画
  失效——[SW, 横幅) 区间的观测只能靠下面的监控核。

### 4.3 监控核（CPU7）

DarwinBoot 在交接前以 PSCI `CPU_ON`（`0xC4000003`，MPIDR `0x700`）拉起 CPU7，
blob 驻留槽页 `0x89B00400`；看门狗在 CPU_ON **之前**已武装，SMC 挂死也能
恢复设备。监控核不切页表、按 PA 直读邮箱、直画 FB **第三排**
（y 2940–3000）：idx0 心跳、idx1 最新里程碑色、idx2/idx3 签名位（v3.4 起）。

- v1 的教训：延时环按循环计数标定，在小核上电低时钟下单次延时超过看门狗
  29 s 窗，表现为「块静止」。**v2 起节拍改用 CNTPCT 架构计时器**（0.5 s 真实
  时间），此后心跳可信。
- v3 的教训：邮箱指针立即数链手算拆三段
  （`0x4848 | 0xF148<<16 | 0x00C1<<32`）实得 `0xC1F1484848`，撞物理空洞，
  首读数据异常后无向量静默停泊——整轮症状与「civac 有罪」完全一致，真凶是
  地址。已由 Unicorn 主机模拟定罪。**此后一切 movz/movk 链必须过数值求值
  断言门**（§7）。
- 版本谱系：v3.2（684 B，M3Q3 起的现役基线：轮询邮箱、读前无维护）、
  v3.3（读前 `dc civac`+`dsb`，M3R 用）、v3.4（868 B，+SIG 槽显示，M3T 用）、
  v3.5（1212 B，开 MMU＋缓存，M3U 用，见 §4.5）。规格全在
  `patches/monitor-core-m3p.md`。

### 4.4 相干律（本项目最贵的一条经验）

> **经 TTBR0 身份路径（VA＝PA）的 store，必达关缓存监控核的 DRAM 直读；
> 经 TTBR1 内核 VA 的 store，永不达——`dc cvac`、`dc civac`、`dsb sy`
> 全套维护都救不回来。**

- 身份写三证：① locore 诸桩（x20 保 x0、按 PA 写 PROG 槽，真机可见）；
  ② L3b/L4 在 SCTLR 切换后经 TTBR0 身份映射的写可见；③ **M3T 的 γ**——
  P1 桩在同一执行点内，TTBR1 写主记录不达，而经身份别名 `0xC1F14880`
  的纯 store 写 SIG_A 被监控确读（第三排 idx2 绿，照片像素实测 (108,255,110)）。
- TTBR1 写三败：P 桩 VA 写（M3F 起从未被同轮读到）→ 桩自加 `dc cvac`+尾
  `dsb`（M3S）→ 再加 `dc civac`（M3T 的 α）皆败；监控侧（关缓存）发
  `dc civac`（M3R）亦无效，其广播够不到主核缓存。
- DRAM 里偶尔出现的靠后值（M3Q3 的粉＝P5、M3R 的黄＝L4）是**缓存淘汰
  抽奖**：值是真的（证明对应桩执行过），但出现哪一个纯属时序，不证终点。
- **页表无嫌疑（M3T 走查）**：QEMU 实读运行时页表——bootstrap 双环与切换后
  `*_cpu_ttep` 表对 args 页的条目，目标 PA 精确、属性位段（Normal WB、
  Inner Shareable；块 `0x601` / 页 `0x603`）逐位相同，仅粒度（2 MiB 块 vs
  4 KiB 页）与取指位有差；生成逻辑（`_arm_vm_init` 按 Mach-O 段新建、
  `_pmap_bootstrap` 不建任何映射）与实测互证。地址五方对账差为 0（见 §8）。
  悖论被收敛到**硅级相干语义**：在 SM8150 上，两种翻译体制的写落入监控核
  直读不可见的不同相干域——这是经验律，不必先有微观解释才可用。

### 4.5 两个未达项

- **physmap δ（已砍）**：曾设计让 P5 桩经 physmap VA 写 SIG_B。派生在 rig
  准入两启两挂：实测 physmap 区表 region[0] 起点 PA 在 args 页之上、args 页
  落在空档，**physmap 对 args 页 PA 非线性覆盖**，朴素滑动派生不成立。
  按预登记规则砍除，未带猜测上真机（M3T 出货的 P5 桩与 M3S 逐字节同）。
  复活此路须按真实区表逐段走查，而不是公式平移。
- **M3U v3.5 开缓存监控（2026-11-01 真机：第三排全黑）**：思路是让监控核开
  MMU＋数据缓存、以身份映射（邮箱页 Normal WB/ISH、FB 走 Device）加入相干域，
  直接窥探主核脏行——若成立，现役全部 P 桩零改动即可全程精确读。
  真机结果是监控**未完成首画**。死因未分：(a) 前导（建四级表 → 装 TTBR0 →
  开 SCTLR 的 M+C）途中故障、无向量静默停泊；(b) 固件侧 `AllocatePages`
  失败走了降级路径（设计即不启监控、idx0 画黑）。两个死因的画面相同。
  另须知：**QEMU rig 演练不了 CPU_ON**——其 TF-A 接受 CPU_ON 却从不把次核
  交付到普通世界入口，换入真机实证可用的 v3.4 症状相同，是 rig 的问题；
  因此 v3.5 前导从未获得全栈演练（Unicorn 门只证了主体逻辑与建表走查）。
  前导调试必须真机主导，首步见 §5 甲 0。
- **M3U2 更新（2026-11-01，主机侧定位，待真机确认）**：v3.5 槽页 L3 项
  `0x743` 的 AP[2:1]=01（EL0 也可写），按 ARM ARM D8.4.1，EL0 可写即在
  EL1 被视为 PXN——blob 正是在这一页上执行，开 SCTLR.M 后第一次取指
  （`0x89B004F8`）即权限故障，无向量静默停泊，与「第三排全黑」吻合，属死因 (a)。
  已出 **v3.5.2**（`0x743`→`0x703`，并在 idx4 加 S1–S4 阶段色标、固件对
  表页 `dc civac`、分配失败画紫），门见 `tools/m3u/gate.py`，判读见
  `patches/monitor-core-m3p.md` 的 M3U2 节。

## 5. 下一步选项（按序）

- **✅ 甲 0′ 已完成（2026-11-01）：v3.5.2 真机读侧成立，终点＝P4→P5 之间（§3）。甲 0/甲 1/甲 2① 随之作废；下一步直接进入乙：在 P4→P5 区间内加更细桩（现役 v3.5.2 监控零改动即可精确读），二分 `pmap_bootstrap` 返回 / `_arm_vm_init` 返回 / kprintf 初始化后 / `PE_create_console` 后。**
- ~~**甲 0′（已备好，先刷）：v3.5.2。** 修复 + 阶段色标合一刷；idx4 绿且 idx0
  心跳即读侧成立，再按 M3U 判读读 idx1。若停在灰，再回到下面的甲 0 细分。
- **甲 0（最便宜，先行）：v3.5.1 二分刷。** blob 在建表/开 MMU **之前**先以
  现役关缓存方式画 idx0 并闪一拍，分开「前导死」与「分配降级死」；若前导
  前活、前导后死，再在建表后、装 TTBR 后、开 SCTLR 后各加一记关缓存画法
  （注意开 MMU 后画法须走 Device 映射）逐步夹逼。内核逐字节不变。
- **甲 1：写侧修复（γ 已证之路）。** 切换前桩 P1/P7/P2/P3 改为（或双写为）
  经 TTBR0 身份别名直写邮箱（PA 即 VA，纯 store），监控沿用关缓存 v3.4。
  这一半区间的读数立即变精确，成本一轮内核改动＋全套门。
- **甲 2：切换后桩 P4/P5/P9/P10 的候选（按成本序）。**
  ① 调通 v3.5 读侧（成则全区间通解、现役桩零改动）；② physmap 按真实区表
  走查后重试 δ；③ 早期切换后桩在桩内短暂换装 bootstrap TTBR0 写后恢复——
  **仅限 P4/P5 的单核窗口**，P9/P10 时多核已起，禁用。
- **M3V 读数 #1（2026-11-01）**：p4p5 点集 0x20–0x2C 全命中 ⇒ 终点在 `PE_create_console` 内
  （含尾调 initialize_screen）。头号嫌疑：bcm2837 硬编码 PA 0x3C0FC000（SM8150 上非 DRAM）的
  映射与读取。下一刷：`patch_trace.py --set console`（M3V2，见 `patches/m3v-trace.md`）。
- **M3V 读数 #2（2026-11-01）**：console 点集只中 0x20 ⇒ 第一次读 bcm2837 遗留 PA 0x3C0FC000 即总线挂死
  （坐实）。修复 M3W：`tools/m3v/fix_console_pa.py` 一字把 PA 改为 0x9D1FC000（Display Reserved 尾部）。
  源码层修复待做（ci/0019，M4 线必需）。
- **乙-1（M3V 飞行记录仪）**：监控 v3.6 + 15 个 trace 桩（pmap_bootstrap 内 3、
  arm_vm_init 尾 4、arm_init 区间 8），一刷在菜单区画出执行顺序色带，直接读出终点
  落在哪两个调用之间。规格/判读：`patches/m3v-trace.md`；工具：`tools/m3v/`。
- **乙：终点钉死之后**，对被夹出的子函数做定点修复或更细桩距，
  再谈横幅、`mountroot` 与 M4 衔接。

## 6. M4 备忘（雷区清单）

- **版本三角**：见 §1。16K 线的 kernelcache、prelink、用户态三者同进同退；
  M3 的 4K 线结论只有语义可迁移。
- **generatePlatformUUID**：ADT 数据已证合规、QEMU 之死是模拟器假象（§3）；
  但此函数在 16K 线上仍是**必经点**：16.7.16 出货内核是 `xnu-8796.142.1.703.8`，
  与 141.3 源码不同修订，M4 首启前须对该版本重新核对它从 `/chosen` 读取的
  `unique-chip-id` / `chip-id` 长度与类型（〔重建〕具体措辞已丢失，此句据 §3 补全）。

> 🔧 **§6 余文、§7、§8 为 2026-11-01 重建版，不是原文。** 原文在最初写文件时即被
> 截断（原维护者本地副本与提交 `32406ef` 逐字节相同），无任何完整副本。以下内容
> 只取自仓库内现存资料（AGENTS.md、DEVIATIONS.md、ci/README.md、NOTES.md、
> patches/*.md、本文 §1–§5），每条注明出处；原文中仓库内无据可查的内容标「待补」，
> 不臆造。

- **iOS 16 内核来源**：iOS 16 无开源源码，「源码内核 + 原版 kernelcache prelink」
  对 16.7.16 不存在可用组合；唯一实机验证过的做法是 16 KiB 单体内核（内置
  HFS/AMFI/UFS/pthread，不 prelink）。（DEVIATIONS.md）
- **16K 单体内核 workflow 尚未建立**：需 `MACHINE_CONFIG=FLASHLM` + 板级件替换，
  先做板级移植；路线见开发工作区 `docs/notes/16-ios16-route.md` §16.3。（ci/README.md）
- **M3 结论迁移边界**：可迁 ADT 语义、地址/桩位、观测通道与 §4.4 相干律；不可迁
  4K 内核二进制、prelink 假设。（§1）
- 其余雷区条目：**待补**。

## 7. 构建纪律（重建）

1. **不带 Sheng**：ShengBootMemoryDxe 在本板黑屏，任何构建都不许带；每轮构建前
   复核基线补丁集。（§2）
2. **刷机只用 boot_b 回路**，A 槽（Android + TWRP）永不动；回退 `set_active a`。（§2）
3. **Apple 产物不入库**；**不改 mkadt 节点语义**绕检查（`/chosen` 必带 CHRP NVRAM
   proxy、`/options` 必存在）。（AGENTS.md 硬规则 2/3）
4. **内核补丁与 `ci/0019-unixnu-8796-ci.patch` 同一提交同步**；内核不在本地编，跑
   Actions `kernel-8796`（macOS + Xcode 15，因 iig 世代；默认 pin UniXNU `40d21cc`，
   一次 2–3 小时，上限 350 分钟）。prelink 步骤故意失败，由 `|| true` + `test -f` 接住。
   （AGENTS.md 4、ci/README.md）
5. **payload 走 FV 内 FAT12（B1）**，不走 boot.img ramdisk（LG ABL ram console /
   secure watchdog）。（AGENTS.md 6）
6. **每个镜像记录大小 + MD5 + 构建日志**（`logs/build-<tag>.log`），证据入
   `evidence/<任务>/`；仓库只留可复现输入与结论。（AGENTS.md「记录方式」、patches/*.md 惯例）
7. **监控 blob 改动走 `tools/m3u/`**：改 `.S` → `build.sh` → `gate.py` 全 PASS → 回填
   补丁字节。（M3U2 新增）
8. 其余原文条目：**待补**。

## 8. 资产索引与镜像清单（重建）

工作区根：`~/workspace/unixnu-flashlm/`（不在 git）。已知目录（据仓库内引用）：
`builds/`（镜像）、`logs/`（`build-<tag>.log`）、`evidence/<任务>/`、
`ci-artifacts/run1/`（CI 内核 run `41150570344`）、`docs/notes/`。

镜像清单——只列仓库文档里出现过的；大小/MD5 取自所注文档，「—」= 仓库内无记录：

| 镜像（`builds/`） | 大小 B | MD5 | 出处 |
| --- | --- | --- | --- |
| `lg-flash-baseline-uefi.img`（M1 基线） | 3,158,016 | `a75132e7a314b1c36bd71e0eb03a50a4` | §2 |
| `lg-flash-unixnu-m2.img` | 3,194,880 | `87ef45b8fe067cb43818e7c6c94d589f` | NOTES.md |
| `lg-flash-unixnu-m2e-kern83.img` | 3,194,880 | — | NOTES.md |
| `lg-flash-unixnu-m2f-diag.img` | 3,194,880 | — | NOTES.md |
| `lg-flash-unixnu-m2i-window.img`（**M2I，最后已知良好**） | 28,356,608 | `d61545de1972a443ac1ca5760bc91eb2` | §2 |
| `lg-flash-unixnu-m3d-panicreroute.img` | — | `249a8c1d4fa5574f0c27a3a6395ef1a2` | kernel-panic-psci-reroute.md |
| `lg-flash-unixnu-m3g-locore.img` | 28,356,608 | `be454dc549e031e22206cb156424f104` | kernel-locore-prog.md |
| `lg-flash-unixnu-m3j-pscitest.img` | 28,356,608 | `95fb40a8082bb9d81f11ec2fd9c40cdd` | firmware-psci-survival-test.md |
| `lg-flash-unixnu-m3l-earlycopy.img` | 28,356,608 | `e67e91eaa2939b1e99792ee29b742732` | m3l-earlycopy-fbmarks.md |
| `lg-flash-unixnu-m3m-fbmarks.img` | 28,356,608 | `46876c0fb4c2f805a247c2d7cc61ce54` | m3m-flow.md |
| `lg-flash-unixnu-m3p-cpuon.img` | 28,356,608 | — | monitor-core-m3p.md |
| `lg-flash-unixnu-m3p2-timer.img` | 28,356,608 | — | monitor-core-m3p.md |
| `lg-flash-unixnu-m3q-monitor.img` | 28,360,704 | — | monitor-core-m3p.md |
| `lg-flash-unixnu-m3q2-ablate.img` | 28,356,608 | `a50196e260fe9220ec3502e92ea868d0` | monitor-core-m3p.md |
| `lg-flash-unixnu-m3q3-fix.img` | 28,356,608 | `12509da7dadb654c7e170ac25c6a0dcd` | monitor-core-m3p.md |
| `lg-flash-unixnu-m3r-civac.img` | 28,356,608 | `350307b7b17351b0f79b287a7df278e4` | monitor-core-m3p.md |
| `lg-flash-unixnu-m3t-sig.img` | — | — | m3t-coherence-sig.md |
| `lg-flash-unixnu-m3u-cohread.img` | 28,356,608 | `ff9fcf5d01954d17a4a80634f8f14e38` | monitor-core-m3p.md |

待补：表中「—」项请在工作区用 `stat -c%s` / `md5sum builds/*.img` 实测回填；
M3U2（v3.5.2）镜像构建后追加一行。
