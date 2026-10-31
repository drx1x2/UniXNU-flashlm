# Device agent guide — LG V50 ThinQ (flashlm)

本仓库是 **format 1** 的 UniXNU 设备仓库（没有 `schema_version = 2`，没有 `porting.toml`）。
选择 format 1 的原因与代价写在 [DEVIATIONS.md](DEVIATIONS.md)；改路线前先读它。
本文件由 UniXNU-mh2lm 的同名文件改写——两台机器同厂（LG）、同 SoC（SM8150）、
同 ABL 世代，mh2lm 的真机教训默认适用于 flashlm，除非有 flashlm 自己的证据推翻。

## 本仓库拥有什么

| 东西 | 位置 |
| --- | --- |
| 设备描述（IPSW 身份、内核 defconfig/归档、payload、bootimg 偏移） | `board.toml` |
| 内核开关 | `configs/flashlm_defconfig` |
| ADT 生成（板级值 + 设备树构建） | `scripts/devices.py`、`scripts/mkadt.py`、`scripts/make-flashlm-adt.py`、`scripts/adt.py` |
| 内核构建 CI（macOS + Xcode 15） | `.github/workflows/kernel-8796.yml` |
| 对 UniXNU 的改动（补丁） | `ci/0019-unixnu-8796-ci.patch` |
| 固件输入清单 | `proprietary-files.txt` |

## 先读这些

| 任务 | 必读 |
| --- | --- |
| 任何改动 | [DEVIATIONS.md](DEVIATIONS.md)（为什么是 format 1）、[README](README.md)、`ci/README.md` |
| 内核/补丁 | [UniXNU: source and patches](https://unixnu.com/xnu/source-and-patches)、`ci/README.md` |
| 启动链/镜像 | [Payload](https://unixnu.com/concepts/payload)、[UEFI firmware](https://unixnu.com/porting/uefi-firmware)、[bring-up](https://unixnu.com/porting/bring-up) |
| 硬件事实 | Project Aloha `Platforms/SurfaceDuo1Pkg/Device/lg-flash/`（内存映射、DTB、PCD）；mh2lm 的 NOTES.md（LG ABL ramdisk 看门狗、FV payload 路线） |

## 硬规则

1. **只 `fastboot boot`，不写任何分区**（不 `flash`/`erase`/`format`；写 userdata 属于需要单独批准的动作）。
2. **Apple 产物不入库**：IPSW、kernelcache、DeviceTree、`scripts/base-d22ap.adt`。它们由工具在本地抽取/校验。
3. **不要改 `mkadt.py` 产出的节点语义去"绕过"内核检查**：`/chosen` 必须带 CHRP NVRAM proxy，`/options` 必须存在
   （`ArmDTPlatform::configure()` 缺任一都拒绝启动）。
4. 改内核补丁后，**同一提交里**更新 `ci/0019-unixnu-8796-ci.patch`，否则 CI 与本地树不一致。
5. 版本三角是硬约束：iOS 16 用户态需要 **16 KiB 单体内核**；不要试图用"源码内核 + 原版 kernelcache prelink"
   去配 iOS 16（`DEVIATIONS.md` 有实测表）。
6. **LG 特有**：payload 默认走 FV 内 FAT12（B1 路线），不走 boot.img ramdisk——LG ABL 对
   带大 ramdisk 的 boot.img 有 ram console / secure watchdog 检查（mh2lm 真机实测）。

## 常用命令

```sh
# 本地：选配置、检查解析
python3 unixnu defconfig flashlm_defconfig -D ../UniXNU-flashlm
python3 unixnu status -D ../UniXNU-flashlm

# 本地：生成 ADT（需要 scripts/base-d22ap.adt 才有 /product 节点）
python3 scripts/mkadt.py out.adt --device flashlm --dram-size 0xc0000000

# 内核：不在本地编，跑 CI（Actions → kernel-8796）；产物是 artifact kernel-8796
```

## 记录方式

format 1 没有 `porting.toml` 和记录检查。证据仍要留：

- 构建/启动结果写进开发工作区的 `evidence/<任务>/`；
- 本仓库里只保留**可复现的输入**（board/defconfig/scripts/CI patch）和结论性说明（README/DEVIATIONS）。
