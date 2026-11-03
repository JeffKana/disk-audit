# Sprint 4（W4）计划与任务卡包 · 名义 2026-11-03 ~ 11-07

**Sprint 目标一句话：M2 收口——提权闭环 + 输出出口齐备，M2 五闸过闸。**

## 1. 收数（Sprint 3 终章，08 报告 §10）

- 完成率 **100%**（Wave 1 四卡 + Wave 2 五卡 + T3-07 热修并入）；退回 0；测试 264 → **316**。
- 计划外工作：T3-07 P1 热修（evidence_chain 枚举）、texts.py 两轮并行解突 + 一次测试文件语义解突、T2-09 子项③ VM 基准重建（方法学闸门：宿主校准）。
- 缺陷/回归集：本 Sprint 无新增真实误判；渲染入口新增"非法 source 拒绝"防御。
- 风险看板：R1 收口在即（T4-09 优化卡）；R5 防线加厚（judge 修正 + 渲染拒绝双层）；R2/R9 将在 S5~S6（打包/提权复测）进入观察期；R8 注意——VM 未激活 + UAC 静默配置对 M2 闸④⑤是**新发现的验收障碍**（见 R-M2 卡约束）。

## 2. 对表（方案第七节 M2 验收）

| M2 闸门 | 现状 | S4 动作 |
| --- | --- | --- |
| ① 双击到看到报告 ≤3 步 | ✅ 证据已具（T3-06 截图） | VM 复验（R-M2） |
| ② 断网环境报告样式与功能完整 | 等效口径已认证 | VM 物理断网复验（R-M2） |
| ③ 中止扫描不留半成品结论 | ✅（C7+G2） | VM 复验（R-M2） |
| ④ 提权全流程 VM（入口→UAC→重扫→管理员模式标注） | ❌ **H1~H4 未交付** | 本 Sprint 主攻 |
| ⑤ UAC 取消后结果不变且无错误弹窗 | ❌ H2 未交付 | 本 Sprint 主攻 |

M2 交付物缺口：F3（CSV 默认脱敏）、F4（A1~A5 接线）、B3（白名单封装——F4 的前置）。

## 3. 排程（依赖拓扑 + 波次）

| 波次 | 卡 | 说明 |
| --- | --- | --- |
| Wave 1（立即并行） | T4-01（H1 提权重扫，L）、T4-05（B3 白名单，S）、T4-06（F3 CSV 脱敏，M）、T4-08（X-1 边界，S）、T4-09（段③批查，M）+ M-02 随卡 | T4-01 最重；T4-05/06 独立；T4-08/09 为 S4~S5 排期卡提前领取 |
| Wave 2（栈式） | T4-02（栈 T4-01）、T4-03（栈 T4-01）、T4-04（栈 T4-01）、T4-07（栈 T4-05） | H 系列小卡快速跟进 |
| Sprint 末 | **R-M2 · M2 五闸 VM 验收**（负责人 + 执行侧 vm-ops + PM 主持） | 含断网复验与 UAC 全流程 |

