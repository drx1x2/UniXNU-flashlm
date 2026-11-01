# M3K 交接前武装 APSS 看门狗（darwinboot-watchdog-arm）

诊断专用，**不得带入正式镜像**。源码补丁：[darwinboot-watchdog-arm.patch](darwinboot-watchdog-arm.patch)
（对 DarwinBootPkg/Driver/DarwinBoot.c 的纯新增 diff + DarwinBoot.inf 加 IoLib 一行，
基线 = M3J 构建树）。内核与 payload 沿 M3G 补丁件逐字节不变。

## 背景与目的

M3J 在真机验证「PSCI 温复位后 DRAM 存活」这一前提（固件自发复位、
次轮读回探针）。地基成立之后，看门狗路线随之可用：DarwinBoot 在交接前
把 APSS 看门狗武装到约 29 秒 bite，内核若在交接后挂死（不喂狗），bite
即 SoC 级温复位，次轮固件读回块就能读到挂死那轮留在 DRAM 里的
EXC/PROG 记录——把「挂死取证」从依赖人工长按强制重启（已实锤会丢
DRAM 记录）换成自动的温复位通道。本版 = M3J 全部内容（PSCI 自测试
状态机原样保留）+ 本武装，互不干扰：自测试在读回阶段（Boot 中段）
自发复位，武装在交接前（Boot 末段），时序不重叠。

## 寄存器模型（出处逐条对回原文）

模型调研存档 `refs/wdt-model/`（README 含来源与 commit 锁定）。
本机 DTS 锚点：`refs/los-kernel/arch/arm64/boot/dts/qcom/sm8150.dtsi:1835`
compatible = `qcom,msm-watchdog`、reg 0x17c10000/0x1000——该 compatible
由 CAF 驱动 `drivers/soc/qcom/watchdog_v2.c` 绑定，主线 `qcom-wdt.c`
的 kpss 布局与之逐位一致，两源互洽：

| 项 | 值 | CAF 出处（watchdog_v2-los.c） | 主线出处（qcom-wdt-mainline.c） |
| --- | --- | --- | --- |
| 基址 | 0x17C10000 | DTS reg（同上） | — |
| RST | +0x04 | :46 `WDT0_RST 0x04` | :34 `[WDT_RST] = 0x4`（kpss 表 :33–39） |
| EN | +0x08 | :47 `WDT0_EN 0x08` | :35 `[WDT_EN] = 0x8` |
| STS | +0x0C | :48 | :36 |
| BARK_TIME | +0x10 | :49 | :37 `[WDT_BARK_TIME] = 0x10` |
| BITE_TIME | +0x14 | :50 | :38 `[WDT_BITE_TIME] = 0x14` |
| EN bit0 | 使能 | :54 `EN 0`（BIT(EN)） | :23 `QCOM_WDT_ENABLE BIT(0)` |
| EN bit1 | UNMASKED_INT_EN（bark 中断） | :55；仅 wakeup_irq_enable 时置（:818–819） | —（本版不置，见下） |
| 计数时钟 | 32765 Hz（睡眠时钟） | :129 `WDT_HZ = 32765`（注释 :125–129） | DT clock rate（:240），本机按 CAF 常数 |
| 计数宽度 | 20 位，上限 0xFFFFF | :397 读计数 `(STS>>1)&0xFFFFF` | :187 `max_tick_count = 0xFFFFFU`；:241–242 rate 须 ≤ 上限 |
| 量程上限 | 0xFFFFF / 32765 ≈ 32.0 s | — | 同左 |

平台侧在册证据：内存映射 `PlatformMemoryMapLib.c:144` 与
`uefiplat.cfg:83` 均有 `APSS_WDT_TMR1 0x17C10000 + 0x1000, AddDev,
MMAP_IO, UNCACHEABLE, MmIO, NS_DEVICE`——DXE 阶段该块为非安全设备
MMIO 映射，可直接 MmioWrite32 编程；厂商 `QcomWDogDxe`
（Silicon/QC/QcomPkg/Drivers/QcomWDogDxe）在本固件 BUILD_REPORT
在册、其 FFS 已进 FVMAIN，它在 EL1-NS 对同一块的既有编程（二进制
数据点：写 [0x17C10014] ← 4 再写 EN ← 1，与本模型下「BITE_TIME 写
近零值 + EN bit0」的强制咬合惯用法同构，见 refs/wdt-model/README）
进一步证明该块在本固件环境可达可写。

## 换算复算（构建方独立复算，留痕）

计数时钟 32765 Hz、写值单位 tick：

