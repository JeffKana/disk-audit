---
name: vm-ops
description: 磁盘体检（disk-audit）项目的 VirtualBox VM 实验室操作手册。凡需要启动/克隆/快照/回收 VM、经 guestcontrol 操作虚拟机内部（跑命令/拷文件/装软件/截图）、执行 T2-09 归属率实测、M4 八台矩阵验收、M5 干净机首跑，或排查 VM 挂死/睡眠暂停/磁盘写满/Winget 崩溃时必须使用——即使没说"VM"两个字。
---

# VM 实验室操作（磁盘体检 / VirtualBox 7.2.22）

权威事实以《[环境基线](../../../docs/governance/环境基线.md)》§2/§3 为准；本技能是其操作化版本。R-L1 建成记录（含 WU 排障全链）见 PR#15 执行记录（`docs/agile/05_Sprint2_计划与任务卡.md` 的 R-L1 卡）。

## 机队清单（全部位于 `H:\Virtual Machine\`）

| VM | 角色 | 要点 |
| --- | --- | --- |
| L1-base-22h2 | 父镜像（22621.382 Pro zh-CN） | 快照 `base-v1` 冻结只读；python+repo 已烤入 |
| L1-base-24h2 | 父镜像（26100.9711 Pro zh-CN） | 同上；VDI 43.8G（WU 载荷大） |
| L1-acc-22h2 | linked-clone 差分验收机 | GT 11 件已装 |
| L1-acc-24h2 | linked-clone 差分验收机 | 同上 |

Guest 账号 `qa`（autologon、UAC 静默 ConsentPromptBehaviorAdmin=0 已配置）。

## 五条运行纪律（违反的代价见括号，都已实际发生过）

1. **24H2 系 VM 全程 headless**：禁止 GUI 附加（`--type separate` 触发 GA 显示驱动挂死，只能回滚快照）。
2. **长任务先抑制主机睡眠**：主机 System Idle 睡眠会暂停全部 VM——任务前置位 `SetThreadExecutionState(0x80000003)`（4 小时持有）。
3. **新建 VM 一律 `clonevm --basefolder 'H:\Virtual Machine'`**：默认目录落 C 盘，曾把 C 盘写满触发 VBox 磁盘满保护自动暂停。
4. **H 盘仅剩 ~11G**：建新差分盘前先 `df` 核对；M4 八台矩阵滚动创建/销毁，验收完立即回收差分盘。
5. **父镜像快照永不改动**：一切实验在差分机/新克隆上；镜像回收前 sdelete 置零 + `modifymedium --compact`（22H2 曾压至 16.1G）。

## guestcontrol 五坑（MSYS Git Bash 环境）

1. 置 `MSYS_NO_PATHCONV=1`——MSYS 路径转换会篡改 `/c` 之类参数。**漏置时 `run` 不是立即报错，而是挂在进程启动回执等待（WaitForArray 30s 超时、VBOX_E_IPRT_ERROR），与"GA 未就绪/账号锁定"同形**；mkdir/copyto 等文件通道操作不含 `/` 开头参数不受影响，会进一步掩盖根因（2026-11-01 T2-09 子项③实证）。
2. `copyto` 源必须 **Windows 风格路径**（`H:\...`），目标同理；置了 `MSYS_NO_PATHCONV=1` 后读宿主文件也要用 Windows 路径（`/h/...` 会被原生工具当选项前缀）。
3. 复杂/多命令操作写成 `.cmd` 脚本拷进去执行，不要在命令行嵌套引号；`run` 的 guest 命令用完整路径 exe（`'C:\Windows\System32\cmd.exe' '/c' '...'`）最稳。
4. 控制台打字注入避开 `>&|` 字符；`screenshotpng` 在 7.2.22 归 `controlvm` 子命令（`VBoxManage controlvm <vm> screenshotpng <file>`），输出路径同样受路径转换影响（Windows 风格）。
5. **探活/排障不吞 stderr**（勿 `2>/dev/null`）——报错原文是定位第一线索；桌面状态存疑时先 `controlvm <vm> screenshotpng` 截图（headless 黑屏 = 显示器断电属正常，autologon 失败则见登录屏）。

## 常用操作配方

```bash
# 启动（headless）与查询
VBoxManage startvm L1-acc-22h2 --type headless
VBoxManage list runningvms

# guest 内执行命令（账号 qa）
MSYS_NO_PATHCONV=1 VBoxManage guestcontrol L1-acc-22h2 run \
  --username qa --password '<口令>' --wait-stdout --wait-stderr \
  -- 'C:\Users\qa\repo\run_scan.cmd'

# 拷贝仓库进 guest（源用 Windows 路径）
MSYS_NO_PATHCONV=1 VBoxManage guestcontrol L1-acc-22h2 copyto \
  --username qa --password '<口令>' \
  'E:\develop\project\磁盘体检大师\disk_audit' 'C:\Users\qa\repo\disk_audit'

# 截图（输出路径 Windows 风格）
VBoxManage screenshotpng L1-acc-22h2 'H:\vm-shots\acc22h2.png'

# 快照：GT 装完后打标；验收后回滚差分机
VBoxManage snapshot L1-acc-22h2 take gt-v1
VBoxManage snapshot L1-acc-22h2 restore gt-v1
```

口令来源：负责人处获取；**凭据不写入任何文件、不打印到执行记录**。

## Guest 内装软件与 Windows 更新

- **winget 在 22H2（v1.2）崩 0xC0000005** → 改官方安装包直下 + 静默开关（如 `/S`、`/qn`）。
- **Windows 更新卡在 DO 载荷 CDN**（tlu.dl.delivery.mp.microsoft.com 不可达）→ 注册表 `DODownloadMode=0` 直连 download.windowsupdate.com（需提权）→ guestcontrol 进程非提权 → `Start-Process -Verb RunAs` + 注入应答 UAC（UAC 已静默，左键+回车即过）。全链细节见 PR#15 执行记录。
- GT 清单（11 件）：Chrome、Firefox、7-Zip、Notepad++、Git、VS Code、微信、QQ NT、WPS、网易云音乐、Steam——覆盖 Program Files / Local / Roaming 三类写入位；新装软件按同口径补登记。

## 与其他技能的边界

- 领任务卡执行 → exec-sop；本技能只管"VM 这台机器怎么操作"。
- 归属率实测的判定口径（9.2、GT 分母）→ accept-verify / 《交付与验收流程》§3。
- VM 出现新型故障 → 修复后把新坑补进《环境基线》§2/§3 与本技能（勿只留在执行记录）。
