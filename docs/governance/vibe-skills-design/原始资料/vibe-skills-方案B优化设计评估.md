# vibe-skills 方案 B 优化设计与 GitHub 同类方案评估

> **前置声明（不计入四部分）**
> 1. 本报告为**目标态（to-be）设计提案**。现有 8 个文件（README.md、6 个 SKILL.md、references/模板库.md，共 619 行）**全部保持原样，未做任何修改**；下文所有「应改为／目标设计中」均指后续采纳实施时的处置，不代表已生效。
> 2. 全文**不提供代码片段、不提供操作教程**：frontmatter 字段以要点描述、状态机以迁移表描述、校验脚本只写「检查什么／输出什么／谁触发」，不写实现与命令。
> 3. **数据口径**：两路调研给出的 star 数据存在分歧，统一以 **GitHub REST API 2026-11-10 一手快照**为准，早期搜索结果与第三方观测值不再采用（详见第三部分「数据裁决」）。未能一手核验的条目均单独标注。
> 4. **总体定性：自研规范层重构，不是合规整改，也不是「本套已完全合规」**。统一表述（判定层四轮校准后的单一口径）：「**不存在可机械判定的官方违规；剩余问题全部落在官方规范未覆盖或明文不强制的自研层，故方案 B 的性质是自研规范层重构，而非合规整改／合规修补**」。官方可机械判定的硬约束仅 4 项（SKILL.md 存在、frontmatter 在开头、name 必填且匹配目录名、description 必填非空 1–1024 字符），本套 6 个文件 **6/6 全部通过**；**判定分级表 B 类（明确不合规）= 0 条 / 零命中**。成立原因是「官方管辖面极窄 + 本套采用规范未覆盖的自研结构」，**不是「本套写得完美」／「本套完全合规」**。方案 B 的靶心因此是**自研约定与内部一致性**，不是格式合规。
> 5. **三轴分离**：① 官方规范符合度；② 自研治理缺口（方案 B 的真正靶心）；③ 内部一致性／可维护性。方案 B 的「统一命名／消除悬空／SSOT 与单写者／职责边界」中，仅「消除悬空引用」的**事实层**部分与轴①相关，其余绝大多数落在轴②③。**不可拿官方规范去评判自研约定**（详见 1.1.1 判定分级与三条防误判红线）。
> 6. **包级共享结构约定**：本套 `vibe-skills/references/模板库.md` 位于 6 个技能目录**之外**，属**包级共享资产层**；官方目录模型只描述「每技能目录内含自己的 `references/`」，**未覆盖这一层**。因此所有引用的解析基准须由「技能根」显式改为「**包根**」，这是自研结构约定（规范不禁止但未覆盖），归入轴②。不得为贴合官方把模板复制进各技能目录——那会制造 6 份副本，正是 SSOT 的反面。

---

# 一、优化后的设计说明

## 1.0 口径声明：as-is / to-be 与 L0 的两条前提

### as-is 与 to-be 必须分开读

| 口径 | 流程技能数 | 文件构成 | 说明 |
| --- | --- | --- | --- |
| **as-is 现状** | 6 个流程技能 + 三角色 | 8 个 md（README + 6 个 SKILL.md + `references/模板库.md`，619 行） | 第四节现状依据、A~H 多写者冲突、编号-名称别名、`ci-cd-ops:57` 与 `ops-runbook:61` 往验收报告追加、README §三「6 个必选」与 §五 映射表——**全部是 as-is 描述，不作目标态结论** |
| **本报告推荐 to-be** | **仍为 6 个流程技能** | 8 个 md 原样不动（本轮仅出报告）；后续实施时**新增 1 个非技能包级文件** `references/契约字典.md` | 依据 1.3 裁决「推荐不合并」。用户授权「允许合并/拆分」是**授权而非要求**，故本报告的推荐目标态不变 |
| **备选 to-be（方案 B，不默认执行）** | 5 个流程技能（04+05 合并为 platform-guard） | 同上 + L0 | 见 1.3 可选方案 B，仅在 go/no-go 闸门满足时评估 |

**互指边界范式的 as-is 限定**：`ci-cd-ops:55` ↔ `ops-runbook:47` 的双向互指是 **as-is 6 技能态**下全包唯一写好的跨技能边界范式，可作其余技能边界节的 as-is 对照；**若采纳 6→5 合并，这两节变为同一技能内的两节，互指不再是跨技能边界，不能照搬为目标态其余技能的边界模板**，只能作为「技能内分节互指」参考。若采纳 6→5 合并，as-is 清单中带「跨技能」判定的条目在目标态须逐项转述（**as-is 照实写「跨技能」，目标态写「同技能内」，两者不可混**）：① 该互指改称「**同一技能内步骤/边界分节的清晰范例**」；② `04-ci-cd-ops` / `05-ops-runbook` 两个编号-名称别名及四处互引（`ci-cd-ops:55/:77`、`ops-runbook:47/:88`）变**内部引用**；③ README:43-44 技能清单两行、§三「6 个必选」、§五 映射表（本就漏 `project-bootstrap`）随 5 技能调整；④ **F 类冲突不因合并而消失**——`ci-cd-ops:57` 与 `ops-runbook:61` 的非 PM 追加方虽从两处收敛为一处（platform-guard），但「验收报告 PM 单写者 vs 故障态留痕」的冲突仍在，1.4 的「受控 append-only 保留区 + PM 复核 ACK 封存」裁决继续有效。**本报告推荐 to-be 不合并，故上述转述未发生**。

**全篇标注约定**：① **本报告存在两个目标态口径，必须分开**：**推荐 to-be = 6 个流程技能**（依据 1.3 裁决「推荐不合并」）；**备选 to-be = 5 个流程技能**（架构代理方案，04+05 合并，不默认执行，仅在 go/no-go 闸门满足时评估）。凡与「6 个技能 / 8 个 md / 三角色 / `ci-cd-ops`↔`ops-runbook` 跨技能互指 / README §三 6 个必选 / §五 映射表」绑定的描述**一律为 as-is 现状**——在推荐 to-be 下多数仍成立（差别仅在「新增 L0 文件 + 引用基准改为包根 + 单写者收敛」），在备选 to-be 下须按上文「互指边界范式的 as-is 限定」逐项转述为同技能内关系。**不得把 as-is 的 6 技能直接写成任一目标态结论，也不得把两个目标态口径混用**。② **文件名统一**：新增的非技能包级文件统一称 `references/契约字典.md`，正文简称「契约字典」；**「L0 / L1 / L2」仅是层级标签，不是文件名**。③ 本报告的流程图式描述（1.2 层级表、1.3 重组表、1.4 交接矩阵）均以推荐 to-be 的 6 技能为准；若采纳备选 to-be，技能协作关系须按 ① 重述。

### L0 的两条前提（并列，不合并）

**共同基础**：本套**无运行时、由协调角色显式选取技能**。该前提在包内是**隐含未明写**的（佐证：`README:3`「三角色协作的 vibe coding 开发模式」、`README §二` L27-31 角色表、各 SKILL.md:8「使用角色：PM／执行 Agent」）。L0 的两条前提是把这一现状**补齐成显式约定**，不是新增假设。

- **前提 A｜只读共享资产与引用基准**：`references/` 为包级共享资产层，相对路径以包根为基准。**失效条件**：若未来引入遵循官方 `client-implementation` 的自动发现/激活运行时（由 client 负责 discovery / selection / activation，技能被选中后才读取内容），包级共享层无法保证被正确解析，须改为「技能内 `references/`」或增加一层路径映射。**该条件句只放在前提 A 下**。
- **前提 B｜可写状态隔离与交接**：单一写入者、文件级写隔离、交接 ACK、状态字典、本地锚定。**有无运行时都需要**，不随前提 A 的失效与否而变。

两者**不合并**的理由：规范对象不同（静态引用的解析基准 vs 动态并发的隔离边界），结论方向也相反——**只读资产中心化共享，可写状态分散隔离**。

**与校验脚本的相容性（只对应前提 A）**：本轮允许的离线只读静态校验器（不接入 CI / 不写回 / 不阻塞 / 不调度）**不做 discovery/activation、不解析技能引用**，因此**不触发前提 A 的失效条件**，包根基准保持不变。**此判断不适用于前提 B**——前提 B 本就「有无运行时都必须满足」，不得据此放宽单一写入者或并发隔离要求。

## 1.1 设计目标与不变量

| 类别 | 内容 | 依据 |
| --- | --- | --- |
| 必须保留的核心用途 | 立项治理初始化（先治理后编码）、Sprint 规划与任务卡、任务卡执行、交付验收三选一、CI/CD 门禁管护、平台与环境故障运行手册 | 6 个 SKILL.md 各自「目标」节、README §三 |
| 高可信、慎改 | 验收七步、DoR、九条红线、防死胡同四条、故障分级与事实回填义务 | README §七（40+ PR 反复运行 / 真实事故驱动） |
| 需在目标项目校准 | 门禁分阶段的节奏、可选技能自建判据 | README §七 |
| 本轮不触及 | 00→01→02→03 阶段划分、三角色分权、合入分权 DR-006、git 分支/PR/CI 门禁链 | 属 40+ PR 实证资产，且外部同类项目普遍缺 CI/CD 与故障独立阶段 |

**关键口径修正（分三层，缺一即误判）**：上一轮评估称「PM 单点」，经复核——① **验收判定层**：PM 是单点（README:30、accept-verify:8）；② **制品写入层**：**不成立**，至少 8 处由不同角色写同一制品（见 1.4 A~H）；③ **合入层**：也**不是纯 PM 单点**，按 DR-006 分权（README:33）——执行侧 PR 由 PM 验收通过后合入，PM 自己产出的 PR 交负责人把关，负责人越序合入须留「显式委托/自行把关」标注，发布终审归负责人。因此方案 B 的准确表述应为：**PM 是验收判定单点；合入按 DR-006 分权；制品写入当前为多写者，需确立单写者**。若把「PM 单点」当成既成事实，「确立单写者」这一步会失去靶心。

### 1.1.1 判定分级与防误判红线（三轴落地）

| 类别 | 判定 | 本套对应发现 |
| --- | --- | --- |
| **A 已合规（4 项硬约束，6/6 通过）** | 官方范畴，可机械判定 | SKILL.md 存在；frontmatter 在文件开头；`name` 必填且与父目录名一致；`description` 必填非空、1–1024 字符。README.md / 模板库.md 无 frontmatter（非 SKILL.md 入口，正常） |
| **A′ 符合推荐（Should / recommendations，非硬约束）** | 官方范畴但**不可**机械判定，不得与 A 混标 | `description` 的 what + when（Should）；正文 56–89 行（<500 行建议）；目录约定、文件引用一层深度（建议） |
| **B 明确不合规（可机械判定）** | **0 条 / 零命中** | 不写「0~1 条」「仅结构性不适用」等模糊表述；见下方「口径调和」 |
| **C 自研治理缺口（轴②，方案 B 靶心）** | 官方**无对应条款**，不违规 | 重复定义口径冲突、合入分权 SSOT 错位、00–05 代号与复合别名无唯一映射、《交付与验收流程》及 `R-M 类验收卡` 术语无权威定义点、**包级共享层的包根基准未声明**、`02-task-exec` 等引用了不存在的技能标识符 |
| **D 引用完整性缺陷（事实层，与合规判定无关）** | 在任何基准下都成立的硬缺陷 | `治理文档骨架.md` 目标实体不存在（改名未同步）、`rules-map` 悬空且两套写法、`README:45` 与 `:49` 迁移指南矛盾 |
| **E 内部一致性／可维护性（轴③）** | **明确不违反官方规范**（#body-content「正文无格式限制」） | 章节结构不统一（独有节、`###` 混用、§五映射表漏 `project-bootstrap`）、description 残留项目名与结构不齐 |
| **F 非硬约束可改进（社区/最佳实践）** | Should / recommendations，非违规 | 5 个 description 的「覆盖：…」章节枚举有 Description Trap 倾向、6 个 description 无 differentiator、中文非祈使式、无 should-trigger 查询集、正文无显式 validation loop / Gotchas |

