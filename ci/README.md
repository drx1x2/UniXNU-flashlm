# CI：在 GitHub Actions 上编内核

这里放的是"设备仓库 + 一条 workflow"，用来在 macOS runner 上得到 xnu-8796 内核。
**为什么不在本机 Linux 上编**：Linux 工具链（`/opt/unixnu-linux`）能编到 848 个 `.o`，唯一卡点是
`iig`——它是 DriverKit 的接口生成器，输出格式跟 Xcode 世代绑定，新 iig 生成 `IORPC.kernelContent`，
而 8796 的 `IORPC` 没有这个字段。Xcode 15 的 iig 才是对的（cepheus 的 8796 CI 也钉在 Xcode 15）。

## 文件

| 文件 | 作用 |
| --- | --- |
| `.github/workflows/kernel-8796.yml` | 克隆 UniXNU → 打 `ci/0019-unixnu-8796-ci.patch` → `unixnu build kernel` → 传 artifact |
| `ci/0019-unixnu-8796-ci.patch` | 本设备仓库对 UniXNU 的改动**只保留内核相关部分**：`feeds.toml` 钉 8796、`patches/xnu/*`、`scripts/unixnu/ipsw.py`。**不含** `package/`（固件侧）、**不含** dirty 子模块指针 |

## 推之前的三件事

1. **仓库放 GitHub**。macOS runner 在**公开仓库**上是免费的；私有仓库按 10× 计费，
   免费额度 2000 min/月 → 实际只有 ~200 macOS 分钟，**一次内核构建就可能超**。
   建议：单独建一个**公开的 CI 仓**（只放本目录的 `board.toml`、`configs/`、`scripts/`、`ci/`），
   主工作区继续私有。不要推 IPSW、kernelcache、设备分区镜像（纪律 C-03 / P5）。
2. **确认 UniXNU 提交**：workflow 默认 pin 到 `40d21cc`（2026-10-28 验证过 patch 能干净打上）。
   上游 main 变动时改 `unixnu_sha` 输入即可，不用改代码。
3. **跑一次要多久**：macos-14 标准 runner 是 3 核，`unixnu build kernel` 含一次 bootstrap pass，
   预计 **2–3 小时**（超时上限设 350 分钟）。产物 ~几百 MB。

## 跑完拿什么、怎么用

artifact `kernel-8796` 里有：

```
mach.development.bcm2837.unstripped     ← 内核（4 KiB 页，BCM2837 machine config）
kernel.log + out/flashlm/logs/*.log       ← 构建日志
```

拿到本地后：

```sh
unzip kernel-8796.zip -d /tmp/k8796
cd <UniXNU checkout>
# 1) 直接当 payload 的内核用（跳过 prelink）
python3 unixnu payload --kernel /tmp/k8796/mach.development.bcm2837.unstripped \
        -D ../UniXNU-flashlm
# 2) 但它写的是 FAT32/整数 MiB —— B1 的 512 KiB FAT12 还没脚本，先手工做（见 NOTES.md B1）
```

## 这条 workflow 的边界（别误解）

- 产出的是 **UniXNU 主线风格的 4 KiB 内核**（无内置 HFS/AMFI、无 prelink）：
  - ✅ 可以冲 **M3**（内核入口、打印版本与 boot args、平台专家匹配 ADT）；
  - ❌ 到不了 **M4**（没有 Apple kext，也没有单体内核里的 HFS/AMFI/UFS）。
- 想要 **iOS 16 用户态**，内核必须走 cepheus 8796 那条**单体内核**线（内置 HFS/AMFI/pthread/UFS、
  iPhone X 身份、16 KiB 页）。那是另一条 workflow（`MACHINE_CONFIG=FLASHLM` + 板级件替换），
  目前**还没准备**，因为要先做板级移植；见 开发工作区 `docs/notes/16-ios16-route.md` §16.3。
- prelink 那一步会**故意失败**（board.toml 没有 `[kernel.prelink]`，且 16.7.16 的 kernelcache 是
  `8796.142.1`、与源码 `141.3` 不同修订）。workflow 用 `|| true` 接住，再用 `test -f` 断言内核二进制存在。