- BARK = 26 s × 32765 = **851890**（0xCFFB2）
- BITE = 29 s × 32765 = **950185**（0xE7FA9）
- 两值均 < 0xFFFFF（1048575），余量分别为 196685 / 98390 tick；
  源码以 `STATIC_ASSERT(... < 0x100000)` 编译期兜底。
- BARK 先于 BITE 3 s：bark 时刻只产生（未使能的）bark 事件、
  不复位；bite 在交接后约 29 s 咬合。超时自 RST 写起算（见武装序）。

## 武装序与实现

语义照 CAF `init_wdog`（watchdog_v2-los.c:798–821：先写
BARK_TIME（:799）、BITE_TIME（:800），再写 EN = BIT(EN)（:816–820），
末写 RST = 1（:820））；主线 set_timeout/start 同构
（qcom-wdt-mainline.c:79–83）。RST 写 1 = 清计数并起算（喂狗同义，
:189、:406）；停狗 = 写 EN = 0（:196、:247）。实现
`M3KWatchdogArm()`，四次 MmioWrite32 写序不重排，末尾以
MmioRead32(EN) 回读作 posting read，确保交接前写已落地（不改变
语义，仅保证完成性）：

1. `MmioWrite32 (0x17C10010, 851890)` — BARK_TIME（EN 尚为 0）
2. `MmioWrite32 (0x17C10014, 950185)` — BITE_TIME（EN 尚为 0）
3. `MmioWrite32 (0x17C10008, 1)` — EN = bit0（**不置 bit1**：不碰
   bark 中断，bite 为无条件 SoC 复位，不需要中断通路）
4. `MmioWrite32 (0x17C10004, 1)` — RST = 1，计数自此起算
5. `(VOID)MmioRead32 (0x17C10008)` — 回读 EN 落地

**不喂狗**：交接后无人写 RST，计数直达 bite——这是设计目的。

落点：Boot() 内现有探针写点（PRB/SLT/VAR）之后、ExitBootServices
重试循环之前，排在该段最末，使计数起点尽量贴近交接；ExitBootServices
成功至 DarwinEnter 跳入内核的间隔为毫秒级，bite 实际发生在交接后
约 29 s（内核挂死场景）。Boot() 的全部失败路径（Fail 标签）在武装点
之前返回，失败轮次不带武装回菜单。

## Boot() 入口关狗与 PrePi 的关系

Boot() 第一条语句（参数校验之前）调用 `M3KWatchdogDisarm()`
写 EN = 0。平台 PrePi 本就每轮启动时关狗（M3I 审计结论），故正常
链路上入口关狗面对的是已静默的狗；它防的是 PrePi 之后、本轮
Boot() 之前任何阶段（包括上一轮咬合复位后的异常残留状态）留下的
武装——双保险，保证每轮 Boot() 从已知静默状态开始。菜单阶段
（Boot() 被调用之前）本版不做任何 WDT 访问。

## 菜单不受影响（论证，沿 M3I 审计结论）

- 武装只发生在 Boot() 的交接路径末段；进入菜单、浏览菜单、菜单内
  停留期间狗恒为静默（入口关狗 + 失败路径不武装）。
- 菜单 Restart / Power off 条目走固件自身的复位/关机通路，不经过
  Boot()，与武装无交集；M3I 审计已定案菜单阶段不武装则两条目不
  受 WDT 影响，本版严守同一边界。
- 唯一「带武装离开 Boot()」的出口是 ExitBootServices 成功后的
  DarwinEnter（不返回）与三次 EBS 全败后的 CpuDeadLoop（死循环
  约 29 s 后被 bite 复位回启动链，属自愈而非挂死；该路径历轮未
  出现过）。

## 残余风险

- 交接完成后狗仍在数秒：若 Yun 在咬合前（约 29 s 内）长按进
  fastboot 或切回 A 槽，武装可能在该窗口内**多咬一次**——表现为
  目标链路（ABL/fastboot/Android）启动初段的一次额外复位。ABL 与
  Android 链会自行接管/重程 WDT（其原生驱动即本模型的 CAF
  watchdog_v2），本固件链再入时有 PrePi 每轮关狗兜底，故至多
  一次且自限。止损与历轮相同：fastboot 切 A 槽后等约 30 s 让
  残余武装咬完（或直接正常使用，Android 侧会重程）。
- bark 未使能中断：26 s 的 bark 时刻无任何可见信号，屏幕判读以
  bite 复位（约 29 s）与次轮读回为准。
- 武装后若内核实际**正常运行并喂狗/停狗**（未来里程碑），本版
  武装会被内核的原生 WDT 驱动重程覆盖——属预期协作，非冲突。

## 构建与静态验证证据（2026-10-31 本轮）

