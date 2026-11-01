> **交接（2026-11-01）**：项目现状、死点定位结论与后续路线见 [HANDOVER.md](HANDOVER.md)，接手前先读它。

# UniXNU device repository — LG V50 ThinQ (flashlm, SM8150)

LG V50 ThinQ（LM-V500，`flashlm`，骁龙 855 / SM8150）的 UniXNU 设备仓库。
结构与路线照同厂同 SoC 的 [UniXNU-mh2lm](https://github.com/shenli99/UniXNU-mh2lm)（LG G8X）
移植，目标系统为 iPhone X 身份的 iOS 16.7.16 用户态 + xnu-8796 单体内核，
与 guacamole（OnePlus 7 Pro，SM8150，已真机进用户态）同一条线。

## 当前阶段（2026-10-29，P1 骨架）

- 设备仓库骨架已建：`board.toml`、`configs/flashlm_defconfig`、ADT 工具链
  （`scripts/devices.py` 已加 `flashlm` profile）。
- **ADT 已能离线生成**：`python3 scripts/mkadt.py out.adt --device flashlm
  --dram-size 0xc0000000` → 9904 B。目前缺 `base-d22ap.adt`
  （Apple 的 /product 身份节点，要从 iOS 16.7.16 IPSW 里抽），生成时有警告。
- 板级关键值已定（来源：Project Aloha 的 `lg-flash` 目标）：
  - 面板 1440×3120，framebuffer（Display Reserved）`0x9C000000 + 0x01200000`
  - ABL "Kernel" 区 `0x80000000 + 0x02A00000`（42 MiB）
  - UEFI FD `0x9FC00000 + 0x00300000`
- 内核（`kernel.macho`）还没有：走 CI（macOS + Xcode 15 编 xnu-8796）或本地工具链。

## 与 mh2lm 的关键差异

| 项 | mh2lm（G8X） | flashlm（V50） |
| --- | --- | --- |
| Aloha 设备目标 | `lg-mh2lm`（较新） | `lg-flash`（上游现成，含 DTB/内存映射） |
| ABL Kernel 区 | 仅 6 MiB | 42 MiB |
| Display Reserved | `0x9D200000`（与 DTB splash 不一致） | `0x9C000000`（与内存映射一致） |
| payload 路线 | FV 内 512 KiB FAT12（B1） | 同左（LG ABL 的 ramdisk 看门狗同样适用） |

## 硬规则（沿 mh2lm）

1. **只 `fastboot boot`，不写任何分区**（不 `flash`/`erase`/`format`）。
2. **Apple 产物不入库**：IPSW、kernelcache、DeviceTree、`scripts/base-d22ap.adt`
   由工具在本地抽取/校验。
3. 版本三角是硬约束：iOS 16 用户态需要 **16 KiB 单体内核**，理由见 `DEVIATIONS.md`。

## 里程碑

- **M1**：UEFI 菜单在 V50 面板上出现（Aloha `lg-flash` + UniXNU 菜单，`fastboot boot`）
- **M2**：DarwinBoot 校验通过并 ExitBootServices（stub 内核即可验收）
- **M3**：真内核入口 + 串口/帧缓冲打印 + 平台专家匹配 ADT
- **M4**：UFS root 挂载 → iOS 16.7.16 用户态（对标 guacamole r15）
- **M5**：触控/USB/显示等驱动逐个补齐（GPU 为已知难点）

## CI：编内核

同 mh2lm：触发 `.github/workflows/kernel-8796.yml`（macOS runner + Xcode 15，
约 1–2 小时），产物 artifact `kernel-8796`。仓库须公开（macOS 分钟计费原因见 mh2lm README）。

## 本地：payload / ADT（Linux，秒级）

```sh
# 1) 拿内核后生成 ADT（需先按下面从 IPSW 抽 base-d22ap.adt）
python3 scripts/mkadt.py out.adt --device flashlm --dram-size 0xc0000000

# 2) IPSW: iPhone10,3,iPhone10,6_16.7.16_20H392_Restore.ipsw（需自备）
python3 scripts/adt.py unwrap Firmware/all_flash/DeviceTree.d22ap.im4p scripts/base-d22ap.adt
```

## 不放进仓库的东西

IPSW / kernelcache / DeviceTree 原文件、`scripts/base-d22ap.adt`、任何设备分区镜像/备份。
