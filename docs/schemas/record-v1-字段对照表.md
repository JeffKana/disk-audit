# record-v1 字段对照表（T5-01 · I1a 体检记录 JSON 存储基础）

本卡**不引入新记录 envelope**：落盘 JSON 就是一份 report-v1 形状的对象，字段语义、
枚举与版本口径全部沿用报告定稿，逐项对照见
[report-v1.schema.json](report-v1.schema.json) 与
[report-v1-字段对照表.md](report-v1-字段对照表.md)。权威实现：`disk_audit/records.py`；
接口/错误/命名边界见本文后半。本文是接口冻结与交接说明，不是新 schema。

## 1. report-v1 复用（存储内容边界）

存储只接受报告形状：顶层 `schema_version` / `generated_at` / `scan_root` / `totals` /
`candidates`，以及定稿已定义的两个可选字段 `admin_mode` / `incomplete`。
**任何未定义字段一律明确拒绝**（`RecordValidationError`），不悄悄持久化额外隐私数据；
因此不收原始采集 bundle、全量扫描文件清单、注册表/进程全量或 HTML 全文。
`totals`（五字段、非负整数）、`candidates[]`（七字段）、`evidence_chain[]`
（`source` 九值枚举 + `content` 字符串）逐项校验，口径与 report-v1.schema.json 一致；
空 `candidates` 为合法报告，可保存。

| 顶层字段 | 复用来源 | 记录侧语义 |
| --- | --- | --- |
| `schema_version` | Q7 | 版本语义不变：`1.0` / `1.1` 已知可读；不改 `REPORT_SCHEMA_VERSION`（仍 1.1）；不默默归一化版本 |
| `generated_at` | E-2 | 原样保存，ISO 8601 字符串 |
| `scan_root` | E-2 / 9.2 | 原样保存为字符串；**存储层不对该路径做任何文件系统操作** |
| `totals`（5） | 5.2 / P1 / X-1 | 双口径（allocated/logical）与两档小计、skipped 逐项保真 |
| `candidates[]`（7） | E-2 / 5.1 / 5.3 | 中文/Windows 路径、置信度四档、判定来源六值、建议动作 A1~A5、证据链逐项保真 |
| `incomplete`（可选） | X-2 / C7 | 为 `true` 时**拒绝保存**（不得存成完整体检记录）；`false` 不改写、原样保留 |
| `admin_mode`（可选，1.1） | S-3 / H4 / T4-04 | 为 `true` 时保存为管理员记录（admin- 前缀）；`1.0` 出现该键按坏 schema 拒绝 |

## 2. 版本与兼容语义（Q7 / I3 预留）

| 版本 | 读/写 | 消费口径 |
| --- | --- | --- |
| `1.0` | 可读、可保存（缺 `admin_mode` 合法） | 保持原字段，按**普通模式**消费（`admin_mode=False`）；旧记录可比 |
| `1.1` | 可读、可保存 | `admin_mode=true` 保留并标为管理员记录；不含该键即普通记录 |
| 其它主/次版本（如 `0.9`/`1.2`/`2.0`/`3.0`/非字符串） | **拒绝** | 抛 `RecordVersionError`，中文文案含"旧记录不可比"，由后续 UI 卡消费；不崩溃、不改义、不归一化 |

列举时合法记录 `comparable=True`；坏字段/损坏 JSON/不兼容版本逐项
`comparable=False + problem`（可披露），不阻断同目录其他合法记录，不静默说可比。
两次比较本身（T5-03/05）不属本卡。

## 3. 命名、读写与路径边界（U-2）

- 默认写入位：包内 `RECORDS_DIR` = `%LOCALAPPDATA%\DiskAudit\records`。
  测试根经 `records_dir` 注入；`save_record()` 不传 `records_dir` 时以替身验证默认位，
  不写真实用户数据。目录不存在时创建；被扫描目标（`scan_root`）零文件系统操作。
