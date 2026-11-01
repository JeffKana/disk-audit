---
name: exec-sop
description: 磁盘体检（disk-audit）项目执行 Agent 的任务卡执行 SOP。凡用户要求"执行/领取/开始"某张任务卡（T-XX 或待办 ID）、发来任务卡内容、以执行 Agent 身份接手本项目开发任务、要求修复 PR 退回或 CI 红灯、或要求 push 分支/创建 PR 时必须使用——即使没说"SOP"三个字。覆盖：先读后做、依赖确认、建分支、测试先行、编码模式、自测、回填执行记录、push 与 PR、九条红线。
---

# 执行 SOP（磁盘体检 / disk-audit · v2 · 2026-10-31）

你现在是本项目的**执行 Agent**。本技能是《[交付与验收流程](../../../docs/governance/交付与验收流程.md)》§2 的可执行版；与文档冲突时以文档为准，优先级：**方案定稿 > 治理 > 敏捷指南 > 其他**（《项目治理》§4）。

## 边界：本技能管什么 / 不管什么

- **管**：一张任务卡从领取到"PR 等待验收"的全流程（读卡 → 读依赖 → 分支 → 测试 → 编码 → 自测 → 记录 → push → PR → 跟 CI → 退回处理）。
- **不管**：验收与 Sprint 评审（PM 职责，流程见《交付与验收流程》§3/§6）；Sprint 规划与建卡（§6）；VM 实验室深度操作（[references/rules-map.md](references/rules-map.md) 环境速查 + 《环境基线》§2/§3）；发布（项目治理 §3，S10 起）。
- **决策分级**（《交付与验收流程》§5）：实现细节（算法/结构/命名）自决并记入执行记录；技术偏离与验收标准歧义 → **上报 PM，D-技术裁决默认归 PM，你只交数据与选项，不代裁决**（先例：DR-004 选项 c 由负责人委托裁决、PM 事后会签并修正程序）；范围/排期 → 负责人。

## 第 0 步：识别任务卡

- 用户给了卡号（T-XX / 待办 ID）→ 到 `docs/agile/` 对应任务卡文件读全卡（Sprint 1 在 `03_Sprint1_任务卡.md`；Sprint 2 在 `05_Sprint2_计划与任务卡.md`；后续 Sprint 用最新编号文件，用 [references/rules-map.md](references/rules-map.md) 文档索引定位），包括文件开头的**通用红线**。验收报告里追加的卡（如 T2-08/T2-09）在对应 `0N_SprintN_验收报告.md`。
- 用户直接贴卡内容 → 以该内容为准，仍执行第 1 步读文档。
- 找不到卡或缺关键字段（目标 / 输入指针 / 验收标准）→ 停下要补卡，不脑补（字段清单见 DoR，交付与验收流程 §1）。

## 第 1 步：先读后做

按顺序读齐：① 任务卡全文；② 卡内"输入指针"指向的方案节 / DR / 归档物 / 代码路径；③ 《开发规范》《项目治理》相关条款（用 rules-map 场景表定位）；④ 依赖模块现有代码。

**冲突即停**：任何一项与任务卡冲突 → 停下回报冲突原文与出处，不自行取舍。只有不违反规范的实现细节可自决。

## 第 2 步：确认依赖

- 依赖未完成 → 执行记录标 `阻塞：依赖 xxx` 并回报，不得顺手先做。
- 依赖是**未合入的分支** → 可栈式切出：`git checkout -b <新分支> <依赖分支>`（不是 main），PR 描述注明"基于 <分支>"；**合入顺序 = 栈序**（先例：#21 C7 → #22 F1，F1 含 C7 的提交，乱序合会带进未验收内容）。

## 第 3 步：建分支

`git checkout -b <类型>/<待办ID>-<短横线摘要>`，类型 `feature/`、`fix/`、`docs/`、`chore/`（《项目治理》§2）。**分支名用卡内标注的待办 ID，不是 T-XX 卡号**（T-02 待办 C2 → `feature/C2-文件枚举器`）。一个分支一个待办条目。

## 第 4 步：测试先行

判定类逻辑：先写/补测试用例（**含反例**），跑红，再实现，跑绿。测试规范见《开发规范》§3；回归样例格式参考 `tests/data/regression/*.json`（R001~R005 先例：根因 / 禁词断言 / 期望依据）。

## 第 5 步：编码

遵守《开发规范》§1~§3：公共函数签名类型标注、判定逻辑纯函数、运行时零第三方依赖、枚举类异常按 X-1（跳过+计数+继续）、对外文案中文且集中在 `disk_audit/engine/texts.py`。涉及文件系统/注册表/提权的代码，先扫 rules-map 的**安全底线**。

**两个必守编码模式**（都有退回单/整改项先例，违反即 CI 假红或测试假红）：

1. **中文输出**：`tools/` 脚本含中文 print → 入口处 `sys.stdout.reconfigure(encoding="utf-8")`（stderr 同理，hasattr 守卫）。先例：T-01 退回单（runner stdout 默认 cp1252，中文 print 抛 UnicodeEncodeError 门禁假红）；CI 顶层已设 `PYTHONUTF8: "1"` 双保险。
2. **argv 隔离**：测试里调用脚本 `main()` → 显式传 `main([])` 或 monkeypatch sys.argv。先例：整改项 M-01（`test_real_package_passes` 未隔离，本地带 `-q/-v` 跑 pytest 必红）。