**口径调和（四方交叉确认后的 V2 定稿口径）**：早期曾把「文件路径引用（含 `../`、跨目录、目标无实体、写法不一）」整体判为 B 类，与「包级共享层不在官方模型内」相冲突。调和后的口径为——(a) **路径写法基准／结构层**：包级共享层不违规，归 C 类自研结构约定缺失；(b) **实体存在与写法统一**：归 D 类「引用完整性缺陷」，单独列出，不写「违反官方规范」；(c) 官方 `#file-references` 的适用域**收窄为「官方模型覆盖的技能内文件引用」**，本套相关条目落在适用域外；据此 **B 类 = 0 条**，报告不硬造 B 类条目。

**三条限定（防止审阅挑刺）**：① `#file-references` 官方原文仅约束**写法三条**（相对路径、相对技能根、一层深度），**不声明路径目标实体存在、不约束「不可协商／唯一事实源」类绝对方针，也无「每个技能目录必须自带 `references/`」的条款**；② 第三部分「包级共享层不在官方模型内」的精确依据是「**没有任何一处引用真正指向某技能目录内的实体文件**」，而非「引用写法违规」；③ 两轴（官方符合度／自研扩展质量）在本报告扩为三轴后，须加注「**以上 Axis-2/Axis-3 均为社区／外部项目约定或本套自研约定，仅作机制类比，不作官方规范依据**」。

**三条防误判红线（写入方案 B 约束）**：
1. **不得**把「缺 SSOT／权威定义点」「章节结构不统一」「合入分权 SSOT 错位」判成官方规范违规——它们是自研工程约定缺失，按「清晰／可执行／无歧义」评估；尤其不得把「统一章节模板」误当合规要求。
2. **不得**把「无 `version`」当缺陷、**不得新造顶层字段**——官方为可选字段，如需版本／成熟度追踪应走 `metadata` 自定义键；README／模板库无 frontmatter 也正常。
3. **不得**把 00–05 数字代号判成 `name` 违规——6 个 `name` 字段本身全部合规，问题在跨文件引用层；数字代号归「允许的人类展示索引」，**禁止用于跨文件引用或作唯一标识**。

**严格程度说明**：`description` 的 what/when 是 **Should**、正文 <500 行与目录约定是 **recommendations**、规范附带的校验工具只校验 frontmatter 与命名约定。因此本报告的「应改为」一律是自研工程建议，不是合规要求。

## 1.2 层级关系（按引用方向形成 DAG，非僵硬堆叠）

| 层 | 组成 | 职责 | 引用规则 |
| --- | --- | --- | --- |
| **L0 契约权威层** | 新增一个**非技能**包级文件 `references/契约字典.md` | 唯一权威定义（SSOT）：红线全集、安全底线、红灯分类、数据裁决留痕格式、合入分权、状态字典与合法迁移、DoR/DoD、命名总表、单写者注册表、权威定义点索引 | 自身不引用任何技能；被所有技能/模板/README **只读**引用 |
| **L1 流程技能层** | 6 个 SKILL.md，分三组：立项组（project-bootstrap）／迭代循环组（plan-cards → exec-sop → accept-verify）／横切保障组（ci-cd-ops、ops-runbook） | 各阶段 SOP 与交接 | 只能单向指向 L0/L2；组内按流水线单向交棒；同层间仅允许「边界节」双向互指 |
| **L2 包级共享资产层（自研结构）** | README.md（降为包索引 + 迁移指南 + 成熟度声明，不再承载规则正文）、references/模板库.md（四模板 + 状态台账 + 条件项跟踪表） | 索引、模板、制品 schema | **位于 6 个技能目录之外，引用以「包根」为解析基准**；只读引用 L0；不定义流程规则；不被流水线写入 |

**引用硬规则**：① 任何规则/定义/枚举只允许在 L0 出现一次（权威定义点 ADP），他处一律「见 契约字典 §X」指针，不复制正文；② 禁止循环，唯一的迭代回边是 accept-verify → plan-cards 的「下一 Sprint 触发」，须显式标注为迭代边界而非同实例依赖；③ 交棒只写「交棒对象 + 交接制品 + 状态迁移 + ACK」，不写对方怎么做；④ L0 的变更只能走包级 DR 由负责人批准（SSOT 保护）；⑤ 引用保持一层深度；⑥ **在 L0 显式声明「`references/` 为包级共享资产层、所有相对路径以包根为基准、统一写法指向 `references/模板库.md#模板 N`」**，消除 `exec-sop/rules-map` 与 `环境基线/rules-map` 两套写法。

**结构性取舍（必须写明）**：官方目录模型隐含「技能自包含」（每技能带自己的 `references/`），而本套 SOP 的核心诉求是「跨技能 SSOT／单一定义点」，两者**结构性冲突**。方案 B 显式选择「**包级共享 + 包根基准**」，放弃贴合官方目录结构；因为把 4 个模板复制进 6 个技能各自目录会产生 6 份副本，直接加剧已发现的重复定义与缺 SSOT。该取舍属轴②自研约定，不违规。

**为何这样分层**：现状的重复定义源于「定义者同时是消费者」——`exec-sop` 定义九条红线、`plan-cards` 又复述五条，`ci-cd-ops` 定义四类红灯、`plan-cards` 又列三类。把声明性契约上收到一个只读的 L0，可使「权威定义只读、无人可就地放大」成立，同时不新增任何运行时能力。

## 1.3 技能重组裁决（含与架构代理方案的分歧处理）

用户本轮授权「允许合并或拆分技能」。经对两路结论的实证比对，给出如下裁决：

| 议题 | 裁决 | 依据 |
| --- | --- | --- |
| **是否合并 ci-cd-ops + ops-runbook 为 platform-guard** | **推荐不合并（默认）**；列为可选方案 B 并附触发条件 | 架构代理原以「双向引用构成潜在循环」为合并理由，**该理由已由本地审计实证后主动撤回**：`ci-cd-ops:55`（推操作步骤）↔ `ops-runbook:47`（推合规边界）是「步骤 vs 边界」的**互补分工**，是包内唯一清晰的边界范式，不是同一事实循环定义，判成循环会误删。真正的问题是 **SSOT 权威点标记缺失**（「应急合入」主题在 `ci-cd-ops §5`、`ops-runbook §3`+`§76`、`accept-verify:76` 三处声明却无一处标权威点）。此外 `README §七` 把故障运行手册列为高可信资产，合并会稀释其「事实回填义务」（`ops-runbook:70`「排障不回填 = 故障必然重演」）。正确做法是**保留互指、显式指定 `ci-cd-ops §5` 为合规边界权威点**，其余改为引用 |
| **是否拆分 references 新增契约字典** | **采纳**（拆出的是非技能文件，不改变技能数量） | 方案 B 的状态字典/SSOT/认领 ACK/统一命名/权威定义均为跨阶段、被所有技能只读引用的声明性契约，塞进任一阶段技能会造成「定义者同时是消费者」矛盾 |
| **6 个阶段技能数量** | **保持 6 个** | 6 个环节对应 40+ PR 实证链、README §三 必选清单与 §四 三步迁移；改数量会切断实证与迁移路径 |
| **必须裁决的现有职责重叠** | 首个 Sprint 任务卡包**统一由 plan-cards 产出**，bootstrap 只产出治理文档链与输入 | `project-bootstrap:29`「交 01-plan-cards 或由本技能内联产出」存在二义 |
| **可选方案 B（不默认执行）** | 合并为 platform-guard（门禁态／故障态两模式，用「模式 × 角色」矩阵切分双角色未细分问题）+ 拆 accept-verify 的「里程碑闸门 + 防死胡同」为独立闸门技能 | 触发条件：**并发 Agent ≥4 且裁决积压成为主要停滞**；否则不拆，避免破坏 §三/§五/§四。若采用，须同时把三处「应急合入」声明收敛为内部单一权威点 |

### 核心用途保留逐项对照（用户明确要求）

| 原技能 | 核心用途 | 目标归属 | 保留方式 | 影响的 README 章节 |
| --- | --- | --- | --- | --- |
| project-bootstrap | 基线确认、范围冻结、治理文档链、CI/CD 规范、工程骨架、首 Sprint 计划 | 保留（立项组） | 6 类产出原样；仅移除「首个 Sprint 卡包内联产出」二义 | §三、§五（需补缺失的映射行） |
| plan-cards | 收数/对表/排程/成卡/报批、DoR 自查、并行与栈式依赖 | 保留（迭代循环组） | 步骤原样；通用红线与红灯分类改指针；description 剔除项目名并补齐「覆盖：」段 | §二、§三 |
| exec-sop | 九步执行、测试先行、纯函数+注入、自测、执行记录、九条红线、退回处理 | 保留（迭代循环组） | 步骤与九条红线原样保留为**唯一权威**并上收 L0，技能内留指针；**name 字段不动** | §二、§三 |
| accept-verify | 七步验收、三选一结论、证据采集、防死胡同、里程碑闸门 | 保留（迭代循环组） | 全部原样；定义类内容上收 L0 后改指针；description 剔除「M1 五闸」；`:76` 的应急通道声明移出「项目参数定制位」 | §二、§三 |
| ci-cd-ops | 分阶段门禁 A~D、触发/合入矩阵、红灯诊断分类、CD 四原则、应急合入合规边界 | 保留（横切保障组） | 原样；**指定 §5 为合规边界权威点**；§3 四类红灯分类升为权威 | §二、§三 |
| ops-runbook | 故障分级 L1~L5、通道降级链、Git Data API 应急合入、树哈希终验、事实登记义务 | 保留（横切保障组） | 原样，含 §五 明确「保留为示例条目」的 Windows/MSYS 坑；回填落点由 L0 的 SSOT 注册表唯一指定 | §二、§三、§五 |
| references/模板库.md | 四模板（任务卡/验收报告/DR/治理骨架） | 保留 + 新增契约字典.md | 四模板原样；模板内嵌的「通用红线/DoR/§x 引用」改指针；补状态台账与条件项跟踪表；**须补迁移说明** | §三、§四 |

## 1.4 职责边界矩阵与八类单写者冲突裁决

### 主矩阵（writes = 唯一写入；reads = 只读依赖）

> **标注**：本矩阵是**推荐 to-be 的目标态设计，不是 as-is 现状描述**，且**尚未落地**（本轮仅出报告）；as-is 现状见下方「八类单写者冲突逐条裁决」所引的原始行号。矩阵中的 6 个技能对应推荐 to-be（保持 6 技能）；若采纳备选 6→5 合并，按 1.0「互指边界范式的 as-is 限定」转述。

