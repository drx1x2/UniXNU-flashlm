# UniXNU-flashlm 移植笔记

LG V50 ThinQ（`flashlm`，SM8150）的 UniXNU 设备仓库。
结构照 `UniXNU-mh2lm` 抄；板级值来自 Project Aloha 的 `lg-flash` 目标与真机待核对项。

## 现状（2026-10-29）

- 前置条件已满足：目标机 bootloader 已解锁（用户真机，2026-10-29）。
- **P0 真机数据已到（2026-10-30，fastboot getvar all，存工作区 `P0-getvar-2026-10-30.md`）**：
  product=flashlmdd、unlocked=yes（实证）、serialno 含 LMV500N（韩版确认）、
  hw rev_10、固件 Android 12 SKQ1.211103.001、sda≈125.9 GiB（128 GB UFS SKU 确认）、
  A/B 双槽、boot 分区 96 MiB。注意：采集时处于 fastbootd（is-userspace: yes），
  试启前须先 `fastboot reboot bootloader`；**getvar 没有 RAM 容量**；已由真机
  `adb shell cat /proc/meminfo` 终核（2026-10-31）：MemTotal 5,546,868 kB，
  **本机为 6 GiB**（机主最初记的 8 GiB 经实测更正——8 GiB 机型 MemTotal 应在
  7.4 GiB 以上）。devices.py 已按 6 GiB 定值（high bank `0x180000000 + 0x80000000`）。
- `board.toml` 已按 flashlm 写好（IPSW 身份与 mh2lm 同一份 iPhone X / iOS 16.7.16）。
- `scripts/devices.py` 已加 `flashlm` profile：GIC/timer/UFS 沿 SM8150 标准值；
  fb/内存布局取自 Aloha lg-flash 的 PlatformMemoryMapLib（见下表）。
- **ADT 已生成完整版**：IPSW 已用 UniXNU 驱动按 board.toml 的 pin 拉取校验
  （kernelcache + DeviceTree，区间下载），`base-d22ap.adt` 已抽出（本地文件，
  .gitignore 不入库）；`mkadt.py --device flashlm` 产出 **12,588 B**，
  /product 节点齐了（无警告）。lzfse 工具链在工作区 `tools/` 下自备。
- Aloha 的 `android-flash.dtb` 已解析核对：根 compatible `qcom,sm8150`、
  splash_region `0x9C000000 + 0x02400000`（跨 Display Reserved 18 MiB + 后随
  RAM 分区）、reserved-memory 与内存映射逐项吻合；/memory 由 ABL 运行时填充
  （DTB 里是空的，属正常）。devices.py 的 flashlm profile 已按此定稿，
  high_mem_size 按实测 6 GiB 定为 `0x80000000`（2026-10-31 /proc/meminfo 终核）。
- 内核（`kernel.macho`）还没有：走 CI 编 xnu-8796（4 KiB 源码内核先拿 M3；
  用户态需要 16 KiB 单体内核线，见 DEVIATIONS.md）。

## 关键数值（Aloha lg-flash，已核对）

| 项 | 值 | 来源 |
| --- | --- | --- |
| 面板 | 1440×3120，32bpp | `PcdsFixedAtBuild.dsc.inc`（PcdMipiFrameBufferWidth/Height） |
| 显示 framebuffer | `0x9C000000`（"Display Reserved" 18 MiB） | `PlatformMemoryMapLib.c` |
| ABL "Kernel" RAM 区 | `0x80000000` + `0x02A00000`（42 MiB） | 同上 |
| DBI Dump | `0x82A00000` + `0x00D22000` | 同上（与 mh2lm 相同，ramdisk 回退路线要避开） |
| UEFI FD | `0x9FC00000`，`0x300000` | 同上 |
| 低端内存洞（按 RAM SKU 而定） | 6 GiB: `0xBCC00000`–`0xC0000000`；8 GiB: `0xBBB00000`–`0xC0000000` | 同上注释按 SKU 列全（4/6/8/10/12 GiB）；**本机已实测 6 GiB**（2026-10-31 /proc/meminfo），适用 `0xBCC00000`–`0xC0000000` |
| GICD/GICR | `0x17A00000` / `0x17A60000` | 同上（APSS_GIC500 条目） |
| QTIMER | `0x17C20000` | 同上 |