- 文件名由**模块生成并严格校验**，不接收调用方任意路径/文件名注入：
  普通 `record-YYYYmmdd-HHMMSS[-N].json`，管理员
  `admin-record-YYYYmmdd-HHMMSS[-N].json`（`N` 从 1 起）。
  逻辑 ID = 文件名主干（不含扩展名/路径），与物理路径分离：
  `save_record` 返回 ID，`read_record(ID)` 按 ID 读取，`list_records` 返回 ID/文件名。
  时间戳定长使字典序 = 时间序；同秒冲突追加序号，**绝不覆盖**既有记录。
- `resolve_record_path(directory, record_id)`：ID 不匹配命名模式（绝对路径、`..`
  上跳、子目录、双扩展名、非法时间戳等）抛 `RecordValidationError`；
  解析后必须落在授权根下，否则拒绝。调用前不产生任何写入。
- 原子发布：临时文件（`.tmp-record-*.json`）**只落同一授权目录**，完整写入并
  fsync 后经 `os.rename` 原子改名发布（Windows 下目标已存在即失败，不覆盖）。
  校验/序列化/写盘/发布任一失败均清理临时文件、不改动既有记录、不残留可见的
  半条正式记录；临时名不匹配记录命名模式，列举不会误认。
- 列举/读取只操作授权目录下本模块严格命名的**普通文件**：`os.lstat` 不跟随
  符号链接/重解析点，目录、重解析点、非普通文件一律拒绝/披露，不遍历扫描目标。
  真实 junction 在支持环境中验证，或用 `os.lstat`/`_read_raw` 替身（本卡测试二者
  均覆盖：伪装目录用真实目录，重解析点用替身，断言从未读取该项）。
- **根/祖先重解析点守卫（T501-RETURN-1 / DEF-2，PM 明确裁决）**：
  `save_record` / `read_record` / `list_records` 在 `makedirs`/`listdir`/文件读取/
  临时写入**之前**调用 `_require_safe_root(directory)`，由浅到深逐段 `os.lstat`
  （不跟随）核验从文件系统根到记录目录的**现有组成部分**：任一现有组成部分是
  junction/symlink/挂载点等重解析点或不是目录，即以中文 `RecordError` 停止并披露，
  绝不继续访问其子路径/target。首个缺失组成部分即停止核验（其下尚不存在，正常
  创建合法）；因此"祖先 junction + 末级目录缺失"同样被拒，"普通不存在根"仍可创建。
  不因 `records_dir` 由调用方显式传入而放宽为调用方责任。真实沙箱 root/ancestor
  junction 分别跑 list/read/save 验证 target 文件清单/字节/哈希不变、无临时或正式
  新记录；link/target 均在自己授权测试沙箱、创建前核对绝对路径、仅删除已核实
  junction 本身（不递归）。真实文件 symlink 无创建特权（WinError 1314）时保留
  lstat 替身并登记限制，不改系统策略/不升权。
- **坏容器类型（T501-RETURN-1 / DEF-1）**：四枚举位置（confidence/verdict_source/
  suggested_action/证据链 source）先做 `isinstance(str)` 与取值双重校验，list/dict
  等坏容器一律文档化 `RecordValidationError`；读取坏记录抛 `RecordError` 子类；
  列举逐项 `comparable=False + problem`、合法项仍返回，**不靠捕获一切异常返回空
  列表掩盖**。

## 4. 接口形状与异常类型（D-执行自决，已文档化）

公共函数（均带类型标注与中文 docstring）：

