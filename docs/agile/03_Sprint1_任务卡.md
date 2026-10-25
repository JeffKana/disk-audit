# Sprint 1（W1）任务卡包 · 2026-10-27 ~ 10-31

按《[交付与验收流程](../governance/交付与验收流程.md)》§1 DoR 制作。**分发建议**：T-01、T-02、T-04、T-05、T-06、T-07、T-09 相互独立可并行；T-03 依赖 T-02；T-08 依赖 T-07。执行 Agent 每卡一分支一 PR；验收由项目经理按 §3 SOP 执行。

通用红线（适用于所有执行卡，卡内不再重复）：不 merge、不 push main、不改验收标准、不改 `%LOCALAPPDATA%\DiskAudit\` 之外的任何写入逻辑、发现新问题记入执行记录"未尽事项"而不顺手修、所有命令用完整解释器路径（本机 `python` 为 Store 存根）。

---

## T-01 · import 白名单 CI 门禁（待办 A4）

- **目标**：CI 新增"运行时零第三方依赖"机器门禁。
- **输入指针**：`pyproject.toml`（依赖声明）、《项目治理》§1、《CI-CD 规范》§3 阶段 B、`.github/workflows/ci.yml`。
- **实现约束**：脚本置于 `tools/check_imports.py`（新目录），扫描 `disk_audit/` 全部 import，仅允许标准库与 `disk_audit.*`；接入 ci.yml 为第④段门禁。**本卡例外授权：允许修改 `.github/workflows/ci.yml`**（仅追加 job，不动既有三段）。
- **验收标准**：① 脚本对当前代码退出码 0；② 在临时分支加一行 `import requests` 后脚本退出码非 0（截图/输出贴执行记录）；③ ci.yml 四段门禁在 PR 上全绿。
- **依赖**：无。
- **执行记录**：
  - **做了什么**：新增 `tools/check_imports.py`（ast 扫描 `disk_audit/` 全部 import，白名单=标准库 `sys.stdlib_module_names` + `disk_audit.*`，违规列出并退出码 1）；ci.yml 在既有三段后追加"门禁四 import 白名单"步骤（既有步骤与门禁五注释未动，按卡内例外授权）；新增 `tests/test_check_imports.py`（9 例：干净树通过、第三方 import 正/反例、子模块按顶层名判定、语法错误计违规、winreg 放行、退出码、真实包通过）。关键文件：`tools/check_imports.py`、`tests/test_check_imports.py`、`.github/workflows/ci.yml`。
  - **实现决策及依据**：① 标准库判定用 `sys.stdlib_module_names`（CPython 3.13 内置，含 winreg 等平台专属模块）——开发规范 §2；② 扫描范围仅 `disk_audit/`（卡面约束，tools/tests 属开发侧）；③ 验收②负例用 `--root` 指向临时目录等价验证（免污染分支，证据等效），卡面字面的"临时分支"做法亦列入命令清单备选；④ 相对导入（level>0）视为包内放行。
  - **未尽事项/已知限制**：无新发现。验收③（PR 上四段门禁全绿）待本卡 push 后由 CI 确认。
  - **自测输出摘要**：根因定位与修复过程见《[环境修复记录-2026-10-24-原生exe挂起](../governance/环境修复记录-2026-10-24-原生exe挂起.md)》——负责人 2026-10-24 修复会话挂起问题（HOSTNAME 乱码归一 + HOME/bin 路径补丁），**《环境基线》的变更登记由验收环节依据该记录执行**。修复后已在本会话全量实测：**pytest 全量 115 passed；--selftest 6/6 passed；验收① `python tools\check_imports.py` → 退出码 0（"通过：…所有 import 均为标准库或包内模块"）；验收②负例（临时目录含 `import requests` 的 probe.py）→ 退出码 1，输出"probe.py:1: import requests"**。剩余待验证：验收③（PR 四段门禁全绿，push 后 CI 确认）。分支与提交已由执行 Agent 本地完成（治理文档收尾在 `docs/治理文档Sprint0收尾`；本卡在 `chore/A4-import白名单门禁`，干净树 pytest 33 passed + selftest 6/6）。负责人终端：`git push -u origin docs/治理文档Sprint0收尾 chore/A4-import白名单门禁` → 分别建 PR（描述=各卡执行记录的验收标准对照 + "AI 辅助生成，待验收"）→ 验收通过后合入。
  - **退回处理（2026-10-24，退回 1/2，PM：不占用上限）**：PR #2 CI 门禁④在 windows runner 上假红——根因为 runner 的 Python 3.13 stdout 默认 cp1252（PEP 686 的 UTF-8 默认自 3.15 才生效），中文 print 抛 UnicodeEncodeError（PM 定位；判定逻辑审查通过）。按 PM 建议做 a+b 双保险修复：a) `tools/check_imports.py` 入口 `_force_utf8_stdio()` 强制 stdout/stderr 为 UTF-8（hasattr 守卫兼容 pytest 捕获流）；b) ci.yml workflow 顶层 `env: PYTHONUTF8: "1"`（顺带保护未来含中文输出的步骤；退回单授权的例外变更）。新增回归用例 `test_gate_survives_non_utf8_stdout`（PYTHONIOENCODING=cp1252 子进程复现 runner 场景：干净树必须退出码 0）。修复提交 eaa83c7 已推回同分支，本地 pytest 34 passed + selftest 6/6 + cp1252 直接复现退出码 0，待 PM 复验。

---

## T-02 · 文件枚举器（待办 C2，含 C3 切分修正）

- **目标**：可独立 CLI 调用的文件枚举模块，双口径计量，不漏根级文件。
- **输入指针**：方案第四节"文件枚举"行、X-1、P1（双口径）；`docs/upstream/poc/poc1_scan_bench_v2.py`（性能基线 15.23s 的原型）；W0 实测报告（`docs/upstream/poc/W0_POC实测报告_2026-10-23.html`）中"并列切分漏算根级文件（少 14.76GB）"记录。
- **实现约束**：`os.scandir` + 8 线程前沿切分；**浅层切分 + 叶级单线程递归，禁止线程池内嵌套 submit（实测死锁）**；`\\?\` 长路径；跳过 reparse point；逻辑大小（`st_size`）与占用空间（分配大小，机制自决，如 ctypes）双列，**汇总一律用占用空间**；权限/超长/占用/reparse 跳过并计数（X-1）；模块纯引擎、零 UI 依赖；流式聚合不缓存全量条目。
- **验收标准**：① 对 `%LOCALAPPDATA%` 单目录扫描，根级文件计入（构造含根级文件的测试夹具验证，不再出现 W0 漏算）；② 单元测试覆盖：根级文件、长路径（>260）、reparse point 跳过、权限跳过计数（用可控夹具）；③ 本机 AppData 扫描 ≤ 6s 量级（贴实测数字，正式验收 S2 在 VM）；④ CLI 可独立调用：`python -m disk_audit scan <path>` 输出 JSON 摘要（条目数、双口径总量、跳过统计）。
- **依赖**：无。
- **执行记录**：
  - **做了什么**：新增 `disk_audit/scanner.py`（BFS 浅层前沿切分 + `ThreadPoolExecutor.map` 叶级单线程递归，全程无嵌套 submit；**前沿切分补算**：BFS 展开每层时同步统计该层"未继续下钻目录"中的文件，根级文件不漏——W0 缺陷①修复；双口径：逻辑大小=`st_size`，占用空间=`GetCompressedFileSizeW`（ctypes）；`\\?\` 长路径（≥240 前缀，UNC 特判）；reparse point 跳过；X-1 按 permission/occupied/too_long/reparse/other 分类计数；流式聚合不缓存条目）；`disk_audit/__main__.py` 新增 `scan` 子命令输出 JSON 摘要；新增 `tests/test_scanner.py`（17 例：根级文件 W0 回归夹具、目录计数、并行前沿路径、>260 长路径夹具、junction 跳过、monkeypatch 权限/占用/消失条目计数、双口径、CLI JSON、selftest 不回归）。关键文件：`disk_audit/scanner.py`、`disk_audit/__main__.py`、`tests/test_scanner.py`。
  - **实现决策及依据**：① 占用空间机制**两轮选型**（D-技术上报）：初版按卡面提示选 `GetCompressedFileSizeW`，实测发现对未压缩、非稀疏文件返回的是**逻辑大小**（MSDN Remarks 原文："the value obtained is the actual file size, the same as GetFileSize"；本机探针 5000B 文件 → 返回 5000），与"占用空间"口径不符——改为 `CreateFileW(FILE_READ_ATTRIBUTES)` + `GetFileInformationByHandleEx(FileStandardInfo).AllocationSize`（簇对齐分配量；探针实证：5000B→8192、100B 驻留→104、0B→0，与资源管理器同口径）；② 占用查询失败的文件整个按 occupied 跳过（保证双口径一致，X-1）；③ Windows 共享冲突（WinError 32/33）以 PermissionError 形态出现，分类器先按 winerror/errno 分流到 occupied 再归 permission；④ 目录不计占用空间；⑤ 切分参数沿用 POC v2（max_depth=4、min_parts=workers×3，8 线程）；⑥ 前沿为空（小树）时不启动线程池。
  - **未尽事项/已知限制**：**性能冲突（D-技术，待 PM/负责人裁决）**：FileStandardInfo 每文件一次句柄打开 ≈30µs，本机 AppData 合计 ~25.3s，远超验收③"≤6s 量级"（POC 纯逻辑口径基线 4.79~4.94s）。冲突根源：卡面实现约束"os.scandir"与 P1 双口径在 GetCompressedFileSizeW 真实语义下不可兼得。备选方案：(a) 维持现状，按实际数字验收；(b) 枚举层改 kernel32 `GetFileInformationByHandleEx` 目录批类（FileIdExtdDirectoryInfo，单目录一次调用带回全部条目的 AllocationSize/EndOfFile/属性，预估回到 ≤6s 且更快）——但字面偏离"os.scandir"约束，**未执行，待裁决**；非 Windows 开发环境占用口径降级为逻辑大小（不影响 CI）。
  - **自测输出摘要**（2026-10-24 本会话实测，解释器 `D:\develop\environment\python\python.exe`）：pytest 115 passed（含本卡 17 例）；--selftest 6/6。**验收③实测**：`scan %LOCALAPPDATA%` → **19.36s**、435,694 项（files 367,175 / dirs 68,519）、逻辑 35.04GB / 占用 35.69GB、跳过 permission 2 / occupied 35 / reparse 77 / 计 114；`scan %APPDATA%` → **5.91s**、208,927 项、逻辑 22.69GB / 占用 22.96GB、跳过 reparse 1。合计 644,621 项 / 58.68GB（占用口径）——与 POC 基线 643,178 项吻合（偏差 0.2%）。**验收①**由 `test_root_level_files_counted`（W0 回归夹具）覆盖且全绿；**验收④** CLI JSON 摘要即上述输出格式。分支 `feature/C2-文件枚举器` 已本地提交（干净树 pytest 40 passed + selftest 6/6）。负责人终端：`git push -u origin feature/C2-文件枚举器` → 建 PR → 验收合入（`feature/L2-容量偏差脚本` 基于本分支，请先合入本卡）。

---

## T-03 · 容量偏差对比脚本（待办 L2）

- **目标**：量化"与资源管理器占用空间偏差 <1%"的验收工具。
- **输入指针**：方案第六节"容量口径偏差"行、9.2 节口径定义（|报告汇总 − 资源管理器同范围| ÷ 资源管理器）；T-02 的枚举模块。
- **实现约束**：脚本 `tools/check_size_deviation.py`；对比对象为资源管理器"占用空间"（自决取数机制，如 Shell COM 或已知基准夹具）；输出偏差百分比与明细。
- **验收标准**：① 对至少 3 个真实目录（含 `%LOCALAPPDATA%` 一个子目录）输出偏差，全部 <1%（贴数字）；② 构造已知精确分配的夹具（如 1000 个小文件）偏差为 0 或可解释；③ 脚本只读。
- **依赖**：T-02。
- **执行记录**：
  - **做了什么**：新增 `tools/check_size_deviation.py` 与 `tests/test_check_size_deviation.py`。两种模式：`--baseline <json>`（基准清单逐目录复算偏差并判定 <1%，全程只读）；`--fixture`（1000 个已知大小文件自检：预期=簇对齐公式 ceil(逻辑/簇)×簇，簇大小经 `GetDiskFreeSpaceW` 查询）。偏差公式=方案 9.2 口径。测试 6 例：公式、基准精确匹配（并断言只读——运行前后目录清单不变）、超阈值退出码 1、坏输入退出码 2、缺字段、夹具自检偏差 0。
  - **实现决策及依据**：① 取数机制选卡面授权的"已知基准夹具"：零第三方依赖约束下无可靠的"占用空间"程序化取数途径（Shell COM 需 pywin32，`GetDetailsOf` 无占用空间列且不保证与资源管理器口径一致），资源管理器数字由负责人属性对话框读数登记进基准 JSON；② 夹具文件取 5000~5999 字节（**非 MFT 驻留**——探针实测 100B 驻留文件分配量为 104B，簇对齐公式只对非常驻文件成立）+ 10 个 0 字节文件；③ 夹具仅写系统 TEMP 且用后即删——U-2 约束产品运行时写入，开发期一次性夹具是卡面验收②明确要求。
  - **未尽事项/已知限制**：验收①的基准数字依赖负责人手工登记（机制已在 docstring 说明格式）；"目录本身不计占用"的口径假设待真实目录对数确认，若与资源管理器存在系统性差异，记入本卡退回/未尽事项后另立任务修正 T-02。
  - **自测输出摘要**（2026-10-24 本会话实测）：pytest 全量 115 passed（含本卡 6 例）；**验收② `--fixture` → 偏差 0.000%**（簇 4096B，预期=实测=8,110,080B，"簇对齐公式与扫描口径一致"）；基准模式只读由测试断言（运行前后目录清单不变）覆盖且全绿。分支 `feature/L2-容量偏差脚本` 已本地提交（堆叠于 `feature/C2-文件枚举器`；干净树 pytest 46 passed + selftest 6/6）。负责人终端：push 可先做（`git push -u origin feature/L2-容量偏差脚本`），PR 的 diff 在 T-02 合入后自动收敛为本卡增量，合入顺序 T-02 → 本卡；验收①：登记 baseline.json（≥3 个真实目录含一个 `%LOCALAPPDATA%` 子目录，格式见脚本 docstring）后 `python tools\check_size_deviation.py --baseline baseline.json`（贴逐目录偏差数字）。

---

## T-04 · 证据采集：注册表卸载项（待办 C3）

- **目标**：只读采集注册表卸载记录，产出 `evidence` 数据结构。
- **输入指针**：方案第四节"注册表"行（winreg、KEY_READ）；`docs/upstream/prototype/uninstall.json`（结构参考，206 项实测）；`docs/upstream/prototype/analyze_appdata.py` 中采集部分。
- **实现约束**：覆盖 HKLM/HKCU × 64/32 位视图的 Uninstall 键（含 Wow6432Node）；只读（`KEY_READ`）；**`UninstallString` 只采集不执行**（U-4）；输出结构需含： DisplayName、Publisher、InstallLocation、InstallDate、UninstallString（原文）、注册表路径。
- **验收标准**：① 单元测试：对模拟注册表结构（monkeypatch winreg）解析正确；② 本机运行采集条数 ≥ 200 量级（贴数字）；③ 全程无任何注册表写操作（测试断言只出现 OpenKey/QueryValue）。
- **依赖**：无。
- **执行记录**：
  - **做了什么**：新增 `disk_audit/evidence/` 包与 `registry_uninstall.py`：只读采集四个 Uninstall 键位（HKLM 64 位视图 / HKLM Wow6432Node / HKCU / HKCU Wow6432Node，缺失键位静默跳过），字段 DisplayName/Publisher/InstallLocation/InstallDate/UninstallString 原文/注册表完整路径（reg_path），单键失败 X-1 计数（`skipped`）；新增 `tests/test_evidence_registry.py`（7 例：解析正确、字段映射、缺值补空、DWORD 字符串化、reg_path 全路径、**只读 API 强断言**、全键缺失空结果）。关键文件：`disk_audit/evidence/__init__.py`、`disk_audit/evidence/registry_uninstall.py`、`tests/test_evidence_registry.py`。
  - **实现决策及依据**：① Wow6432Node 用物理路径直取而非 `KEY_WOW64_32KEY` 视图标志——与卡面"含 Wow6432Node"字面一致、避免视图反射歧义（D-执行）；② 无 DisplayName 的键也采集（POC 口径 284 键/206 有名称，条数披露更完整，验收②按"≥200 量级"两种口径均通过）；③ `UninstallString` 只存原文，任何代码路径都不执行（U-4，模块 docstring 声明）；④ winreg 模块可注入：假模块只实现 OpenKey/EnumKey/QueryValueEx/CloseKey 与常量，天然保证"无任何写方法可调"，比事后 grep 更强（验收③）；⑤ 卡面输入指针"analyze_appdata.py 中采集部分"实际是证据消费端，仓库内真实采集参考在 `docs/upstream/poc/poc2_app.py`（284 键/206 有名称实测），本卡按 poc2 用法重写并补齐字段（指针偏差，D-执行记录）。
  - **未尽事项/已知限制**：HKCU\Wow6432Node 多数机器不存在（属正常跳过，不计 skipped）；InstallDate 保留注册表原文不归一格式（归一属判定层职责，超出本卡范围）。
  - **自测输出摘要**（2026-10-24 本会话实测）：pytest 全量 115 passed（含本卡 7 例）；**验收②本机实测：uninstall entries = 286、skipped = 0、sources = 4**（四个 Uninstall 键位全部打开成功；POC 基线 284 键——本机键数微增属正常漂移；本采集含无 DisplayName 的键，"≥200 量级"通过）；验收③由 `test_only_readonly_registry_api_used` 断言（假 winreg 只实现只读 API）且全绿。分支 `feature/C3-注册表卸载项采集` 已本地提交（干净树 pytest 31 passed + selftest 6/6）。负责人终端：`git push -u origin feature/C3-注册表卸载项采集` → 建 PR → 验收合入（`feature/C4-Appx商店包采集` 基于本分支，请先合入本卡）。

---

## T-05 · 证据采集：Appx 商店包（待办 C4，含 C5 绝对路径）

- **目标**：采集商店包注册清单，失败降级可披露。
- **输入指针**：方案第四节"UWP/商店包"行；`docs/upstream/prototype/appx.json`（结构参考，164 包实测）。
- **实现约束**：**必须绝对路径** `%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe`（W0 教训：PATH 被裁剪时静默失败）+ `-NoProfile -NonInteractive`；超时保护；失败降级为"该证据源不可用"标记并进入报告披露字段（不抛异常中断）；只读。
- **验收标准**：① 单元测试：正常解析样例 JSON；② 降级测试：模拟命令不可用时返回"不可用"标记且不抛异常；③ 本机运行采集包数 ≥ 150 量级（贴数字）；④ 子进程调用参数在测试中可断言（绝对路径）。
- **依赖**：无。
- **执行记录**：
  - **做了什么**：新增 `disk_audit/evidence/_ps.py`（PowerShell 调用底座：绝对路径 `%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe` + `-NoProfile -NonInteractive` + timeout + CREATE_NO_WINDOW，T-06 复用）与 `appx.py`（`Get-AppxPackage | Select Name,PackageFullName,InstallLocation | ConvertTo-Json`）；任何失败（exe 缺失/超时/非零退出/解析失败）降级为 `available=False` + 中文 reason，不抛异常；新增 `tests/test_evidence_appx.py`（9 例：样例解析、单包 dict 归一、空输出、成功采集、四种降级不抛异常、argv 绝对路径与参数断言）。关键文件：`disk_audit/evidence/_ps.py`、`disk_audit/evidence/appx.py`、`tests/test_evidence_appx.py`。
  - **实现决策及依据**：① 绝对路径调用为卡面硬约束（W0-C5 教训：PATH 被裁剪时裸 `powershell` 静默失败，W0 报告"顺带一个诚实说明"节）；② SystemRoot 缺失时回退 `C:\Windows`（保证路径仍绝对）；③ 采集字段选 Name/PackageFullName/InstallLocation（包全名含版本哈希，供 S2 归属判定；原型 appx.json 仅包全名字符串数组，本卡结构化升级）；④ `ConvertTo-Json` 单包时输出对象而非数组，解析层归一。
  - **未尽事项/已知限制**：W0 POC 本机实测 199 包，验收③ ≥150 预期通过，待负责人复核；`Get-AppxPackage` 在部分加固环境可能被策略限制——此时走降级路径披露"该证据源不可用"，属设计行为。
  - **自测输出摘要**（2026-10-24 本会话实测）：pytest 全量 115 passed（含本卡 9 例）；**验收③本机实测：appx available = True、count = 199**（与 W0 POC 实测 199 包一致，"≥150 量级"通过）；验收②由 `test_collect_degraded_missing_exe/timeout/nonzero/bad_json` 四个降级用例覆盖（均不抛异常）且全绿；验收④由 `test_argv_absolute_path_and_flags` 断言（绝对路径 + -NoProfile -NonInteractive）且全绿。分支 `feature/C4-Appx商店包采集` 已本地提交（堆叠于 `feature/C3-注册表卸载项采集`；干净树 pytest 40 passed + selftest 6/6）。负责人终端：push 可先做（`git push -u origin feature/C4-Appx商店包采集`），PR diff 在 T-04 合入后自动收敛；合入顺序 T-04 → 本卡 → T-06。

---

## T-06 · 证据采集：进程 / 服务 / 自启动（待办 C5）

- **目标**：三源活动证据采集，与 T-04/T-05 汇成统一 `evidence` 集合。
- **输入指针**：方案第四节"证据采集"；`docs/upstream/prototype/processes.json`、`services.json`、`runkeys.json`（结构参考：54 进程/303 服务/10 自启动实测）。
- **实现约束**：只读；机制自决（ctypes 快照或 PowerShell，注意命令拆小与绝对路径教训）；自启动覆盖 HKCU/HKLM Run 键 + 启动文件夹列举；统一输出 `evidence` 聚合结构（设计一个 `evidence.py` 汇总接口，供引擎消费）。
- **验收标准**：① 本机三源均非空（贴数字量级）；② 单元测试覆盖解析与聚合逻辑；③ 聚合接口的 JSON 结构在文档中示例化（docstring 或 README 节选）。
- **依赖**：无（建议在 T-04/T-05 之后做以对齐聚合接口）。
- **执行记录**：
  - **做了什么**：新增 `processes.py`（Get-Process 可执行路径去重清单）、`services.py`（Win32_Service PathName 原文清单）、`autostart.py`（HKCU/HKLM Run + HKLM Wow6432Node Run 三键 + 用户/公共启动文件夹列举）、`evidence.py`（`collect_all()` 聚合 + `to_json_dict()`，单源失败记入 errors 披露不中断）；新增 `tests/test_evidence_bundle.py`（11 例：路径行解析去重、三源成功/降级、自启动注册表+文件夹+跳过计数、聚合结构、单源故障隔离、全默认不崩）。关键文件：`disk_audit/evidence/{processes,services,autostart,evidence}.py`、`tests/test_evidence_bundle.py`。
  - **实现决策及依据**：① 三源机制统一选 PowerShell 底座（_ps.py 复用 T-05；ctypes 进程快照复杂度高且无额外收益，D-执行）；② 自启动 Run 键三处 + 两启动文件夹与原型 runkeys.json 口径对齐（原型的 k 字段即这三种键位）；③ 聚合结构带 `schema_version: "evidence.v1"`（开发规范 §7 数据结构带版本的精神），完整 JSON 示例写在 `evidence.py` docstring（验收③）；④ 聚合层 `except Exception` 兜底仅限聚合边界，各采集器内部仍按 X-1 精确处理。
  - **未尽事项/已知限制**：Get-Process 拿不到以更高权限运行进程的 Path（PowerShell SilentlyContinue 静默略过）——高权限进程的归属判定会落到其他证据源，属已知盲区；服务清单含驱动路径原文（如 `\SystemRoot\System32\drivers\...`），语义归一留待判定层；**服务条数 172 低于原型 303**：本卡解析层对相同命令行去重（如大量 svchost 同参服务收敛为一条），原型 runkeys/服务 JSON 未去重——口径差异如实记录，不改卡。
  - **自测输出摘要**（2026-10-24 本会话实测）：pytest 全量 115 passed（含本卡 11 例）；**验收①本机三源非空：processes = 65、services = 172、autostart = 15（skipped = 0）**（原型基线 54/303/10，量级一致）；验收③ JSON 结构示例见 `evidence.py` docstring，`to_json_dict()` 与之一一对应（test_collect_all_aggregates 断言结构键与计数）。分支 `feature/C5-进程服务自启动采集` 已本地提交（堆叠于 `feature/C4-Appx商店包采集`；干净树 pytest 49 passed + selftest 6/6）。负责人终端：push 可先做（`git push -u origin feature/C5-进程服务自启动采集`）；合入顺序 T-04 → T-05 → 本卡。

---

## T-07 · 知识库 schema v1（待办 E1）

- **目标**：定义知识库条目数据结构并定稿。
- **输入指针**：方案 M1 交付、P10（许可边界）、《项目治理》§6（知识库治理）；`docs/upstream/prototype/analyze_appdata.py` 内置知识库（~260 条现状）。
- **实现约束**：字段至少含：`name`（目录名/正则）、`product`（归属产品）、`vendor`、`aliases`（别名表）、`category`（12 类之一，类目沿用调研报告分类）、`lifecycle`（在用/已停止/未知，**仅允许登记有公开依据的结论**）、`regex_family`（正则族指针，可空）、`source`（来源登记：本机实测/公开软件名/推断）、`notes`；配套 JSON Schema（`knowledge/schema.json`）+ 校验脚本；全部自行整理，不含 BCU 数据。
- **验收标准**：① JSON Schema 文件通过自身合法性检查；② 5 条代表性样例（系统组件/开发缓存/国产软件/更新缓存/未知长尾各一）通过校验；③ 1 条缺 `source` 字段的样例被校验拒绝；④ 分类枚举与调研报告 12 类对齐（贴对照）。
- **依赖**：无。
- **执行记录**：
  - **做了什么**：新增 `knowledge/schema.json`（draft 2020-12；字段 name/product/vendor/aliases/category/lifecycle/regex_family/source/notes，必填 5 项：name/product/category/lifecycle/source）、`tools/validate_knowledge.py`（零第三方依赖的 JSON Schema 子集校验器 + `--check-schema` 自检模式）、`knowledge/examples/examples.v1.json`（5 条代表性样例）、`tests/test_knowledge_schema.py`（9 例）。关键文件：`knowledge/schema.json`、`tools/validate_knowledge.py`、`knowledge/examples/examples.v1.json`、`tests/test_knowledge_schema.py`。
  - **实现决策及依据**：① category 12 类逐字沿用原型常量（`analyze_appdata.py` L31~42），测试将其硬编码为 ground truth 断言 schema 枚举与之相等（验收④）；② lifecycle 仅"在用/已停止/未知"且治理 §6 要求只登记有公开依据的结论——样例中"在用"仅用于有公开依据者（resmon/NuGet/百度网盘/XMind），未知长尾一律"未知"；③ source 枚举=治理 §6 的来源铁律三分法；④ 校验器不引 `jsonschema`（运行时零第三方依赖 + 开发期唯一第三方为 pytest，开发规范 §1/§2），自实现 type/required/properties/additionalProperties/enum/const/items/minLength/minimum 子集；⑤ 5 条样例全部取自原型实条目可追溯：resmon.resmoncfg（L246，系统组件）、nuget（L174，开发缓存）、baiduyunkernel（L232，国产软件/已安装应用）、xmind-vana-updater（L251，更新缓存，regex_family=updater-suffix）、aclos（L196，未知长尾/残留候选·低置信）。
  - **未尽事项/已知限制**：样例 vendor 为简写（正式 500 条登记时需逐条核实）；`name` 目前限定目录名字面量，正则形态的 `regex_family` 机制留给后续卡。
  - **自测输出摘要**（2026-10-24 本会话实测）：pytest 全量 115 passed（含本卡 9 例）；**验收① `--check-schema` → "schema 自身合法"；验收② `validate_knowledge.py knowledge\examples\examples.v1.json` → "通过：5 条条目符合 schema v1"；验收③由 test_missing_source_rejected 断言**（缺 source 被拒，报错含字段名）且全绿。验收④对照表：schema category 枚举 = 系统组件/兼容链接·严禁删除/已安装应用/使用中(无安装记录)/更新缓存/开发缓存/缓存/转储/游戏数据/残留候选·高置信/残留候选·中置信/残留候选·低置信/容器(已下钻)，与原型 CAT_SYS~CAT_CONT 十二常量一一对应（由 test_category_enum_matches_prototype_12 断言）。分支 `feature/E1-知识库schema-v1` 已本地提交（干净树 pytest 33 passed + selftest 6/6）。负责人终端：`git push -u origin feature/E1-知识库schema-v1` → 建 PR → 验收合入（`feature/E2-知识库种子迁移` 基于本分支，请先合入本卡）。

---

## T-08 · 知识库种子迁移（待办 E2）

- **目标**：原型知识库 ~260 条迁入 schema v1，语义不变。
- **输入指针**：T-07 产物；`docs/upstream/prototype/analyze_appdata.py`。
- **实现约束**：写一次性迁移脚本（可保留在 `tools/`）；**只迁移不修改语义**（发现疑似错误记"未尽事项"）；每条补全 `source` 登记字段；输出统计（总数、分类分布、正则族数）。
- **验收标准**：① 迁移后条目 ≥ 260 且全部通过 schema 校验；② `source` 字段无空值；③ 迁移前后各抽 10 条人工对照一致（贴对照表）；④ 统计输出贴执行记录。
- **依赖**：T-07。
- **执行记录**：
  - **做了什么**：新增 `tools/migrate_knowledge.py`（ast 静态提取原型 KB_ROAM/KB_LOCAL/KB_ANY——不执行原型代码，CAT_* 常量经环境表解析；非字面量赋值自动跳过）与 `tests/test_knowledge_migration.py`（7 例：常量解析、字段映射、空说明仍记置信度、去重保留首次、3 元组形态错误中止、合成条目过 schema、真实原型集成测试——条目 ≥260 且全部通过校验，即验收①②的可执行形态）。输出 `knowledge/entries.json`（容器格式 `{"schema_version": "knowledge.v1", "entries": [...]}`，校验器已支持容器装载）。
  - **实现决策及依据**（只迁移不修改语义的四条映射决策，D-执行）：① `lifecycle` 全部"未知"——原型无公开生命周期依据，治理 §6 禁止登记无依据结论；② `source` 全部"本机实测"——原型 KB 依据本机 320 项长尾实测整理（方案 P10/第八节）；③ 原型 4 元组的"置信度"无 schema v1 字段，以"置信度：X（原型遗留字段）"并入 `notes`，判定语义不变；④ 重复键保留首次出现（ROAM > LOCAL > ANY 顺序），丢弃者打印进统计。原型已知重复：KB_LOCAL 内 `fastpdf_sogou`（同值）、KB_ANY 内 `nutstoreclient`（'坚果云客户端'→'坚果云'，与 Python dict 末次生效语义一致，运行时行为不变）；跨 dict 重复约 10 处（clash plus/pixcake-qt_pro/kwallpaper_sogou/doubao/netease/stardock/everything/openark/copilot/claude-3p/hideandseek），由脚本统计披露。
  - **未尽事项/已知限制**：`*-updater` 归"更新缓存"是原型代码级规则，未迁为条目级 `regex_family`（正则族登记留待后续卡）；实测丢弃的 11 个重复键全部为**跨 dict** 重复（kwallpaper_sogou/pixcake-qt_pro/hideandseek 落 ROAM，doubao/netease/clash plus/everything/stardock/openark/copilot/claude-3p 落 ANY），保留首次出现、语义与原型运行时一致；KB_LOCAL 内 `fastpdf_sogou`（同值）、KB_ANY 内 `nutstoreclient`（'坚果云客户端'→'坚果云'）为 dict 字面量内重复，Python 末次生效语义在提取时保持一致。
  - **自测输出摘要**（2026-10-24 本会话实测，`knowledge/entries.json` 已生成）：**原型 KB_ROAM 84 + KB_LOCAL 143 + KB_ANY 53 = 280 条 → 迁移后 269 条（丢弃重复键 11 个，已逐键列出）**；分类分布：系统组件 31 / 兼容链接 3 / 已安装应用 69 / 使用中 7 / 更新缓存 15 / 开发缓存 34 / 缓存转储 13 / 游戏数据 21 / 高置信 16 / 中置信 32 / 低置信 28 / 容器 0（合计 269）；正则族 0；**source 空值 0；lifecycle 非"未知" 0**；10 条抽样对照已由脚本打印（按名称排序：.identityservice/.lingma/.qoder-cn/360safe/@deepseek-ai/@deepseek-aidsh-desktop-updater/@genieworkbuddy-desktop-updater/…，逐条展示迁移前元组与迁移后 JSON）；**验收①复核：`validate_knowledge.py knowledge\entries.json` → "通过：269 条条目符合 schema v1"**（269 ≥ 260 ✓）；pytest 全量 115 passed（含真实原型集成测试）。分支 `feature/E2-知识库种子迁移` 已本地提交（堆叠于 `feature/E1-知识库schema-v1`；干净树 pytest 41 passed + selftest 6/6）。负责人终端：push 可先做（`git push -u origin feature/E2-知识库种子迁移`）；合入顺序 T-07 → 本卡（人工抽验 10 条对照表后勾销验收③）。

---

## T-09 · 报告 JSON Schema 草案（待办 F1）

- **目标**：报告数据结构草案（含 `schema_version`），供 S2 判定引擎与 S3 渲染消费。
- **输入指针**：方案 M1 交付、E-2（每条候选字段）、5.1~5.3（置信度四档/可再生两档/动作 A1~A5）、Q7（schema_version 语义）。
- **实现约束**：候选条目字段：路径、逻辑大小、占用空间、置信度（枚举：高/中/低/受保护）、判定来源（枚举：硬保护/知识库/注册表/进程服务/Appx/启发式）、证据链（数组，每项含来源与内容）、建议动作（枚举 A1~A5）；顶层 `schema_version`；**不含"可回收"字段、不含合并"可释放"总量字段**（Q3 硬规则）。
- **验收标准**：① JSON Schema + 1 个合法完整样例（含受保护项与低置信项各一）；② 非法样例（含"可回收"字段 / 缺 schema_version）被拒绝；③ 字段与 E-2、5.1~5.3 逐项对照表。
- **依赖**：无。
- **执行记录**：
  - **做了什么**：新增 `docs/schemas/report-v1.schema.json`（顶层 schema_version/generated_at/scan_root/totals/candidates；候选条目 7 字段 + 证据链条目结构）、`docs/schemas/report-v1.example.json`（合法完整样例：受保护项（硬保护/DPAPI/A5）+ 中置信项（知识库/注册表/A4）+ 低置信项（启发式/A5））、`tests/test_report_schema.py`（14 例：样例通过且含受保护与低置信各一、受保护/低置信固定 A5、"可回收"字段拒绝、totals 合并"可释放"字段拒绝、缺/错 schema_version 拒绝、枚举与约束负例、E-2 字段精确集断言）。测试内实现支持 `$defs/$ref` 的子集校验器（开发期专用，不进运行时）。
  - **实现决策及依据**：① 判定来源枚举顺序=方案第四节流程③（硬保护 → 知识库 → 注册表 → 进程服务 → Appx → 启发式）；② 不设候选级"可再生"字段——E-2 定死 7 字段，5.2 两档以 totals 的 `regenerable_subtotal` / `regenerable_confirm_subtotal` 两个小计字段承载（5.2/Q3："两档分别列示各自小计，总量仅呈现磁盘占用"）；③ Q3 双负例进测试（可回收字段、合并可释放字段均被 additionalProperties:false 拒绝）；④ schema_version 用 `const "1.0"`（Q7 语义：版本不匹配提示"旧记录不可比"，禁止原地改义）；⑤ skipped_entries 进 totals（X-1/W0-C6 跳过统计对外可见）；⑥ 存放位置选 `docs/schemas/`（草案期文档位，S2 判定引擎落地时可随代码迁移进 `disk_audit/`，D-执行）。
  - **未尽事项/已知限制**：`schema_version` 是否用 "1.0" 还是 "1.0.0" 语义待 S2 定稿评审；证据链 item 的 source 当前为自由字符串（与 verdict_source 枚举不同源），S2 定稿时可考虑收紧枚举。
  - **自测输出摘要**（2026-10-24 本会话实测）：pytest 全量 115 passed（含本卡 14 例，覆盖验收①样例通过与验收②双负例拒绝）。分支 `feature/F1-报告JSON-Schema草案` 已本地提交（干净树 pytest 42 passed + selftest 6/6）。负责人终端：`git push -u origin feature/F1-报告JSON-Schema草案` → 建 PR → 验收合入。验收③对照表：E-2 七字段 path/logical_bytes/allocated_bytes/confidence/verdict_source/evidence_chain/suggested_action → schema 同名属性（test_candidate_has_exactly_e2_fields 断言精确相等）；5.1 四档 高/中/低/受保护 → confidence 枚举；5.3 A1~A5 → suggested_action 枚举；5.2 两档 → totals 两小计字段；Q3/Q7 → 负例测试（"可回收"字段、合并"可释放"字段、缺/错 schema_version 均被拒绝）。

---

## R-L1 · VM 父镜像准备（负责人任务，非执行卡）

- **目标**：Sprint 2 的 M1 验收环境就绪。
- **动作要点**（详见《[环境基线](../governance/环境基线.md)》§3）：在 `H:\Virtual Machine\` 分别创建 22H2 / 24H2 两台基础 VM（每台 4GB 内存、2 vCPU、动态 VHDX），装好系统更新，关机前 `Optimize-VHD` 压缩，父镜像设只读；验收差分盘 Sprint 2 再建。
- **完成标志**：两台基础 VM 可开机进系统，父镜像就位。
- **状态**：待负责人安排（不阻塞本 Sprint 执行卡）。