| 技能 | 唯一写入的制品（SSOT 归属） | 只读依赖 | 明确不做什么 | 交接点 |
| --- | --- | --- | --- | --- |
| project-bootstrap | 方案基线结论、敏捷三件套、治理文档链、CI/CD 规范初版、工程骨架（仅首 Sprint 前一次性） | 立项材料、环境事实、L0、模板四 | 不介入日常迭代；不内联产出首 Sprint 卡包；不写验收/回归/风险结论 | → plan-cards（治理链 + 卡包输入） |
| plan-cards | Sprint 计划与任务卡.md、产品待办列表状态列、Sprint 总览行、风险登记册 | 上轮验收报告、待办列表、里程碑口径、L0、模板一 | 不写验收结论、实测数据、回归集、环境基线；不改他技能规则 | → exec-sop（发卡） |
| exec-sop | 任务分支、PR、PR 描述、任务卡内「执行记录四项」预留区、本卡范围内代码/测试/文档 | 任务卡、治理文档链、依赖模块、L0 | 不改验收标准；不写验收报告/待办状态/回归集/环境基线；不自行发明应急通道；不改 workflow | → accept-verify（提 PR）；冲突按 L0 §冲突受理 上报 |
| accept-verify | Sprint 验收报告.md（逐卡结论/退回单/条件项/裁决/合入清单/评审数据/里程碑判定）、方案「实测」列、回归集 | PR/分支清单、卡面验收标准、CI 记录、执行记录、L0、模板二 | 不直接回填待办列表（只产出「状态变更建议」）；不写任务卡/环境基线；不改门禁设计 | → plan-cards（下阶段输入）；→ ops-runbook（应急合入前置=内容已验收） |
| ci-cd-ops | CI/CD 规范文档、红灯诊断结论、分支保护配置清单、workflow 变更（走 PR） | 仓库现状、里程碑计划、L0 | 不做故障通道降级；不写验收报告；不绕过 CI 改 main | → ops-runbook（合规边界，互指） |
| ops-runbook | 故障分级结论、通道选择记录、**环境基线.md 变更记录（环境事实唯一落点）**、验收报告的「受控保留子区块」 | 故障现象、L0、ci-cd-ops §5 | 不设计门禁；不写待办/验收结论（受控保留区除外）；不越过已验收前置做应急合入 | → accept-verify（合入后状态回填）；→ 全员（事实回填义务） |
| L0 的 `契约字典.md` / L2 的 `模板库.md` 与 `README.md` | 自身（仅包维护者按 DR 追加） | L0（后两者） | 不存运行时状态、不广播、不调度；不定义流程规则（L2） | 被全部技能只读引用 |

### 八类单写者冲突逐条裁决

统一原则：**一个事实 = 一个 SSOT = 一个单写者，其余一律指针 + 快照版本，不各自回填**。

| 编号 | 冲突 | 裁决 |
| --- | --- | --- |
| A | 待办/卡状态：plan-cards:25 vs accept-verify:25/50/56 | **plan-cards 唯一写**；accept-verify 只产出「状态变更建议」，由 plan-cards 在收数时一次性回填 |
| B | 方案「实测」列：bootstrap:44 建 vs accept-verify 填 | bootstrap 只建列（结构），**accept-verify 唯一填值** |
| C | **回归集：exec-sop:56（执行 Agent 写）vs accept-verify:50（PM 写）** | **accept-verify 唯一写**。理由：缺陷须经 PM 判定/复现确认才成立，回归集是验收资产。exec-sop 只在执行记录写「回归增补建议（根因 + 禁词断言）」；accept-verify 七步第 3 步审核后写入并递增版本；plan-cards:29 只读增量；模板库:98「回归集回灌」改为指向 L0 §SSOT 注册表，不定义为写动作。**代价**：PM 成写入瓶颈，以「≤1 工作窗口」时限补偿原有「当天回灌」时效 |
| D | 环境事实：ops-runbook:22/61/70（全体）vs accept-verify:50（PM），且落点三套名称 | **ops-runbook 唯一写《环境基线》变更记录表**。理由：环境事实由排障实证产生，故障态是唯一具备「现象→根因→修复」完整证据链的环节。其余 4 处（accept-verify:50、exec-sop:64、README:68、模板库:104）由「回填」改为「按 SSOT 指针引用 + 快照日期」；`ops-runbook:70`「强制回填两处」收敛为「**回填一处 + 本手册加一条现象索引**」；模板库:104 的规则上收 L0；统一制品名（消除「风险登记册/风险看板」类命名不一） |
| E | 决策记录 DR：被 4 个技能多角色写 | 由「发起决策的技能」写入，遵守「登记册统一分配序号、append-only、不得改写已有 DR 正文（只能加取代状态）」 |
| F | **验收报告被非 PM 追加：ci-cd-ops:57、ops-runbook:61** | 验收报告 SSOT 归属不变、**单写者仍 = accept-verify（PM）**；把「合入记录／应急路径合规性」显式登记为**唯一受控 append-only 保留子区块**，写入者仅限故障态，三条件：① 前置 = 该卡已通过验收（不变）；② 区块 schema 固定、只追加、不改写 PM 正文；③ 故障态写入后由 **PM 复核并 ACK 封存**，封存后任何角色不得再改。**备选（不作首选）**：故障态产出独立「应急合入留痕单」自身 SSOT、验收报告只留指针——但需新增制品并改模板二，与「保留核心用途」有张力。另 `accept-verify:76` 把该通道写在「项目参数定制位」属**错置**（它不是项目参数），应移到 L0 §合规边界，定制位只留「是否启用」开关 |
| G | 风险登记册 vs 风险看板 | 统一为单一制品名，plan-cards 唯一写 |
| H | 退回计数：exec-sop:36 vs accept-verify:35/60 | **accept-verify 唯一写并计数**；exec-sop 只记录「收到退回单」事实 |

**统一冲突受理路径**（消除 exec-sop:28 与 accept-verify:80 口径不一）：执行侧冲突 → PM 数据裁决 → 超时按 48h 保守默认 → 负责人以 DR 追认。升级规则沿用「同一卡退回 ≤2 次，第 3 次强制升级」。

**四类停机条件映射到本套既有角色（不新增角色）**（借鉴 superpowers「Rulings, not stalls」，映射到 README §二 三角色分权）：

| 停机条件 | 既有裁决人 | 本套依据 |
| --- | --- | --- |
| 不可逆／破坏性动作 | 负责人审批 | README:29「事故拍板」、治理 §4 不可协商底线 |
| 安全敏感改动 | 负责人／安全口径审批 | README:29「终审」、项目治理 §7 安全底线清单 |
| 工作区外副作用（merge / push / publish） | 负责人（默认 merge 与发布）+ DR-006 合入分权 | README:29、README:33 |
| 计划整体失效 | PM 重新规划／负责人事故拍板 | README:30「Sprint 计划」、README:29 |

**效力层级（补「DR 有载体、无效力层级」缺口）**：借鉴 superpowers 一手表述「The spec is the binding authority, the plan is its argument」「无上游规格时裁决仅临时（provisional）」，目标态在 L0 写明「立项／规划制品 > 执行卡 > 实现决策」；本地实证为全文检索「覆盖／优先／凌驾／高于／为准／override」零命中，即 DR 模板虽完备却未声明效力。

**必须自研的反向证据**：superpowers 全文**没有任何一句**授予任何角色改写 plan 文件的权限，其 controller 只有裁决权、没有写入权——这意味着「三角色权限矩阵 + 单一写入者」在外部方案里**没有现成答案可抄**，1.4 主矩阵与 L0 §SSOT 注册表属本套自研，不能表述为「借鉴自某成熟方案」。

**纯文本并行准入条款（进 L0）**：「无共享状态才允许并行」「不得并行分派多个实现型 Agent 到同一文件」写成规范条款；配套「状态外置到 ledger 文件、每个计划独占目录、上下文压缩后以 ledger 与 git 记录为准而非会话记忆」——纯 Markdown 即可落地，不引入运行时。

## 1.5 命名、结构与复用约束

**唯一规范名** = frontmatter 的 `name`（kebab-case、无编号）。**6 个 `name` 字段本身完全合规，不改**；流水线编号 00–05 与 `00-bootstrap`／`01-plan-cards` 等复合别名**降级**为「README 流水线图的人类展示索引」，**禁止用于跨文件引用或作唯一标识**。经核实，全包 8 处复合别名均为纯代号形式（无 `/`、无 `.md`、无 `skills/` 前缀），属**技能标识符引用**而非文件引用，不套用官方 `#file-references`——因此 `02-task-exec` 的修法是**改引用／建别名映射表，不是给 6 个技能改名**。

### 引用完整性缺陷与自研治理缺口的逐项处置

| 悬空/不一致项 | 位置 | 判定类别 | 处置 | 目标态 |
| --- | --- | --- | --- | --- |
| 《交付与验收流程》§1/§2/§3/§6（6 处） | plan-cards:8、exec-sop:8、accept-verify:8、模板库:12/34、ci-cd-ops:77 | **C 术语/文档名无权威定义点**（非文件路径引用，不违反规范） | 改写为指针 + 删除书名号残留 | 该文档是 disk-audit 先例外部契约、泛化时未随包迁移；§1 DoR→L0 §DoR；§2→L0 §交接与 ACK；§3→accept-verify 核心步骤；§6→plan-cards 核心步骤 |
| `references/治理文档骨架.md` | project-bootstrap:35 | **D 引用完整性缺陷**（目标实体不存在，在任何基准下成立）+ **C 包根基准未声明** | 改写为指针 + 显式声明包根基准 | 实为 `references/模板库.md:85` 模板四，属改名未同步；**不得**把 `../references/…` 表述为「符合官方规范的修正」 |
| `rules-map`（两处写法不一） | 模板库:15、ops-runbook:22 | **D 引用完整性缺陷**（悬空 + `exec-sop/rules-map` 与 `环境基线/rules-map` 两套写法） | 删除或补实体、统一写法 | 无对应制品，概念已被 L0 + 环境基线覆盖 |
| `02-task-exec` | project-bootstrap:59 | **C 自研命名层**（引用不存在的技能标识符；`exec-sop` 的 name 合规） | 改引用为纯 `exec-sop` + 建别名映射表 | 不动 name 字段 |
| `00-bootstrap` 等编号别名 | README:51/72、bootstrap:27/29/37/59、ci-cd-ops:14/55 | **C 自研命名层**（允许展示，禁止跨文件引用） | 改写为规范名 | 统一纯 name |
| `R-M 类验收卡` | README:29 | **C 术语无权威定义点** | 删除或补定义 | 全文无定义，疑为 disk-audit 先例残留 |
| `方案第七节` | plan-cards:20/51、accept-verify:54 | **C 先例节号未抽象** | 改写为指针 | 抽象为「里程碑验收口径文档」 |
| description 残留项目名/先例 | plan-cards:3「磁盘体检项目」、accept-verify:3「如 M1 五闸」 | **E 内部一致性**（由 README:3「与具体项目解耦」**自研声明**判定，非规范违规） | 删除；并补齐 plan-cards 缺失的「覆盖：」段 | frontmatter 常驻层优先清理 |
| 任务卡文件命名三套 | plan-cards:24 / accept-verify:8 / 模板库:111 | **E 内部一致性** | 统一 | 由 L0 命名总表定义唯一格式 |
| README §五 缺 project-bootstrap 行 | README:57-62 | **E 内部一致性** | 补齐 | §三 明列 6 个必选，映射表只有 5 行 + 1 个可选项 |
| **README:45 与 :49 迁移指南矛盾** | README:45 / :49 / :3 | **D 可复现的交付失效（P0）** | **修订迁移指南** | `§三` 把 `references/` 列为 ✅ 必选（第 7 行），`§四` 却只复制「六个技能目录（不含 README 与本层）」——`references/` 是第 7 个目录、属「本层」，被排除在复制范围外；`README:3` 也未提共享层；全包 Grep 确认 README 中 `references/` 仅出现 L45 一次、全包无共享层迁移说明。**按现指南迁移后 4 个模板不会带到目标项目，`project-bootstrap:35` 引用彻底悬空**。这是「包级共享层未写进规范」的直接后果，须与包根基准声明一并修复 |

**模板库「孤儿资产」修复（明确不违规）**：4 个模板在模板库.md:7/29/62/85 **反向标注**了产出物归属，但**没有任何 SKILL.md 正文正向指向它们**（`project-bootstrap:35` 指向的是不存在的路径）。官方 `references/` 本就是**可选、按需加载**，故此项**不违反规范、也不是「渐进式披露未落地」的违规**，准确定性为「**资产未挂接／复用约束缺口**」。它**不在悬空引用清单里**，因此「补齐悬空引用 + 抽 L0 权威点 + 指针化」三件事都做完仍会漏掉它——必须单列处置：各技能正文以**条件式指针**（「当 X 时读 `references/模板库.md#模板 N`」）建立正向引用链（plan-cards→模板一、accept-verify→模板二、DR→模板三、project-bootstrap→模板四），并把该引用纳入**离线静态校验**的引用完整性检查项。