- 基线/台架隔离：产品树 DarwinBoot.c 与存档 M3H 源码 + M3J 补丁
  MD5 逐字等合（3a0e1583…）后才动手；EL 门仍
  `(DarwinCurrentEl () != 4)` 单条件、DarwinBoot.c/Entry.S 中
  EL2 字样计数 0；产品 FDF 含 FvSimpleFileSystemDxe
  （SurfaceDuo1.fdf:157）；PythonLibs/emptyramdisk 仍 6 B 占位
  （MD5 f02e326f…）。stuart 全量重建一次 Success
  （logs/build-m3k-watchdog.log）。
- DarwinBoot.c 相对 M3J diff：+82 行 / −0（IoLib 头、M3K 定义与
  两助函数、入口关狗调用、武装调用，纯新增）；.inf +1 行（IoLib）。
- 反汇编实证（llvm-objdump，DarwinBoot.efi MD5 ba8bcd67…，
  22,016 B）：IoLib 收敛为两条 thunk——0x3a9c `str w1,[x0]; ret`
  （MmioWrite32）、0x3a8c 常数地址读 EN 的 posting read
  （`mov w8,#0x8; movk w8,#0x17c1,lsl #16; ldr wzr,[x8]; ret`）。
  Boot 内的武装序列（x27 = 0x17C10008 基准）逐字为：

  ```
  2918: mov  w1, #0xffb2          ; w1 低半
  291c: add  x0, x27, #0x8        ; x0 = 0x17C10010 BARK_TIME
  2920: movk w1, #0xc, lsl #16    ; w1 = 0x000CFFB2 = 851890
  2924: bl   MmioWrite32          ; ① BARK_TIME ← 851890
  2928: mov  w1, #0x7fa9
  292c: add  x0, x27, #0xc        ; x0 = 0x17C10014 BITE_TIME
  2930: movk w1, #0xe, lsl #16    ; w1 = 0x000E7FA9 = 950185
  2934: bl   MmioWrite32          ; ② BITE_TIME ← 950185
  2938: mov  w0, #0x8
  293c: mov  w1, #0x1
  2940: movk w0, #0x17c1, lsl #16 ; x0 = 0x17C10008 EN
  2944: bl   MmioWrite32          ; ③ EN ← 1
  2948: sub  x0, x27, #0x4        ; x0 = 0x17C10004 RST
  294c: mov  w1, #0x1
  2950: bl   MmioWrite32          ; ④ RST ← 1（起算）
  2954: bl   0x3a8c               ; ⑤ 回读 [0x17C10008] 落地
  ```

  入口关狗同址在 Boot 首部：`mov w0,#0x8; mov w1,wzr;
  movk w0,#0x17c1,lsl #16; bl MmioWrite32`（EN ← 0），位于参数
  校验分支之前。
- 格式串：`PSCI SURVIVED`、`PSCI TEST ARMED`、`PSCI NOFIRE`、
  `PSCI ODD k=%d`、`PRB OK/NO`、`SLT %s VAR %s`、`WIN %lx SZ %lx`、
  `EXC %lx ESR %lx`、`ELR %lx FAR %lx`、`PROG %lx CNT %lx`、
  `PROG NONE`、`DB 0 ENTER`、`M3Probe` 于 DarwinBoot.efi 中各恰
  1 次；FVMAIN.Fv 内 Sheng 计数 0。
- 同一性：整镜像 ramdisk 区与 M3G 逐字节相同（组装时对 M3J 与
  M3G 两镜像双向断言）；卷内 KERNEL MD5 = 850602e6…（M3G 补丁
  件）、KERNEL.ADT = 8766bcb3…、unixnu.toml = 08ec0480…；整镜像
  与 M3J 的 diff 全部落在 ramdisk 起点之前（ramdisk 起点后差异
  0 字节）；bootpayload 头部（BootShim 区）与 M3J 仅 2 字节
  尺寸字段不同。

## 真机判读

刷入切槽重启 → 首轮 Row 9 `PSCI TEST ARMED` 大字、约 15 秒自发
复位（M3J 自测试）→ 次轮见 `PSCI SURVIVED` 后正常交接、内核冻结
→ **什么都不按**，约 29 秒后看门狗咬合自复位 → 第三轮屏幕同时带
上轮内核的 PROG/EXC 读数，整屏拍照。此后设备以约「启动 + 29 秒」
为周期自循环（每轮交接后武装、咬合复位、读数每轮重画），拍照
窗口充足。收尾：长按进 fastboot 切回 A 槽；切走后约 30 秒内
可能多咬一次，属预期（见残余风险）。
