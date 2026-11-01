---
name: kb-curator
description: 磁盘体检（disk-audit）项目的知识库维护 SOP。凡用户要求新增/扩充/修正知识库条目、做 E 类任务卡（扩容/迁移）、修正误判后回填知识库、或审校 entries.json 的来源与生命周期标注时必须使用——即使没说"知识库"三个字。覆盖：来源铁律、字段纪律、去重与正则族指派、校验流程、误判当天进回归集。
---

# 知识库维护（磁盘体检 / kb-curator）

权威：`knowledge/schema.json`（schema v1，9 字段，additionalProperties: false）+ 《[项目治理](../../../docs/governance/项目治理.md)》§6。现状：`knowledge/entries.json` 503 条；校验器 `tools/validate_knowledge.py`（**无重名检查**——查重需一次性脚本辅助，这是已知限制）。先例：E3 执行记录（05_Sprint2 卡 T2-06）。

## 来源铁律（P10，不可协商）

- **全部自行整理**：本机实测（TreeSize 长尾、证据采集）+ 公开软件名（产品/厂商公开可查证）；**不复制 BCU 数据**；NOTICE 仅致谢思路。
- `source` 字段三值：`本机实测` / `公开软件名` / `推断`——观测事实填"本机实测"（即使分类依据是公开名，先例 `adrive`）；**不允许空值**。
- `lifecycle` 三值：`在用` / `已停止` / `未知`——**仅在有公开依据时填非"未知"**（先例：`atom` → 已停止，依据 GitHub 2022 官方停服公告）。拿不准就"未知"，置信度由引擎 5.1 规则给，不写死在知识库。

## 字段与命名纪律

- 12 类枚举照 `schema.json`（系统组件/兼容链接·严禁删除/已安装应用/使用中(无安装记录)/更新缓存/开发缓存/缓存/转储/游戏数据/残留候选·高中低置信/容器(已下钻)）；归档候选分析 CSV（`docs/upstream/output/`）是分类对照基线。
- `name` 统一小写；嵌套在已登记父目录下的子目录不重复登记（先例：wechat 不入，Tencent 已覆盖）；Microsoft 系目录由 S-1 硬保护处理，**不入库**；`programs`/`packages` 容器由规则层下钻，不入库；`.ini` 文件行排除。
- `regex_family` 只用既有族名：`updater-suffix`（*-updater）、`hash-name`（哈希）、`guid-name`（GUID）；新族先在 notes 说明模式再指派。
- `notes` 公开条目统一模板：`{product}（{vendor}）公开产品的数据目录命名；用途：{brief}`——不含推测性置信度表述。敏感目录（如 `.aws`）notes 注明"仅诊断，不读取内容"。
- 保持既有键序与缩进风格（合并脚本一次性完成，别手工散改）。

## 新增/扩容流程（E 类卡）

1. 求差集：候选来源（桌面 TreeSize CSV 长尾 / 公开软件清单）与现有 503 条去重（重名跳过并计数）。
2. 逐条定字段：name / product / vendor / aliases / category / lifecycle / regex_family / source / notes。
3. 写入 `knowledge/entries.json`（`schema_version: "knowledge.v1"` 容器结构不动）。
4. 校验：`python tools/validate_knowledge.py knowledge/entries.json` → 必须"全部符合 schema v1"；输出条目数、source 分布、lifecycle 分布、category 分布（超纲分类排末尾显式暴露，不静默丢弃）。
5. **提交 ≥20 条抽样清单**（名称/来源/类别/产品）供 PM 复核（DoR 级要求，先例 24 条）。
6. 测试联动：`tests/test_knowledge_schema.py` 等存量用例必须仍绿（部分用例断言条目数下限）。

## 误判修正流程（底线二：当天进回归集）

1. 修 `entries.json` 对应条目（改分类/生命周期/别名）。
2. **同一天**在 `tests/data/regression/` 增加回归样例（JSON 格式：case_id / 根因 / path_pattern / evidence_scenario / expect 含禁词断言——照 R001~R005）。
3. 跑 `python -m pytest`（裸跑）确认新样例绿。
4. 执行记录登记：误判原文、根因、修正链接。

## 红线

- 不复制 BCU 数据；引用外部结论（服务下线、项目停更）必须留公开依据于 notes。
- 不为"凑数"降低登记质量——来源登记字段缺失的条目会被 schema 拒绝（required）。
- 修正知识库 = 行为变更：涉及判定结果的修正必须走第"误判修正流程"，禁止只改 JSON 不加回归样例。
