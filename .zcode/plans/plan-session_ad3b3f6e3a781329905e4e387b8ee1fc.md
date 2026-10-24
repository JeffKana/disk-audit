# 前期内容定稿计划（不进入开发流程）

## 0. 本轮目标
完成立项后的四件前期事项：①上游资料归档 ②根目录文档入档 ③Hyper-V 结论与环境基线 ④治理与开发规范。**不写引擎代码**（Sprint 1 开发 10-27 才开始）。

## 1. 上游资料归档（待办 A3）
- 用 `cp -r` 从 `C:\Users\querkecor\WorkBuddy\电脑磁盘清理大师\` 拷贝到 `docs/upstream/`，**排除 `.workbuddy/`**（AI 工具内部记忆，非项目资料；原路径在归档说明中注明）
- 完整保留 `poc/build`、`poc/dist`（含 U1 动作需要的 `poc2_tk.exe`）于本地，但 **git 不纳管**（见第 7 条）
- 更新 `docs/upstream/README.md`：勾销 9 项清单，并按实际内容修正（evidence 实为 5 个分文件 uninstall/appx/processes/services/runkeys.json；补充技术选型决策表、历史落地方案、W0 POC 报告与全部 POC 脚本、build_decision.py / build_html.py、poc4_bigreport.html）
- 用 diff/字节数抽查验证拷贝完整性

## 2. 根目录两份 HTML 移入归档（你的建议）
- `mv 磁盘体检_v0.1方案_定稿_2026-10-23.html`、`AppData残留识别_调研与自研可行性报告.html` → `docs/upstream/`（与 WorkBuddy 副本同名同大小，冲突时以项目根目录版为准）
- 更新所有引用链接：`README.md`（改指 `docs/upstream/…`）、`docs/agile/00、01、02`（改 `../upstream/…`）

## 3. Hyper-V 结论与环境基线 → `docs/governance/环境基线.md`
探测结论写入文档：
- Windows 为 Pro 级（lusrmgr.msc 存在），**Hyper-V 支持但未安装**（vmms.exe、Hyper-V PS 模块缺失）；WSL2/HCS 在用（vmcompute.exe 存在），CPU 虚拟化已开，启用阻力小
- 资源：内存 32GB；磁盘 C 剩 20G / D 剩 13G / E 剩 40G
- **启用步骤（你执行，需管理员 + 重启一次）**：`DISM /Online /Enable-Feature /All /FeatureName:Microsoft-Hyper-V`，重启后 `Get-VM` 验证
- VM 约定：磁盘根目录 `E:\Virtual Machine\disk-audit\`，22H2/24H2 各一父镜像 + 差分盘（M1 约 35~45GB 预算；M4 扩 8 台时滚动重建）。注明：你的答复提到 "Virtual Machine" 目录与 D 盘装软件——D 盘仅剩 13G 不够两个父镜像，故默认 E 盘；坚持 D 盘需先清理 ≥40G
- 风险提示：启用 Hyper-V 后旧版 VMware Workstation（<15.5.5，本机未装）不兼容；Docker Desktop/WSL2 不受影响

## 4. 项目治理文档 → `docs/governance/项目治理.md`
- 目录结构与归档规范（`docs/upstream/` 为唯一归档入口；构建产物/二进制不进 git）
- **分支与合入（按你选定的方案）**：短分支 + PR 合入 main；main 保护规则建议（CI 必绿、禁 force push）；分支命名 `feature/PB-ID-摘要`、`fix/…`
- 版本与发布：P9 semver（0.1.0 起、-beta.N）；发布 checklist（SHA256SUMS、VirusTotal/SmartScreen 留档、已知限制清单）
- 变更管理：范围变更 → 方案第十三节变更记录 → 待办列表；三条不可协商底线不可变更
- 决策记录：`docs/governance/decisions/` ADR-lite（沿用方案 D/Q/P 编号，新增决策入册）
- 知识库治理：全部自行整理、不复制 BCU、来源登记字段、许可边界
- 安全底线执行清单（只读边界、交互白名单、DPAPI 永久保护、提权约束、Procmon 留档时点）

## 5. 开发规范文档 → `docs/governance/开发规范.md`
- Python：PEP 8、判定层纯函数强制类型标注、引擎/UI 解耦零 UI 依赖、中文 docstring
- 零依赖白名单机制：运行时仅标准库、开发期仅 pytest；CI import 白名单校验与增补流程
- 测试：pytest；硬保护 100% 覆盖；真实误判当天进回归集；回归样例 JSON 脱敏格式
- Git/PR：Conventional Commits + 中文描述；PR 自审清单（对照 DoD 六条）
- CI 四段门禁定义（tkinter 断言 / pytest / 构建 / --selftest）与失败处置
- AI 协作守则：AI 产出必须人审 + CI 绿才合入；AI 不执行 git push；超长命令拆小（WorkBuddy 踩坑记录）；本机 `python` 命令为 Store 存根会挂起、须用 POC 那套 3.13.5 完整路径

## 6. 状态同步
- `docs/agile/02_Sprint0与Sprint1_计划.md`：0.5 git init 标记你已完成；0.6 归档完成；新增 0.7 Hyper-V 启用（你执行）、0.8 首次本地验证与推远端（你执行）
- `docs/agile/01_产品待办列表.md`：A3 完成勾销；L1 备注环境结论
- `README.md`：目录说明补 docs/governance/，链接改归档路径

## 7. .gitignore 扩展
追加：`docs/upstream/poc/build/`、`docs/upstream/poc/dist/`、`*.exe`、`*.vhdx`、`*.vhd`（防 VM 磁盘误入仓库）

## 8. git 远端命令清单（交付给你执行——本会话 git.exe 挂起无法代跑）
```
git remote add origin https://github.com/JeffKana/disk-audit.git
git add -A
git commit -m "chore: 项目基线——敏捷文档、上游归档、治理规范与工程骨架"
git branch -M main
git push -u origin main
```
注：若 GitHub 建仓库时勾选了自动生成 README/LICENSE，push 前先 `git pull --rebase origin main`。

## 不做的事
- 不写引擎代码、不启动 Sprint 1 开发
- 不执行 Hyper-V 启用 / git push（需你的管理员权限与 GitHub 凭据）
- 不改动 WorkBuddy 原目录（只读拷贝）

## 执行可行性
cp/mv/ls/diff 均为 Git Bash 自带工具（本会话已验证可用）；文档用 Write/Edit。归档总量 62MB，其中约 50MB 构建产物仅留本地。