## 与 mh2lm 的路线差异

- **UEFI 不用从零做**：Aloha 上游已有 `lg-flash` 完整设备目录（DTB、内存映射、
  配置映射、PCD）。mh2lm 的 `lg-mh2lm` 是后来补的；flashlm 直接用现成的，
  M1 的主要工作是把 UniXNU 菜单/DarwinBoot 的 INF 接进这棵树（照
  guacamole 的 `aloha-guacamole.patch` 与 mh2lm 的 0015–0017 号补丁做）。
- **payload 路线相同**：LG ABL 对带大 ramdisk 的 boot.img 有 ram console /
  secure watchdog 检查（mh2lm 实测 `lge crash handler: secure watching bite!
  invalid ram console`，0x81000000/0x82000000 均触发）。flashlm 的 ABL 同世代，
  默认按同一结论处理：payload 做成 FFS 文件塞进 FV（512 KiB FAT12），
  boot.img 保持空 ramdisk。
- **Kernel 区 42 MiB**（mh2lm 只有 6 MiB）：若 FV 路线受阻，回退选项是
  ≤32 MiB 的 ramdisk payload（0x80800000 起、避开 DBI Dump），但要先过 ABL 看门狗那关。

## M1 集成设计（2026-10-29 盘清）

- UniXNU 侧模块已全部 fetch 到位，`unixnu tree -D UniXNU-flashlm` 能组装出
  build tree（out/flashlm/tree）。
- **FV payload 的驱动缺口已定位**：上游 `UniXNURamDiskDxe`
  （package/UniXNUPkg/Driver/UniXNURamDiskDxe，222 行）只认 FDT
  `/chosen` 的 `linux,initrd-start/end`，没有 FV 来源、没有 PCD 回退——
  这正是 mh2lm 私有补丁 0014/0017 补的东西（未公开，需自写）。flashlm 补丁设计：
  1. 入口先走现有 FDT 路径；无 initrd 时用 DxeServicesLib 的
     `GetSectionFromAnyFv()` 按 FFS GUID 取 FV 里的 payload section，
     把该缓冲区按现有 PublishInitrd 同样的 BlockIo 方式发布；
  2. FDF 侧把 `payload.img`（512 KiB FAT12）以
     `FILE FREEFORM = 7E2B4C1A-...` + `SECTION RAW` 塞进 FV
     （GUID 与 mh2lm B1 记录一致，便于对照）；
  3. lg-flash 的 DXE.inc/DXE.dsc.inc 加入 UniXNU 菜单、DarwinBoot、
     UniXNURamDiskDxe 的 INF（照 guacamole 的 aloha 补丁里 device 段写法）。
- 待 Aloha 完整树拉完后先编基线（lg-flash 原版 UEFI 能否出 FD），再叠集成补丁。

## 待办（按里程碑）
| # | 事项 | 依赖 | 备注 |
| --- | --- | --- | --- |
| P0 | 真机数据采集：getvar、分区备份、TWRP `fastboot boot` 验证 | 真机 | 见工作区《移植任务单》 |
| M1 | Aloha `lg-flash` 构建 + UniXNU 菜单上屏 | P0 | TARGET_DEVICE=lg-flash；NOSB |
| M2 | stub 内核过 DarwinBoot 校验 + ExitBootServices | M1 | 手搓最小 Mach-O，mh2lm 有 make-stub-kernel.py 参考 |
| M3 | CI 编 xnu-8796 → 内核入口/打印/平台专家 | M2 + IPSW | 产物 artifact kernel-8796 |
| M4 | 16 KiB 单体内核 + UFS root → iOS 16.7.16 用户态 | M3 | 对标 guacamole r15 / ios-sweet 树 |
| M5 | 触控/USB/显示驱动；GPU 单独跟踪 | M4 | GPU/GMU 是 SM8150 公认堵点 |

## M2 软件侧完成（2026-10-30）：stub 内核 + payload v2

