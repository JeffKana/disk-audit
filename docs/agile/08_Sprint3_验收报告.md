# Sprint 3 验收报告（项目经理 · 2026-11-01 起，随波次追加）

按《[交付与验收流程](../governance/交付与验收流程.md)》§3 + accept-verify SOP 执行。Wave 1（T2-08 / T2-09 / T3-02 / T3-04）已验收并合入；Wave 2 待分发。本文档随 Sprint 3 推进追加，终章在 Sprint 末。

## 1. Wave 1 逐卡结论总表

| 卡 | PR | 范围 | PM 实证 | 结论 |
| --- | --- | --- | --- | --- |
| T2-08 选项 c 四段分流 | #32 | scanner +32/-20、tests +58、probe +19、卡记录 | 四段实现与裁决节逐条一致；**PM 复测：夹具 0.000%、三目录基准 0.088%/0.345%/0.000% 全 <1%**（Programs 0.848%→0.088% 如预测收敛）；本地 218 passed + 远端 CI 绿 | **有条件通过，已合入**（条件=§2 裁决：DR-004 实测规模更正 + T3-09 优化卡） |
| T2-09 VM 归属率实测 | #35 | 纯留档：22 文件（扫描/判定 JSON、9.2 口径脚本、命令日志、GT 核对 dump） | **acc-22h2 96.15%（125/130）、acc-24h2 95.45%（105/110）**；GT 11 件逐一核对 **误判 0**；方法学完整（headless 纪律、UTF-8 双保险、凭据不落盘）；本地 215 passed + CI 绿 | **通过，已合入**（M1 终判见 §4） |
| T3-02 F2 报告渲染 | #34 | render.py 352 行 + texts +98 + CLI +50 + tests 415 | 零外部引用为**结构性断言**（test_zero_external_references）；四区顺序、受保护/低置信无任何按钮、incomplete 徽标且无汇总区、Q3 禁词、文案零硬编码（取 texts.py）；解突后 264 passed | **通过，已合入** |
| T3-04 G1 范围界面 | #33 | launcher.py 335 行（根目录，UI 层）+ tests 245 + 截图证据 | build 22621 检测与盘型枚举**全可注入**（边界值测试齐）；四预设按方案顺序；不支持时永不弹窗；launcher 在包外不破门禁④ | **通过，已合入** |

## 2. 裁决一：T2-08 验收③ 耗时增量超标（执行侧红线二上报，数据齐备）

**事实**：Roaming 同进程 A/B 交替实测（monkeypatch 模拟旧三段，排除负载漂移）——旧 2.81~2.89s → 新 4.77~4.87s，**增量 +1.9~2.0s**，超卡面 ≤0.5s；根因为裁决节"Local 该段 ~12k 文件、仅增 ~0.4s"的估算**差一个数量级**（601B~4095B 段实测：Roaming 67,035 / Local 163,238 个文件）。Local 改后 9.5s，AppData 合计 ~14.4s（仍为原全句柄 25.3s 的 1.75× 加速，超 6s 预算 2.4×）。

**裁定：选项 a + b 组合**：
- **a（采纳，PM 执行）**：DR-004 裁决节追加"实测规模更正"——③段规模数字按实测更正，①量级判定重述为"**R1 止损线（任一目标机全盘 > 60s）远未触发；双口径正确性优先的产品决策不变**"。验收标准③的"≤0.5s"按红线二不予改动，判定记录为"未达，经裁决转量级口径"。
- **b（采纳，立卡 T3-09）**：段③批查取数优化（FileIdExtdDirectoryInfo 方向——单次目录调用带回整目录 AllocationSize），P2，排 S4~S5 非阻塞。理由：月度/季度体检定位下 14.4s 可接受；R1 不触发；但 163k 次句柄开销是已知量级，值得收回。
- **c（否决）**：回退段③为推算=接受已知系统性偏差，违反 DR-004 开篇"正确性无争议"立身标准。

## 3. 裁决二与三：两个既有问题（执行侧按红线记未尽事项，未顺手修——处置正确）

| # | 问题 | 定级 | 裁定 |
| --- | --- | --- | --- |
| 1 | **judge.py:358 schema 枚举漏洞**（T3-02 发现）：知识库"已停止"高档残留分支输出 `verdict_source="进程服务"`，不在定稿 schema 九值枚举内——端到端夹具恰好未触达该分支故 CI 未拦，**真实扫描命中即产出非法报告** | **P1** | **立卡 T3-07（热修，Wave 2 首发）**：verdict_source 修正为语义正确层（该判定源于知识库生命周期标注，应为"知识库"）+ 端到端夹具补"已停止"分支覆盖 + 修后真实输出必须过定稿 schema 校验。修前 F2 渲染入口对非法 source 的行为由 T3-07 一并明确（拒绝并披露优于静默渲染） |
| 2 | **X-2 边界**（T2-09 发现）：`_expand_dir`/`_scan_tree` 枚举段不在 X-1 捕获区，VM 开机后 AppX 实时增删目录致首轮 4/4 扫描走"不完整"出口（弃用重跑后正常）——X-2 防半成品设计实证有效 | **P2** | **立卡 T3-08（Wave 2）**：枚举段 OSError 折入 X-1 跳过+计数+继续；X-2 保留给真实中止/致命异常。不阻塞（重跑即恢复，且有"不完整"兜底） |

