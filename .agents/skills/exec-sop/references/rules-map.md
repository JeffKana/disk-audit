# 规则速查：做什么 → 读哪里（v2 · 2026-10-31）

执行 Agent 的文档导航。**内容以文档原文为准**，本文件只给节号与路径，不复制规则；环境事实（代理、VM、编码模式）在此给全文，因为它们散落且易失。

## 仓库文档索引

| 文档 | 路径 | 管什么 |
| --- | --- | --- |
| 方案定稿 | `docs/upstream/磁盘体检_v0.1方案_定稿_2026-10-23.html` | 需求与范围唯一基线 |
| 交付与验收流程 | `docs/governance/交付与验收流程.md` | DoR、执行/验收 SOP、决策机制、防死胡同 |
| 项目治理 | `docs/governance/项目治理.md` | 仓库组织、分支合入、版本发布、变更管理、DR 索引、安全底线 |
| 开发规范 | `docs/governance/开发规范.md` | 代码 / 测试 / git / CI 门禁 / AI 协作 / 文档义务 |
| CI-CD 规范 | `docs/governance/CI-CD规范.md` | 流水线触发、阶段门禁、main 保护、发布原则 |
| 敏捷开发指南 | `docs/agile/00_敏捷开发指南.md` | Sprint 节奏、DoD、变更管理、风险看板 |
| 产品待办列表 | `docs/agile/01_产品待办列表.md` | 待办条目与状态 |
| 环境基线 | `docs/governance/环境基线.md` | 解释器、代理、VirtualBox VM、磁盘余量的权威记录（2026-10-26 修订版） |
| Sprint 报告 | `docs/agile/04_Sprint1_验收报告.md`、`05_Sprint2_计划与任务卡.md`、`06_Sprint2_验收报告.md` | 验收结论、任务卡与执行记录、追加卡（T2-08/T2-09）、条件项 |
| 报告 Schema | `docs/schemas/report-v1.schema.json`（+ example） | 报告结构唯一权威（v1 定稿：source 九值、incomplete、版本语义） |
| 知识库 | `knowledge/schema.json` + `entries.json` | 判定知识（503 条，schema v1，来源三值登记） |
| 工具集 | `tools/` | 门禁与验收脚本（用法见各脚本 docstring） |

## 任务场景 → 必读

| 你正在做 | 先读 |
| --- | --- |
| 理解任务卡 / 核对字段齐全 | 交付与验收流程 §1（DoR） |
| 建分支 / 栈式切出 / 提 PR | 项目治理 §2 + 本技能第 2/8 步（栈序合入） |
| 写引擎 / 判定代码 | 开发规范 §1（类型标注、纯函数、X-1、文案集中在 texts.py） |
| **动 scanner 占用空间 / 性能** | **DR-004 全文含选项 c 裁决节**（四段分流勿重议）+ `tools/probe_resident_allocation.py` |
| **动报告结构 / schema_version** | `docs/schemas/report-v1.schema.json` + Q7 + `tests/_mini_schema.py`（自研校验器，不是 jsonschema 包） |
| **写 tools/ 脚本或其测试** | 本文件"环境速查 → 编码模式"（UTF-8 输出 / argv 隔离） |
| 误判修复 / 回归样例 | `tests/data/regression/` + 开发规范 §3（当天进回归集） |
| 想引入任何运行时依赖 | 开发规范 §2（DR 增补流程，禁止直接加白名单） |
| 写提交信息 | 开发规范 §4（Conventional Commits + 中文） |
| CI 红灯 | 开发规范 §5 + CI-CD 规范 §3/§5（禁止删用例换绿灯） |
| **改 CI 结构 / 拆新 check** | CI-CD 规范 §2（必须同步登记必填检查列表） |
| 版本号相关 | 项目治理 §3（`__version__` 唯一来源，tag 三处一致） |
| 范围好像要变 / 文档冲突 | 项目治理 §4（优先级：方案定稿 > 治理 > 敏捷指南 > 其他） |
| 需要新决策留档 | 项目治理 §5（`DR-<序号>-<日期>-<标题>.md`） |
| **做知识库条目 / 修正误判** | 项目治理 §6（来源铁律、lifecycle 纪律、503 条现状；修正当天进回归集） |
| 涉及文件系统 / 注册表 / 提权 | 项目治理 §7（安全底线，见下） |
| 搬运上游资料 | 项目治理 §8（只进 `docs/upstream/` + 登记 + 校验） |
| PR 退回 / 技术争议 | 交付与验收流程 §5（返工上限、保守默认；裁决归 PM） |

