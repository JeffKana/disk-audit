# Sprint 2（W2）计划与任务卡包 · 名义 2026-10-27 ~ 10-31（进度领先，可在 PR#2 合入后即开工）

**Sprint 目标一句话：判定流水线立骨架，M1 五条闸门过闸。**

产出依据：《交付与验收流程》§6（收数→对表→排程→成卡→报批）。收数输入：Sprint 1 验收报告（6 过 / 2 条件闭环 / 1 退回闭环）、DR-004 修订版、M1 闸门口径（方案第七节）。

## Sprint 2 目标（周五可逐条打勾）

1. C2 性能达标：AppData 全量恢复 ≤6s 量级，三真实目录基准复测 <1%（DR-004 修订版验收口径①②'③⑤）。
2. 归属引擎 v1 可运行：六层流水线 + 四档置信度 + 可再生两档，判定纯函数、零 UI 依赖、CLI 可调。
3. 防误判起步：回归样例格式落地 + 首例（子串误判）入集。
4. 中止安全：X-2 口径实现（不完整报告、无汇总结论）。
5. 知识库 ≥500 条全过校验，来源登记完备供 PM 抽查。
6. 报告 Schema 定稿（版本语义 + 证据链枚举收紧，与引擎输出对齐）。
7. VM 基线就绪并在其上完成 M1 验收（①②在 VM 复测）。

