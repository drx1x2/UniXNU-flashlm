# M3M — 摘除 PSCI 自发复位实验件（DarwinBoot 流程定版）

M3M = M3L 固件 − M3J/M3L 的复位实验件。删除补丁：
`darwinboot-psci-removal.patch`（相对 M3L 的 DarwinBoot.c，纯删除
149 行、零新增）。内核沿 M3L 逐字节不变；BootShim 沿 M3L 不重建。

## 为什么删（裁决回顾）

- M3L 真机：CPY NO NO——连 BootShim 在镜像入口（早于全部 UEFI）
  拷出的探针都是空，跨轮 DRAM 记录在本机判死，此线关闭。
- PSCI 状态机因 k 恒为 0，每轮在交接**之前**自发复位：M3K/M3L
  的真机轮次里内核从未运行，看门狗从未武装，locore 帧缓冲色块
  从未获得测试机会。本轮摘除该实验件即修复此耦合。

## 删除清单（DarwinBoot.c，相对 M3L）

1. `M3JPsciSystemReset()` 助手函数及其注释块（原 M3J 补丁，SMC
   发起 PSCI SYSTEM_RESET 的内联汇编函数）——30 行。
2. Boot() 读回块末尾的 PSCI 状态机整块：探针计数（M3L 改读
   BootShim 拷贝的接线在内）、写槽 0、缓存清洁、`PSCI TEST ARMED`
   驻留 15 s、SMC 复位、`PSCI NOFIRE` 上屏、`gRT->ResetSystem`
   兜底、`PSCI SURVIVED` / `PSCI ODD k=%d` 分支——与第 3 项合计
   119 行。
3. M3L 新增的 Row 8 `CPY %s %s` 读回块（含其注释块）。

删除后接缝与 M3J 之前结构一致：SLT/VAR 块（Row 7）之后直接进入
窗口地址计算（`ArgsAddress = ...`）。

## 新流程（Boot() 行为定义）

Boot() = 入口关狗 → 参数/镜像校验 → 分配窗口 → **读回上屏**
（DB 0 / WIN / EXC / PROG / PRB / SLT·VAR 各行）→ 窗口填充 →
**探针写点**（PRB 窗口内写、SLT 槽页写、VAR 变量写）→
**武装看门狗**（BARK 851890 / BITE 950185 tick，CAF 写序）→
ExitBootServices 尝试（≤3 次）→ DarwinEnter 交接。

### 不变式：Boot() 任何路径不得自发复位

- 成功路径止于 DarwinEnter；失败路径经 `Fail:` 释放资源后返回
  状态码、固件留存（菜单可达）。看门狗只在交接前武装，失败路径
  不武装（入口关狗后保持解除），菜单的 Restart / Power off 条目
  运行时无活狗。
- 源码自证（改后 DarwinBoot.c 全文检索）：`M3JPsciSystemReset`
  0、`smc` 0、`ResetSystem` 0、PSCI 魔数 `0x50534349…` 0。
  `PSCI` 一词的唯一残留是 M3E 读回块注释中描述**诊断内核**记录
  器行为的一句（"resets via PSCI"），属保留项 EXC 读回的说明
  文字，不是本驱动的调用点。
- 平台其它合法复位路径与本不变式的关系：复位只经 (a) ABL/UEFI
  菜单的 Restart / Power off 条目（用户动作，在 Boot() 之外）、
  (b) M3K 看门狗在交接后咬合（硬件超时，非代码路径复位调用，
  且正是交接后唯一的复位来源）、(c) 用户长按强制重启。DarwinBoot
  代码内不存在第四条。

## 保留项（逐项核对在位，.efi 静态计数）

- 读回行格式串（UTF-16 计数各恰 1）：`WIN %lx SZ %lx`、`PRB OK`、
  `PRB NO`、`EXC %lx ESR %lx`、`ELR %lx FAR %lx`、
  `PROG %lx CNT %lx`、`PROG NONE`、`SLT %s VAR %s`、`M3Probe`、
  `DB 0 ENTER`。
- 删除项格式串计数为 **0**：`PSCI TEST ARMED`、`PSCI SURVIVED`、
  `PSCI NOFIRE`、`PSCI ODD`、`CPY %s %s`（UTF-16 与 ASCII 双编码
  均 0）；PSCI 探针魔数在 .efi 中 0。
- 看门狗：Boot() 入口 `MmioWrite32(EN, 0)` 关狗（反汇编
  0x1188–0x11a8 实证）；交接前武装四写 + EN 回读在
  .text+0x17a4 起逐字在位且顺序正确（x27 = 0x17C10008 基准：
  BARK_TIME ← 0xCFFB2、 BITE_TIME ← 0xE7FA9、EN ← 1、RST ← 1、
  回读 EN；写 thunk `str w1,[x0]` @0x3928）。FVMAIN.Fv 内
  Sheng 计数 0。
- BootShim 不重建：新 bootpayload 解压流以 M3L BootShim.bin
  （160 B，MD5 `64a92a25…`）逐字开头，拷贝字 @dec[64..96] 与原
  槽位字 @dec[96..108] 逐字复核在位。

## 同一性证明

- DarwinBoot.c：M3L MD5 `5e472dfd…` → M3M MD5 `d403bee5…`，
  diff 纯删除 149 行 / 新增 0 行；DarwinBoot.efi 22,016 B →
  21,504 B。
- 组装沿原位换固件段：最终镜像 ramdisk 切片与 M3L 镜像**逐字节
  相同**（整镜像 diff 仅固件区，ramdisk 区 0 字节）；卷内
  KERNEL MD5 `884949415562806d6df07261aa70f7fa`（M3L 内核）、
  KERNEL.ADT `8766bcb3571f2b70dc03a4295c7ad824`、unixnu.toml
  `08ec0480941c9efea566189c6f6ff77e`（与 M3C 一致）。
- 产物 `builds/lg-flash-unixnu-m3m-fbmarks.img`，28,356,608 B，
  MD5 `46876c0fb4c2f805a247c2d7cc61ce54`，SHA-256
  `ba96703ab70bfafc38dfad14d7e1550cd6648dbdccbbc47ed3baa1123d5282fd`。

## 真机判读

刷入、切 B 槽、重启 → 菜单倒计时后**正常交接**（`DB 0 ENTER`
+ 顶部绿条，本轮起不再有 ARMED 自发复位拦截）→ 内核冻结，看
屏幕**最底部横带**亮起的彩色块：左→右 红 / 蓝 / 品红 / 青 /
黄 = locore 五步（__start / _start_first_cpu 入口 /
_start_first_cpu 尾 / common_start SCTLR 后 / common_start
出口）。整屏拍照。约 29 s 后看门狗咬合自复位、下一轮重画，
拍照窗口每轮都有。0 块也是有效读数（死点在交接尾巴或 FB
通路本身，另行诊断）；5 块全亮 = locore 全程通过、死点在
_arm_init 之后（与 M3F 的 PROG 互证）。