## 4. M1 终判（五闸门，方案第七节口径）—— ✅ **M1 正式关闭**

| # | 闸门 | 判定 | 证据 |
| --- | --- | --- | --- |
| ① | 容量偏差 <1% | ✅ | PM 复测三目录 **0.088% / 0.345% / 0.000%**（四段分流后）；夹具 0.000%。VM 侧复测（T2-09 子项③）随 #32 合入已解锁，作为证据加固补跑（非闸门条件——9.2 口径即本机 vs 资源管理器） |
| ② | 自动归属率 ≥70%（VM GT） | ✅ | **96.15% / 95.45%**（acc 双机，2026-11-01；非自指——VM 为全新环境，GT 11 件为预装清单）；**GT 误判 0**。诚实注记：出厂 VM 单元构成以 Appx 注册为主（22h2 的 124 个 Local 单元中 103 个由 Appx 证据命中），M4 八台真实软件组合矩阵（装 N 卸 M）是更严的考验——75% 闸与高置信误判 0 在 M4 |
| ③ | 硬保护 pytest 覆盖 100% | ✅ | 自 Sprint 0 未改动；27 用例矩阵；全量 264 passed |
| ④ | 引擎独立 CLI、零 UI 依赖 | ✅ | scan/judge 双子命令 + launcher 在包外；门禁④ exit=0 |
| ⑤ | CI tkinter 断言 + --selftest 门禁 | ✅ | 四分支 CI 全绿；main 合入后全量绿 |

**回填**：方案第六节"容量口径偏差"与"自动归属率"实测列已更新（本分支）；W9 检查点（归属率 <70% 收缩范围）**解除**。M1 关闭，项目进入 M2（S4 收口：提权闭环）。

## 5. PM 独立抽查汇总

- #32：夹具 0.000% + 三目录 0.088/0.345/0.000（与执行记录互证）；四段代码逐条对裁决节。
- #35：留档含完整命令链、凭据不落盘声明、首掌 X-2 事件如实弃用留档——证据链质量为历次最佳。
- #34/#33：解突后全量 264 passed（render/launcher/wording 三套断言齐过，append-only 无内容损失）。

## 6. 合入记录（DR-006，PM 执行）

| 序 | PR | 方式 | main 落点 |
| --- | --- | --- | --- |
| 1 | #32（T2-08） | merge commit | c5e1e1d |
| 2 | #33（G1） | merge commit | d759de2 |
| 3 | #34（F2） | **PM 本地解突**（texts.py 文末双追加，append-only 保留双方区块，264 passed 验证后 push）→ PR merge | 7ebeca3 |
| 4 | #35（T2-09 留档） | merge commit | fd62948 |

合入后 main：**264 passed + selftest 6/6 + 门禁④ exit=0**。

## 7. Wave 2 分发（验收后即可领卡）

| 顺序 | 卡 | 说明 |
| --- | --- | --- |
| 首发 | **T3-07（新，P1 热修）** | judge.py:358 枚举修正 + 分支覆盖（§3 裁决 1） |
| 并行 | T3-01（栈 T2-08 ✅已合）、T3-03（栈 T3-02 ✅已合）、T3-05（双栈 T3-01+04）、T3-06（双栈 T3-02+04） | 原 Wave 2 栈依赖已全部就绪 |
| 排期 | T3-08（P2，X-1 边界）、T3-09（P2，段③批查优化） | S4~S5 非阻塞 |

**负责人动作**：T2-09 子项③（VM 容量偏差复测）已随 #32 合入解锁——与执行侧按 vm-ops 技能补跑一次 acc 双机 `--baseline`（基准登记物需在 VM 内重建或比对宿主登记值），结果并入闸门①证据归档。

### T3-07 执行记录（2026-11-01）