- **stub 生成器**：`scripts/make-stub-kernel.py` 手搓最小 ARM64 Mach-O
  （不用 ld64.lld，其 LC_MAIN 必被拒），内置一份与 DarwinBoot
  ParseKernel 同规则的自检（生成即验，`--check FILE` 可复验任意副本）。
  布局（依据 ParseKernel 源码，DarwinBootPkg/Driver/DarwinBoot.c）：
  基址 0x1_0000_0000（页对齐且 32 MiB 对齐，窗口候选偏移为 0）；__TEXT
  vmaddr=基址、vmsize 0x2000、fileoff 0、filesize 0x2000、r-x；__DATA
  vmaddr=基址+0x2000、vmsize 0x1000、fileoff 0x2000、filesize 0x1000、rw-；
  LC_UNIXTHREAD（cmd 5、cmdsize 288、flavor 6、count 68、pc@+272）=
  基址+0x1000；文件总长 0x3000。入口先向 0x89B00010 写魔数 "M2STUB!!"
  （LE 0x212142555453324D，可选标记，失败不影响验收），`dsb sy` 后
  `wfe; b .` 死循环；跳入时 MMU 已关（DarwinEnter 关 MMU 后 br 入口），
  物理直写安全。
- **清单 vs 源码三处出入**（以源码为准）：mh2lm 调研清单漏
  cpusubtype==0、漏入口 4 字节对齐；其「window」实为 ParseKernel 固定
  常量 256 MiB（WINDOW_SIZE），与 ADT 运行时窗口（本机 3 GiB）是两回事。
- **payload v2**：`make-flashlm-payload.py` 升级（同几何 FAT12/FLASHSP，
  自带 VFAT LFN 写入与回读校验），装入三件套（路径由 Config.c 的
  MakePath 与 core payload.py 双重确认，条目相对 `\EFI\UniXNU`）：
  `EFI/UniXNU/unixnu.toml`、`EFI/UniXNU/Payloads/kernel.macho`（stub）、
  `EFI/UniXNU/Payloads/kernel.macho.adt`（完整 flashlm ADT，12,632 B；
  比 NOTES 旧记的 12,588 多 44 B，正是本次显式带上的
  darwinboot-memory-size 属性）。簇账：约 54/985 簇，512 KiB 不动 FV 布局。
  toml 照 core 模板：xnu 条目（title/args 照 board.toml [payload]，
  无 initrd、无 dtb 字段）+ reset/shutdown/tools 三个 action 条目。
- **toml 一致性（DarwinBoot 硬约束）**：xnu 条目无 dtb 字段 →
  UniXNUPrepareDeviceTree 返回 DeviceTree=NULL，正是 DarwinBoot.c:515
  校验所要求（非 NULL 反被拒）；ADT 的 /chosen/memory-map 无
  RAMDisk/PackedRAMDisk 占位（已二进制扫描确认 0 处），与无 initrd
  一致；TrustCache/GpuAddon 同理缺席且被 DarwinBoot 容忍（NOT_FOUND 分支）。
- **无输入自动引导（真机菜单触控/按键不可用对策）**：toml
  `[boot] timeout = 3` + `default = "xnu"`。菜单源码（UniXNULib/Menu.c
  UniXNUMenuRun）：Timeout≥0 时倒计时与 HasInput 无关，到点自动选
  DefaultIndex 启动；Timeout<0 才依赖 FallbackTimeout/输入。3 秒后
  无需任何输入即进 DarwinBoot。
- **构建基线 = M1 摘除版 DXE 清单（无 ShengBootMemoryDxe）**：
  DXE.inc/DXE.dsc.inc 仅 UniXNU 应用、UniXNUDxe、DarwinBoot、
  UniXNURamDiskDxe + payload FFS。成品 FVMAIN.Fv.txt 中
  ShengBootMemoryDxe 计数为 0（Ffs 目录里的同名中间产物是旧构建
  残留，时间戳可辨）。**Sheng 缺席对 M2 验收的影响评估：无**——
  DarwinBoot 源码零引用 Sheng/0x89B 状态块，其 DeviceTree 输出由
  payload 里的 ADT 文件构建（DarwinBoot.c:638）；Sheng 负责的
  BootShim DT 存取链服务于真内核阶段（M3+），不在「校验→
  ExitBootServices」路径上。唯一连带：stub 的 0x89B00010 魔数标记
  无人读取（该地址仍在 Reserv 区、写入安全），验收证据以
  DarwinBoot 打印 + hand-off 绿条为准。
