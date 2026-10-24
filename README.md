# 磁盘体检（disk-audit）

> **只诊断，不动手。**

扫描本机磁盘，判定每个大目录“属于谁、是不是残留、凭什么这么判”，输出可审计、可分享的离线报告。**本工具不执行任何删除。**

- 方案基线：[磁盘体检 v0.1 方案（定稿 F1）](docs/upstream/磁盘体检_v0.1方案_定稿_2026-10-23.html)
- 市场调研：[AppData 残留识别调研与自研可行性报告](docs/upstream/AppData残留识别_调研与自研可行性报告.html)
- 敏捷过程：[docs/agile/](docs/agile/)（开发指南 / 产品待办列表 / Sprint 计划）
- 治理与规范：[docs/governance/](docs/governance/)（项目治理 / 开发规范 / 环境基线）
- 上游归档：[docs/upstream/](docs/upstream/)（方案、调研、选型决策、POC、原型、数据）

## 状态

v0.1 开发中（M1 引擎阶段 · Sprint 1）。支持矩阵：Windows 11 x64 22H2（build 22621）及以上，仅固定本地盘。

## 开发

要求 CPython 3.13.x（构建机 3.13.5，须含 Tcl/Tk —— 缺失只在运行时暴露，CI 有门禁）。

```bash
python -m pytest                 # 单元测试（开发期唯一第三方依赖：pytest）
python -m disk_audit --selftest  # 内置自检（CI 门禁）
```

运行时零第三方依赖，仅标准库；打包用 PyInstaller `--onedir`（随 M5 接入）。

## 目录

```
disk_audit/       引擎与 CLI（判定纯函数、零 UI 依赖）
tests/            pytest 测试
docs/agile/       敏捷开发文档（指南 / 待办 / Sprint 计划）
docs/governance/  项目治理 / 开发规范 / 环境基线 / 决策记录
docs/upstream/    上游资料归档（方案、调研、POC、原型、数据）
```

## 安全边界

本程序自身仅在 `%LOCALAPPDATA%\DiskAudit\` 内写入；对被扫描对象、注册表、文件属性零写入。`Roaming\Microsoft\Protect`（DPAPI 密钥）与 `Crypto` 永久标记“受保护”——删除它们会导致浏览器密码、证书、Wi-Fi 凭据**永久无法解密**。提权进程同样只读、不联网、不执行任何外部程序。

## 许可

Apache-2.0。判定仅供参考，处置后果由用户自行承担；本工具不含任何删除能力。