**包级共享层的四步修法**（第 ④ 步为本轮新增，缺它则前 3 步做完仍失效）：① 在 L0 显式声明 `references/` 为包级共享资产层、相对路径以**包根**为基准、给统一写法；② 修实体与名字（`治理文档骨架.md` 正名指向模板四；`rules-map` 补实体或删引用）；③ 每个 SKILL.md 用条件式指针把 4 个孤儿资产接入引用链；④ **修订 `README:45/:49/:3` 的迁移指南矛盾**——明确 `references/` 如何复制、包根基准在目标仓库 `.agents/skills/` 下如何保持。

**两轴分离的具体应用**：`version`／`license`／`metadata` 是官方**可选**字段，现状缺失不构成合规缺陷；但作为**自研治理增强**，版本与成熟度追踪应通过 **`metadata` 自定义键**承载，**不新造顶层字段**。若需 `role`／`layer`／`writes`／`reads`／`depends_on` 等自研字段用于让单写者与依赖白名单可被离线校验，同样置于 `metadata` 下并写入 L0 规范，避免与官方字段空间冲突。明确不使用 `allowed-tools` 等客户端专有字段，避免隐性运行时依赖。README.md 在**包根**、不在任何技能文件夹内，故「人类向文档不应放在技能文件夹内」这一反模式**不适用**。

**章节统一模板**（收敛现状 7–12 个二级节、命名不一的差异）——注意这是**轴③内部一致性改进，不是合规要求**（官方「正文无格式限制」）：目标 / 角色与触发 / 输入（只读指针）/ 输出（唯一写入，指向 SSOT）/ 核心步骤 / 状态与交接（迁移 + 认领 + ACK，指针）/ 权威定义指针（只列指针不列定义）/ 项目参数定制位 / 与其他技能的边界（单向交棒 + 明确不做什么）/ 版本与回归。规则类内容上收 L0，技能内只留指针。

**description 触发契约**：官方规范中 description 由客户端运行时做语义匹配；本套无自动发现能力，故其职能应重新定义为「**阶段路由说明 + 边界声明**」，由 L0 维护一张 6 阶段路由表（阶段／触发条件／相邻阶段边界／排除项／should-trigger 与 should-not-trigger 样例），各技能 description 与之对齐、由协调角色显式选取。写法上须含「做什么 + 何时用 + 与相邻阶段的 differentiator」，且**不写流程步骤**（避免 Description Trap）；这直接解决 6 个阶段型 SOP 最大的「阶段串台」风险。此为最佳实践建议（Should），非强制条款。

**L0 必收录的 7 组条目**（架构代理蓝图，补全版）：① 状态字典与状态机；② **SSOT 注册表（L0 的心脏）**——A~H 每类制品逐行写「唯一载体／单写者／只读方／指针形式／受控保留区登记」；③ 权威定义点索引 ADP（九条红线、「本地绿≠CI 绿」公理、假绿根因枚举、红灯 4 类裁决、栈式依赖与合入序、新鲜 main + 树哈希终验、防死胡同四条、合入分权 DR-006、冲突受理与升级路径、DoR/三选一/七步准出定义）；④ 命名总表 + 定制位词表（含 `accept-verify:3` 与 `plan-cards:3` 两处 frontmatter 残留、缺「覆盖：」段的结构不齐、disk-audit 先例词黑名单）；⑤ 结构与接口规范（frontmatter 必填/选填、10 节章节模板、阶段间制品接口契约：输入制品／输出制品／schema／准出验收）；⑥ **显式组合／冲突裁决／状态台账必须单列成章**，不塞进格式规范章——官方规范层完全不解决技能组合、依赖、优先级、冲突仲裁、注入顺序与多 Agent 并发状态共享，这部分只能自研、恰是本套差异化价值，含角色×实例权限矩阵、指令优先级、阶段路由表、Red Flags 与跳过留痕、**裁决权三分**（不与 superpowers 单点 controller 合并）；⑦ 治理与校验纪律（semver／CHANGELOG／弃用流程、回归清单、文档化触发样例集、离线静态校验检查项与触发者时机、脚本版本↔L0 版本绑定、依赖矩阵与指针化规则，含 accept-verify→plan-cards 迭代回边例外）。

**复用约束**：① 任何定义/枚举只在 L0 出现一次，他处指针化（沿用 `plan-cards:55` 已验证的「只指 DR/方案节不复制正文」）；② 跨项目可复用（仅需替换定制位）= 6 个流程技能 + 模板库；包级固定（只能以 DR 升级包版本）= 契约字典；③ 定制位只允许在「项目参数定制位」节替换，不得改核心步骤与权威定义指针；④ README §六 两个可选技能（kb-curator / vm-ops）若自建，须遵循同一规范并声明 layer 与依赖，不得绕过 L0；⑤ 明确哪些制品**只能追加**（验收报告波次、DR、环境事实变更记录、回归集、受控保留子区块）与哪些**必须单写者就地更新**（待办状态列、Sprint 总览行、方案「实测」列、风险登记册）。

## 1.6 权威定义裁决

> 以下 18 类重复定义**均属 C 类「自研治理缺口」，不是官方规范违规**——官方**没有** SSOT／单一权威定义点条款，只有最佳实践中的「coherent units／progressive disclosure」与文件引用一层深度。收敛依据是「清晰／可执行／无歧义」的工程判断，不是合规要求。

收敛到 L0 的唯一节，其余改指针。核心 9 项：

| 重复概念 | 现状 | 收敛后唯一权威点 |
| --- | --- | --- |
| 通用红线/九条红线 | 模板库:14-16、plan-cards:35、exec-sop:38-48、README:72 | L0 §红线条目（**以 exec-sop 九条为全集**），其余三处指针 |
| 本地绿≠CI 绿 | exec-sop:33、ci-cd-ops:64、accept-verify:44/67 | L0 §门禁公理（一条公理 + 一句释义） |
| 三类假绿 / 环境差异根因 | exec-sop:54、accept-verify:67、ci-cd-ops:43-44 | L0 §假绿根因枚举（作为红灯分类树的子项，不再与分类并列） |
| CI 红灯分类 | plan-cards:29（3 类）vs ci-cd-ops:43-46（4 类） | L0 §红灯分类（见下方裁决） |
| 栈式依赖 / append-only / 合入序 | plan-cards:31/43、exec-sop:30/55、accept-verify:67、模板库:23/48 | L0 §依赖与合入序 |
| 新鲜 main / 树哈希终验 | accept-verify:46/67、ops-runbook:52/60/75、ci-cd-ops:59 | L0 §基线新鲜度与内容终验 |
| 事实回填义务 | ops-runbook:70、模板库:104、accept-verify:50、exec-sop:64、README:68 | L0 §SSOT 注册表（消除多落点） |
| 防死胡同四条 | accept-verify:58-63、exec-sop:36、plan-cards:31 | L0 §防死胡同与升级（统一计数/时限/保守默认/go-no-go） |
| 合入分权 DR-006 | README:33、project-bootstrap:36、模板库:51 | L0 §角色与分权（现状规则正文**只在 README**，设立它的 bootstrap 反而没有） |

**红灯分类 3 类 vs 4 类裁决**：采纳 `ci-cd-ops §3` 的**四类**（环境差异类／测试质量类／真缺陷类／流程类）为权威。理由：ci-cd-ops 是门禁诊断权威且 `exec-sop:68` 已指明「分类查 ci-cd-ops」；「测试质量类」与「环境差异类」处置指向不同（前者改测试、后者改环境配置），合并会丢失处置指向。同时把「三类假绿」「三类根因」明确降级为「环境差异类」下的**根因子项**，从根上消除字面冲突。按 `accept-verify §防死胡同`「新阈值须先入决策记录」的一致性要求，此为**设计裁决建议，须由负责人以 DR 追认后生效**，不宣称已生效。另：合入分权 SSOT 错位可参 superpowers `RELEASE-NOTES.md` 单一事实来源思路，但须标注**社区约定、非官方**。

## 1.7 状态契约（纯文档契约，非运行时实现）

**状态枚举**（定义于 L0，所有技能/模板共用）：任务卡主状态 = 待规划／待认领／已认领／执行中／阻塞／待验收／已通过／有条件通过／退回重做／已合入／已冻结／已取消／已关闭；PR 状态 = 草稿／待验收／验收通过／有条件通过／退回／已合入；验收结论沿用三选一；里程碑闸门 = 未到点／判定中／go／no-go／止损触发；故障态 = 正常／降级中／应急合入中／已恢复／待回填；包版本 = 草案／生效／已弃用。

**合法迁移**（以「现状 → 事件/条件 → 目标态 → 写入者 → 留痕」表描述）：待规划→(成卡+DoR+报批)→待认领→(认领)→已认领→(开分支/测试先行)→执行中→(提 PR)→待验收→(七步验收)→已通过/有条件通过/退回重做；退回重做→(同分支修复+CI 绿)→待验收（计数 +1，累计 2 次强制升级）；有条件通过→(整改项闭环)→已通过；已通过→(合入)→已合入→(SSOT 回填)→已关闭。非法迁移须列为禁止：待认领→已合入（跳验收）、执行中→已通过（越权）、已合入→退回（终态不可逆，只能新开卡或 DR）。

**认领/租约/ACK/超时的规范层表达**：
- **认领**不是系统调用，而是「在任务卡执行记录预留区写入一行认领记录」的文档动作，字段 = 实例 ID／角色／认领时点／所依据的卡版本／租约到期。同一卡同一时刻只允许一条有效认领记录，出现第二条即冲突上报，不自行取舍。这同时回应「定义的是角色不是实例」：引入纯文档 `instance_id` 字段允许一角色多实例，靠认领区分。
- **租约**以「时点 + 有效期」文档字段表达，不是定时器；到期未提 PR 视为回到待认领，原实例须先续租并注明。
- **心跳明确不引入**；以「执行记录追加一行进度戳」作等价文档信号；无进度戳且超租约由人/PM 判断是否重派，不自动重派。
- **ACK**：每次交棒双向留痕——下游写入「已接收 + 制品版本 + 时点」ACK 行，上游交出后不再改写该制品；缺 ACK 的交接视为未完成。
- **上下文版本**：每个制品带「制品版本号／依赖的契约字典版本／依赖的上游制品版本」三字段；上游变更则版本递增，下游发现依赖落后须「重读并确认」而非静默继续。这是「上下文包与版本广播」的**规范层等价物**：不广播，靠版本字段 + 离线比对。
- **单写者 + 版本号的文档等价**：制品头部单写者字段 + 版本号 + append-only 变更记录行；任何写入须追加变更记录并递增版本；版本不连续或出现双写者即冲突上报，离线检测。不引入锁/CAS 系统。
- **超时**：把 48h 保守默认从 accept-verify 提升为 L0 全局规则。

> **必须写死的边界声明**：以上全部是「写入文档字段 + 离线校验」的约定，**不存在**并发串行化、实时广播、失败自动重派、WIP 自动排队。这些属运行时协调，按上一轮结论「暂不引入 superAgent」不在本方案范围。

## 1.8 校验脚本定位（用户本轮对方案 B 的一处受控放宽）

**边界重定义**：上一轮方案 B 定义为「纯规范层、不引入运行时组件」，本轮用户放开到允许校验脚本。为避免推成方案 C，严格限定为 **离线、只读、静态一致性校验器**，等价于拼写/链接检查，而非多 Agent 协调器。