- **构建结果**：stuart Success（日志 logs/build-m2.log）；
  FVMAIN_COMPACT used 2,231,872 B（空 payload 基线 2,231,472，+400 B
  为三件套 LZMA 后增量）；构建树 Ffs 中 payload FFS 的 SEC2.raw
  （524,292 B = 4 B 段头 + 524,288 B）尾部与 payload.img 逐字节一致；
  payload 本体另经自带回读校验 + pyfatfs 独立实现回读双确认。
  成品 `builds/lg-flash-unixnu-m2.img`（3,194,880 B，
  MD5 87ef45b8fe067cb43818e7c6c94d589f），未覆盖任何旧产物。
  环境注记：本轮 VM 的 LLVM 工具链是开工后由系统 provisioning
  补装的（clang 18.1.3）；ClangPdb 插件实际读 `CLANG_BIN`
  且须带尾随斜杠（/usr/lib/llvm-18/bin/）。
- **真机验收预期**（走已实证的 fastbootd 写 boot_b + set_active b 法）：
  菜单上屏 → 3 秒倒计时自动选 "LG V50 - XNU" → DarwinBoot 打印
  `DARWINBOOT: inputs validated; exiting boot services` → 大字 hand-off
  屏 + 顶部绿条 → stub 死循环挂住（或看门狗复位）。仍未验证：
  RAM 容量（6/8 GiB）、UEFI 交互（已知不可用，靠倒计时绕开）、
  DT 槽位约定（Sheng 线另行修复）。

## M2 修复版（2026-10-30）：8.3 改名 + mtools 成卷 + 菜单重试兜底

真机 M2/M2B 实测的 NOT_FOUND 定案后，这一版只动三处（产物
`builds/lg-flash-unixnu-m2e-kern83.img`，3,194,880 B，
MD5 `afd49e7ee654d33369e20b40a2b9f8f`，构建日志 `logs/build-m2e-kern83.log`）：

- **payload 改 8.3 名**：`kernel.macho` → `KERNEL`、`kernel.macho.adt` →
  `KERNEL.ADT`，toml 里 `path = "Payloads/KERNEL"`（DarwinBoot 按
  KernelPath+".adt" 派生 ADT 名，自动对上）。原名一个是 5 字符扩展名、
  一个双点，都不是合法 8.3，在 FatDxe 里没有短名匹配通道、全靠 LFN，
  而 LFN 在 Payloads 目录层运行时匹配失败 → DarwinBoot 开文件
  NOT_FOUND。改严格 8.3 后内核文件不再依赖 LFN。
- **成卷换 mtools**：`make-flashlm-payload.py` v3 弃用手写 Python FAT
  写入器，改照上游 `payload.py` 的 write_volume 用 `mformat` + `mcopy -s`
  写卷（对照组 guacamole/mh2lm 与我们的唯一系统性差异就是写卷工具）。
  一处实测修正：上游的 `-F` 在本机 mtools 上是强制 FAT32（512 KiB 卷
  会得到 FAT32 引导扇区、类型串落到偏移 82），与本卷 FAT12 设计矛盾，
  故去掉 `-F` 让 mformat 按尺寸选 FAT12（标签@43、类型@54 回归原位，
  序列号仍 53484e47）。
- **菜单失败重试兜底**：UniXNULib/Menu.c 第 115/117 行去掉 HasInput
  门控，倒计时关闭/超时为负时也无条件按 FallbackTimeout 重试默认条目，
  不再永久停在选条目界面（本机无可用输入设备、启动失败为快速无副作用
  返回，故偏离上游防循环设计可接受）。补丁存
  `patches/menu-fallback-retry.patch`。