**口径红线**：动 `scanner.py` 占用空间/性能 → 先读 [DR-004](../../../docs/governance/decisions/DR-004-2026-10-24-占用空间取数性能.md) 全文含选项 c 裁决节（四段分流：压缩/稀疏句柄实查、≤600B align8、601B~<簇 句柄实查、≥簇 簇对齐；**勿重议，新卷先跑 `tools/probe_resident_allocation.py`**）；动报告结构 → `docs/schemas/report-v1.schema.json` 定稿 + Q7 版本语义；动知识库 → 治理 §6（503 条现状，修正当天进回归集）。

## 第 6 步：自测

- `python -m pytest` **裸跑**（不带 `-q/-v`：M-01 修复合入前带参会假红）+ `python -m disk_audit --selftest`，输出摘要贴执行记录。
- 本会话**可以直接运行** git / python / pytest（2026-10-24 env.sh 修复后实测；勿再因旧文档"沙箱挂起"拒绝执行或把验证推给负责人）。`python` 异常时用完整路径 `D:\develop\environment\python\python.exe`（CPython 3.13.5 含 Tcl/Tk 8.6）。
- 命令拆小（超长单行会被安全层拦截）；PowerShell 任务优先 `C:\Program Files\PowerShell\7\pwsh.exe -NoProfile -NonInteractive`；代码内 PowerShell 子进程必须绝对路径 `%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe`（W0 教训：PATH 裁剪时静默失败）。其余（GitHub 代理、VM、guestcontrol）见 rules-map 环境速查。

## 第 7 步：回填执行记录

任务卡"执行记录"区四项：

```
做了什么：<一段话 + 关键文件清单>
实现决策及依据：<每个自决/偏离点：决策 + 依据（方案节号/规范条号/DR 编号）>
未尽事项/已知限制：<新问题、已知缺陷——不顺手修，另立任务>
自测输出摘要：<pytest/selftest 数字；未覆盖的验收标准要标明>
```

## 第 8 步：push 与 PR（自办）

- **push 工作分支**：本仓库 origin 为 SSH（`git@github.com`），`git push -u origin <分支>` 直连即可；gh / REST API 先直连，失败再临时注入 `HTTPS_PROXY=http://127.0.0.1:7890`（勿写进仓库/全局配置，精化依据见 rules-map"GitHub 网络"）。
- **建 PR**：gh CLI；令牌失效则 `git credential fill` 取 PAT 走 REST（凭据仅内存，不打印不落盘）。PR 描述结构：

```
对应待办：<待办 ID>（任务卡 <T-XX>）
验收标准对照：
  ① <标准原文> → <结果/证据>
  ② …
自测：<pytest / --selftest 摘要>
状态：AI 辅助生成，待验收
```

- **main 分支保护**（2026-10-25 起）：合并必须走 PR 且必填 check `windows` 绿；enforce_admins 开启（管理员同受约束）；delete_branch_on_merge 生效（合完分支即删，重建显示 new branch 属正常）。
- **跟 CI**：`HTTPS_PROXY=… gh api repos/JeffKana/disk-audit/actions/runs?branch=<分支>` 查结论；红灯 → 查 jobs 定位失败步骤 → 修复 → 推回同分支 → 等绿 → 回报 PM 复验（CI-CD 规范 §5 失败处置；禁止删用例换绿灯）。
- 提 PR 前自查 DoD 六条（《敏捷开发指南》§3）。

## 九条红线（任何时候不得违反）

1. 不 merge、不 push main、不 force push、不删远端分支——**PR 是否合入由 PM 验收后决定并执行（DR-006）**，main 一切操作归负责人。
2. 不改任务卡验收标准——觉得有问题就回报，不改。
3. 不改 `.github/workflows/`（卡内明确例外授权除外）；若授权拆分 CI 门禁出新 check，**必须在同 PR 登记必填检查列表**（CI-CD 规范 §2，否则新门禁不设防）。
4. 不动 `%LOCALAPPDATA%\DiskAudit\` 之外的写入逻辑。
5. 发现新问题记执行记录"未尽事项"，不顺手修——另立任务。
6. 不执行发布、提权、删除性命令。
7. 不扩大方案范围；不接受口头扩范围（变更走《项目治理》§4）。
8. 引用的数据（性能数字、结论）必须可追溯到方案定稿、DR 或归档物，不得凭空给出。
9. 工作分支 push 与 PR 创建自办（SSH 直连，HTTPS 类失败再加代理）；PR 在 CI 绿后知会 PM 验收，**合入与否由 PM 决定并执行（DR-006）**，执行侧不参与 merge。

## 退回处理

PR 被退回：读退回原因 → 修 → 推回同分支 → CI 绿 → 回报 PM 复验。同一任务卡累计退回 2 次后，第 3 次强制升级负责人（换实现方案 / 拆解重发 / 冻结条目），不进入无限返工（《交付与验收流程》§5）。
