# 为什么这个仓库是 format 1（与官方 8 步的偏离说明）

官方 [Port a device](https://unixnu.com/porting/) 的 8 步是按 **format 2** 写的。本仓库是 **format 1**，
不是疏忽，而是 format 2 的三个前提对 **iOS 16 用户态** 都不成立。这个文件把偏离、证据和补救方式记清楚，
方便后来人（或上游维护者）判断要不要迁。

## 1. format 2 需要什么

| 前提 | 官方在哪定义 | 我们的现状 |
| --- | --- | --- |
| `UniXNU-<soc>-common`（SoC 共享仓：soc.toml、DTSI、platform ops、补丁） | [SoC support](https://unixnu.com/porting/soc-support) | 上游没有 SM8150 的共享仓；`UniXNU/UniXNU` 的 `devices.toml` 里 SM8150 设备全是社区 format 1（`cepheus`、`guacamole` 都写着 `format = 1`） |
| OS profile（`profiles/os/<name>/profile.toml`：xnu 版本、ABI、prelink、OS 补丁） | [OS profiles](https://unixnu.com/reference/configuration) | 上游只有 `ipados-17.7.11-21H461`，**没有 iOS 16** |
| 可配对的 prelink（源码内核 + 同修订的原版 kernelcache） | [Prelink](https://unixnu.com/concepts/prelink) | **iOS 16 没有开源源码**（见 §2），prelink 无法成立 |
| `board.toml` 用 `[components]` + `[device_tree]`（DTS→ADT） | format 2 模板 | 我们的 ADT 由 `scripts/mkadt.py` 直接生成（sweet 内核的形状），没有 DTS |
| `porting.toml` + 记录检查 | [Device records](https://unixnu.com/porting/records) | 检查器强制 `board.os_profile` 与 `board.components.include`（`scripts/porting-record.py:65,71`），format 1 没有这两个字段 |

## 2. 关键证据：iOS 16 的内核与开源 tag 对不上

用区间读取（每个只下 ~18 MB）实测了 5 个 IPSW 的内核版本：

| 系统 | 内核版本 |
| --- | --- |
| iOS 16.5.1（20F75，iPhone10,3） | `xnu-8796.122.5` |
| iOS 16.6（20G75） | `xnu-8796.142.1` |
| iOS 16.6.1（20G81） | `xnu-8796.142.1` |
| iPadOS 16.6.1（20G81，j120ap） | `xnu-8796.142.1` |
| **iOS 16.7.16（20H392）** | **`xnu-8796.142.1.703.8`** |
| macOS 13.5 | `xnu-8796.141.3` |

而 Apple 开源的 xnu 只有三个 8796 tag：

```
xnu-8796.101.5   xnu-8796.121.2   xnu-8796.141.3
```

**没有任何 iOS 16 的内核版本在开源列表里。** 所以：

- 「源码内核 + 原版 kernelcache prelink」对 iOS 16 **不存在**可用组合（既没有 142 的源码，141.3 又与 142.1 不同修订）；
- 唯一被实机验证过的 iOS 16 做法是 **16 KiB 单体内核**（内置 HFS/AMFI/UFS，不 prelink），内核 141.3 + 用户态 16.7.16
  （参考 `guacamole` 在 SM8150 上的结果）。这条路线与 format 2 的 prelink 模型不兼容。

## 3. 因此本仓库的选择

- `board.toml` 保持 **format 1**（无 `schema_version`），模块解析走 `unixnu` 的 format 1 路径；
- 内核由 CI 用 **Xcode 15** 编（iig 世代问题），产物是 artifact，不进仓库；
- ADT 由 `scripts/mkadt.py` 生成，节点形状对齐单体内核（`/sweet-fbcon`、`/sweet-ufs`），并满足
  `ArmDTPlatform::configure()` 的硬要求（`/cpus`、`/arm-io`、`/defaults`、`/options` + `/chosen` CHRP NVRAM proxy）；
- 发布定位为 **format-1 社区设备**（与 `cepheus`、`guacamole` 同档），登记进 `devices.toml` 的 `format = 1` 条目。

## 4. 如果要迁到 format 2

需要依次补齐（按依赖顺序，均为月级工作）：

1. 建 `UniXNU-sm8150-common`：`soc.toml`、`dtsi`、platform ops、`patches/xnu/series`、`kits`；
2. 建 `profiles/os/ios-16.7.16-20H392`（含 ABI 与 prelink 定义）——**但 prelink 需要 142.1 的源码，目前不存在**；
3. 把 `mkadt.py` 的输出改写成 `dts/<device>.dts`，走 format 2 的 DTS→ADT；
4. 写 `porting.toml`（13 个 area）+ 启用 `Porting record` 工作流；
5. 通过记录检查后，把 `devices.toml` 条目从 `format = 1` 改为 `format = 2`。

**结论**：除非 (a) 改成跑 iPadOS 17（10063 线，prelink 可用），或 (b) 上游为 iOS 16 / 单体内核新增 profile 模型，
否则 format 2 无法表达这条路线。当前以 format 1 发布是**有意选择**，不是欠债。