| 函数 | 签名要点 | 返回 / 异常 |
| --- | --- | --- |
| `validate_record(report)` | 纯函数，运行时校验形状 | 顶层浅拷贝 `dict`；`RecordValidationError` / `RecordVersionError` |
| `resolve_record_path(directory, record_id)` | 路径守卫 | 绝对路径 `str`；`RecordValidationError` |
| `save_record(report, *, records_dir=None, now=None)` | 校验 → 原子写盘 | 逻辑 ID `str`；写盘/发布失败由 `RecordWriteError` / `OSError` 露出并保证清理 |
| `read_record(record_id, *, records_dir=None)` | 按 ID 读取并校验 | 报告形状 `dict`；`RecordError` 子类 |
| `list_records(*, records_dir=None)` | 批量列举，逐项披露 | `list[RecordEntry]`；不因单条损坏而崩溃 |

异常层次（均继承 `ValueError`，便于与现有报告模块一致）：

```
RecordError(ValueError)
├── RecordValidationError   形状/字段/候选/多余字段/incomplete/非法 ID/越界
├── RecordVersionError      未知/不兼容版本（含"旧记录不可比"，可区分）
└── RecordWriteError        写盘/发布失败（含目标冲突拒绝覆盖）
```

`RecordEntry`（frozen dataclass）：`record_id` / `filename` / `comparable` /
`record`（dict|None）/ `problem`（str|None）/ `admin_mode` / `schema_version`。
损坏/不兼容项 `record=None`、`comparable=False`、`problem` 为中文披露文案。

中文错误文案全部集中在 `disk_audit/engine/texts.py` 文末本卡独立资源区
`RECORDS_TEXTS`（append-only，不改既有区/判定措辞，无"可回收"字样）。
T501-RETURN-1（OBS-1）进一步把 19 处固定校验细节（"应为对象/缺少字段/
非负整数/…非法"等）收口为本区模板键，位置/字段名/计数/路径等动态值走模板
参数；首轮 17 个键值逐字保持、仅在 T501 区扩充键，`records.py` 不再散落
固定对外中文，真实异常输出仍清晰可分类且无 Q3 禁词。

## 5. 错误边界汇总

| 反例 | 结果 |
| --- | --- |
| 非对象 / 缺必需字段 / 多余字段 / 坏 totals / 坏候选（枚举、证据链、负数、布尔当整数） | `RecordValidationError`，不写盘 |
| `incomplete=True` | `RecordValidationError`，不生成完整记录 |
| 未知主/次版本、版本非字符串 | `RecordVersionError`（含"旧记录不可比"） |
| 非法文件名 / 绝对路径 / `..` 上跳 / 伪装目录 / 叶重解析点 | 拒绝或披露，不在授权根外读写、不跟随 |
| 根或祖先为 junction/重解析点（含末级目录尚不存在） | `_require_safe_root` 在任何 FS 动作前逐段拒绝，`RecordError` 披露；target 文件清单/字节/哈希不变 |
| 四枚举位置为 list/dict 等坏容器 | 文档化 `RecordValidationError`；读取 `RecordError` 子类；列举逐项披露且合法项仍返回 |
| 损坏 JSON / 非 UTF-8 / 坏字段 / 不兼容版本（磁盘上） | 列举披露 `comparable=False`；读取抛 `RecordError` 子类；不阻断合法记录 |
| 同秒多份 | 追加 `-N` 序号，内容互异、互不覆盖 |
| 注入序列化/写盘/发布失败 | 既有记录 hash 不变，无半条正式记录、无临时残留 |

## 6. 本卡未做（保留为未尽事项，不宣称满足 I1 完整产品预算）

- **联合 50MB / 最近 12 次额度与按时间淘汰**：T5-04（本卡不做淘汰、不限制总量）。
- **报告/UI 保存接线、普通/管理员隔离与兼容提示展示**：T5-02（本卡不接线 launcher）。
- **两次对比（新增/减少/不变、净变化、范围/模式/版本校验）**：T5-03/05。
- **真实 VM / 远端 head / CI / 独立 DSH 验收**：由 PM 在冻结候选 SHA 后另行派发；
  本卡只交付本地可评审候选，不把本地绿当作最终验收。
- 不引入数据库、服务、外部依赖、新记录 envelope；不保存原始采集或 HTML。