**通用红线**（所有执行卡适用）：不 merge、不 push main（main 已开分支保护，PR 必须等 `windows` 检查绿）；不改验收标准；只写 `%LOCALAPPDATA%\DiskAudit\`；新问题记"未尽事项"不顺手修；命令用完整解释器路径；越界改动即使"更好"也退回。

---

## T2-01 · C2 性能优化（DR-004 修订版）

- **目标**：占用空间取数恢复 POC 量级，同时保持偏差达标。
- **输入指针**：[DR-004（含 2026-10-25 修订节）](../governance/decisions/DR-004-2026-10-24-占用空间取数性能.md)、`disk_audit/scanner.py`、`tests/test_scanner.py`、`tools/check_size_deviation.py`、`tools/baseline.json`（已登记三目录）。
- **实现约束**：三段分流——压缩/稀疏（`st_file_attributes`）句柄实查；**逻辑 < 簇 → align8**；逻辑 ≥ 簇 → 簇对齐（簇大小经 `GetDiskFreeSpaceW` 查询缓存）。双口径语义与接口不变；探针（align8 vs 句柄实查）沉淀为测试。
- **验收标准**：① 本机 AppData 全量（Local+Roaming）≤6s 量级，贴实测；② 混合夹具（0B/~100B/~700B/~1KB/~5KB 梯度）混合 vs 纯句柄汇总偏差 <0.1%，其中 <簇样本 align8 与实查逐文件一致；③ 三真实目录基准复测（`--baseline tools/baseline.json`）全部 <1%，贴数；④ 属性分流单测（属性位 monkeypatch）；⑤ CI 绿。
- **依赖**：无（与 T2-02 并行，接口不变）。
- **执行记录**（2026-10-31，分支 `feature/C2-占用空间三段分流`，基于未合入的 D1 分支栈式切出——D1 已改 `_account_file` 签名，push 前需等 D1 合入后 rebase；合入顺序 D1 → C2）：

  **做了什么**：占用空间取数按 DR-004 修订版三段分流重构，扫描耗时恢复量级。`disk_audit/scanner.py`：新增 `_FILE_ATTRIBUTE_COMPRESSED/_SPARSE_FILE` 属性位判别、`_align8`、`GetDiskFreeSpaceW` 绑定与按盘符缓存 `_cluster_bytes`（失败回退 4096），`_account_file` 三段分流（①压缩/稀疏→句柄实查，失败仍 X-1 计 occupied；②逻辑<簇→align8；③逻辑≥簇→簇对齐），非 Windows 降级不变，scan 输出接口不变。新增 `tools/probe_resident_allocation.py`（DR-004 修订节探针条款的测定脚本）。测试：`tests/test_scanner.py` 新增属性位 monkeypatch 分流、常规文件零句柄、align8 纯函数、句柄失败 X-1、驻留探针（≤600B 稳定驻留样本逐文件 align8==句柄）、大文件簇对齐逐文件一致、簇缓存/回退共 7 例，`_FakeEntry` 支持注入属性位。

  **实现决策及依据**：
  1. 探针测试样本取 0/1/100/600B——驻留边界实测约 600~750B 且**不稳定**（700B 两次探针一次驻留一次非驻留），>600B 样本会 CI 抖动；完整梯度表由 `tools/probe_resident_allocation.py` 承载（DR-004 修订节探针条款"沉淀为测试**或** tools/ 测定脚本"）。
  2. 普通文件不再开句柄后，"occupied"跳过语义收窄为"压缩/稀疏文件句柄失败"（推算路径不存在查询失败）——双口径一致性不受影响（推算无失败态），X-1 披露口径变化记入本记录。
  3. `_cluster_bytes` 直接传 `c_ulong` 实例（ctypes 自动按 POINTER 转换）以便测试桩注入。

  **⚠️ 冲突上报（SOP"冲突即停"，取舍权在 PM/D-技术，未自行取舍）**：DR-004 修订版前提"**<簇且非常驻的文件罕见，残差受控**"经探针证伪——
  - 本卷（C: NTFS，簇 4096B）MFT 驻留上限实测约 **600~750B**（DR-004 记"<700~900B"），且边界不稳定（700B 文件两次探针分别驻留 704B / 非驻留 4096B）；
  - **713~4095B 文件既 <簇又必然非驻留**，align8 规则对每个文件系统性低估 (4096−逻辑) 字节。仅 Programs 一个目录该段就有 **11,906 个文件、低估合计 25.9MB**（1-712 段另有 2.1MB 边界抖动）；
  - 后果①：DR-004 ②'（混合夹具 vs 纯句柄汇总 <0.1%）在字面梯度（0B/~100B/~700B/~1KB/~5KB）上**不可达成**——仅 ~1KB 非驻留样本一项即引入 ~23% 偏差，与权重无关。②'前半句"常驻小文件逐文件 align8 与句柄实查一致"已由测试证实成立（≤600B 样本逐文件精确）。
  - 后果②：验收③ Programs 基准复测 **3.246% 不通过**（阈值 <1%）。经剪枝 walk 同文件集分解（29,673 文件两口径一致）：**三段 vs 纯句柄实查 = 0.942%**（713-4095 段系统性低估所致，贴 M1 ①闸门边缘）；**纯句柄 vs 2026-10-25 基准 = +4.227%**（目录 6 天净增 ~101MB，基准过期，非实现回归——Sprint1 同口径句柄实现今天跑也会 ~4.2%）。Tencent 0.565%、Package Cache 0.009% 通过（同为旧基准）。
  - **请 PM 裁决**（数据齐备）：a) 维持 align8 字面实现，接受 ~1% 量级系统残差，②'口径修订；b) 分流边界改为"≤驻留上限 align8、其余簇对齐"；c) 713~4095 段恢复句柄实查（Local 实测该段 ~12k 文件，30µs/句柄仅增 ~0.4s，总耗仍 ~7s）；d) 其他。①耗时已达标，④⑤无争议；③需负责人重读三目录资源管理器"占用空间"刷新基准后复测（旧基准已过期）。

  **未尽事项/已知限制**：
  1. 上述 DR-004 冲突未裁决前，验收②③保持"未认证"状态（不red不绿，不自行改阈值或口径）。
  2. Local 扫描 6.8~7.0s 略超"≤6s"字面（Roaming 3.95~4.1s 达标；合计 ~11s，为原 25.27s 的 2.3×加速），按 DR-004 验收④未触发 R1 预案（<2× 预算）——"量级"判定请 PM 一并裁决。
  3. 诊断工具 os.walk 会下钻 junction 而 scanner 正确跳过（本轮诊断已踩坑并剪枝），后续排查容量偏差时注意。

  **自测输出摘要**：
  - pytest 158 passed（较 D1 基线新增 7 例）；`--selftest` 6/6，RC=0。
  - 验收①实测（解释器 `D:\develop\environment\python\python.exe`）：scan `%LOCALAPPDATA%` **6.8s**（预热复测 7.0s），439,352 files / 76,155 dirs，跳过 83；scan `%APPDATA%` **3.95s**（复测 4.1s），193,969 files / 47,679 dirs，跳过 1。（原句柄逐文件实现：19.36s + 5.91s。）
  - 验收③：Tencent 0.565% ✓、Package Cache 0.009% ✓、Programs 3.246% ✗（分解见冲突上报：基准过期 +4.227% 为因，实现系统残差 0.942%）；`--fixture` 回归 0.000% ✓。
  - 验收④：属性位 monkeypatch 分流测试（压缩/稀疏→句柄、常规→零句柄、句柄失败→occupied）全绿。
  - 探针表（`tools/probe_resident_allocation.py`）：0/1/100/600B align8 逐字节精确；700~4095B 非驻留段句柄 4096 vs 推算 size（低估）；≥4096B 簇对齐逐字节精确。

---

## T2-02 · D1 归属判定流水线 v1

- **目标**：六层判定流水线可运行，产出符合 report-v1 草案的候选结构。
- **输入指针**：方案第四节架构③、5.1；`disk_audit/hardprotect.py`（S-1 短路）、`knowledge/entries.json`、`disk_audit/evidence/evidence.py`（EvidenceBundle）、`docs/schemas/report-v1.schema.json`（草案）、调研报告原型流水线（`docs/upstream/prototype/analyze_appdata.py`）。
- **实现约束**：**硬保护在最前短路返回，不参与打分、不可配置覆盖（S-1）**；其后知识库 → 注册表 → 进程/服务 → Appx → 启发式；判定单元按 9.2（扫描范围顶层目录及下钻子项，文件级不单独计入）；判定为纯函数（输入：单元路径 + 大小聚合 + EvidenceBundle + KB；输出：档位/来源/证据链/动作），I/O 只在采集层；消费 evidence 时统一"唯一路径"口径（服务 172 vs 原型 303 的差异按验收报告 §3.3 口径处理并在输出披露口径字段）。
- **验收标准**：① 对本机 AppData 319 顶层目录全量判定跑通，每单元有档位/来源/证据链/动作，无异常中断；② 纯函数快照测试（固定输入 → 固定输出，至少 6 个代表单元：受保护/已安装/知识库命中/启发式/更新缓存/未知长尾各一）；③ 硬保护优先且不可覆盖的专项测试；④ CLI：`python -m disk_audit judge <scan-result>` 可独立调用（零 UI 依赖）；⑤ 产出候选条目通过 report-v1 草案校验（T2-07 定稿前按草案）。
- **依赖**：无（与 T2-01 并行；知识库与证据集已合入 main）。
- **执行记录**（2026-10-31，分支 `feature/D1-判定流水线`）：

  **做了什么**：六层归属判定流水线 v1 落地。scan 增加判定单元级聚合输出（`UnitStats`：files/dirs/双口径/max_mtime/exe_files；BFS 段共享聚合、并行段局部增量后串行合并，零额外系统调用）；新增 `disk_audit/engine/` 包：`knowledge.py`（知识库装载与 name/别名精确匹配）、`judge.py`（六层顺序短路纯函数判定）、`report.py`（report-v1 草案装配 + judge 编排）；CLI 新增 `judge <scan-result>` 子命令（零 UI 依赖）。关键文件：`disk_audit/scanner.py`、`disk_audit/engine/{__init__,knowledge,judge,report}.py`、`disk_audit/__main__.py`、`tests/test_engine_units.py`、`tests/test_engine_judge.py`、`tests/_mini_schema.py`（自 test_report_schema 抽出共用校验器）、`tests/test_report_schema.py`（改导入）、`tests/test_scanner.py`（_FakeEntry 对齐 DirEntry.name/st_mtime）。

  **实现决策及依据**：
  1. 判定单元划分：顶层目录为单元；顶层 `Programs`/`Packages` 容器（大小写不敏感）下钻一层，子目录亦为单元，容器本身仍为单元——对齐原型 drill_programs/drill_packages 与 9.2"顶层目录及其下钻子项"。
  2. 陈旧度阈值取 180 天（方案 5.1），不取原型 540——优先级"方案定稿>原型"（项目治理 §4）。
  3. 知识库命中但注册表/进程/服务/自启动证据表明在用 → 以在用为准（注册表→A3、运行证据→A5），知识库作证据链上下文——依据 9.2"已安装"口径与 M4"高置信档对在用软件误判=0"；5.1 高档五证据在 KB 层内部核验（无注册表+无运行证据+陈旧），未破坏架构③层序（原型"KB 命中即返回"不采用，避免在用软件被 KB 残留条目误判）。
  4. "已停止"但不够陈旧 → 中（KB 标注+无运行证据=2 项证据成立，5.1 中档）；180 天边界参数化锁定（180→中、181→高），全组合矩阵留 T2-03。
  5. 仅启发式（哈希/GUID/陈旧/无 exe 任一或组合）一律低置信+A5+措辞"归属未知，需人工判断"——S-2"上限锁低"字面执行（原型 stale→中 不采用）；"无 exe"仅在单元有文件时记信号，避免空目录噪声。
  6. 服务证据"唯一路径"口径披露写入服务命中证据链 content（"服务唯一路径口径，全库 N 条唯一路径"）；报告草案顶层 `additionalProperties:false` 不容独立字段，T2-07 定稿时再议。
  7. Appx 匹配三口径（原型 match_appx + drill_packages）：包名/全名精确 → 含点号包名式命名双向包含（code≠openaicodex 防护）→ Packages 数据目录 FamilyName_hash 按全名前缀比对；注册表包含匹配保留 len≥5 门槛（原型口径）。
  8. 动作映射 v1：注册表/Appx 命中→A3；KB"已安装应用"→A3；运行证据/受保护/在用/容器/系统组件/低置信→A5；KB 残留候选、更新缓存（*-updater 正则族）→A2——F4（S4）定稿时对齐 5.3。
  9. scan 输出新增 `units` 数组为附加字段，现有键不动（L2 脚本、T2-05 部分结果消费不受影响）。
  10. `mini_validate` 抽到 `tests/_mini_schema.py` 共用（引擎输出草案校验复用），test_report_schema 改导入，行为不变。

  **未尽事项/已知限制**：
  1. **新问题（属 C5，建议另立任务）**：`evidence/_ps.py` 以 UTF-8 解码 PowerShell 输出，本机实测 Get-Process 输出含中文路径（GBK 字节）时读取线程 UnicodeDecodeError 崩溃，进程证据**静默变空**（available=True + 0 条，未降级未披露）。本次全量判定进程源实际为空（注册表 286/Appx 199/服务 173/自启动 15 均正常），"在用"判定退化。建议：解码容错（errors=replace 或按控制台代码页/PowerShell 侧 OutputEncoding）+ 空 stdout 与 0 路径区分披露。VM 差分机 GT 软件进程路径均为 ASCII，M1 验收②预计不受影响，但应在 M1 前修复确认。
  2. "无版本信息"启发式（5.1 低档列举）v1 未实现（需读 PE 版本资源，超本卡范围）——留 D4/M4。
  3. 中档"2 项证据成立"完整组合矩阵由 T2-03 参数化锁定；本次仅锁"已停止+无运行证据（不够陈旧）→中"与 180 天边界。
  4. 本机实测注册表命中仅 6 单元（双目录合计 3+3），叠加进程源为空，"已安装/在用"占比偏低——归属率真实水平待 VM 环境 + 未尽事项 1 修复后评估（M1 ②在差分机验收）。

  **自测输出摘要**：
  - pytest 151 passed（含新增 test_engine_units 10 例、test_engine_judge 24 例）；`--selftest` 6/6，RC=0。
  - 验收①实测（本机，解释器 `D:\develop\environment\python\python.exe`）：
    scan `%LOCALAPPDATA%`：22.1s，files 439,357 / dirs 76,237，跳过 120，单元 341（顶层 160 + 下钻 181）；scan `%APPDATA%`：9.53s，files 193,966 / dirs 47,679，跳过 1，单元 138；顶层目录合计 298（方案口径 319 为调研时点状态，以实测为准）。
    judge 双目录 RC=0：479 单元全部产出档位/来源/证据链/动作，路径唯一、无异常中断；置信度分布 Local 高68/中240/低32/受保护1，Roaming 高57/中71/低9/受保护1。
    Q3 复核：输出不含"可回收"、totals 无合并"可释放"字段；抽查 `Roaming\Code` → 高·知识库·"Visual Studio Code 用户数据（已安装应用）"·A3（无 openaicodex 误判）；`Roaming\Microsoft` → 受保护·A5。
    本机 judge 无服务命中单元，"唯一路径口径"披露未在输出出现（机制由 test_service_hit_discloses_unique_path_scope 覆盖）。

---

## T2-03 · D2+D3 置信度四档与可再生两档

- **目标**：打标规则完全对齐方案 5.1/5.2。
- **输入指针**：方案 5.1（四档触发条件与输出措辞）、5.2（两档覆盖范围与表述）、Q3 硬规则；T2-02 流水线。
- **实现约束**：高置信 = 5 项证据**同时成立**（注册表无卸载记录 + 无匹配进程/服务 + 无自启动 + 陈旧 >180 天 + 知识库标注"已停止"）；中 = 2 项成立或 KB 命中缺生命周期；低 = 仅启发式（哈希/GUID/陈旧度/无 exe），**措辞无倾向性**；受保护固定 A5；措辞枚举与方案表格逐字一致、集中在文案资源；可再生两档按 5.2 范围归类，各自小计，**禁止"可回收"字样与合并"可释放"总量**。
- **验收标准**：① 参数化用例覆盖每档触发组合（含高档 5 证据缺一降中的边界）；② 措辞枚举与方案 5.1/5.2 对照表断言；③ 输出全文不含"可回收"（负例断言）；④ 低置信项固定 A5、无倾向表述断言。
- **依赖**：T2-02（建议栈式）。
- **执行记录**（2026-10-31，分支 `feature/D2D3-置信度打标`，基于 E3 分支栈式切出，合入顺序 D1→C2→E3→D2D3）：

  **做了什么**：置信度四档与可再生两档对齐方案 5.1/5.2。新增文案资源 `disk_audit/engine/texts.py`（5.1 四档输出措辞、高档两短句、5.2 两档表述，逐字摘自方案定稿 HTML 并经对照表断言锁定）；判定输出注入措辞——残留类判定（受保护/高残留/中/低）在证据链首条携带对应 5.1 措辞，更新缓存（*-updater）证据链携带 5.2 可再生表述逐字原文，已安装/在用判定不携带残留措辞；六代表单元快照随措辞注入同步演进；新增 `tests/test_engine_wording.py` 19 例。关键文件：`disk_audit/engine/texts.py`、`disk_audit/engine/judge.py`、`tests/test_engine_wording.py`、`tests/test_engine_judge.py`（快照更新）。

  **实现决策及依据**：
  1. 档位触发矩阵（验收①参数化锁定）：高=5 证据同时成立；已停止+无运行但不够陈旧→中（"2 项成立"）；KB 命中缺生命周期→中（含陈旧不升档）；无 KB 仅启发式→低（S-2 上限锁低，与信号数量无关）。
  2. 高档缺"无注册表/无运行"证据的边界：单元本属已安装/在用，走正向判定层（注册表/进程服务），而非降中——"缺一降中"只适用于同属残留评估路径的证据缺失；矩阵测试两行分别锁定。
  3. 高档措辞在方案表格为两短句（"高度可能为残留"＋"删除前请确认"），输出串以"；"连接（呈现决定），两短句逐字保留并有独立断言。
  4. 措辞注入证据链而非新增字段：report-v1 草案 candidate 七字段固定（additionalProperties:false），措辞作为首条证据链（source=判定层）输出，F2 渲染可直接取用；T2-07 枚举收紧后仍兼容。
  5. 5.2 归类范围断言：可再生={更新缓存, 缓存/转储}、需确认={开发缓存}（report.py 既有映射，本卡测试锁定，未改动）。

  **未尽事项/已知限制**：5.2"下载缓存"在知识库 12 类中无对应类别，暂由"缓存/转储"覆盖，F1/T2-07 对照表已留注意项。

  **自测输出摘要**：pytest 177 passed（新增 test_engine_wording 19 例：对照表 4、措辞资源 Q3 1、触发矩阵 6、边界 2、措辞注入 4、低置信 A5 3、5.2 归类 1）；`--selftest` 6/6，RC=0。

---

## T2-04 · D6 首例回归用例与样例格式

- **目标**：误判回归基础设施落地，首例（子串误判）入集。
- **输入指针**：9.1 底线二、调研报告"Roaming\Code 误判 openaicodex"实证、开发规范 §3（回归样例 JSON 脱敏）。
- **实现约束**：样例格式定义（JSON：路径模式 / 期望档位 / 期望来源 / 误判根因 / 登记日期 / 来源登记）；样例数据驱动跑引擎；**脱敏**（不含用户名/机器名/SID）；包含匹配防护规则 = 仅限含点号的包名式命名（原型修复口径）。
- **验收标准**：① 样例格式文档 + schema；② 首例 Code≠openaicodex 通过（引擎对该路径输出不含 openaicodex 判定）；③ 至少 3 个反例锁定防护规则边界（如 `com.example` 合法包含、`code` 裸名不参与包含匹配）；④ 样例全脱敏断言。
- **依赖**：T2-02（建议栈式）。
- **执行记录**（2026-10-31，分支 `feature/D6-首例回归`，基于 D2D3 分支栈式切出，合入顺序 D1→C2→E3→D2D3→D6）：

  **做了什么**：误判回归基础设施落地。样例格式 schema `docs/schemas/regression-case-v1.schema.json`（字段：case_id/title/registered_at/registered_by/root_cause/path_pattern/unit/evidence_scenario/expect[confidence+verdict_source+forbidden_terms]/notes，与卡面"路径模式/期望档位/期望来源/误判根因/登记日期/来源登记"对应，另加复现所需的罐装证据场景）；格式文档 `docs/schemas/回归样例格式-v1.md`（存放位置、三层校验流程、脱敏规则、知识库修正联动）；样例 `tests/data/regression/` 5 例（R001 首例 Code≠openaicodex + R002~R005 边界）；数据驱动测试 `tests/test_regression_cases.py`（schema 校验 + 脱敏断言 + 引擎判定断言，新增样例零改动自动纳入）。共用校验器 `tests/_mini_schema.py` 增 `pattern` 关键字支持。关键文件：上述 schema/文档/样例/测试 + `_mini_schema.py`。**引擎零改动**——防护规则 T2-02 已正确实现，本卡以回归集锁定。

  **实现决策及依据**：
  1. 样例增补 `evidence_scenario` 字段（卡面字段清单之外）：回归样例需可复现触发边界，必须携带罐装证据（判定为纯函数的输入之一）；unit 字段与 scan 输出 units 元素同构（开发规范 §3 数据驱动）。
  2. 脱敏断言动态取本机真实值（getpass 用户名/COMPUTERNAME/SID 正则），而非硬编码名单（开发规范 §3：不含用户名/机器名/SID）。
  3. R002 原用 com.example，实测与生产 KB 已登记条目（示例包名调试残留）冲突——知识库层先于 Appx 层短路属正确架构③层序；样例改用 com.sample 避开 KB，层序交互本身固化为 R005 备案（误判样例发现新交互 → 当天入集，底线二）。
  4. R001 期望来源=知识库（依赖生产 KB 含 code 条目）：回归样例锁定当前真实判定，KB 未来变更导致样例失败时即触发人工复核（回归集的本意）。

  **未尽事项/已知限制**：回归样例期望绑定生产知识库内容，KB 大规模扩充（E4）时可能批量触发复核——届时按治理 §6 修正流程逐条处理。

  **自测输出摘要**：pytest 193 passed（新增 test_regression_cases 16 例：schema 校验 5、首例在场 1、脱敏 5、引擎断言 5）；`--selftest` 6/6，RC=0。样例 5 例：R001 首例（输出全文禁现 openaicodex ✓）、R002 含点号合法包含 ✓、R003 短名拒包含 ✓、R004 长名合法包含 ✓、R005 层序备案 ✓。

---

## T2-05 · C7 中止与部分结果

- **目标**：X-2 口径实现——中止/异常退出保留部分结果并标记，不输出汇总结论。
- **输入指针**：X-2、方案六节（流式聚合）；`disk_audit/scanner.py`、`__main__.py`。
- **实现约束**：用户中止（Ctrl+C/停止信号）与异常退出统一走"不完整"出口：已采集单元保留、汇总（totals）不输出或显式标记无效；不产生半成品结论；与 E-4"未扫描条目数"字段衔接。
- **验收标准**：① 模拟中止（注入中断/超时）→ 输出含"不完整"标记且无有效 totals；② 正常完成路径不受影响（回归）；③ 部分结果可被 judge 消费并同样标记不完整；④ 测试覆盖两种触发（用户中止/异常）。
- **依赖**：T2-01（同改 scanner/CLI，建议在其后栈式）。
- **执行记录**：

---

## T2-06 · E3 知识库扩至 500

- **目标**：269 → ≥500 条，来源登记完备。
- **输入指针**：知识库治理（项目治理 §6：全部自行整理、不复制 BCU、来源登记、lifecycle 仅公开依据）、`knowledge/schema.json`、`tools/validate_knowledge.py`。
- **实现约束**：新增条目覆盖建议优先级：①本机 TreeSize 长尾中仍未登记的常见目录（归档 CSV 可查）；②公开软件名（登记可查证的产品/厂商名）；lifecycle 只能填"未知"除非有公开下线依据；正则族指针复用既有族；**不复制 BCU 数据**。
- **验收标准**：① ≥500 条全过 schema 校验（贴校验输出）；② 新增条目的 source 分布统计与 lifecycle 分布（预期绝大多数为"未知"）；③ 提交 ≥20 条抽样清单（名称/来源/类别）供 PM 复核；④ CI 绿。
- **依赖**：无。
- **执行记录**（2026-10-31，分支 `feature/E3-知识库扩至500`，基于 C2 分支栈式切出——执行记录同文件，合入顺序 D1 → C2 → E3）：

  **做了什么**：知识库 269 → **503 条**（新增 234，24 个候选与既有条目重名被去重跳过）。数据来源按卡面优先级：①本机 TreeSize 长尾未登记目录 22 条（桌面 Local/Roaming 详细信息 CSV 共 319 行，与既有 269 条求差集；`programs`/`packages`/`microsoft` 由规则层处理不入库、`.ini` 文件行排除、跨目录重名去重），分类沿用归档候选分析 CSV（2026-10-23）的原型判定；②公开软件名 212 条（产品/厂商公开可查证的常用软件数据目录命名：通讯协作、效率工具、浏览器、网盘、安全、硬件厂商、游戏、开发缓存、更新/崩溃缓存等）。合并脚本一次性完成去重、regex_family 指派（*-updater→updater-suffix、哈希→hash-name、GUID→guid-name，复用既有族名）、键序与缩进保持原文件风格。关键文件：`knowledge/entries.json`（89,642→177,342 B）。

  **实现决策及依据**：
  1. lifecycle 全部"未知"，唯一例外 `atom` 填"已停止"（GitHub 2022 官方停服公告，公开依据，治理 §6"仅允许登记有公开依据的结论"的正确使用示例）。
  2. `adrive` 归档原判"残留候选·低置信"，目录名与公开产品阿里云盘（adrive）一致，依公开软件名归类"已安装应用"并在 notes 披露原判——来源字段仍填"本机实测"（观测事实）。
  3. 公开条目 notes 统一模板"{product}（{vendor}）公开产品的数据目录命名；用途：{brief}"，不含推测性置信度表述（置信度档位由引擎 5.1 规则给出，不写死在知识库）。
  4. `.aws` notes 明确"仅诊断，不读取内容"（凭据目录，呼应 DPAPI 底线精神）。
  5. `wechat` 等嵌套在已登记父目录（Tencent）下的目录不重复登记；Microsoft 系嵌套目录由 S-1 硬保护处理，不入库。

  **未尽事项/已知限制**：
  1. `tools/validate_knowledge.py` 不含重名检查（本次以一次性脚本独立查重，见自测）；建议后续卡给校验器补重名规则（另立任务，不顺手改）。
  2. 公开条目 212 条基于公开可查证的产品命名常识整理，PM 抽查若发现个别"产品-目录名"对应存疑，按治理 §6 修正流程处理（知识库修正当天同步回归集）。
  3. TreeSize CSV 仍留在桌面原处不入库（含个人目录清单，项目治理 §7）。

  **自测输出摘要**：
  - `python tools/validate_knowledge.py knowledge/entries.json` → `[校验] 通过：503 条条目符合 schema v1`；独立查重：503 条全部唯一，0 重复。
  - 分布：source = 本机实测 291 / 公开软件名 212；lifecycle = 未知 502 / 已停止 1（预期绝大多数"未知"✓）；category = 已安装应用 214 / 开发缓存 64 / 系统组件 49 / 残留候选·低置信 46 / 游戏数据 40 / 残留候选·中置信 34 / 更新缓存 16 / 残留候选·高置信 16 / 缓存/转储 14 / 使用中(无安装记录) 7 / 兼容链接·严禁删除 3 / 容器(已下钻) 0。
  - pytest 158 passed；`--selftest` 6/6（知识库校验测试自动覆盖新条目）。
  - **PM 抽样清单（24 条，名称/来源/类别/产品）**：discord/公开软件名/已安装应用/Discord；telegram desktop/公开软件名/已安装应用/Telegram；teams/公开软件名/已安装应用/Teams；feishu/公开软件名/已安装应用/飞书；obsidian/本机实测/已安装应用/Obsidian；sublime text/公开软件名/已安装应用/Sublime Text；sharex/公开软件名/已安装应用/ShareX；brave-browser/公开软件名/已安装应用/Brave；dropbox/公开软件名/已安装应用/Dropbox；huorong/公开软件名/已安装应用/火绒；kaspersky/公开软件名/已安装应用/卡巴斯基；intel/公开软件名/系统组件/Intel；logitech/公开软件名/系统组件/罗技；battle.net/公开软件名/游戏数据/暴雪战网；.minecraft/公开软件名/游戏数据/Minecraft；huggingface/公开软件名/开发缓存/HuggingFace；.cargo/公开软件名/开发缓存/Cargo；go-build/公开软件名/开发缓存/Go；squirreltemp/公开软件名/更新缓存/Squirrel；crashpad/公开软件名/缓存转储/Crashpad；rapoogamedev/本机实测/已安装应用/雷柏；adrive/本机实测/已安装应用/阿里云盘；antdownload/本机实测/残留候选·中置信/归属不明。

---

## T2-07 · F1 报告 Schema 定稿

- **目标**：从草案转定稿：版本语义 + 证据链 source 枚举收紧 + 与引擎输出对齐。
- **输入指针**：草案（`docs/schemas/report-v1.*`）、Q7（schema_version 语义）、evidence.v1 的 source 集合、T2-02 引擎输出。
- **实现约束**：版本语义写明升级规则（结构破坏性变更 → major+1，并联动 I3"旧记录不可比"提示）；证据链 `source` 收紧为枚举（与 evidence.v1 六源对齐）；保持 Q3 双禁止。
- **验收标准**：① 版本语义与枚举收紧后样例同步更新、非法样例被拒；② T2-02 引擎真实输出（本机 AppData 全量）通过定稿 schema 校验；③ 对照表：schema 字段 ↔ E-2/5.1/5.2/5.3 逐项；④ CI 绿。
- **依赖**：T2-02 产出后对齐（定稿合入前完成对齐校验）。
- **执行记录**：

---

## R-L1 · VM 基线与 M1 验收环境（负责人任务，S2 内必须完成）

- **动作要点**：`H:\Virtual Machine\` 建 22H2 / 24H2 父镜像（各 4GB 内存 / 2 vCPU / 动态 VHDX，更新后 `Optimize-VHD` 压缩、设只读）；每父镜像建 1 台差分验收机；在差分机上装 10~15 个常见软件作为最小 ground truth（供 M1 ②归属率估算；正式装 N 卸 M 矩阵在 M4）。
- **完成标志**：两台差分机可开机，`python -m disk_audit scan/judge` 可运行，软件清单登记到本卡记录。
- **状态**：✅ 已完成（2026-10-26，负责人委托 AI 会话以 VirtualBox 执行，执行记录如下）

### R-L1 执行记录（2026-10-25 ~ 10-26）

**做了什么**：在 VirtualBox 7.2.22（负责人 2026-10-25 裁决改用 VirtualBox，替代 DR-002/DR-003 的 Hyper-V 假设，避免对 Hyper-V 栈做提权安装与整机重启；WSL2/Docker 不受影响）下建成 4 台 VM：

| VM | 系统 | 状态 | 磁盘位置 |
| --- | --- | --- | --- |
| L1-base-22h2 | Win11 22H2 专业版 zh-CN，build 22621.382（WU 至 ALL_DONE） | 已关机，快照 base-v1（只读基线） | H:\Virtual Machine\L1-base-22h2\ |
| L1-base-24h2 | Win11 24H2 专业版 zh-CN，26100.1742 → KB5127648 后 26100.9711（WU ALL_DONE） | 已关机，快照 base-v1（只读基线） | H:\Virtual Machine\L1-base-24h2\ |
| L1-acc-22h2 | 差分验收机（linked-clone，父 base-v1） | 关机（GT 装毕、scan 验证毕） | H:\Virtual Machine\L1-acc-22h2\ |
| L1-acc-24h2 | 差分验收机（linked-clone，父 base-v1） | 关机（GT 装毕、scan 验证毕） | H:\Virtual Machine\L1-acc-24h2\ |

父镜像：4GB 内存 / 2 vCPU / EFI + TPM 2.0 / 80GB 动态 VDI / NAT；本地管理员 `qa`（autologon，密码登记于 VM 内 autounattend，未入库）；OOBE 全跳过（无 MS 账号）；Guest Additions 已装；`C:\stage\python-3.13.5`（含 Tcl/Tk）与仓库 main 快照已烤入父镜像（差分机开箱即含）；父镜像更新后 sdelete 置零 + `VBoxManage modifymedium --compact`（22H2：16.97→16.07GB；24H2：46.3→43.8GB）+ base-v1 快照 = 只读基线（差分盘只写子层）。

**ground truth 软件清单（11 个，双差分机同构；覆盖 Program Files / Local / Roaming 三类写入位）**：
Chrome（enterprise MSI）、Firefox 157.0.1、7-Zip 26.05、Notepad++ 8.9.8.1、Git 2.56.0.3、VS Code 1.141.2、微信（WeChatSetup）、QQ NT 9.9.33、WPS Office 12.2.0.23196、网易云音乐 3.1.42.205594、Steam 2.10.91.91。另有系统预置 Edge。VLC 弃装（镜像源不可达，11≥10 达标）。

**实现决策及依据**：
1. 虚拟化层 Hyper-V→VirtualBox：负责人 2026-10-25 口头裁决（原计划 Hyper-V 未真正启用——`vmms`/管理栈缺失，环境基线 §1"已开启"记录与实际不符，已在本文件与《环境基线》修正）；VLC→VDI、Optimize-VHD→`modifymedium --compact` 为等价替代，父镜像"更新后压缩、只读基线"意图不变。
2. ISO 来源：sysin→msdl CLI（`winget install starkSV.msdl`，直取微软官方 CDN，绕开其服务器封锁窗口）；负责人百度网盘下载 22H2/24H2 商业版简中 ISO（X23-12741/X23-69833）。
3. 安装方式：VirtualBox unattended install（autounattend 自动装 Pro#3 + 免 MS 账号 + 自动装 GA）；差分机 = `clonevm --options=link`（差分盘等价语义）。
4. WU 排障链（全部记录于 host 侧 stage 目录与 VBox 日志）： guest 内 `tlu.dl.delivery.mp.microsoft.com`（DO 载荷 CDN）不可达 → 注册表 `DODownloadMode=0` 强制直连 `download.windowsupdate.com`（需提权）→ guestcontrol 进程为非提权 token → `Start-Process -Verb RunAs` + 键盘注入应答 UAC（22H2 GUI / 24H2 盲注入）→ wu4.ps1 三轮 search→download→install 双机 ALL_DONE。
5. GT 安装：winget 在 22H2 镜像（v1.2）崩溃（0xC0000005，客户端本体缺陷），改为主机下载官方安装包（URL 取自 acc-24h2 的 winget 日志）+ guest 本地静默装（msiexec /qn、/S、/VERYSILENT）；24H2 镜像 winget 1.7+ 正常，winget 路线装成。
6. 运行纪律：24H2 系 GUI 附加（`--type separate`）会触发 GA 显示驱动挂死（BLKCACHE 之前表现为 heartbeat flatlined），全程 headless；主机自动睡眠（System Idle，Event 42）会同步暂停 VM，已临时置位 SetThreadExecutionState 4 小时并两次救援恢复。

**未尽事项/已知限制**：
- 父镜像 Windows 未激活（实验室豁免；M1 验收不受影响）。
- `judge` 子命令属 T2-02（本 Sprint），R-L1 验证时点引擎为 scan CLI——差分机已验证 scan 可运行，T2-02 交付后在同一环境直接可跑 judge。
- 24H2 差分机 GA 显示驱动与 GUI 附加不兼容（挂死两次），该机永久 headless 运行；M1 在差分机上以 CLI 验收，无需显示。
- H 盘余量紧张（ISO 已删除释放 11GB，当前 ~11GB free；M4 八台差分机扩容前需清理或扩容，见《环境基线》§3 修订）。
- 主机自动睡眠（System Idle）与 VM 并行工作冲突，验收期间建议保持本记录中的睡眠抑制。

**自测输出摘要**：
- 完成标志①：两差分机均 headless 开机并 autologon 成功（guestcontrol 探活通过）。
- 完成标志②：`C:\stage\python-3.13.5\python.exe -m disk_audit scan C:\Users\qa\AppData\Local\Microsoft` 双机 RC=0——22H2 机：906 files/408 dirs、logical 274,231,124B、allocated 275,673,872B、reparse 跳过 22；24H2 机：2268 files/1049 dirs、logical 500,956,217B、allocated 504,125,856B、reparse 跳过 44（`--selftest` 6/6 双机通过，见安装期验证）。
- 完成标志③：软件清单见上表，双机目录级 census 已核（Program Files / AppData\Local / AppData\Roaming 落位与清单一致）。

## M1 五条闸门验收清单（Sprint 2 末，PM 主持）

| # | 闸门（方案第七节） | 现状 → 目标 | 验收方式 |
| --- | --- | --- | --- |
| ① | 容量偏差 <1%（占用空间口径） | 三目录 0.091%/0.026%/0.000% 已达 → VM 上复测 | VM 差分机跑 `--baseline`（新建 VM 侧基准） |
| ② | 自动归属率 ≥70%（VM ground truth） | 待 T2-02/03 → VM 实测 | 差分机软件清单为分母，按 9.2 口径统计 |
| ③ | 硬保护规则 pytest 覆盖 100% | 已达（Sprint 0 起） | CI + coverage 核对 |
| ④ | 引擎层可独立 CLI 调用、零 UI 依赖 | T2-02 交付 → VM 验证 | VM 上 scan/judge 全流程 |
| ⑤ | CI 的 tkinter 断言与 --selftest 门禁生效 | 已达 + 门禁④修复绿 | CI 记录 |

过闸后回填方案第六节"容量偏差"实测列，M1 关闭，进入 M2（S3~S4：启动器与报告 UI、提权闭环）。