**通用红线**（沿 07 号卡包 + Wave 2 增补）：不 push main（DR-006）；不改验收标准；只写 `%LOCALAPPDATA%\DiskAudit\`；**"本地绿"不作数（远端 CI 为准）**；测试禁真 KI、断言禁依赖系统 locale、CLI/`main()` 显式传参；**texts.py 多卡并行一律文末 append-only**，改既有测试语义与新增测试不得同文件并行（Wave 2 交织解突教训）；**本 Sprint 新增红线：提权代码路径禁联网、禁执行外部程序（R9），UI 触发前的 UAC 提示行为以方案 U-3 为准**。

---

## T4-01 · H1 以管理员身份重扫（待办 H1，M2 闸④⑤核心）

- **目标**：用户点击触发 → `ShellExecuteW runas` 重启自身 → 管理员模式完成重扫，产出独立标注报告。
- **输入指针**：方案 Q6/E-4/U-3、R9、S-3、`disk_audit/__main__.py`（scan/judge CLI）、`launcher.py`（G2 中止先例）、`%LOCALAPPDATA%\DiskAudit\tmp\spec.json`（Q1 定稿的规格传递位）、DR-006、`docs/upstream/poc/poc2_app.py`。
- **实现约束**：**仅用户点击触发**（U-3，不得自动弹 UAC）；扫描规格经 `tmp\spec.json` 传递（U-2 合规位）；提权进程**只读、不联网、不执行任何外部程序**（R9 硬约束，代码路径不得出现网络/子进程调用）；提权实例扫描结果写 reports\\ 并以"管理员模式"显著标注（S-3，H4 承接标注与独立记录）；`ERROR_CANCELLED` → E-5/H2 口径；chinese 输出守卫沿用（PYTHONUTF8 双保险先例）。
- **验收标准**：①单测：spec.json 写入/读取往返、runas 参数构造（ShellExecuteW 调用参数断言， verbs="runas"）；②本机端到端：点击 → UAC → 提权重扫 → 管理员模式报告生成（截图留档）；③提权实例不联网断言（无网络 API 调用路径——代码审查 + 可选 netstat 抽查留档）；④取消路径按 H2 卡；⑤远端 CI 绿。
- **依赖**：无（Wave 1 首位；H2/H3/H4 栈其上）。
- **执行记录**：

---

## T4-02 · H2 UAC 取消处理（待办 H2，栈 T4-01）

- **目标**：UAC 取消 → 保留原报告、不重试、无错误弹窗，仅提示"已取消，结果未变更"（E-5）。
- **输入指针**：方案 E-5、T4-01 产物、`launcher.py` 提示文案机制。
- **实现约束**：`ShellExecuteW` 返回 `ERROR_CANCELLED` 判定精确（不得把其他失败误判为取消）；提示为非阻塞状态栏文案（沿用 G2 状态栏）；**不弹错误对话框**（E-5 明文）。
- **验收标准**：①取消路径单测（注入 ERROR_CANCELLED）；②本机端到端：UAC 弹窗点否 → 状态栏提示 + 原报告不变（截图留档）；③重试计数为零断言（无自动重试路径）；④远端 CI 绿。
- **依赖**：T4-01（栈式）。
- **执行记录**：

---

## T4-03 · H3 提权进程异常退出（待办 H3，栈 T4-01）

- **目标**：提权实例崩溃/被杀 → 保留普通模式既有报告，提示"管理员重扫失败，已保留上次结果"（X-4）。
- **输入指针**：方案 X-4、T4-01 产物。
- **实现约束**：宿主侧等待提权实例退出码；异常退出（非 0 且非取消）→ 既有报告/体检记录**零改动**；提示走状态栏（同 H2 风格）；崩溃现场信息记 tmp\\ 日志（U-2 合规位）供排查。
- **验收标准**：①注入提权实例异常退出单测；②本机端到端：宿主报告 hash 前后一致（零改动断言）+ 提示留档；③远端 CI 绿。
- **依赖**：T4-01（栈式）。
- **执行记录**：

---

## T4-04 · H4 管理员模式标注与独立记录（待办 H4，栈 T4-01）

- **目标**：管理员模式报告显著标注（S-3）；作为独立体检记录，不与普通记录自动对比（M3 预备）。
- **输入指针**：方案 S-3、F1 定稿版本语义（docs/schemas/report-v1.schema.json）、`engine/render.py` 页眉、`engine/report.py`。
- **实现约束**：报告数据结构新增管理员模式字段**必须遵循 F1 定稿版本语义**（新增字段是否触发版本升级按定稿规则判定，升级则同步 I3"旧记录不可比"联动预留）；render 页眉徽标（管理员模式，POC 配色类）；**体检记录管理本身属 I1/M3**——本卡只做到"输出结构可区分 + 不写普通记录键"，记录存储联动在 M3。
- **验收标准**：①新增字段过定稿 schema 校验（或按版本语义升版后校验）；②render 管理员模式徽标 DOM 断言；③管理员/普通报告在输出结构上可区分（单测）；④普通模式输出不受影响（回归）；⑤远端 CI 绿。
- **依赖**：T4-01（栈式）。
- **执行记录**：

---

## T4-05 · B3 系统交互白名单封装（待办 B3）

- **目标**：A1~A3 所需系统交互收敛为单一白名单模块（U-4 的代码级落地）。
- **输入指针**：方案 U-4、治理 §7 清单、`launcher.py`（现有系统调用点）、F4 卡。
- **实现约束**：仅三能力：`explorer.exe /select,`（定位）、`ms-settings:appsfeatures`（打开）、剪贴板写；**`UninstallString` 永不执行**（模块级注释 + 断言）；调用参数可注入便于测试；供 F4 消费。
- **验收标准**：①三能力各一单测（参数断言，子进程 mock）；②越权调用拒绝测试（传入非白名单目标 → 拒绝并披露）；③grep 断言产品代码无 `UninstallString` 执行路径；④远端 CI 绿。
- **依赖**：无（Wave 1；T4-07 栈其上）。
- **执行记录**（2026-11-03，分支 `feature/B3-系统交互白名单`，基线 main=3af5868）：
  - **做了什么**：新增 `disk_audit/system_actions.py`（U-4 代码级落地，仅三能力：`locate_in_explorer(path, *, executor=None)`＝A2 `explorer.exe /select,<path>`、`open_apps_settings(*, executor=None)`＝A3 `ms-settings:appsfeatures`、`copy_to_clipboard(text, *, writer=None)`＝A1 剪贴板 CF_UNICODETEXT 纯文本写；唯一 shell 出口 `_shell_execute` 按白名单常量校验，越权抛 `SystemActionRejected` 披露目标与边界；默认实现 ctypes ShellExecuteW 直调与 user32/kernel32 剪贴板写，零子进程零第三方，调用参数全部可注入）；`disk_audit/engine/texts.py` 文末 append-only 新增 `B3_TEXTS` 区块（6 键：拒绝披露/空路径/剪贴板三类失败出口）；新增 `tests/test_system_actions.py` 14 例（三能力参数断言、5 组越权拒绝、AST+grep 双红线断言、模块 import 结构断言、B3_TEXTS 接线）。随卡携带 M-02：`tests/test_engine_units.py` 模块 docstring 改 raw string（`\P` 转义警告根修）；`tools/check_size_deviation.py` `main()` 入口补 stdout/stderr reconfigure 守卫（照抄 probe_resident_allocation.py 先例写法）；`tests/test_check_size_deviation.py` 新增守卫单测（记录型替身流断言两流各 reconfigure 一次）。
  - **实现决策及依据**：① ShellExecuteW 经 ctypes 直调而非 subprocess——launcher.py GetDriveTypeW/GetLogicalDrives 同模式先例，结构性消除子进程治理面（开发规范 §1 零第三方依赖；另以测试固化"白名单模块不 import subprocess/os"）；② 越权防护双层＝结构性（模块仅三能力函数、无通用"执行命令"入口）＋显式拒绝（`_shell_execute` 仅放行白名单常量表内 (file, params) 组合，拒绝文案含被拒目标与白名单边界——验收②"拒绝并披露"）；③ 空白路径拒绝为 A2 语义防御（`explorer /select,` 空参退化为打开"文档"夹，属白名单外交互），实现细节自决并记录；④ 验收③固化为三断言：AST 执行调用位置禁现 UninstallString（按执行函数名清单判定"执行调用位置"，`evidence/registry_uninstall.py` 的 KEY_READ 采集语境按卡面允许）、grep 行级"UninstallString×执行标记"互斥断言（治理 §7 U-4 行 grep 门禁口径）、白名单模块字符串常量禁现（docstring 豁免——红线声明本身写在模块头，文档语境不构成可执行路径）；并做突变自检：临时植入 `subprocess.run(["uninstall_string_helper.exe", …])` 确认断言真实可失败后即删；⑤ 真实剪贴板冒烟抓到 64 位句柄截断缺陷（ctypes 默认 restype=c_int 截断 HGLOBAL/指针 → GlobalLock 恒失败），修复为显式 argtypes/restype 原型声明，复测写入＋回读一致（冒烟留档：写入 `E:\smoke-T4-05-剪贴板冒烟-路径样例` 回读逐字一致，CF_UNICODETEXT）——注入测试无法覆盖真实 Win32 边界，冒烟一次性留档即卡面要求全部；⑥ launcher 现有 os.startfile 属 G3 报告打开（reports.open_report），卡面明示不在 A1~A3 范围，未动。
  - **未尽事项/已知限制**：① explorer /select 与 ms-settings 的真实端到端触发归 T4-07（F4 接线）验收③截图留档，本卡按卡面仅做剪贴板真实冒烟；② ShellExecuteW 返回值不解释（三能力为用户点击触发的火后不管交互），T4-07 若需失败态呈现（返回 ≤32）需另立任务；③ `texts.py:34` 与 `check_size_deviation.py:94` 两处既有超宽行（>100 列）非本卡引入，按红线⑤未顺手修。
  - **自测输出摘要**：`python -m pytest` 裸跑 **331 passed**（基线 316＋system_actions 14＋M-02 守卫 1）；`python -m disk_audit --selftest` **6/6**（exit 0）；M-02 验证 `python -W error::SyntaxWarning -c "import tests.test_engine_units"` **exit 0、无任何警告输出**；`python tools/check_size_deviation.py --fixture` 守卫生效、偏差 0.000% 正常退出（exit 0）；真实剪贴板冒烟写入＋回读一致（留档见上）。验收④远端 CI 推送后以 PR checks 为准。

---

## T4-06 · F3 CSV 导出（默认脱敏）（待办 F3）

- **目标**：报告候选导出 CSV，默认脱敏（P7 四类：用户名/计算机名/SID/其他用户目录名）。
- **输入指针**：方案 P7、M2 交付、八节"脱敏"、`engine/report.py` 输出结构、桌面 TreeSize CSV 的列样式参考（docs/upstream README 项 11，仅格式参考）。
- **实现约束**：**默认脱敏**，显式参数才出原文；脱敏覆盖四类（正则 + 环境变量双锚定）；CSV 仅数据列（路径/大小/置信度/来源/建议动作），无证据链全文（控体量）；导出文件写 `DATA_DIR\\reports\\`（U-2）；分享提示文案（"报告含本机路径"）在导出完成态展示。
- **验收标准**：①四类脱敏各有正反单测（用户名在路径中段/尾部、SID 形如 S-1-5-21-*、其他用户目录 C:\\Users\\<other>\\）；②默认导出不含原文断言（含机器名/用户名的真实样例）；③显式 `--raw` 参数才出原文；④CSV 可被 Excel 打开（BOM/编码留档：utf-8-sig）；⑤远端 CI 绿。
- **依赖**：无（Wave 1）。
- **执行记录**：

---

## T4-07 · F4 建议动作接线（待办 F4，栈 T4-05）

- **目标**：报告/UI 中 A1~A5 五种建议动作可执行（A4 已由 F2 details 折叠原生实现，接线为入口明确化）。
- **输入指针**：方案 5.3（A1~A5 固定枚举）、T4-05 白名单模块、`render.py` 建议动作区、`launcher.py`。
- **实现约束**：A1 复制路径（剪贴板，经 B3）；A2 打开所在文件夹（`explorer /select,`，经 B3）；A3 `ms-settings:appsfeatures`（经 B3）；A4 报告内展开（F2 `<details>` 原生，本卡仅确认入口语义与文案）；A5 无建议（受保护/低置信固定，**不渲染任何可点入口**——F2 已断言，本卡回归）；**受保护/低置信项不得出现 A1~A3 入口**。
- **验收标准**：①A1~A3 经 B3 的参数断言单测；②受保护/低置信无入口 DOM 断言（回归 F2）；③本机端到端：报告内触发 A1/A2/A3 各一次（截图留档）；④远端 CI 绿。
- **依赖**：T4-05（栈式）。
- **执行记录**：

---

## T4-08 · T3-08 X-1 枚举段边界（遗留 P2 卡）

- **目标**：`_expand_dir`/`_scan_tree` 枚举段 OSError 折入 X-1（跳过+计数+继续），X-2 保留给真实中止/致命异常。
- **输入指针**：08 报告 §3 裁决 2、T2-09 首轮 4/4 不完整实证（VM AppX 增删目录）、`disk_audit/scanner.py`。
- **实现约束**：仅收窄捕获边界，**不改变 X-2 统一出口语义**；跳过计入 skips.other（或新枚举 churn 子类，自决并记录）；VM AppX 抖动场景复测为验收手段。
- **验收标准**：①注入枚举段 OSError 单测 → 计数+继续、incomplete=False；②中止路径回归（真中止仍走 X-2）；③VM AppX 活跃期首扫不再整体不完整（如 VM 可用，vm-ops 协同；否则注入式测试 + 留档）；④远端 CI 绿。
- **依赖**：无（Wave 1）。
- **执行记录**：

---

## T4-09 · T3-09 段③批查取数优化（遗留 P2 卡，DR-004 既定方向）

- **目标**：601B~<簇 段改目录级批查（FileIdExtdDirectoryInfo 单次调用带回整目录 AllocationSize/EndOfFile），消除 163k 次逐文件句柄，AppData 合计从 ~14.4s 回收。
- **输入指针**：[DR-004 实测规模更正节](../governance/decisions/DR-004-2026-10-24-占用空间取数性能.md)、`disk_audit/scanner.py`、`tools/check_size_deviation.py`、`tools/baseline.json`、POC 代码参考（BCU 方向仅思路，禁复制）。
- **实现约束**：批查 API 仅 Windows（ctypes），失败回退现行逐文件句柄（X-1）；**双口径语义与汇总口径不变**（P1）；与 T4-08 同改 scanner.py——**两卡不得并行**，后合者栈式；批查结果与句柄实查逐文件一致（含驻留边界样本）。
- **验收标准**：①混合夹具（②' 梯度）批查 vs 纯句柄 <0.1%；②三目录基准复测维持 <1%；③Roaming+Local 合计耗时较 14.4s 显著回收（目标 ≤8s，贴实测）；④批查失败回退路径单测；⑤远端 CI 绿。
- **依赖**：无（但与 T4-08 同文件，**顺序执行：T4-08 先合，T4-09 栈式**）。
- **执行记录**：

---

## M-02 · chore 微卡（随任意 Wave 1 PR 携带）

`tests/test_engine_units.py:4` docstring `\\P` 转义警告修正（raw string 或双反斜杠）；`tools/check_size_deviation.py` 入口补 stdout/stderr reconfigure 守卫（对齐 T-01 双保险先例）。验收：警告消失（`python -W error::SyntaxWarning -c "import tests.test_engine_units"` 不再报）+ 守卫单测或行为留档。

## R-M2 · M2 五闸 VM 验收（负责人 + 执行侧 vm-ops + PM 主持，Sprint 末）

- **范围**：方案第七节 M2 五闸在 VM 全量复验——①≤3 步端到端 ②**物理断网**报告完整 ③中止不留半成品 ④提权全流程（入口→UAC→重扫→管理员模式标注）⑤UAC 取消不变无错误弹窗。
- **关键约束（新识别的验收障碍）**：R-L1 建机时 acc 双机 UAC 已置静默（`ConsentPromptBehaviorAdmin=0`）——**闸门④⑤要求 UAC 真实弹窗与取消**，验收前必须临时恢复 UAC 提示模式（注册表改回默认并留档，验收后按需还原）；VM 未激活状态照旧豁免。
- **完成标志**：五闸逐条判定留档；③断网复验即 08 报告 §9.4 遗留项的正式闭环。
- **状态**：待负责人与执行侧安排（Sprint 末）。

## Sprint 4 验收清单（周五可逐条打勾）

1. H1 端到端：点击 → UAC → 提权重扫 → 管理员模式报告（截图留档）。
2. H2/H3：取消与异常退出两路径各自留档（原报告零改动断言）。
3. F3 默认脱敏 CSV 导出（四类脱敏单测 + 真实样例）。
4. F4 A1~A3 端到端触发 + A5 无入口回归。
5. T4-08/T4-09 合入：X-1 边界收窄 + AppData 耗时回收（≤8s 目标）。
6. **R-M2：M2 五闸 VM 全量复验通过 → M2 正式关闭，项目进入 M3（体检记录与对比）**。

## 报批

Sprint 目标与卡包交负责人确认；改动条目由 PM 重排依赖后生效。分发建议：T4-01 与 T4-05/06 最先（提权主线 + 独立卡并行）；R-M2 需要负责人本周排期 VM 窗口（含 UAC 配置调整）。