**缓和依据**：`README §六:66` 的「领域数据治理技能」判据原文已含「来源铁律、字段纪律、**校验脚本**、错误回灌流程四件套」。因此校验脚本在本包内并非全新增概念，而是把可选技能里的局部判据**上升为包级静态自检能力**——属既有概念的范围调整，而非引入运行时层。

| 维度 | 设计 |
| --- | --- |
| 职责 | 离线、只读、静态一致性校验；不修复、不写回、不阻塞、不调度 |
| 输入 | 只读扫描包内 8 个文件的 frontmatter 与正文，以 L0 的命名总表／状态字典／SSOT 注册表／权威定义点索引作为**期望值源**；不读运行时状态、不连远端、不访问网络 |
| 检查项 | ① 命名一致性（是否只用规范 name、是否残留编号别名/旧技能名作跨文件引用）；② 引用完整性（跨技能/跨文件指针是否可解析到包内现存节、是否成环、是否指向 ADP 而非复制定义，**含 4 个模板的正向指针与包根基准一致性**）；③ 状态字典合法性（状态取值是否在枚举内、迁移是否合法、认领/租约/ACK/版本字段是否齐备）；④ 定制位替换检查（是否残留 `磁盘体检`／`DiskAudit`／`DPAPI`／`tkinter`／`PyInstaller`／`%LOCALAPPDATA%`／`T2-T4`／`M1-M5` 等先例词，词表依据 README §五）；⑤ 单写者一致性；⑥ 必填字段完整性 |
| 输出 | 只读清单，按「检查项 → 文件:节 → 严重级别（阻断/警告/提示）→ 现状值 → 期望值 → 关联权威点」列出；注明「输入文件未被修改」；不写回 |
| 触发时机 | 包版本升级/变更记录合并前（包维护者）；迁移到新项目替换定制位之后（负责人/PM）；每 Sprint 收数时离线体检（PM）；采纳实施后的回归门禁。**执行 Agent 不得触发、不得据输出改文件** |
| 与 SSOT 关系 | 脚本不存储状态、不是 SSOT、不是状态中枢；L0 契约字典是 SSOT，脚本是其只读一致性校验器 |
| 三条护栏 | **不接入 CI/CD 门禁、不写回任何文件、不阻塞 PR**；任何扩大都须重新裁决并记 DR |

**与「不引入运行时组件」是否冲突**：不冲突。统一措辞为「**规范层一致性检查项（由离线只读静态检查器或人工核对清单执行）**」——对已静态写好的 Markdown 做一致性核对，不产生运行时状态、不参与任务分发；保守备选是不引入脚本时的**人工核对清单**。官方附带的校验工具是**运行时 CLI**，只校验 frontmatter 与命名约定、覆盖不了本套自研约束，**不引入、勿与本检查项混为一谈**。该检查项不做 discovery/activation、不解析技能引用，故不触发 1.0 前提 A 的失效条件（**此判断不适用于前提 B**）。

**两件独立事项，不得混写**：① 官方推荐的 `scripts/` / `references/` / `assets/` 三方存在性检查，检查的是**目录约定**；② 本套的**包级共享引用基准**，解决的是跨技能引用的解析基准。二者无关，不得把后者写成「脚本根因」或「合规整改」。同理，「官方规范不解决包级共享层级」属**规范层不负责**，与「本包不解决并发状态仲裁」是同一类边界，不是缺陷。

**实施前提（否则检查项会空跑）**：
- **状态字典合法性**：现状下**无可校验对象**——包内无任务/卡/制品状态取值枚举，唯一枚举是 `模板库.md:68` 的 DR 文档自身状态，`模板库.md:110` 的「状态列」无取值。**须先按 1.7 定义状态字典与合法迁移**，否则检查项③无的放矢。
- **命名一致性**：覆盖 6 个 `name`、8 处编号-名称复合别名、跨文件引用是否只用规范名（**不要求改 `name` 本身**）。
- **引用完整性**：覆盖三个悬空对象（《交付与验收流程》系列引用、`references/治理文档骨架.md`、`rules-map`）、`R-M 类验收卡`、4 个模板的正向指针、包根基准一致性。

**收益**：把命名/引用/状态字典/定制位漂移从「靠人肉自觉」变为可重复、可回归的判定；使「不改原文件只出报告」仍具未来可验证性；降低跨项目迁移的先例词残留漏检；成本低（离线、无依赖）。
**风险**：① **边界蠕变**（最需警惕，一旦接 CI 门禁或赋予写/修复能力即滑向运行时组件）；② 误报与词表维护成本；③ 只检**静态**一致性，**检不出运行时并发写冲突**——不得因引入脚本而宣称已解决「上下文/状态共享」；④ 易造成「已解决状态共享」的错觉；⑤ L0 升级或技能拆并时脚本规则须同步，须把「脚本版本 ↔ 契约字典版本」绑定并纳入变更记录。

## 1.9 本部分的信息不足与假设

- 目标运行时/Agent 框架未给出，影响「校验脚本由谁触发、能否被触发」以及 description 是否可能获得自动发现能力；当前按「无自动发现、由协调角色显式选取」设计。
- disk-audit 的真实并发度、状态冲突与裁决耗时数据缺失（README §七 仅给 40+ PR 与三次里程碑闸门），故 1.3 的可选拆分触发条件只能沿用上一轮 go/no-go 阈值，未做实证校准。
- 《交付与验收流程》全文、`rules-map`、原 `references/治理文档骨架.md` 是否在项目其他位置存在，当前工作区仅见 8 个 md；处置按「包内无实体」给出。

---

# 二、方案B对应调整点

## 2.1 逐条对照矩阵（对照上一轮 13 项 P0/P1/P2 建议，并新增 1 项 P0）

| 编号 | 原建议 | 本轮状态 | 变化说明 | 落在报告何处 |
| --- | --- | --- | --- | --- |
| **P0-0（新增）** | 修复 `README:45` 与 `:49` 迁移指南矛盾 | **采纳（设计层）** | 本轮新发现的可复现交付失效：共享层被排除在复制范围外，迁移后 4 模板与 `project-bootstrap:35` 引用彻底悬空。与包根基准声明**必须同批处置**，否则前 3 步修法做完仍失效 | 1.5 |
| P0-1 | 统一命名与消除悬空引用 | **采纳（设计层）** | 由「改文件」变为「给补齐/指针/删除处置建议」；**按三轴重新分级**：仅实体缺失/写法不一属 D 类引用完整性缺陷，编号与别名属 C 类自研命名层，章节与 description 残留属 E 类内部一致性；新增 `R-M 类验收卡`、§五缺行、模板库孤儿资产、`accept-verify:3` 残留、任务卡三套文件名 | 1.1.1、1.5 |
| P0-2 | 状态字典 + 状态机 + 认领/租约/ACK | **采纳（设计层）** | 明确为纯文档契约；补充「不引入心跳/锁/CAS、靠版本字段+离线比对」的边界声明 | 1.7 |
| P0-3 | SSOT 与单写者 | **采纳（设计层）** | 新增 L0 契约字典承载 SSOT；逐条裁决 A~H 八类冲突（C/D/F 为硬冲突，F 采用受控保留区 + ACK 封存） | 1.2、1.4 |
| P0-4 | 冲突受理通道与超时 | **采纳（设计层）** | 统一为单一受理路径；48h 保守默认升为 L0 全局规则 | 1.4、1.7 |
| P1-5 | 共享上下文包规范 | **调整后采纳** | 吸收 BMAD 的 step-file / document sharding 与官方规范的三层渐进披露；降级为「制品版本三字段 + 离线比对」，不广播 | 1.2、1.7 |
| P1-6 | 抽取权威定义点 | **调整后采纳** | 吸收 spec-kit constitution 与 `/speckit-analyze` 校验定位；收敛 18 类重复定义；明确红灯分类以四类为准；**标注为自研治理而非合规修补** | 1.6 |
| P1-7 | 失败检测与恢复 | **本轮仅描述不落地** | 涉及运行时检测（心跳/自动重派），与纯规范层边界冲突，列为后续项 | 1.7 边界声明 |
| P1-8 | 扩展点从流程扩到规模 | **调整后采纳** | 因用户允许合并/拆分而扩为「技能重组裁决 + 角色/实例分离」；但**推荐保持 6 技能**，合并列为带触发条件的可选方案；合并理由中的「循环」表述已撤回，改为「SSOT 权威点标记缺失」 | 1.3 |
| P1-9 | 条件项台账与回滚 SOP | **采纳（设计层）** | 补模板库缺口（条件项跟踪表）；明确「已合入→退回」为非法迁移，只能新开卡或走 DR | 1.5、1.7 |
| P2-10 | 先例与通用规则结构隔离 | **采纳（设计层）** | 统一「先例」标记块；须保留 README §五:61 明确「保留为示例条目」的 Windows/MSYS 坑 | 1.3、1.5 |
| P2-11 | 参数定制位统一清单 + 迁移自检 | **升格** | 因用户允许校验脚本，由「人工核对清单」升为「离线静态校验脚本的法定检查项」，并附三条护栏与边界蠕变风险；**检查项②含 4 模板正向指针** | 1.8 |
| P2-12 | 技能效果度量与回归清单 | **调整后采纳** | 吸收 skill-creator 的 eval 方法论与 superpowers「无失败测试不建技能」思想，改造为纯 Markdown 的 should-trigger/should-not-trigger 样例清单 + 输入制品→期望输出制品对照 + 变更前后基线表；去掉自动化脚本与 JSON 产物 | 1.5 |
| P2-13 | 试运行 Sprint 回填 + 人类注意力预算 | **采纳（设计层）** | 保留 README §七 的校准要求；门禁分阶段节奏与可选技能判据仍标注「需目标项目实证」 | 1.1、1.9 |

## 2.2 本轮相对上一轮方案 B 的三处变化

| 变化 | 对原建议的影响 | 与上一轮结论是否冲突 |
| --- | --- | --- |
| ① 交付形态仅报告 | 13 项全部由「执行项」变为「设计说明项」；统一采用「现状 → 目标态 → 处置类型 → 依据 → 落地形态」五列对照，一律用「建议/应改为/目标设计中」措辞；删除≠信息丢失（权威内容已在 L0 有唯一落点，靠指针可达） | 不冲突，实施强度弱化 |
| ② 允许技能合并拆分 | 新增 1.3 重组裁决与「核心用途保留逐项对照表」、1.4 职责边界矩阵、1.2 层级与复用约束；最终**推荐不合并**，把授权作为可选方案与触发条件 | 不冲突，属用户授权范围内的设计展开 |
| ③ 允许校验脚本 | P2-11 升格；经「离线/只读/静态」重定义 + 三条护栏后，不构成运行时编排 | **不冲突但需护栏**；若接 CI 或赋写权限即越界 |

**总体定性变化（新增）**：本轮经官方规范逐条核实后，方案 B 的性质由「修补规范偏差」更正为「**自研规范层重构 + 内部一致性治理**」。这不改变 13 项建议的实质内容，但改变了它们的**依据表述**：不得再写成「为符合官方规范」，而应写成「为消除自研约定中的歧义与多写者冲突」。

**变更影响小结**：新增（校验脚本定位、拆分出 L0 契约字典、层级与边界矩阵、核心用途对照、P0-0 迁移指南修复、三轴判定分级）／弱化（不改文件 = 实施变设计）／坚持（纯规范层、不引入运行时协调）。

## 2.3 明确不做

不引入运行时状态中枢、不做并发仲裁与自动重派、不接管 PM 的计划与验收裁决、不把校验脚本接入 CI 门禁、不改现有 8 个文件、不写脚本实体、不提供代码片段与操作教程。