## 安全底线（写相关代码前扫一眼；完整表见项目治理 §7）

- **S-1** 硬保护规则在判定流水线最前短路，不可配置覆盖。
- **U-2** 程序自身仅在 `%LOCALAPPDATA%\DiskAudit\` 写入。
- **U-4** 系统交互白名单仅 A1~A3；`UninstallString` 只采集、永不调用。
- **DPAPI** `Roaming\Microsoft\Protect`、`Crypto` 永久"受保护"。
- **提权** 仅用户点击触发；提权后只读、不联网、不执行外部程序。
- **隐私** 不收集、不上传、默认不联网（联网代码仅"检查更新"一处）。

## 环境速查

### 命令通道（2026-10-24 起已修复，勿再用旧结论）

- 会话内**可直接运行** git / python / pytest（根因修复：中文计算机名 → HOSTNAME 乱码 DNS 超时 + HOME=/ 的 PATH SMB 问题，补丁在 `D:\develop\tools\Git\etc\profile.d\env.sh`；过程见 `docs/governance/环境修复记录-2026-10-24-原生exe挂起.md`）。
- `python` 异常或挂起时：用完整路径 `D:\develop\environment\python\python.exe`（CPython 3.13.5，含 Tcl/Tk 8.6）。
- 命令拆小：超长单行命令会被安全层拦截或挂起。
- PowerShell 任务优先 `C:\Program Files\PowerShell\7\pwsh.exe -NoProfile -NonInteractive`。
- 代码内 PowerShell 子进程：绝对路径 `%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe`（W0 教训：PATH 裁剪时静默失败）。

### GitHub 网络（2026-10-31 验证）

- **SSH 远程（`git@github.com`）push / fetch 实测可直连**（本仓库 origin 即 SSH）；HTTPS 类操作（gh CLI / REST API / HTTPS remote）直连 443 不通，需**临时注入** `HTTPS_PROXY=http://127.0.0.1:7890`（勿写死配置；代理客户端未开时连接被拒，改走 SSH 或等代理恢复）。
- gh CLI 令牌可能失效：`printf "protocol=https\nhost=github.com\n" | git credential fill` 取 PAT 走 REST（凭据仅内存，不打印不落盘）。
- `api.github.com` 可经 WebFetch 只读访问（不经代理也通）。

### 编码模式（先例：退回单 T-01 / 整改项 M-01）

- 工具脚本含中文 print → 入口 `sys.stdout.reconfigure(encoding="utf-8")`（stderr 同理，hasattr 守卫）；CI 顶层已设 `PYTHONUTF8: "1"` 双保险。
- 测试调用脚本 `main()` → 显式 `main([])` 或 monkeypatch sys.argv（防 pytest 参数泄漏成 SystemExit: 2）。

### main 分支保护（2026-10-25 起生效）

- 合并必须走 PR 且必填 check `windows` 绿；enforce_admins 开启；delete_branch_on_merge 生效（合完即删远端分支，重建显示 new branch 属正常）。
- CI 拆出新 check 必须同步登记必填列表，否则新门禁不设防。

### VM 实验室（VirtualBox 7.2.22；权威：《环境基线》§2/§3）

- 四机全在 `H:\Virtual Machine\`：`L1-base-22h2` / `L1-base-24h2`（父镜像，快照 base-v1 冻结）+ `L1-acc-22h2` / `L1-acc-24h2`（linked-clone 差分验收机，GT 11 件已装；账号 qa，autologon，UAC 静默）。
- **24H2 系 VM 禁止 GUI 附加**（`--type separate` 触发 GA 显示驱动挂死），全程 headless。
- 新建 VM 一律 `clonevm --basefolder 'H:\Virtual Machine'`（曾把 C 盘写满）；**H 盘仅剩 ~11G**，M4 扩容前必须清理或扩容。
- 主机自动睡眠会暂停全部 VM：长任务前置位 `SetThreadExecutionState(0x80000003)`。
- guestcontrol 四坑：置 `MSYS_NO_PATHCONV=1`（MSYS 路径转换篡改 `/c` 等参数）；copyto 源必须 Windows 路径；复杂命令写 `.cmd` 脚本承载（勿嵌套引号）；控制台注入避开 `>&|` 字符。
- VM 内装软件：winget 在 22H2（v1.2）崩 0xC0000005 → 官方安装包 + 静默开关；Windows 更新卡 DO CDN → 注册表 `DODownloadMode=0` + Start-Process -Verb RunAs（详见 PR#15 执行记录）。
- VM 磁盘文件（`*.vdi`/`*.vhd`/`*.vhdx`）永不进 git。