- 构建前树状态注记：动手时 aloha 树实际停在 M2D 状态（Sheng INF 在列、
  BootShim 带 DT 存指针段），已先按 M2B 基准摘除 Sheng 两行 INF 并把
  BootShim.S 恢复基线（BootShim.bin 回到 112 B）再构建；ButtonsDxe
  保持原版。验收：构建报告 Sheng 计数 0、四组件齐全；从 FV 的 payload
  FFS 段提取的卷与输入 payload.img 逐字节一致，mdir 见
  KERNEL/KERNEL.ADT/unixnu.toml 齐全，KERNEL 回读跑 stub 自检通过。

## M2F（2026-10-30）：KERNEL 上移一层 + DarwinBoot 黑匣子插桩

M2E 真机仍返回 Not Found。三轮定位已把路径构造、卷句柄/媒体、卷面
字节四层全部验净，故障只剩 DarwinBoot.c 的两个 Root->Open
（:548 kernel、:557 adt）；经验规律是深度≤2 的打开（\EFI\UniXNU\
unixnu.toml）每轮必成、唯一试过的深度-3 打开（经 Payloads 目录）
全败。本版双管齐下：

- **payload v4**：KERNEL 与 KERNEL.ADT 从 Payloads/ 上移到
  \EFI\UniXNU\ 直下（取消 Payloads 目录），toml 改为
  `path = "KERNEL"`；成卷仍走 mtools、512 KiB、卷标 FLASHSP。
  `make-flashlm-payload.py` 已同步（布局说明与 verify 期望路径）。
- **DarwinBoot 屏幕插桩**（`patches/darwinboot-diagdraw.patch`）：
  新增 DbFail(Stage, What, Status)，失败时用既有 DiagDraw 帧缓冲
  画笔在阶段独占行画大字 `DB <阶段> <何物> <状态>` 并 Stall 15 秒
  供拍照（菜单重绘会盖掉普通 Fail 打印，这是装它的原因）。成功
  路径除入口一行 `DB 0 ENTER`（行 0）外零影响。判读表：

  | 屏幕字样 | 含义 |
  | --- | --- |
  | `DB 0 ENTER`（行 0） | DarwinBoot 已被调用（每次尝试都会闪现） |
  | `DB 6 VOLUME <状态>` | HandleProtocol/OpenVolume 失败（卷句柄层） |
  | `DB 1 KERNEL Not Found` | :548 打开 KERNEL 失败——上移后若仍出现，深度说证伪 |
  | `DB 2 PARSE <状态>` | ParseKernel 拒绝 stub（布局问题，与文件打开无关） |
  | `DB 3 ADT Not Found` | kernel 已打开、:557 打开 KERNEL.ADT 失败（双点名/派生名问题） |
  | `DB 4 ADTWALK <状态>` | ADT 已读入但 AdtNode 遍历/收尾校验失败 |
  | 无 DB 失败行、出现 hand-off 屏 | 全部通过，M2 验收达成 |

构建验收：stuart Success；BUILD_REPORT 四组件齐全、Sheng 计数 0；
FV 内 payload 段与 v4 输入卷逐字节一致，mdir 确认新布局；对
DarwinBoot.efi 做 UTF-16LE 字节检索，`DB 0 ENTER`、格式串
`DB %u %s %r` 与 KERNEL/VOLUME/PARSE/ADTWALK 阶段字样全部命中。
产物 `builds/lg-flash-unixnu-m2f-diag.img`（3,194,880 B，
MD5 f837b3a1…）。构建插曲：本轮执行环境缺 clang/llvm 与 mtools，
经清华镜像补装（mtools 4.0.43、llvm-toolchain-18）；另 DarwinBoot.c
的插桩改动曾被外部树状态恢复覆盖一次，靠 strings 验收发现后以
补丁文件重新应用并复验——补丁文件即真源，勿只信工作区状态。

## 内核步骤需要什么

同 mh2lm 笔记：`unixnu kernel` 在 Linux 上准备工具链即可（16–32 GiB 内存的
联网 Linux + iOS 16 IPSW），CI 路线则用 GitHub Actions 的 macOS runner（Xcode 15）。
