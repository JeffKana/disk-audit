# CI/CD 规范（磁盘体检 / disk-audit）

流水线的**唯一权威定义**：哪些门禁、何时触发、谁可合入、产物去哪。门禁的技术失败处置见《[开发规范](开发规范.md)》§5；本文件管流程。实施节奏与里程碑对齐（分阶段启用，不提前实现）。

## 1. 现状（2026-10-24）

- 已有 `.github/workflows/ci.yml`（阶段 A，三段门禁），远端 **ci #1 运行成功（26s）**。
- main 分支 push 与 PR 双触发；windows-latest + setup-python 3.13。
- CD（发布流水线）**尚未建设**，规范先行，S10 起实施（§3 阶段 D）。

## 2. 触发与合入策略

| 事件 | 触发 | 作用 |
| --- | --- | --- |
| 任意 PR（→ main） | ci | **合入前置门禁**：不全绿不可合并（main 保护规则强制） |
| push 到 main | ci | 合入后复核；红灯=当天最高优先修复 |
| tag `vX.Y.Z`（S10 起） | release | 构建双形态产物 → **Release 草稿**（不自动发布） |
| 手动 `workflow_dispatch`（S9 起） | acceptance | 里程碑验收流水线（回归集 + 基准），仅项目经理触发 |

- main 保护规则（负责人在 GitHub 仓库设置一次）：要求 CI 绿灯合并、禁止 force push、禁止直接 push（仅 PR 合入）。
- PR 流程与角色分工见《[交付与验收流程](交付与验收流程.md)》。

## 3. 流水线分阶段全景

### 阶段 A：基础门禁（✅ 已上线，S0~S1）

```
① tkinter 断言   python -c "import tkinter"          ← C4 教训：缺失只在运行时暴露
② pytest         全部单元测试                          ← 禁止删用例换绿灯
③ --selftest     内置自检，退出码 0
```

### 阶段 B：零依赖与构建门禁（S1~S2 接入）

```
④ import 白名单  扫描 disk_audit/ 的 import 仅允许标准库+包内模块；
                 产物中不得出现 site-packages 第三方包        ← A4（S1）
⑤ 构建+产物自检  PyInstaller --onedir → 产物内 import tkinter 断言
                 + 产物 --selftest（S2，J1 前置）
```

### 阶段 C：里程碑验收流水线（S9，手动触发）

```
⑥ 回归集全量     判定样例 JSON 数据驱动回归（M4 前 ≥30 例）
⑦ 性能基准       报告 5000 行首屏/筛选基准（阈值告警不阻断，数据留档给 M4 验收）
```

### 阶段 D：CD 发布流水线（S10~S12，tag 触发）

```
构建 portable zip + Inno Setup 安装包
→ 生成 SHA256SUMS
→ GitHub Release【草稿】+ 变更说明 + 已知限制清单
→ 【人工闸门】负责人核对 VirusTotal/SmartScreen 留档（U1~U3）后手动发布
```

## 4. CD 原则（不可协商）

1. **不自动发布**：Release 永远停留在草稿态，等人工确认（与方案"不自动下载并安装更新"同源）。
2. **产物不进 git**：构建产物仅存在于 Actions artifact 与 Release 附件；`.gitignore` 永久排除 `*.exe`、`dist/`。
3. **可追溯**：Release 必须对应 git tag + 提交哈希 + CI 运行链接；`SHA256SUMS` 由流水线生成，不手写。
4. **发布前置条件**（发布 checklist 见《项目治理》§3）：里程碑验收全过、回归集 100%、三件套齐备、安全留档齐备。

## 5. 机密与安全

- 仓库**零机密**设计：不引入任何 token/签名密钥；GITHUB_TOKEN 足够（无部署目标）。
- 若未来需要签名（超出 v0.1 范围）：密钥只进 GitHub Secrets，先建 DR 决策。
- workflow 文件本身的修改走 PR（治理 §2），CI 失败不改 workflow 换绿灯，先查代码。

## 6. 指标与留存

- 每次里程碑验收回填：CI 平均时长、红灯次数、失败步骤分布（敏捷指南 §6 度量）。
- Actions artifact 保留 30 天默认值即可；Release 附件永久。

## 变更记录

| 日期 | 变更 | 原因 |
| --- | --- | --- |
| 2026-10-24 | 初版定稿（阶段 A 已上线） | 项目经理职能落地，开发阶段前置确认 |