**沿用三条防误判红线作为实施约束**：不把缺 SSOT／章节不统一／合入分权错位判成官方违规；不把「无 `version`」当缺陷、不新造顶层字段（走 `metadata`）；不把 00–05 代号判成 `name` 违规、不因 `02-task-exec` 给 6 个技能改名。另加一条结构约束：不把 `../references/…` 写成「合规修正」、不把包级共享判成违规、**不把模板复制进各技能 references/**。

---

# 三、github可借鉴方案清单与评估

## 3.0 数据裁决、勘误与验证状态

| 项 | 处理 |
| --- | --- |
| **star 数据冲突** | 两路调研与早期搜索给出的数值不一致（例：spec-kit 80.3k vs 149,131；superpowers 77.1k vs 315,455；OpenSpec 36.6k vs 74,496）。统一采用 **GitHub REST API 2026-11-10 一手快照**；早期/第三方数值标注为「不同时间快照或口径混淆，不再采用」。`obra/superpowers` 315,455 由两路 API 独立取得，交叉验证通过 |
| **勘误 1** | `ruvnet/claude-flow` 与 `ruvnet/claude-code-flow` 已非独立仓库，API 均 302 到 **`ruvnet/ruflo`**；旧 README 中的 SPARC、CRDT memory、64-agent registry 等主要来自 fork/第三方，未在官方 README 复现，不作结论 |
| **勘误 2** | BMAD 规范组织名为 **`bmad-code-org/BMAD-METHOD`**（旧 `bmadcode/BMAD-METHOD`） |
| **勘误 3** | Agent Skills 规范权威已**外移**：`anthropics/skills` 的 `spec/agent-skills-spec.md` 现仅一行指向 `agentskills.io/specification`；规范仓库为 `agentskills/agentskills`（含 GOVERNANCE.md / MAINTAINERS.md / `skills-ref` 校验库） |
| **勘误 4** | `agentskills.io/authoring-best-practices` 与 `/integrating-skills` 实测 404；官方页面清单以 `agentskills.io/llms.txt` 为准，正确地址为 `/skill-creation/best-practices.md` |
| **许可证分歧** | `anthropics/skills` API license=null，README 称 Apache-2.0，第三方称文档技能为 source-available；BMAD API license=Other/NOASSERTION 但 README 标 MIT。引用时均标注分歧 |
| **未验证项** | spec-kit 社区扩展 MAQA/CI Guard 与旧版统计（仅旧快照）；BMAD「12+ agents / 34+ workflows / .bmad-core 结构」（来自 fork 与营销页）；agent-os 完整目录清单（第三方对比教程，官方 v3 迁移页只确认部分）；agency-agents 数量（第三方互相矛盾）；OpenSpec delta 细节；AWS Kiro（未独立检索）。以上均不进入采纳依据 |
| **筛除项** | `msitarzewski/agency-agents`（167,599，人格库，无阶段/制品链/门禁/状态）、`PatrickJS/awesome-cursorrules`（41,140，单编辑器规则清单且约 5.5 个月无推送）——与目标不同层，不进入清单 |

**适用性共同判据**（每项结论据此推导）：本套是**纯 Markdown 规范层、三角色、文档制品交接、PM 为验收判定单点（合入按 DR-006 分权）、无运行时、本轮不改现有文件**。纯文本可表达的机制 → 可直接借鉴；依赖 CLI/插件市场/hook/安装器/编排运行时的机制 → 需改造（只吸收纪律描述，剥离运行时）或不适用。

**两轴加注（全报告通用注，不只适用于本节表格）**：Axis-2（自研治理）与 Axis-3（内部一致性）**均为社区／外部项目约定或本套自研约定，仅作机制类比，不作官方规范依据**；官方规范不符合「自研约定是否合格」的裁判。验证状态列记录的只是「**是否亲自抓取一手资料**」，与「**是否为官方规范**」是两件不同的事，勿混用。

**验证状态三档**：`一手实测` = 本次亲自抓取 GitHub REST API / 官方仓库文件 / 官方文档原文；`部分核实` = 内含 A 档（他人独立抓取一手资料后转述，内容属一手、仅未独立重抓，非推测）与 B 档（第三方教程／官网／营销页／fork README，属推测性转述），两子档分别标注；`仅社区或第三方观测` = 无一手来源、只作旁证；`未验证` = 不进入采纳依据。

**立论出处收窄**：「官方规范不解决技能组合／依赖／优先级／冲突仲裁／多 Agent 状态共享」这一判断**只以 `agentskills.io/llms.txt` 官方页面清单 + `client-implementation` 一手表述为依据**；第三方的 composition cliff、遵循率衰减实验、arXiv 综述仅作旁证，**不进入 P0 采纳依据**。第三部分「包级共享层不在官方模型内」的精确依据是「**没有任何一处引用真正指向某技能目录内的实体文件**」，而非「引用写法违规」。

## 3.1 `github/spec-kit` — 判定：需改造（优先级最高之一）

- **来源与验证**：https://github.com/github/spec-kit ｜ GitHub 官方 org，API 一手 **149,131 stars / 13,391 forks**，创建 2025-08-21，2026-11-10 当日 push，MIT，Python。一手：GitHub Blog 发布文、spec-driven.md、constitution-template.md、github.github.io/spec-kit 文档。
- **设计思路**：当前核心 SDD = `Specify → Plan → Tasks → Implement → Converge`，另加 `constitution / clarify / checklist / analyze` 门禁；每阶段产出 Markdown 制品喂给下一阶段（官方表述「Each phase produces a Markdown artifact that feeds the next」）；`.specify/feature.json` 记录当前活动 feature（准 SSOT，「Commands resolve the feature from that state, not from the checked-out Git branch」）；`/speckit-analyze` 为**只读**跨 spec/plan/tasks 一致性检查，问题「fix them at the source and re-run」；constitution 模板含九条 Articles、`NON-NEGOTIABLE` 措辞、`Version / Ratified / Last Amended` 元数据与「Constitution supersedes all other practices; Amendments require documentation, approval, migration plan」；模板强制 `[NEEDS CLARIFICATION]` 标记与 Phase -1 Gates。角色为**单一 coding agent + 人类逐阶段 review**。
- **可复用点**：① constitution 式不可协商约束（对应本套红线/安全底线 SSOT）；② `[NEEDS CLARIFICATION]` 强制不确定性标记；③ checklist 作为「unit tests for requirements」；④ 规格→计划→任务可追溯链 + 只读跨制品一致性检查；⑤ 单一事实源字典；⑥ 带版本号/批准日/修订日的治理段；⑦ 逐阶段人审契约。**其中 ④ 恰好是本轮校验脚本最成熟的定位参照**。
- **局限**：依赖 `specify` CLI + Python 3.11+/uv + 各 agent 的 skills/slash-command 运行时；**假定单 Agent 顺序执行**，无认领契约、无并发写控制（其「冲突」指制品间语义一致性，不是文件写冲突）；流程重、Markdown 制品多；九条 Articles 是硬编码技术原则（Library-First / TDD），须整体替换为本套流程纪律。
- **适用性**：**需改造**。只吸收「规范条款 + 模板结构 + 只读一致性检查的定位」，不引入工具链，不整体替换 00→05 流水线（会破坏 40+ PR 实证）。

## 3.2 `buildermethods/agent-os` — 判定：可直接借鉴（契合度最高）

- **来源与验证**：https://github.com/buildermethods/agent-os ｜ API 一手 **5,592 stars / 831 forks**，2026-10-07 push，MIT，Shell。官方 v3 迁移页为一手；完整目录清单部分来自第三方对比教程（已标注）。
- **设计思路**：**纯文件、无运行时、无角色扮演**（官方/第三方一致「Not role-based. It has no personas」）。三层目录即 SSOT 分层：全局 `~/.agent-os/standards/`、每项目 `.agent-os/product/`（`mission.md` / `tech-stack.md` / `roadmap.md` / **`decisions.md` append-only 决策日志，具 override authority**）、每 spec 一个日期目录；`tasks.md` 首尾固定「write tests」→「verify all tests pass」；v3 退役 implementation 与 orchestration 阶段及 subagent，改为 defer to Plan Mode。**靠重读文件恢复上下文**：「state persists between sessions … re-reads roadmap.md, knows what phase you're in」。
- **可复用点**：① 三层目录即 SSOT 分层；② `decisions.md` append-only + 覆盖全局规则的权威声明；③ `roadmap.md` + `tasks.md` 构成状态字典；④ 首尾固定验收门禁；⑤ 「重读文件即恢复上下文」的无运行时持久化；⑥ 一个 spec 一目录的天然写隔离。
- **局限**：v2 曾带安装脚本，v3 仍依赖 `~/agent-os` 与 Plan Mode；**无多角色、无认领契约、无并发控制**；流程粗（plan→spec→execute），不含 code review / 故障 / CI 阶段；默认技术栈有偏见；star 与活跃度远低于其他候选；详细目录清单未由官方 README 一手确认。
- **适用性**：**可直接借鉴**。它是唯一「纯 Markdown 文件驱动、无角色扮演、无编排运行时」的成熟参考，正对本套「无 SSOT、无状态字典、无不可协商约束」三个缺口。**判重提示**：本套已有「文件驱动、无运行时」（README:49-51），真正可借鉴的是把**已有但分散**的 DR 效力层级、状态字典、回灌落点**收拢到单一真源**，应写成「**强化／统一现有机制、勿重复引入文件体系**」而非「新增机制」，否则与「**不引入运行时组件**」及本轮「保持 6 个流程技能、只新增包级 `references/` 文件」的**设计取舍**冲突。注意：「不新增技能」**不是方案 B 的硬约束**（用户决策明确允许合并／拆分），此处只是本报告推荐目标态的取舍。

## 3.3 `Fission-AI/OpenSpec` — 判定：可直接借鉴（制品结构与变更治理）

- **来源与验证**：https://github.com/Fission-AI/OpenSpec ｜ API 一手 **74,496 stars / 5,105 forks**，2026-11-09 push，MIT，TypeScript。
- **设计思路**：`explore → propose → apply → archive`，官方明确「Work fluidly — update any artifact anytime, no rigid phase gates」（与 spec-kit 的刚性门禁形成对照）；**每个变更一个 `openspec/changes/<slug>/`**，含 proposal.md / specs（`ADDED Requirements` + `SHALL` + `#### Scenario: WHEN…THEN…`）/ design.md / tasks.md；`archive` 把 delta **合并回 `openspec/specs/` 单一事实源**并清理变更目录；Stores（beta）表述「One source of truth your whole team and every coding agent can read … No drifting wiki」；「Agree before you build」人工审批门禁。
- **可复用点**：①「一变更一目录」的写隔离与隐式认领（本套无并发控制的最省力规范层解法）；② 四件套制品；③ `SHALL` + WHEN/THEN 场景化验收条件；④ **delta → archive → merge 回 SSOT** 的变更治理闭环（正对应本套 8 处多写者冲突）；⑤ 人工审批门禁。
- **局限**：有 CLI（Node 22.12+）与 30+ 工具 slash command 适配（轻运行时）；官方自评 fluid / 无刚性门禁，若本套要强门禁需反向改造；无多角色、无 owner 认领、无并发调度；Stores 仍 beta；带可关闭的匿名 telemetry。
- **适用性**：**可直接借鉴（制品结构与变更治理）**，CLI 部分不适用。其「按目录隔离 + delta 合并回 SSOT」纯 Markdown 即可落地，且应写成「统一本套已有回灌机制」而非新增变更目录。

## 3.4 `obra/superpowers` — 判定：条款层可直接借鉴；并行机制需改造

- **来源与验证**：https://github.com/obra/superpowers ｜ API 一手 **315,455 stars / 28,058 forks**（两路独立一致），2026-11-03 push，Release **v7.0.2**，MIT，Shell。一手：仓库树 API（扁平 `skills/<name>/SKILL.md` 共 15 个）、README、RELEASE-NOTES.md、`using-superpowers` / `subagent-driven-development` / `dispatching-parallel-agents` / `writing-skills` 原始 SKILL.md。
- **设计思路**：固定 7 步工作流（brainstorming → using-git-worktrees → writing-plans → subagent-driven-development / executing-plans → TDD → requesting-code-review → finishing-a-development-branch）；「**The agent checks for relevant skills before any task. Mandatory workflows, not suggestions.**」；`using-superpowers` 定义**指令优先级**（user/AGENTS.md > skills > default）与 **process skills 先于 implementation skills**，附 Red Flags 反合理化表；`subagent-driven-development` 每任务一个 fresh subagent、两阶段 review（spec compliance → code quality）、ledger 文件、`Rulings, not stalls`（裁决留痕格式）、Global Constraints / per-task Interfaces、**文件化交接**（「Hand artifacts over as files」「Never make a subagent read the whole plan file」）；`dispatching-parallel-agents` 的适用前提写死「without shared state or sequential dependencies」，判定图含「no - shared state → Sequential agents」；`writing-skills` 铁律「NO SKILL WITHOUT A FAILING TEST FIRST」、description **trigger-only**、flat namespace；版本治理 `RELEASE-NOTES.md` 单一事实来源 + semver + 内联迁移说明 + `tests/` 与 `evals/` 分离 + skill-size 门禁；v7.0.1 因 compaction 在 20000 字符截断把长内容移入 `references/` 按需读盘（一次真实的渐进式披露重构）。
- **可复用点**：①「强制而非建议」的纪律条款；② 验收门禁（severity 分级 + Critical 阻断 + verification-before-completion + clean baseline）；③ 两阶段评审；④「状态外置到文件、不依赖会话记忆」；⑤ 冲突单点裁决 + 记录 + 明确停机上报条件；⑥ 并行仅用于无共享状态的独立域；⑦ trigger-only description + 反合理化表；⑧ RELEASE-NOTES 单一来源 + semver + 尺寸门禁；⑨ harness-neutral 改写（把工具名换成动作名，保证规范不绑定具体 Agent 产品）；⑩ `diagnosing-superpowers` 读会话记录逐行取证的复盘机制，正对应本套第 6 阶段「故障」。
- **局限**：强依赖运行时——SessionStart hook 注入 bootstrap、Skill/Task 工具、git worktree、bash/Node 脚本、plugin marketplace；其「强制」是**运行时强制**，纯 Markdown 无等价物；并发/冲突本质是**规避**共享状态（隔离 worktree + 不并发实现 + 文件交接 + 单一 controller 裁决），不是共享状态管理或分布式仲裁；**单一 controller 集中裁决与本套三角色分权冲突**；无跨 Sprint 治理与 SSOT 强约束。
- **适用性**：**条款层可直接借鉴**（阶段编排、制品契约、状态外置、优先级层级、Rulings/停机条件、版本治理、故障取证）；**需改造**的是剥离 hook/工具/git 依赖、改成纯 Markdown 制品模板 + 角色权限矩阵，并把集中裁决权**拆到三角色**。

## 3.5 `bmad-code-org/BMAD-METHOD` — 判定：需改造（角色与制品契约层价值高）

- **来源与验证**：https://github.com/bmad-code-org/BMAD-METHOD ｜ API 一手 **55,203 stars / 6,156 forks**，2026-11-08 push；双版本线 stable v6.12 与 V7 preview alpha（skills 化，官方称 v7 ETA 2026 年 11 月中、期间有 breaking changes）。许可证口径不一（API Other/NOASSERTION vs README MIT + TRADEMARK.md）。
- **设计思路**：delivery loop = `Clarify → Plan → Build and verify → Learn and adjust`；「Right-sized process / Scale-Domain-Adaptive」，按 intent 规模分路径（单 session / epic / project ≥20 sessions）；具名 persona 多角色敏捷团队（v6 经典六角色链 BA→PM→Architect→PO→SM→Dev）；官方明确「Every skill in this chapter writes a document you can hand on」，具名制品 brief / PRD / architecture / DESIGN / `.memlog.md` / 有序 `tickets.toml`（story + build order + `built` 状态）；「Durable context — Carry product and technical decisions forward instead of re-explaining them in every chat」；**并发条款**（纯 Markdown 可表达）：「Independent epic streams can proceed in parallel when their boundaries are explicit. Each stream needs an owner … Run integration checks and a retrospective at each epic boundary」；step-file architecture 与 document sharding 把大文档拆为顺序 step 以省上下文。
- **可复用点**：①「每个 skill 产出一个可 handed-on 文档」的交接契约；② `tickets.toml` 式有序状态字典 + owner；③ 按规模的门禁分级；④「每流一个 owner + 边界处集成检查」的**轻量认领与并发边界条款**；⑤ `.memlog.md` 决策日志；⑥ retrospective 对照需求整体验收；⑦ step-file / document sharding 的上下文预算思路。
- **局限**：依赖 `npx bmad-method install` / `npx skills add` 安装器与 Node/Python/uv；V7 alpha 频繁 breaking changes；角色 12+、workflow 34+ 过重；**无 SSOT 强约束**，并发只是「边界 + owner」约定、无强制冲突检测；未验证项较多（见 3.0）。
- **适用性**：**需改造**。把 12+ 角色压缩到三角色、剥离安装器、把重型 PRD/architecture 映射到本套已有六阶段交接文件；`bmad-orchestrator` 属编排层，不采纳。

## 3.6 `anthropics/skills` + `agentskills/agentskills`（官方规范） — 判定：格式层可直接借鉴；治理层不适用

- **来源与验证**：https://github.com/anthropics/skills ｜ API 一手 **191,867 stars / 22,541 forks**，2025-09-22 创建，2026-11-06 push，README 称 Apache-2.0（API license=null，有分歧）。规范站 https://agentskills.io/specification 与仓库 https://github.com/agentskills/agentskills ｜ API 一手 **27,126 stars / 2,019 forks**，Code Apache-2.0 / Docs CC-BY-4.0，2026-11-04 有「AAIF Donation: Add governance and maintainers」提交。一手：官方规范原文、`llms.txt` 页面清单、`template/SKILL.md`、`skill-creator/SKILL.md`。
- **设计思路**：技能 = 文件夹 + `SKILL.md`（必需）+ `scripts/` / `references/` / `assets/`；frontmatter 必填 `name`（1–64 字符、小写数字连字符、与父目录名一致）与 `description`（1–1024 字符、须同时写「做什么 + 何时用」、含关键词），可选 `license` / `compatibility` / `metadata` / `allowed-tools`；正文无格式限制，建议 <500 行 / <5000 tokens；**三级渐进披露**（metadata ~100 tokens 常驻 → 激活时载入正文 → 资源按需）；文件引用用相对技能根、一层深度；`skills-ref` 提供校验；`skill-creator` 提供「捕获意图 → 起草 → 写测试提示 → with-skill vs baseline 对照 → 迭代 → description 优化」的评测回路；README 明示「演示与教育用途，需自行验证」。
- **可复用点**：① frontmatter 最小二字段与 name 匹配目录（本套**已合规**）；② 三级渐进披露 + 条件式 reference 指针 + 一层深度 + 正文瘦身；③ description 触发契约写法（what/when/differentiator、trigger-only、略 pushy、不写 how）；④ 正文本体技术（checklist / validation loop / 输出模板 / Gotchas / state-check / 按脆弱度调节严格度 / default 而非 menu）；⑤ 制品接口契约（输入/输出/schema/准出四段）；⑥ **`metadata` 承载自定义键值**（本套版本/role/layer/writes/reads 等自研字段的合规落点）；⑦ eval 方法论（改造为纯 Markdown 样例集与对照表）。
- **局限（关键）**：规范是**打包 + 消费协议，不是协调协议，且管辖面极窄**。可机械判定的硬约束仅 4 项（SKILL.md 存在、frontmatter 在开头、name 必填且匹配目录名、description 必填非空 ≤1024），本套 6 个文件全部通过；`description` 的 what/when 是 **Should**，正文 <500 行与目录约定是 **recommendations**，官方校验工具只校验 frontmatter 与命名约定。`llms.txt` 官方页面清单**无任何**关于技能组合、依赖、优先级、冲突仲裁、多 Agent 状态共享的页面（`/integrating-skills` 等实测 404 亦佐证）；`client-implementation` 明确「discovery/selection/activation 机制由各 client runtime 实现」。此外：**官方模型只描述「每技能目录内含自己的 `references/`」，未覆盖本套的包级共享资产层**；`description` 自动语义匹配、校验 CLI、`allowed-tools`、plugin marketplace 均依赖运行时。第三方分析（composition cliff、ScaledIF 遵循率相乘衰减、arXiv 综述把 Skill Composition/Orchestration 列为开放挑战）均为二手，但与官方页面清单一致，故「规范层不解决组合/状态」这一判断可靠。
- **适用性**：**格式层可直接借鉴**；触发机制**需改造**（降级为阶段路由说明 + 边界声明，由协调角色显式选取）；治理层（版本/CHANGELOG/SSOT）**不适用**——官方无强制条款，本套相关设计属**自研增强**，不可写成「遵循官方规范」。包级共享结构须按前置声明 6 与 1.2 的自研约定处理。

## 3.7 `ruvnet/ruflo`（原 claude-flow） — 判定：不适用（反例/边界参照）

- **来源与验证**：https://github.com/ruvnet/ruflo ｜ API 一手 **81,384 stars / 9,576 forks**，2026-11-10 当日 push，MIT，TypeScript；`ruvnet/claude-flow`、`ruvnet/claude-code-flow` 均 302 到此仓库。
- **设计思路**：蜂群编排层，100+ specialized agents、27 hooks + MCP Server + Router 后台路由、HNSW-indexed AgentDB 向量记忆、hierarchical/mesh/adaptive 拓扑与 Raft/Byzantine/Gossip 共识；官方对比表「Claude Code Alone: Isolated, no shared context → + Ruflo: Swarms with shared memory and consensus」；`Team Gateway Checklist` 文档含「Before-merge gates, dual-mode handoff, memory namespace sharing, and witness manifest entry per merge」。
- **可复用点（有限）**：①「合并前门禁 + 每次合并留证据」的条款概念；②「tenant-isolated team that divides work and returns evidence」的分工/回执概念；③「no shared mutable state during execution」架构原则的反面启示。
- **局限**：**完全依赖运行时**——CLI/MCP/hooks/后台 daemon/向量库/SQLite/共识协议/多模型路由；100+ agents、48 插件、学习与维护成本极高；**无 Markdown 制品链、无 constitution、无人类 PM 单点**；冲突解决是 CRDT/共识等代码级机制，纯规范层无法表达；官方大量性能数字为自报，旧代细节未在官方 README 复现（见 3.0）。
- **适用性**：**不适用**。其全部并发/冲突/状态共享价值恰在运行时，正是上一轮判定「暂不引入 superAgent」的方案 C 范畴；仅作为「不采纳」边界参照，并把「合并前门禁 + 每次合并留证据」写成一条 Markdown 条款。

## 3.8 各方案都不解决什么（避免误读）

所有已核验方案**均不解决**：多 Agent 并发写同一状态文档的运行时一致性、认领竞争的机器仲裁、状态文档 SSOT 的运行时保证。superpowers / OpenSpec / BMAD 采取的是**隔离 + 单点合并 + 事后集成检查**的规避策略，ruflo 采取代码级共识，spec-kit 与官方规范则根本不处理。这恰恰印证上一轮判断：这些是 L1 运行时协调问题，不是 SOP 可修补的；本套的自研扩展层（SSOT/状态字典/三角色裁决）是其差异化价值，但同样只到规范层为止。

---

# 四、采纳建议

## 4.1 分级判据

| 级别 | 可判定条件 |
| --- | --- |
| **直接采纳** | ① 纯规范层/文档制品或官方规范本身，不引入运行时；② 与方案 B 的补齐项同向；③ 来源为一手已核实；④ 许可允许借鉴；⑤ 不依赖特定平台运行时 |
| **改造后采纳** | ① 理念可取但绑定运行时/状态中枢/调度器，须剥离为「文档契约 + 离线校验」；② 绑定特定工具链需替换定制位；③ 与三角色模型假设不同需调角色映射；④ 仅部分核实 |
| **暂不采纳** | ① 本质是运行时协调器/状态中枢/并发控制；② 与「仅报告、不改原文件」冲突的实现型产物；③ 需服务端/网络/持久状态；④ 未核实；⑤ 与 README §七 成熟度声明冲突、需目标项目实证 |

**总判据（凌驾于上表）**：**不可拿官方规范去评判自研约定**。凡落入轴②（自研治理缺口）与轴③（内部一致性）的条目，按「清晰／可执行／无歧义／是否与 40+ PR 实证冲突」评估，不按「是否符合官方规范」评估；采纳外部方案时须标明其依据属官方规范、社区约定还是第三方观测。两轴加注为**全报告通用注**：Axis-2/Axis-3 仅作机制类比，不作官方规范依据。

**两条表述纪律**：① 借鉴项一律写「**强化／统一现有机制、勿重复引入文件体系**」，不写「新增机制」；「不新增技能」不是方案 B 硬约束（用户允许合并／拆分），本轮取舍只是**保持 6 个流程技能 + 新增包级 `references/` 文件**。② 「不适用」判的是**整层编排能力**（运行时协调器／状态中枢／并发控制），**不是**其承载的纯文本条款——该条款已在 3.4 与 4.2 的 P1 项中被剥离采纳；两者不可混为一句「不采纳」。③ Part 4 中凡以 `ci-cd-ops` ↔ `ops-runbook` 互指作为「步骤 vs 边界」清晰范例的表述，均为 **as-is 6 技能态**；在备选 6→5 合并的目标态下须改称「同技能内分节互指」（见 1.0）。

## 4.2 采纳优先级与逐项结论

| 优先级 | 借鉴项（来源） | 落到哪一层 | 解决的问题 | 引入的新成本 |
| --- | --- | --- | --- | --- |
| **P0-0（新增）** | 修复共享层迁移缺口（本轮审计新发现，非外部借鉴） | L2 + README §四 | `README:45` 必选 vs `:49` 排除共享层的矛盾；迁移后 4 模板与 `project-bootstrap:35` 引用彻底悬空 | 须同步声明包根基准、修订迁移三步、补共享层复制说明；**不做则前 3 步包级共享修法全部失效** |
| **P0-1** | constitution 式不可协商约束（spec-kit 宪法模板、agent-os `decisions.md` 覆盖权、superpowers「Mandatory workflows」） | L0 契约字典 | 18 类重复定义、红线三处口径不一、DR 无效力层级 | 需一次性把散落定义收拢并裁决；L0 变更须走 DR |
| **P0-2** | 只读跨制品一致性检查的定位（spec-kit `/speckit-analyze`、OpenSpec `archive` 合并回 SSOT） | 校验脚本（1.8） | P2-11 升格后的检查项与触发时机；命名/引用/状态/定制位漂移 | 三条护栏 + 词表维护 + 版本绑定 |
| **P0-3** | 单一事实源 + 状态字典（agent-os `roadmap.md` / `decisions.md`、BMAD `tickets.toml`、spec-kit `feature.json`、OpenSpec `openspec/specs`） | L0 §SSOT 注册表 / §状态字典 | A~H 八类多写者冲突、无状态枚举、回灌多落点 | 需为每个制品指定唯一写者并改写 6 个技能的回填表述 |
| **P0-4** | 官方 frontmatter / 三级披露 / 条件式指针 / description 触发契约（agentskills.io、`skill-creator`、superpowers `writing-skills`） | 1.5 命名与结构规范 | 三套命名、模板孤儿资产、6 阶段串台风险、description 项目名残留 | 需维护一张 6 阶段路由表；description 职能从自动触发改为显式路由说明；自研字段走 `metadata` |
| **P0-5** | 制品接口契约（输入/输出/schema/准出四段）+ 交接 ACK（BMAD「writes a document you can hand on」、superpowers 文件化交接、官方 best-practices） | 1.4 职责边界矩阵 | 交接无 ACK、卡变更后无通知、无制品版本字段 | 每个技能新增固定章节；制品头需带版本三字段 |
| **P1-1** | 强制门禁与验收纪律（superpowers Critical 阻断 / verification-before-completion / 两阶段评审 / clean baseline；spec-kit 逐阶段人审；agent-os 首尾测试门禁） | 强化 accept-verify 七步（不改其判据） | 提升验收纪律，不新增机制 | 需写明「纯文档约定的强制力低于运行时 hook」及「谁有权跳过、跳过需记录什么」 |
| **P1-2** | 认领契约 + 并发边界（BMAD「每流一 owner + 边界集成检查」、OpenSpec 一变更一目录、superpowers 无共享状态才并行） | 1.7 状态契约 | 无认领/租约/ACK；同文件并行风险 | 明确**规范层只能做「文件级隔离 + 单写者 + 合并前门禁」，不能技术性解决并发写冲突** |
| **P1-3** | 版本与变更治理（superpowers RELEASE-NOTES 单一来源 + semver + 内联迁移说明 + 尺寸门禁；spec-kit 宪法版本元数据；OpenSpec delta→archive） | L0 + 包级变更记录 | 技能自身无版本 / 变更记录 / 回归清单 / 效果度量 | 需建立包级变更记录与版本绑定；**属自研增强，官方规范无此强制；不新造顶层字段** |
| **P1-4** | step-file / document sharding（BMAD）、harness-neutral 改写（superpowers v6）、`SHALL` + WHEN/THEN 场景（OpenSpec） | 1.5 章节模板与验收标准写法 | 长文档上下文预算、规范绑定具体 Agent 产品、数据类验收口径 | 需把「先例」与通用规则结构隔离，保留 README §五:61 明示保留的示例条目 |
| **P1-5** | eval 方法论（skill-creator、官方 evaluating-skills、superpowers「无失败测试不建技能」） | 技能自身回归清单 | P2-12：本包要求项目做度量/回归，自身却无 | 改造为纯 Markdown 的 should-trigger/should-not-trigger 样例 + 输入制品→期望输出制品对照 + 变更前后基线表；去掉自动化脚本与 JSON 产物 |
| **P1-6** | 故障取证复盘（superpowers `diagnosing-superpowers`） | ops-runbook 增强 | 故障阶段已有「事实回填义务」，缺「逐行取证说明哪步偏离计划、哪道门禁被跳过」 | 增加一份脱敏复盘制品模板 |
| **P2（改造候选）** | spec-kit 的 `clarify / checklist / converge` 门禁链、BMAD 按规模分级与 retrospective | 后续 Sprint 校准 | 增强规划与里程碑判定 | 与 README §七「门禁分阶段节奏需校准」冲突，需目标项目实证后再定 |
| **P2（可选重组）** | 合并 platform-guard、拆分闸门/裁决技能（架构代理方案） | 1.3 可选方案 B | 若并发上升后裁决积压 | 仅在 go/no-go 闸门满足时评估；会改动 §三/§五/§四 |

## 4.3 暂不采纳清单（每条落到判据）

| 项 | 不采纳判据 |
| --- | --- |
| spec-kit 的 `specify` CLI、模板解析栈、preset/extension catalog | 运行时组件 + 实现型产物，与「不引入运行时/仅报告」冲突 |
| superpowers 的 SessionStart hook、Skill/Task 工具、git worktree、plugin marketplace | 运行时组件；其「强制」无法在纯 Markdown 层等价复现 |
| BMAD 安装器、12+ persona、Web Bundles、Party Mode、`bmad-orchestrator` | 运行时 + 角色过重 + 编排层 |
| OpenSpec CLI、Stores（beta）、匿名 telemetry | 轻运行时 + 未稳定 |
| `ruvnet/ruflo` 的 CRDT/共识/向量内存/守护进程 | 本质是 L1 运行时协调器，与上一轮「暂不引入 superAgent」直接冲突 |
| `anthropics/skills` 的 plugin marketplace、document skills 二进制/脚本、`skills-ref` CLI、`allowed-tools` | 客户端专有 + 运行时 |
| `agency-agents`、`awesome-cursorrules` | 与目标不同层（人格库 / 单编辑器规则清单），且后者维护停滞 |
| 官方规范的「技能组合/冲突仲裁」 | 规范层根本不提供；不能指望外部规范替本套补齐 |
| **把 4 个模板复制进 6 个技能各自 `references/`** | 看似贴合官方目录模型，实则制造 6 份副本、直接加剧重复定义与缺 SSOT；**保持包级共享 + 包根基准** |
| **把 `../references/…` 写成「合规修正」；把包级共享、章节不统一、缺 SSOT、无 `version` 写成合规缺陷** | 违反三条防误判红线；官方管辖面极窄，方案 B 是自研规范层重构而非合规修补 |
| 校验脚本接入 CI / 赋予写权限 | 边界蠕变风险，三条护栏明令禁止 |
| L1 运行时协调（并发写串行化、上下文版本广播、失败自动重派、WIP 排队） | 超出纯规范层，仅在满足 go/no-go 闸门后另案评估 |

## 4.4 一致性收口

1. 上述采纳项**全部停留在规范/文档层**，最激进的也只是离线只读静态校验，不改变「不引入运行时编排层」的立场；因此**不把方案 B 推成方案 C**，与上一轮「现阶段不建议引入 superAgent」自洽。
2. 校验脚本的放宽经「离线/只读/静态 + 三条护栏 + README §六:66 既有概念」三重约束后，不构成边界突破；报告已明确它**不覆盖** SSOT 的运行时一致性，只覆盖文档层一致性。
3. 外部调研反而强化了上一轮判断：所有成熟方案都不解决多 Agent 并发写冲突的运行时保证，隔离与单点合并是唯一可行的规范层策略。官方规范管辖面极窄（4 项硬约束、本套全通过）也印证本轮工作属**自研规范层重构**，不是合规整改。
4. **未来再评估的 go/no-go 闸门**（沿用上一轮，阈值规划期写死、到点判数据）：连续 2 个 Sprint 满足「并发 Agent ≥4」且「出现状态文档写冲突 / 重复领卡 / 48h 裁决停滞任一」，才进入「是否引入编排层」的阶段二评估；届时须先明确 superAgent 定义、SSOT 归属与 PM 边界。

## 4.5 信息不足 / 需补充项

| 项 | 影响 |
| --- | --- |
| superAgent 在本包内仍无定义 | 本轮不引入，仅作「不采纳」边界参照；4.4 的阶段二评估须先补定义 |
| 目标运行时 / Agent 框架未给出 | 影响 description 能否自动发现、校验脚本由谁触发、以及部分 GitHub 方案的适用性判定 |
| disk-audit 真实并发度、状态冲突次数、裁决耗时分布缺失 | 1.3 拆分触发条件与 4.4 闸门阈值无法用本包数据校准 |
| 《交付与验收流程》全文、`rules-map`、原治理骨架文件是否在项目其他位置存在 | 当前工作区仅见 8 个 md；1.5 的处置按「包内无实体」给出，若实际存在需改为指针 |
| 3.0 列出的未验证项 | 不进入采纳依据；若需引用须先一手核验 |
| 红灯 3 类 vs 4 类裁决的效力 | 本报告为**设计裁决建议**，须负责人以 DR 追认后生效，不宣称已生效 |
| 本轮 13 项建议的逐条原文 | 对照矩阵依据上一轮结论摘要重构；若原文措辞有出入，以原文为准 |
| 官方条款的严格级别 | 已区分 Must / Should / recommendations；若需逐字原文用于对外引用，须再取规范原文复核 |