**做了什么**：按 §3 裁决 1 完成 judge 枚举漏洞热修三件套——① 修正 KB"已停止"残留分支证据链来源：`disk_audit/engine/judge.py` `_judge_kb_hit` 中 `EvidenceItem("进程服务", "无匹配进程/服务/自启动")` 改为 `EvidenceItem("知识库", …)`（"进程服务"不在定稿 schema 九值枚举，该缺席核验源于知识库生命周期标注）；② 端到端夹具补"已停止"高档残留分支覆盖：`tests/test_engine_judge.py::_scan_fixture` 增 oldapp（KB 生命周期"已停止" + 目录/文件 utime 回拨 400 天触发高档），`tests/test_engine_render.py::test_judge_real_pipeline_output_renders` 夹具同步增该单元；③ 新增断言：KB"已停止"分支 judge 真实输出 dict 必须过 `tests/_mini_schema.py` 定稿 schema 校验（`test_judge_report_stopped_branch_passes_schema`）+ 证据链 source 逐条落在 schema 九值枚举内（`test_stopped_residual_chain_sources_in_schema_enum`）。渲染入口按裁决改"拒绝并披露"：`disk_audit/engine/render.py::_validate` 对证据链 source 不在九值枚举的输入抛 ValueError 拒绝渲染（枚举常量 `EVIDENCE_SOURCE_ENUM` 进 `disk_audit/engine/texts.py` 文末 append-only 区块，异常文案 `RENDER_ERR_BAD_EVIDENCE_SOURCE` 含非法值与合法枚举提示）；T3-02 的 `test_evidence_source_out_of_enum_still_renders` 改写为 `test_evidence_source_out_of_enum_rejected`（拒绝语义），另增 `test_evidence_source_enum_matches_schema` 防 texts 枚举与 schema 漂移。

**实现决策及依据**：
1. **缺陷位置裁定为证据链 `evidence_chain[].source` 而非 `verdict_source` 字段**：裁定文写 `verdict_source="进程服务"`，但 ① 其引用的九值枚举（硬保护/知识库/注册表卸载项/进程/服务/自启动/Appx/启发式/文件枚举）经对 `docs/schemas/report-v1.schema.json` 核实是 `evidence_chain[].source` 的枚举（`verdict_source` 为六值枚举且"进程服务"在列）；② `git log --follow` 核实该分支自 D1 首版（442befc）起 `verdict_source` 恒为合法的"知识库"，从不产出"进程服务"；③ T3-02 执行记录记 :217 即该 EvidenceItem 行（卡面注明行号漂移以 grep 为准，grep 现指 :217）。修复对象为 :217 证据链 source——这是唯一使"修后真实输出必须过定稿 schema 校验"可成立的解释。分支 `verdict_source="知识库"` 本已合法，不动。
2. **KB"已停止"但不够陈旧（中档）子分支同链同修**：非法 source 位于高/中档共享的 chain 构造段，一处修正两分支同时合法（属同分支内修复，非扩范围）。
3. **渲染拒绝的校验粒度**：仅对"item 为 dict 且含 source 键且值不在九值枚举"拒绝（卡面明确"只动 source 校验，不扩范围"）；非 dict 项/缺 source 项维持既有宽松展示行为不动。
4. **枚举常量放 texts.py 而非 render.py**：render.py 有 AST 守卫禁止中文散落字面量（tests/test_engine_render.py::test_no_chinese_literals_in_renderer_module），九值为中文必入文案资源；配防漂移断言锁定与 schema 逐字一致。
5. **T3-02 用例改拒绝语义**：卡面明示"这是裁决对本卡的要求，属修正 T3-02 防御行为，不是删用例换绿灯"；PR 描述中说明依据。

**未尽事项/已知限制**：
- `tests/test_engine_units.py:4` docstring 存在既有 SyntaxWarning（invalid escape sequence `\P`），非本卡引入、不影响判定，未顺手修（红线五，可另立 chore 卡）。
- 渲染入口对缺 source 键/非 dict 证据项仍宽松展示（与 schema required 不完全对齐）——按卡面"只动 source 校验"未扩，如需收紧另立任务。

**自测输出摘要**：`python -m pytest` 裸跑 **267 passed**（基线 264 + 净增 3：分支 source 枚举断言 / e2e schema 校验 / 枚举防漂移；T3-02 用例改名不改数），1 个既有 SyntaxWarning 与本次改动无关；`python -m disk_audit --selftest` **6/6 passed**（exit=0）。测试先行实证：修复前新增用例 5 红（schema 报 `evidence_chain[3].source：'进程服务' 不在枚举`），修复后全绿。

## 8. Sprint 3 进度数据（中期）

- Wave 1 完成 4/8（T2-08/T2-09/T3-02/T3-04），100% 通过（1 有条件）；退回 0；**新增卡 3 张**（T3-07/08/09，两项为既有缺陷）。
- 测试 215 → 264（+49）；CI：四分支全绿，main 合入后全量绿；texts.py 首现并行解突（append-only 纪律有效）。
- 风险看板：R1 关闭在即（T2-08 落地 + T3-09 优化跟进）；**R5 关注**——judge 枚举漏洞若未在 F2 渲染前修复可能产出误导性报告，T3-07 已定 P1 首发。
