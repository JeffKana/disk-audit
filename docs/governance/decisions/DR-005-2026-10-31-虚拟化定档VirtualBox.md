# DR-005 · VM 虚拟化平台定档 VirtualBox（取代 DR-003 的 Hyper-V 部分）

- 日期：2026-10-31（补档；裁决日期 2026-10-25）
- 状态：已采纳（负责人 2026-10-25 裁决，PM 依治理 §5 补档）

## 背景

DR-003 定档 Hyper-V + `H:\Virtual Machine`。执行 R-L1 时发现：此前"Hyper-V 已开启"的确认失实——系统仅启用了"虚拟机平台"（HCS/WSL2 在用），`vmms.exe` 缺失，完整 Hyper-V 并未安装；启用需要管理员 DISM + 整机重启。负责人裁决改用 VirtualBox 7.2.22 完成基线，避免提权安装与重启。

## 决策

1. M1/M4 的 VM 矩阵运行在 **VirtualBox 7.2.22**；`H:\Virtual Machine\` 目录约定不变。
2. 已建资产（2026-10-26，R-L1 执行记录）：两个父镜像（L1-base-22h2 / L1-base-24h2，4GB/2vCPU/EFI+TPM 2.0/80GB 动态 VDI，快照 `base-v1` 冻结只读）+ 两台 linked-clone 差分验收机；GT 11 件（Chrome、Firefox、7-Zip、Notepad++、Git、VS Code、微信、QQ NT、WPS、网易云、Steam），双差分机 scan RC=0、selftest 6/6。
3. DR-003 中"E 盘改 H 盘"部分继续有效；其 Hyper-V 部分由本 DR 取代。

## 理由

VirtualBox 免提权安装、免整机重启，满足方案 9.3 对 VM 矩阵的全部功能要求（快照回滚、多配置组合）；Hyper-V 的差异化优势（更高性能/嵌套虚拟化）对 M1~M4 的只读扫描验收非必需。父镜像已 sdelete 置零 + compact（22H2 16.07GB / 24H2 43.8GB），可复现性不受影响。

## 影响面

- 《环境基线》§1/§2/§3 已随 PR#15 同步修订（Hyper-V 记录更正、实建资产表、M1 合计约 63G）。
- **H 盘余量告警**：仅剩约 11G；M4 扩 8 台差分机时必须滚动清理（验收完即删差分盘/子代），或评估迁移至其他盘（届时新建 DR）。
- 24H2 差分机内存紧张时以 headless 方式运行（R-L1 已记录）。
- M5 阶段"干净 VM 首次运行"（U2）可复用 `base-v1` 快照的全新克隆，无需 Hyper-V。
