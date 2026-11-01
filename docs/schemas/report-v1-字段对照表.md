# report-v1 字段对照表（T2-07 · F1 定稿验收③）

定稿 schema：[report-v1.schema.json](report-v1.schema.json)；引擎输出实现：`disk_audit/engine/report.py`。逐项对照方案定稿条目（E-2 / 5.1 / 5.2 / 5.3 / 9.2 / X-1 / E-4 / X-2 / Q3 / Q7 / 架构③）。

## 顶层字段

| schema 字段 | 方案依据 | 说明 |
| --- | --- | --- |
| `schema_version` | Q7 | 版本语义：`major.minor`。结构破坏性变更 → major+1，消费方提示"旧记录不可比"（联动 I3）；非破坏可选新增 → minor+1；禁止原地改义。定稿锁 `1.0` |
| `generated_at` | E-2 | 报告生成时间，ISO 8601 含时区 |
| `scan_root` | E-2 / 9.2 | 扫描根（判定单元划分的范围） |
| `totals.allocated_bytes` | P1 | 汇总一律用占用空间口径 |
| `totals.logical_bytes` | P1 | 双口径之一，仅呈现不作汇总 |
| `totals.regenerable_subtotal` | 5.2 第一档 | "可再生：应用会自行重建"（更新缓存/缓存转储）；两档分别列示 |
| `totals.regenerable_confirm_subtotal` | 5.2 第二档 | "可再生但需确认：清理后需重新下载，可能影响离线构建"（开发缓存等；注意：知识库 12 类无"下载缓存"独立类别，暂由"缓存/转储"覆盖） |
| `totals.skipped_entries` | X-1 / E-4 | 未扫描/跳过条目数，不得静默吞掉 |
| `candidates[]` | E-2 / 9.2 | 判定单元逐条候选（顶层目录及下钻子项，文件级不单独计入） |
| `incomplete`（可选） | X-2 / C7 | 中止/异常部分结果标记；true 时 totals 判无效、不作为完整体检结论；正常报告不含本键 |

## 候选条目七字段（E-2）

| schema 字段 | 方案依据 | 说明 |
| --- | --- | --- |
| `path` | E-2 / 9.2 | 判定单元路径 |
| `logical_bytes` | E-2 / P1 | 逻辑大小 |
| `allocated_bytes` | E-2 / P1 | 占用空间（DR-004 三段分流口径） |
| `confidence` | 5.1 | 四档枚举 高/中/低/受保护；触发条件与输出措辞逐字对照见 `disk_audit/engine/texts.py`（tests/test_engine_wording.py 锁定）；受保护项不提供任何"下一步"入口 |
| `verdict_source` | 架构③ | 六层顺序：硬保护 → 知识库 → 注册表 → 进程服务 → Appx → 启发式（顺序短路） |
| `evidence_chain[].source` | E-2 / evidence.v1 | 枚举九值 = 六源（注册表卸载项↔uninstall、Appx↔appx、进程↔processes、服务↔services、自启动↔autostart、文件枚举↔文件枚举器）+ 判定层三源（硬保护/知识库/启发式）；残留类判定首条为 5.1 输出措辞 |
| `evidence_chain[].content` | E-2 / A4 | 人读证据内容；服务证据统一"唯一路径"口径并在 content 披露（验收报告 §3.3） |
| `suggested_action` | 5.3 | A1 复制路径 / A2 打开所在文件夹 / A3 打开系统应用列表 / A4 查看证据链 / A5 无建议（受保护与低置信固定 A5）；受 U-4 白名单约束 |

## 硬规则贯穿项

- **Q3**：全文不出现"可回收"，不给"可释放 X GB"合并总量（schema `additionalProperties:false` 字段集锁定 + 测试负例）。
- **S-1**：硬保护命中固定"受保护"档 + A5，不参与打分、不可配置覆盖。
- **S-2**：仅启发式命中置信度上限锁"低"，措辞无倾向。
- **9.2 归属率口径**：分子 = 已安装/系统组件/可再生/高置信残留/中置信残留 单元；低置信与归属未知计入分母不计入分子。

## 版本与升级规则（Q7）

- 定稿 `1.0`；候选七字段与 totals 五字段为定稿基线。
- 结构破坏性变更（删字段/改语义/收紧枚举致旧记录非法）→ `2.0`，联动 I3"旧记录不可比"提示。
- 可选字段新增（先例：`incomplete`）→ `1.1`，旧消费方按 additionalProperties 兼容。
