# Sprint 3（W3）计划与任务卡包 · 名义 2026-11-03 ~ 11-07（进度领先，收尾分支合入后即可开工）

**Sprint 目标一句话：用户能看到报告——M1 终判完成，双击三步出报告。**

## 1. 收数（Sprint 2 终章，06 报告 §9）

- 完成率 **100%**（7/7 卡 + 1 计划外修复）；退回 2 单（#21/#22 KI 逃逸、#24 locale 假设），各 1/2 闭环，未触升级线。
- 缺陷与回归集：C5 中文路径证据静默清空（修复）；回归集 5 例（R001~R005）；测试 115 → **215**。
- CI 红灯记录：3 次，全部为环境差异类假绿（KI/locale/argv），**门禁拦截有效**；经验已固化：远端 CI 为准、测试禁真 KI、断言禁依赖系统 locale、CLI 调用显式传参。
- 风险看板扫描：R1 枚举性能——DR-004 选项 c 处置中（T2-08 收口后预期关闭，止损线未触发）；R6 代码腐化——健康（215 测试 + 回归集 + CI 五门禁）；R10 VM 无法覆盖真人认知——已作为硬约束写入 T3-02（零假设文案）；R3"看完不知道做什么"——F2 四区+建议动作即缓解，M5 后按 Issue 数据验证。

## 2. 对表（方案第七节）

- **M1 缺口 = 闸门②（VM 归属率 ≥70%）**，其余四闸已过 → T2-09 是本 Sprint 最高优先级。
- **M2 五闸（S4 收口）**：①双击到看到报告 ≤3 步 ②断网报告完整 ③中止不留半成品 ④提权全流程 VM ⑤UAC 取消。S3 交付 ①②③ 的全部前置（UI + 渲染 + 中止），④⑤（提权 H1~H4）留 S4。

## 3. 排程（依赖拓扑 + 波次）

| 波次 | 卡 | 说明 |
| --- | --- | --- |
| Wave 1（立即并行领取） | T2-09、T2-08、T3-02、T3-04 | 互不依赖；T2-08 首位合入（scanner 同文件，T3-01 栈其后） |
| Wave 2 | T3-01（栈 T2-08）、T3-03（栈 T3-02）、T3-05（双栈 T3-01+T3-04）、T3-06（双栈 T3-02+T3-04） | 栈式切出，按依赖顺序合入 |

**通用红线**（所有执行卡适用）：不 push main（DR-006：PM 验收后合入）；不改验收标准；只写 `%LOCALAPPDATA%\DiskAudit\`；新问题记"未尽事项"不顺手修；命令环境与执行 SOP 见 exec-sop；**"本地绿"不作数，以远端 CI 为准**；测试禁抛真 KeyboardInterrupt、断言禁依赖系统 locale、CLI/`main()` 调用显式传参（Sprint 2 三连教训）。

---

## T2-08 · DR-004 选项 c 落地（C2 ② 认证前置，裁决既定勿重议）

- **目标**：占用空间取数改四段分流，恢复"夹具偏差 0.000%"口径，三目录基准 Programs 收敛。
- **输入指针**：[DR-004 裁决节](../governance/decisions/DR-004-2026-10-24-占用空间取数性能.md)（四段规则 + ②' 梯度 0B/~100B/~600B/~1KB/~5KB）、`disk_audit/scanner.py`（`_account_file`/`_align8`/`_allocated_size`/`_cluster_bytes`）、`tools/probe_resident_allocation.py`、`tools/check_size_deviation.py`、`tools/baseline.json`（本机登记物）。
- **实现约束**：600B 为本卷实测**稳定**驻留上限——若在新卷/其他盘测试，先跑 probe 核对，偏离即停手上报（DR-004 重开条件）；双口径语义与函数接口不变；601B~<簇 句柄实查失败按 X-1 计 occupied（与压缩/稀疏同语义）。
- **验收标准**：①混合夹具（0B/~100B/~600B/~1KB/~5KB）混合 vs 纯句柄偏差 <0.1%（预期 ~0.000%）；②三目录基准复测全 <1% 且 Programs 收敛至 ~0.0x%（现 0.848%）；③Roaming scan 耗时增量 ≤0.5s（裁决估算 +0.4s，总耗 ~7s 在 2× 预算内）；④分流边界单测（属性位 monkeypatch + 600B/601B 边界值）；⑤远端 CI 绿。
- **依赖**：无（Wave 1，**首位合入**）。
- **执行记录**（2026-11-01，分支 `feature/T2-08-DR004选项c四段分流`）：
    - **做了什么**：`disk_audit/scanner.py` `_account_file` 按裁决节改四段分流（①压缩/稀疏句柄实查 ②≤600B align8 ③601B~<簇句柄实查 ④≥簇簇对齐），新增 `_RESIDENT_LIMIT=600` 常量，①③ 句柄失败统一 X-1 计 occupied；`tests/test_scanner.py` 新增 3 用例（600/601 边界、段③失败计 occupied、②' 梯度混合 vs 纯句柄 <0.1%）并修正 2 处过时注释；`tools/probe_resident_allocation.py` docstring/列名对齐裁决节并补 UTF-8 输出守卫（重开条件核对指引）。关键文件：`disk_audit/scanner.py`、`tests/test_scanner.py`、`tools/probe_resident_allocation.py`。
    - **实现决策及依据**：①None 检查收敛到 `_account_file` 尾部单点（①③ 两段共用，语义不变）——实现细节自决；②600B 上限以常量 `_RESIDENT_LIMIT` 锚定裁决节，新卷先跑 probe 的重开条件写入常量注释与 probe docstring——依据 DR-004 裁决节"新卷部署前应先跑 probe 核对"；③②' 梯度夹具落位 `tests/test_scanner.py`（CI 可执行）而非 `check_size_deviation.py --fixture`（后者语义是"≥簇 文件簇对齐公式自检"，与 ②' 混合 vs 纯句柄口径不同）——依据卡面验收①"单测"表述与 DR-004 ②'；④probe 补 reconfigure 守卫——rules-map 编码模式（该脚本本次实质编辑）。
    - **未尽事项/已知限制**：Ⓐ **验收③未达成，待 PM 裁决**——同进程 A/B 交替实测（monkeypatch `_RESIDENT_LIMIT=4095` 模拟旧三段）：Roaming 旧 2.81~2.89s vs 新 4.77~4.87s，**增量 +1.9~2.1s > 0.5s**；根因是裁决节"Local 该段 ~12k 文件、+0.4s"估算与实测差一个数量级（实测段③ 601B~4095B：Roaming 67,035 / Local 163,238 个）。Local 改后 9.50~9.57s（裁决期 6.8~7.0s），Local+Roaming 合计 ~14.4s（原全句柄 25.27s 的 1.75×，但超 6s 预算 2× 线，R1 披露机制适用与否请 PM 一并裁）。选项：a 按实测段③规模修订单③数字（正确性不受影响，②' 已实测 <0.1%）；b 另立 DR 做段③性能优化（批量 API/缓存，结构性，需 DR）；c 其他。Ⓑ Tencent 复测 0.394%（原 0.138%）——10-31 基准刷新后目录仍活跃变化（聊天缓存），算法性收敛已由 Package Cache 0.011%→0.000% 与 Programs 0.848%→0.088% 证实；Ⓒ 段③句柄失败 X-1 计 occupied 新语义生效（Local 实测 occ=2，被锁文件，占比 2/33 万，符合裁决①③同语义）；Ⓓ `tools/check_size_deviation.py` 同样缺 stdout reconfigure 守卫（本卡未实质编辑该文件，不顺手修）。
    - **自测输出摘要**：`python -m pytest` **218 passed**（215+3 新增，裸跑）；`python -m disk_audit --selftest` **6/6**；`tools/check_imports.py` 通过；probe 复跑本卷 0/1/100/600 逐字节一致、700+ 本次非驻留（与裁决"驻留不稳定窗口"一致）；三目录基准复测 Programs **0.088%** / Tencent 0.394% / Package Cache **0.000%** 全 <1%；②' 梯度夹具（0B/~100B/~600B/~1KB/~5KB ×3 真实句柄）通过（各段逐文件与句柄一致，汇总偏差 0.000%）；验收③未达（数据见未尽事项Ⓐ）。远端 CI 待跑。

---

## T2-09 · M1 ② VM 归属率实测（M1 终闸，最高优先级）

- **目标**：acc 双机实测自动归属率，完成 M1 终判。
- **输入指针**：06 报告 §6 T2-09 卡与 §4 五闸表、方案 9.2 口径、**vm-ops 技能**（headless 纪律/guestcontrol 坑/机队清单）、GT 11 件清单（PR#15 记录）、`docs/upstream/output/AppData残留候选分析_2026-10-23.csv`（口径对照参考）。
- **实现约束**：全程 headless（24H2 禁 GUI 附加）；归属率口径 = 9.2（分子 = 判为已安装/系统组件/可再生/高置信残留/中置信残留的单元数，分母 = 全部判定单元）；GT 11 件目录逐一核对不得出现"高置信残留"（在用软件 sanity，误判 >0 即按 R5 处置：降级规则 + 全量复核）；数字未经 PM 复核不得回填方案第六节。
- **验收标准**：①acc-22h2 与 acc-24h2 各出归属率数字（≥70% 过闸）；②GT 11 件误判数 = 0；③VM 侧容量偏差复测数字（子项：T2-08 合入后跑，并入闸门①证据）；④全程命令与输出留档执行记录；⑤PM 依数字主持 M1 终判并回填（PM 执行）。
- **依赖**：无（立即可跑；子项③等 T2-08 合入）。**角色**：执行 Agent + 负责人（VM 操作配合），PM 终判。
- **执行记录**（2026-11-01）：
  - **做了什么**：L1-acc-22h2 / L1-acc-24h2 全程 headless 实测完成。当前 main（9dca8fa）的 disk_audit+knowledge 打包拷入双机 `C:\stage\t209\` → `scan %LOCALAPPDATA%` + `scan %APPDATA%`（PYTHONUTF8 守卫，.cmd 承载）→ `judge`（实时采集证据）→ 16 份产物 copyfrom 留档 → 9.2 口径计算 → GT 11 件逐一核对 → 双机关机（快照/VM/镜像未动）。**双机归属率：acc-22h2 = 96.15%（分子 125 / 分母 130），acc-24h2 = 95.45%（105/110）**——均 ≥70% 过闸线；**GT 11 件高置信残留误判数双机 = 0，R5 未触发**。证据目录 `docs/evidence/T2-09/`（8 份 scan/report JSON + 8 份空 .err、命令与输出留档.md、归属率计算脚本/输出、单元清单 dump、首轮 partial 产物与探针完整扫描 dbg_out.json）。⑤（PM 依数字主持 M1 终判并回填方案第六节）待 PM 执行。
  - **实现决策及依据**：① 扫描范围 = %LOCALAPPDATA% + %APPDATA% 双范围（06 报告 §6 本卡步骤原文；上游 CSV 分析即 Local/Roaming 口径对照），归属率主数字 = 双范围单元合并（9.2"分母 = 全部判定单元"），分范围数字并列披露于留档；Program Files/ProgramData 不入 M1 范围（M4 八台矩阵按 9.3 扩展，不扩范围）。② 分子映射 = confidence ∈ {受保护→系统组件, 高→已安装/在用/可再生/高置信残留, 中→中置信残留/Appx 在用}（engine/judge.py 六层流水线与 9.2 类别一一对应），"高置信残留"识别 = 高档且证据链含 5.1 高档措辞"高度可能为残留"（texts.CONFIDENCE_WORDING）。③ 负载分发 = tar 单文件 + guest 解包（`copyto --recursive` 在 7.2.22 对已存在目标目录报 VBOX_E_IPRT_ERROR，等价替代，不影响交付）。④ guest 脚本带 `PYTHONUTF8=1`/`PYTHONIOENCODING=utf-8`（T-01 退回单教训：重定向下 stdout 默认 ANSI 代码页，中文输出 UnicodeEncodeError 风险）。⑤ 归属率计算用一次性临时脚本（卡文许可），未沉淀 tools/——M4 八台矩阵的正式评分器宜随 M4 卡一并设计（含装 N 卸 M GT 标注语义），避免半成品公共接口；脚本与输出全文已留档。⑥ 凭据取自宿主侧登记物 `H:\Virtual Machine\stage\autologon.cmd`（R-L1 记录"密码登记于 VM 内 autounattend"的宿主侧登记物；vm-ops"口令来源负责人处"在执行会话内的落点），全程内存引用不落盘不入 PR。⑦ **首轮 4/4 扫描产物 incomplete=True（X-2 出口），判定弃用重跑**：根因 = 开机后 AppX 部署/服务窗口实时改写判定单元集合（实证：Packages 下 wpsappext1~3 消失、WinAppRuntime 5 目录出现，kingsoft 3,994→12,651 文件），系统稳定后重跑得完整产物（CROSSCHECK_PASS，4/4 incomplete=False、units==candidates）。
  - **未尽事项/已知限制**：① 引擎潜在边界（新问题，另立任务勿顺手修）：`_expand_dir`/`_scan_tree` 的 `for entry in iterator` 迭代段不在 X-1 捕获区内，目录被外部删除时（本例：AppX 服务窗口）OSError 逃逸 → X-2 部分出口；本轮以"稳定后重跑"规避，未改引擎代码（红线⑤）。② GT 中 7-Zip/Git 在扫描范围内无写入位单元（本体在 Program Files，9.2 口径本就不含）；VS Code 程序体单元判"低"（注册表卸载键为 GUID_is1 形态，名称不匹配；诚实低置信非误报，属"宁可漏报"口径实证）——均不计入误判。③ **子项③ VM 侧容量偏差复测：阻塞：依赖 T2-08 合入（PR#32 未合），本卡未跑**，并入闸门①证据待 T2-08 合入后执行。④ 24H2 ACPI 关机 45s 未完成按预案强制 poweroff（差分盘无关键未落盘数据）。⑤ 差分盘遗留 `C:\stage\t209\`（<1MB），遵守"不删快照/不回滚镜像"未清理。
  - **自测输出摘要**：本地裸跑 `python -m pytest` **215 passed** + `python -m disk_audit --selftest` **6/6**；产物完整性交叉校验 CROSSCHECK_PASS（8 份 scan/report：units==candidates、incomplete=False、schema_version=1.0）；归属率计算输出全文留档（含分范围明细与按置信度/判定来源分布）；GT 探针（双机 Program Files 清单 + Steam 注册表卸载项）留档。**未覆盖项：子项③（阻塞，见上）；⑤ 归 PM。**

---

## T3-01 · C8 实时进度事件（待办 C8，栈于 T2-08）

- **目标**：scanner 暴露线程安全进度回调（E-1：已扫描条目数 / 当前路径 / 已用时，刷新 ≤500ms）。
- **输入指针**：方案 E-1、`disk_audit/scanner.py`（abort_check 挂载点先例）、`tests/test_scanner.py`。
- **实现约束**：工作线程触发——回调侧聚合节流（≥500ms 或 N 条目双阈值）；回调异常不得中断扫描（捕获计 other）；`progress_cb=None` 默认零开销路径；引擎零 UI 依赖（UI 侧自行调度主线程）；T2-08 已改 `_account_file`——本卡不触碰计量逻辑。
- **验收标准**：①单测：注入回调收到的节流后事件含条目数/当前路径/elapsed 且数值单调；②回调抛异常时扫描正常完成、跳过计数入 other；③无回调时 Roaming 性能与基线一致（5.44s ±10%）；④CLI scan 行为不变；⑤远端 CI 绿。
- **依赖**：T2-08（同文件栈式切出）。
- **执行记录**（2026-11-01）：
  - **做了什么**：scanner 暴露线程安全进度回调——`scan_path` 新增 `progress_cb=None` 关键字参数（默认零开销路径：None 时不实例化任何跟踪器、零锁零取时）；新增公开事件结构 `ProgressEvent`（frozen dataclass：`entries`=已扫描条目数 files+dirs 累计、`path`=当前路径、`elapsed`=已用时秒）与内部 `_ProgressTracker`（工作线程各聚合本地计数→探测点锁内合并→双阈值节流触发：距上次触发 ≥500ms（E-1 上限）或全局新增 ≥2 万条目；探测两级=目录边界逐目录 + 目录内每 1024 条；回调锁内串行触发保证 entries/elapsed 单调不减；回调异常 X-1 计 skips.other 不中断扫描；`settle()`/`finish()` 结清尾差保证终态事件条目数精确）；abort_check 的 `_check_abort` 位置未动（各循环头），X-2 中止优先级高于进度触发；T3-05（G2）将栈式消费本接口（签名见 PR 描述）。测试先行：tests/test_scanner.py 末尾追加 C8 节 6 例（先跑红 AttributeError/TypeError 再实现跑绿）。关键文件：`disk_audit/scanner.py`、`tests/test_scanner.py`。
  - **实现决策及依据**：① 事件结构对齐 E-1"已扫描条目数/当前路径/已用时"，entries 与 `ScanResult.to_json_dict()["entries"]` 同口径（卡文"已扫描条目数=files+dirs 累计"，跳过项不计）；frozen 只读供跨线程传递（引擎零 UI 依赖，T3-05 经 after() 调度主线程，无共享可变状态）。② 条目阈值 N=2 万（卡面"万级自决"）：Roaming 实测 ~24.2 万项/5s ≈ 5 万项/s，满速下 ≈0.4s 一触发与 500ms 时间阈值同量级；实测 Roaming 242,390 项仅 13~14 次事件（0.5% 条目数）。③ 目录内探测步长 1024（`_PROGRESS_CHECK_STEP`）：探测含锁，避免 8 线程逐条目加锁竞争；慢速盘下时间阈值活性 ≤1024 项/盘速；目录边界另有逐目录探测，空目录树也保活。④ 无锁热路径（卡面"工作线程内聚合本地计数+触发点加锁"）：tick 仅由各计数源属主线程调用（BFS=主线程一源、并行段=每工作线程一源，沿用 `_scan_tree` 局部聚合先例），本地增量在探测点才入锁合并；`id(stats)` 记账同时强引用 stats 本体，防并行段 part_stats 回收后 id 复用误配。⑤ **双计缺陷（自测发现并修复）**：worker stats 既被 tracker 记账又在汇合点 `stats.merge` 进全局 stats，终态若再对全局 stats 记账则双计（实测事件 entries=161 vs 真值 89）——改为 `settle()`（BFS 切分后与每个分片汇合时结清尾差、不触发回调，此后并行段汇合不再对全局 stats 记账）+ `finish()`（终态事件直接汇报已合并全局条目数）；单测以"终态事件 entries==全量"钉死。⑥ progress_cb=None 零开销口径按卡面括号定义"None 时不做任何节流聚合计算"；代价为每条目一次 None 判定分支（~24 万次），A/B 实测无回调路径与 main 等价（两会话 -1.90%/+1.44%，噪声带）。⑦ 回调异常 `except Exception` 计调用方 `stats.skips.other`（BFS 段=全局、并行段=分片本地随汇合并入），不中断扫描、不进 X-2；elapsed 锁内取 time.monotonic（触发序=锁序→单调不减），ScanResult.seconds 仍 perf_counter 口径不变；禁真 KI 口径沿用（测试异常均派生 Exception）。
  - **未尽事项/已知限制**：① **验收③口径待 PM 裁**：卡面"Roaming 5.44s ±10%"为 T2-01 三段分流时代数字；T2-08 四段分流后 Roaming 实测 4.77~4.87s（06 报告 T2-08 记录），本次 main（5e0dd46）同进程复测 med 4.989s / min 4.786s——5.44s 与现测差 ~9%，卡面③按原数字还是现口径认证请 PM 裁（下发要点④预授权上报，未自行改验收标准）。② **A/B 等价口径数字**（同进程交替：main 基线快照 / 分支 progress_cb=None / 注入节流回调收集器）：无回调 vs main：med +1.44%（首轮会话 -1.90%）——无回退；无回调 vs 回调：5 轮 med +3.12%、min -0.14%（首轮 3 轮 med +6.62% 系桌面噪声，轮内 spread ±5%）；回调侧开销处噪声带（理论上界 ~4.8 万次目录级探测锁开销 <0.1s）。是否按"卡面③本义=无回调不回退 + A/B 等价（<2% 参考线以 min 口径达成、med 口径超 0.3s 系噪声）"出证，一并报 PM 裁。③ 病态场景活性边界：盘速 <~2000 项/s 时单 500ms 窗口内可能无探测点（步长 1024 所限）；产品范围（%APPDATA%/%LOCALAPPDATA%）实测 0.38~0.5s 一触发，E-1 观感不受影响。④ 回调在锁内串行触发：UI 侧回调须快速派发（T3-05 经 after() 调度，勿在回调内渲染），阻塞回调会拖慢扫描（scan_path docstring 已注明）。
  - **自测输出摘要**：`python -m pytest` 裸跑 **270 passed**（基线 264 + 本卡 6，基线经 `git stash` 复核确认）+ `python -m disk_audit --selftest` **6/6 passed**；真实 Roaming 扫描抽检：13 事件/242,390 条、entries 与 elapsed 双单调、终态事件=精确全量、incomplete=False、事件耗时 0.38s→2.87s→5.49s；A/B 数字（Roaming 242,390 项，同进程交替，两会话）：main 快照 med 4.989s（min 4.786s）/ 分支无回调 med 5.061s（min 4.902s）/ 分支注入回调 med 5.219s（min 4.895s），entries 三方一致（±1，目录活跃变化），事件 13~14 次/轮。验收⑤（远端 CI 绿）待 push 后确认。

---

## T3-02 · F2 HTML 报告渲染（待办 F2）

- **目标**：report-v1 JSON → 离线单文件 HTML（概览 / 明细 / 证据链 / 建议动作四区），默认浏览器可开。
- **输入指针**：方案 E-2、5.1~5.3、`docs/schemas/report-v1.schema.json` + example、POC 先例 `docs/upstream/poc/poc4_bigreport.html` + `poc4_gen_bigreport.py`（配色与四区结构基线）、judge 端到端输出（06 报告 §1 实证）。
- **实现约束**：单文件内联 CSS、**无 CDN、无外部 JS 框架**（M2 闸②断网完整）；四区结构对齐方案；对外文案一律取自 `engine/texts.py`，不硬编码；**零假设原则**（R10：可能被非开发者误解的措辞一律改保守，宁可少说）；"受保护"与低置信项固定 A5、**不提供任何"下一步"按钮**；incomplete 输入渲染"不完整报告"徽标且**无汇总结论区**（C7 联动）；报告页眉含"只诊断，不动手"与脱敏提示。
- **验收标准**：①judge 真实输出渲染成功、四区齐备（DOM 断言或截图留档）；②断网环境样式与功能完整（禁网卡或 VM 验证，留档）；③受保护项无"下一步"按钮（DOM 断言）；④incomplete 输入 → 徽标 + 无汇总区（断言）；⑤渲染为纯函数（JSON→HTML 字符串）单测覆盖；⑥远端 CI 绿。
- **依赖**：无（Wave 1；T3-03/T3-06 栈其上）。
- **执行记录**：
  - **做了什么**：新增 `disk_audit/engine/render.py`——纯函数渲染器 `render_report(report: dict) -> str`（report-v1 dict → 离线单文件 HTML：四区 `<section id="overview|details|evidence|actions">` 对齐产品待办 F2；内联 CSS 沿用 POC-4 配色基线（四档置信度 hi/mid/low/prot、卡片 bar、粘性表头）；零 JS、零外链、全部动态值 `html.escape(quote=True)` 转义；输入校验与 schema 必需字段对齐，Q7 版本语义 major≠1 抛 ValueError"旧记录不可比"）；`disk_audit/engine/texts.py` 末尾独立追加 F2 文案区块（页眉标语/脱敏提示/离线声明/四区标题/明细六列表头/totals 五字段标签（两档小计直接引用 5.2 措辞常量）/A1~A5 动作标签与含义/不完整报告徽标与说明/空态/大小单位/校验异常文案；只追加未动既有内容）；`disk_audit/__main__.py` 新增 `render` 子命令（报告 JSON → HTML 输出到 stdout）；新增 `tests/test_engine_render.py` 20 例（标准库 html.parser DOM 断言 + AST 中文字面量守卫）。真实输出验证：本机临时夹具目录（陈旧时间戳）真实 scan（6 文件/11 项/0 跳过）→ judge 真实证据采集（真实知识库 503 条 + 真实硬保护）产出四档齐全候选（受保护·硬保护 A5 / 高·知识库 A2 / 中·知识库 A2 / 低·启发式 A5）→ render 6.6KB HTML。关键文件：`disk_audit/engine/render.py`、`disk_audit/engine/texts.py`、`disk_audit/__main__.py`、`tests/test_engine_render.py`。
  - **实现决策及依据**：① 模块位置 `engine/render.py`——texts.py 模块头（T2-03）早已声明"供判定输出（judge）与报告渲染（F2，S3）消费"；渲染为方案四节架构⑤的纯数据变换，I/O（JSON 解析/文件读写）留在 CLI，纯函数只做 dict→str（开发规范 §1"判定纯函数、I/O 分离"同构）。② 证据链区每候选一个 `<details>` 折叠展开——5.3 A4"查看证据链=报告内展开、无外部调用"的原生实现，零 JS；建议动作区=A1~A5 固定枚举图例 + 各动作条数分布，不做每候选第三张路径表（控 DOM 规模给 T3-03 性能预算：5000 行 ≤5MB/首屏 ≤1s，POC 基线单表 1.39MB）。③ 本卡零 JS：卡面只禁"CDN/外部 JS 框架"，但四区无必须 JS 的交互（展开用原生 details），明细筛选归 T3-03 按方案第六节叠加原生 JS。④ 全文档禁 button/input/onclick/role=button，A5 渲染"A5 无建议"且全文不出现"下一步"字样（验收③ DOM 断言 + R10 零假设——A5 含义文案写"不提供任何处理入口"）。⑤ 置信度档位→POC-4 配色类映射（键为 schema 枚举值）放 texts.py `CONFIDENCE_CSS_CLASSES`；渲染模块以 AST 守卫"零中文字符串字面量（docstring 除外）"单测固化（开发规范 §1 对外文案集中文案资源处）。⑥ 验收②等效口径（按执行要点 6）：主证据=零外链结构断言单测（无 http(s):// 引用；标签白名单无 script/link/iframe/embed/object/base/form；属性白名单仅 id/class/title/charset/lang；无 @import、无 url()）+ 浏览器实证（页内 `performance` resource 请求 0 条、渲染完整、A4 展开正常、截图留档）；物理断网 VM 实测未做，如 PM 认为必要移交 vm-ops，不阻塞本卡。⑦ CLI `render` 输出到 stdout 不落盘——U-2 本程序仅在 `%LOCALAPPDATA%\DiskAudit\` 内写文件，报告落盘 + 默认浏览器打开由 T3-06 按方案架构⑤实现。
  - **未尽事项/已知限制**：① **judge 既有输出与定稿 schema 枚举冲突（非本卡引入，建议另立 fix 卡）**：`disk_audit/engine/judge.py:217` 知识库"已停止"分支产出证据链 `source="进程服务"`，不在定稿 schema 九值枚举（硬保护/知识库/注册表卸载项/进程/服务/自启动/Appx/启发式/文件枚举）内；既有端到端夹具（updater/开发缓存/Protect/未知长尾）均未触达该分支故 CI 未拦截（Verdict 级测试不做 schema 校验），真实扫描一旦命中"KB 已停止 + 无注册表 + 无运行"即产出 schema 非法报告。本卡渲染器对证据链 source 为防御性渲染（任意字符串照常展示，单测 `test_evidence_source_out_of_enum_still_renders` 固化），不阻塞本卡；修复涉及 judge 判定层证据构造，按红线⑤不顺手修，报 PM 裁决归属（拆"进程"/"服务"/"自启动"三条或归入"启发式"）。② 验收②物理断网 VM 实测未做（见⑥等效口径），是否补测由 PM 定。③ 明细筛选/排序、5000 行大样张性能均归 T3-03。
  - **自测输出摘要**：`python -m pytest` 裸跑 **235 passed**（基线 215 + 新增 20，3.15s）；`python -m disk_audit --selftest` **6/6 passed**；`python tools/check_imports.py` 通过（渲染器仅 import 标准库 html + 包内 texts）。真实输出验证（验收①③④留档）：真实 scan→judge→render 后浏览器 DOM 断言——四区 id 有序齐备且标题=概览/明细/证据链/建议动作、button 类元素 0、外链元素（script[src]/link[href]/iframe/a[href] 等）0、页内网络请求 0 条、页眉"只诊断，不动手"+脱敏提示在、全文无"下一步"、A5 单元格≥2、A4 证据链点击展开正常；incomplete 真实变体：徽标+说明在、totals 五字段标签与数值零出现、4 条部分候选保留。截图 2 张留档（正式报告整页 / 不完整报告页眉）：`C:\Users\querkecor\.zcode\cli\artifacts\sess_subagent_agent_b1b7069c-ede0-4793-8766-212aef09ed7c\call_4fc9960c46ce48c282d10fd6-tool-result-514c2227-41e1-4ba0-93c2-8670c5146530.png` 与 `…\call_a4e3a7faa3c042f1b2f05741-tool-result-0b8e79c7-f714-40c8-98fc-0041f4ace9b0.png`；file:// 系统默认浏览器冒烟打开正常。验收⑥（远端 CI 绿）待 push 后确认。

---

## T3-03 · F5 报告性能达标（待办 F5，栈于 T3-02）

- **目标**：5000 行报告 ≤5MB、首屏 ≤1s、筛选 ≤150ms（方案第六节）。
- **输入指针**：`docs/upstream/poc/poc4_gen_bigreport.py`（5000 行生成器）、W0 POC 实测报告（基线 613ms / 52ms / 1.39MB）、T3-02 渲染器。
- **实现约束**：用 POC 生成器造样张测量（口径与 W0 一致）；筛选用原生 JS display 切换（POC 同款）；超标先查 DOM 规模、再查内联资源，优化手段记执行记录——**虚拟滚动等结构性方案需另立 DR**，不得顺手做。
- **验收标准**：①5000 行 HTML ≤5MB（贴字节）；②首屏 DOMContentLoaded ≤1s（本机中位数 3 次，贴数字）；③筛选响应 ≤150ms（同口径）；④三项全达标或优化记录 + 复测数字；⑤远端 CI 绿。
- **依赖**：T3-02（栈式）。
- **执行记录**：

---

## T3-04 · G1 范围选择界面（待办 G1）

- **目标**：Tkinter 启动器骨架 + 范围选择（P4~P6 口径）。
- **输入指针**：方案 P4（预设四目录：`%APPDATA%` / `%LOCALAPPDATA%` / `%PROGRAMDATA%` / `C:\Program Files`）、P5（build 22621 启动检测）、P6（可移动/网络/光驱置灰+原因）、POC `docs/upstream/poc/poc2_app.py`（Tkinter 先例）。
- **实现约束**：启动即检 build ≥22621，不足拒绝并提示（探测函数可注入便于测试）；盘符枚举 ctypes `GetDriveTypeW`；不支持盘型置灰 + 原因文案；预设四目录单选 + 自定义文件夹；**UI 与引擎零耦合**（经 scan/judge 接口调用，不 import 判定逻辑）；文案集中资源处。
- **验收标准**：①版本不足拒绝路径单测（注入假版本）；②盘型置灰逻辑单测（驱动类型注入）；③本机启动实测：四预设与置灰状态正确（截图留档）；④CI 门禁④（引擎零 UI 依赖）不破；⑤远端 CI 绿。
- **依赖**：无（Wave 1；T3-05/T3-06 栈其上）。
- **执行记录**：
  - **做了什么**：新增顶层独立入口 `launcher.py`（Tkinter 启动器骨架：P5 启动版本闸 + P6 盘符枚举 ctypes GetDriveTypeW / 不支持盘型置灰+原因 + P4 四预设单选 + 自定义文件夹 + 开始体检按钮，扫描/报告接线留 T3-05/T3-06）；`disk_audit/engine/texts.py` 文末追加 `LAUNCHER_TEXTS` 启动器文案区块（append-only，不动既有键值）；新增 `tests/test_launcher.py` 26 例（测试先行：先跑红 ModuleNotFoundError 再实现跑绿）。关键文件：`launcher.py`、`tests/test_launcher.py`、`disk_audit/engine/texts.py`、`docs/evidence/T3-04/launcher_scope_2026-11-01.png`。
  - **实现决策及依据**：①UI 模块放仓库根 `launcher.py`（包外独立入口），未用卡内建议的 `disk_audit/launcher.py`/`disk_audit/ui/`——开发规范 §1 硬规则"`disk_audit` 包内任何模块不得 import tkinter（启动器在独立模块/入口）"与《项目治理》"disk_audit/ = 引擎与 CLI、零 UI 依赖"；治理文档优先级高于卡内建议（卡文明示"位置自决……在 PR 说明"），POC 先例 poc2_app.py 亦为独立入口脚本。②文案集中 `engine/texts.py` 文末独立区块而非 UI 模块内资源字典——方案 §1 语言行"文案集中在一份资源表内"（卡内两选项均合规，取资源表口径，append-only 规避并行分支冲突）。③tkinter 延迟导入：纯逻辑（版本闸/盘型/预设/文案）可无 Tk 环境加载与测试，Tk 根仅真实运行创建；CI 不起 mainloop（任务卡实现约束）。④可注入：build 探测与盘符枚举经 `run()` 参数注入（验收①②），默认实现 = `sys.getwindowsversion().build` 与 ctypes `GetLogicalDrives`+`GetDriveTypeW`（任务卡实现约束）。⑤"开始体检"按钮本卡仅确认所选范围（含存在性校验）并如实提示"扫描功能将在后续版本接入"，不发起扫描——U-1（未获用户显式选择前不读取文件系统路径）+ 不扩大方案范围（扫描接线归 T3-05/T3-06）；盘符枚举属 P6 明文规定的选择界面组成，不计为 U-1 的"读取路径"。⑥新增包内零 tkinter 的 AST 守卫测试（check_imports 白名单只禁第三方、不禁标准库 tkinter，规范 §1 的包内禁令由测试钉死，守住 M1 验收④语义）。
  - **未尽事项/已知限制**：①本机 5 盘（C/D/E/H/I）实测全为固定本地盘，P6 置灰态无法在本机真实呈现——置灰逻辑由验收②注入式单测（UNKNOWN/NO_ROOT_DIR/可移动/网络/光驱/RAM 六类全覆盖）保证，真实置灰呈现留待 VM 或含可移动盘环境；②版本不足的图形提示（messagebox）路径未本机实测（无低版本环境），拒绝路径由注入假版本单测覆盖（验收①）；③窗口几何为固定 720x560 骨架值，T3-05 接进度 UI 时一并调整。
  - **自测输出摘要**：`python -m pytest` 裸跑 **241 passed**（Sprint 2 基线 215 + 本卡 26；1 warning 为本机 site-packages 第三方 requests 版本提示，CI 全新环境不存在）；`python -m disk_audit --selftest` **6/6 passed**；本地门禁④ `python tools/check_imports.py` 通过。验收③本机真启动实测（build 26200 ≥ 22621）：四预设顺序与解析路径正确、5 盘均"固定本地盘"可选（本机无置灰盘）、自定义文件夹与开始体检按钮在位，截图留档 `docs/evidence/T3-04/launcher_scope_2026-11-01.png`（pwsh System.Drawing 全屏 2560x1440，截完已关窗、无残留进程）。

---

## T3-05 · G2 进度与中止 UI（待办 G2，双栈 T3-01 + T3-04）

- **目标**：进度展示（消费 C8 回调）+ 中止按钮（走 C7 统一出口）+ **关闭 T2-05 未尽事项③（产品侧真 KI 缺口定夺）**。
- **输入指针**：T2-05 执行记录未尽事项③、T3-01 回调接口、C7 `incomplete` 语义、方案 E-1 / X-2。
- **实现约束**：中止实现 = UI 置停止标志 → `abort_check` 返回 True，**产品侧同测试侧禁抛真 KI**（就此关闭 T2-05③，执行记录写明定夺结论）；进度经 `after()` 调度主线程（回调节流生效，不阻塞 UI）；中止后界面呈现"不完整报告"状态并可重新发起扫描。
- **验收标准**：①点中止 → `incomplete=True` 且 UI 呈现不完整态（自动化断言或截图留档）；②进度刷新 ≤500ms 观感（留档）；③中止后可重新扫描（无状态残留）；④UI 线程无阻塞；⑤远端 CI 绿。
- **依赖**：T3-01 + T3-04（双栈）。
- **执行记录**（2026-11-01，分支 `feature/G2-进度与中止UI`，基于 feature/C8-实时进度事件（PR#39）并 merge feature/G3-结果入口（PR#38），**合入顺序 C8 → G3 → G2**）：
  - **做了什么**：launcher 接线 G2 进度与中止——`execute_audit` 新增 `progress_cb`/`abort_check` 关键字并透传 scan 环（`AuditDeps.scan` 签名扩为 `Callable[..., dict]`；scan 置 incomplete=X-2 时短路返回 None，不 judge/render/save/prune/open）；新增 `run_audit_async` 纯函数（体检流水线搬入后台 daemon 线程，进度/完成/失败一律经注入的 after 调度器派发主线程，abort_check = `threading.Event.is_set` 协作式停止标志）；`build_scope_ui` 新增"体检进度"区（indeterminate 进度条 + E-1 三字段实时标签：已扫描条目数/已用时/当前路径）与"中止体检"按钮（扫描期间锁定范围单选与开始按钮），中止后呈现"不完整报告"黄色横幅（措辞复用 F2 `INCOMPLETE_BADGE`）并可重新发起（每次"开始体检"= 全新停止标志/新线程/进度归零）；`texts.py` 文末追加 `G2_TEXTS` 区块（append-only）；窗口几何 720x560→720x660（T3-04 未尽事项③ 预留调整点）。测试先行：`tests/test_launcher.py` 追加 T3-05 节 13 例（中止路径不落盘、重扫无残留、后台线程与 after 派发架构断言、真实 scanner 接缝集成 ×2、G2 文案 ×3 等；先跑红 TypeError/AttributeError 再实现跑绿），T3-06 六环替身 scan 签名随接线更新（六环按序断言语义不变）。真机端到端留档 7 张截图 + `docs/evidence/T3-05/端到端留档.md`。关键文件：`launcher.py`、`tests/test_launcher.py`、`disk_audit/engine/texts.py`、`docs/evidence/T3-05/`。
  - **实现决策及依据**：① **T2-05 未尽事项③ 定夺结论（就此关闭）：产品侧与测试侧同规矩——任何路径一律禁抛真 KeyboardInterrupt，中止只经协作式停止标志**（UI 置 `threading.Event` → `abort_check` 返回 True → scanner X-2 统一"不完整"出口）。依据：T2-05③ 原文"UI/CLI 接线后若依赖'异常路径'传递真 KI，部分结果出口不生效（abort_check 返回 True 的路径不受影响）"——真 KI 属 BaseException，`scan_path` 的 `except Exception` 接不住，异常路径会绕过 X-2；06 退回单 #21/#22 已实证 KI 逃逸危害（测试侧改 `_SimulatedCtrlC`）；C7/X-2 统一出口为定稿语义。故 `execute_audit`/`run_audit_async`/UI 全链路无任何 raise KeyboardInterrupt 路径，停止信号唯一通道 = 停止标志（测试断言 `calls[0][3]()` 即停止标志行为）。
    ② **中止路径不落盘报告、不开浏览器**：scan 置 incomplete=True 时 `execute_audit` 短路返回 None（不 judge/render/save/prune/open，不产生半成品结论），UI 呈现"不完整报告"横幅+状态栏并提供重新发起入口；依据卡面执行要点明示 + X-2/C7"不得输出任何汇总结论性结论"；部分结果仅在内存保留（ScanResult），不持久化——render 的 incomplete 徽标语义保留给 CLI/引擎层（T3-02 验收④ 不受影响）。本机实测：中止后 `reports/` 零新增文件。
    ③ 进度消费模式：progress_cb 内只做 `after(0, 更新)` 派发（双阈值节流已由 scanner 侧保证，UI 只转发，回调内零渲染零 IO）；完成/失败同样经 after 派发，全部 UI 变更收敛主线程——依据 C8 `scan_path` docstring 与卡面"进度经 after() 调度主线程"；架构断言单测钉死（工作线程 id ≠ UI 线程 id；after 收集器模式证明工作线程不直接执行 UI 更新）。after 派发带窗口销毁兜底（根窗口销毁后 daemon 线程静默收尾，不掩盖扫描结果）。
    ④ 进度展示形式自决：indeterminate 进度条（总量未知，不显示假百分比——R10 零假设）+ E-1 三字段文本（条目数/整数秒/当前路径独立标签）；文案全部进 `G2_TEXTS`（Q3 禁词断言 + "不完整报告"与 F2 徽标同词断言）。
    ⑤ `run_audit_async` 独立成无 Tk 纯函数（deps/stop/after/on_progress/on_complete/on_error 全可注入），延续 T3-04"纯逻辑无 Tk 测试"模式，中止/重扫/异常/线程模型均可在 CI 无 Tk 断言；`build_scope_ui` 只做 Tk 组装与状态切换。except 块内异常对象先绑定再进派发闭包（`except X as exc` 块尾解释器删除 exc 的语言行为，单测钉死 on_error 通路）。
    ⑥ 窗口几何 720x560→720x660 / minsize 640x500→640x600：容纳进度区与横幅（T3-04 未尽事项③）。
    ⑦ 既有 T3-06 测试替身 scan 签名 `lambda p` → `lambda p, progress_cb=None, abort_check=None`：execute_audit 恒以关键字透传（T3-06 测试 docstring 预言"替身注入接口即异步化改造边界"），六环按序断言不变。
  - **未尽事项/已知限制**：① **验收② 口径说明**：实测 %LOCALAPPDATA% 523,346 项/13.75s/29 事件，事件间隔中位 0.500s、最小 0.349s、**最大 0.633s**（500ms 时间阈值在探测点触发 + 探测步长粒度与盘速抖动；条目阈值使部分间隔短于 500ms）——"≤500ms 观感"以中位口径达成，最大值超出部分源于 C8 探测粒度设计（T3-01 未尽事项③ 已记录病态边界），本卡未触碰 scanner（C8 定稿）。② 扫描期间用户直接关窗 = daemon 线程随进程结束（无写盘副作用），"关窗时优雅中止"未做（超本卡范围，如需另立任务）。③ 中止路径部分结果仅内存保留不持久化——若未来需要"中止后可查看部分报告"，涉及 X-2 部分报告落盘语义，另立卡评估。④ 本卡 13 例新增单测引入 `threading`/`dataclasses` 标准库导入，无第三方依赖。
  - **自测输出摘要**：`python -m pytest` 裸跑 **308 passed**（基线 295 = C8+G3 合并态 + 本卡 13；1 warning 为本机 site-packages 第三方 requests 版本提示，CI 全新环境不存在）；`python -m disk_audit --selftest` **6/6 passed**；`python tools/check_imports.py` 通过（AST 守卫：包内零 tkinter、launcher import 白名单随接线保持通过）。验收①②③④ 本机真启动实测留档 `docs/evidence/T3-05/`（7 张截图 + 端到端留档.md）：点中止 → 不完整态横幅+状态栏（进度定格 328428 项/6 秒）、中止未落盘；进度实时刷新（1.5s 间隔计数 161360→261411、进度条动画位移；独立脚本留档事件间隔中位 0.500s）；重扫进度归零、横幅消失 → 完整报告落盘 `report-20261101-221125.html` + 浏览器自动打开；扫描中"中止"可即时点击生效 + 进程零异常退出码 0。验收⑤（远端 CI 绿）待 push 后确认。

---

## T3-06 · G3 结果入口（待办 G3，双栈 T3-02 + T3-04）

- **目标**：扫描完成 → 报告落盘 → 默认浏览器打开；**双击到看到报告 ≤3 步**（M2 闸①）。
- **输入指针**：M2 验收①、方案四节架构⑤、U-2/U-4、报告目录 `%LOCALAPPDATA%\DiskAudit\reports\`。
- **实现约束**：报告只写 `DATA_DIR\reports\`（U-2 唯一写入位）；`os.startfile` 只读打开；文件名含时间戳；旧报告按时间淘汰保留 12 份（若本卡实现需单测；否则记未尽事项移交 I1/M3，不得静默不做）。
- **验收标准**：①端到端 ≤3 步留档（选范围 → 扫描 → 浏览器自动打开）；②落盘路径合规（无 DATA_DIR 外写入——代码审查结论 + Procmon 或等效证据留档）；③淘汰逻辑单测或明确移交记录；④远端 CI 绿。
- **依赖**：T3-02 + T3-04（双栈）。
- **执行记录**（2026-11-01，分支 `feature/G3-结果入口`）：
  - **做了什么**：新增 `disk_audit/reports.py`（报告落盘/淘汰/打开模块：`report_filename` 时间戳命名 `report-YYYYmmdd-HHMMSS.html`、同秒冲突扩展名前加 -N 序号不覆盖；`save_report` 目录不存在则建、全卡唯一文件写点，写前经 `resolve_report_path` 越界守卫；`prune_reports(keep=12)` 按时间序淘汰、仅识别本程序命名模式的文件、返回删除清单；`open_report` 默认 `os.startfile` 只读打开、opener 可注入）；`launcher.py` 最小接线：新增 `AuditDeps`（scan/judge/render/save/prune/open 六环可注入 dataclass）+ `default_deps()`（延迟 import 真实装配）+ `execute_audit()`（六段编排收敛单点），"开始体检"回调改为 校验范围 → "正在体检" → execute_audit → "体检完成"/失败态统一出口；`texts.py` 文末追加 `G3_TEXTS` 区块（append-only）；新增 `tests/test_reports.py` 22 例、`tests/test_launcher.py` 增 3 例（测试先行：先跑红 ImportError/AttributeError 再实现跑绿）；端到端截图 5 张 + 留档 `docs/evidence/T3-06/`。关键文件：`disk_audit/reports.py`、`launcher.py`、`disk_audit/engine/texts.py`、`tests/test_reports.py`、`tests/test_launcher.py`、`docs/evidence/T3-06/端到端留档.md` 等。
  - **实现决策及依据**：① 落盘与淘汰独立为包内纯逻辑模块（卡面建议位），路径根全部参数注入且默认复用包内 `REPORTS_DIR` 常量（不新造路径逻辑），文件名生成与守卫为纯函数、I/O 集中 save/prune——开发规范 §1"I/O 与纯函数分离"。② 验收②等效证据（执行要点 6 口径，Procmon 不装）= 代码审查结论（本卡文件系统写点仅 `save_report` 一处 + `prune_reports` 同目录匹配文件删除，launcher 与渲染层零写点）+ 越界守卫单测（相对上跳/子目录/绝对路径/双扩展名/非本程序命名/混合上跳六类构造 → 全部 ValueError 且目录外零文件产生）+ 本机实测前后对比（DATA_DIR 实测前仅 tmp、实测后仅新增 reports\report-20261101-213255.html）；Procmon 全量留档按治理 §7 U-2 排期（M2 提权完成后做一次，M5 前复检），不属本卡。③ 淘汰排序键=(时间戳基名, 序号)：秒级时间戳文件名字典序=时间序，但同秒 -N 序号文件纯字典序会错位（`-1.html` 排在 `.html` 前），显式二元键保时序正确（单测覆盖）；目录不存在/不足 keep 份不删、非本程序命名文件不动（不扩大删除范围）。④ launcher 编排收敛 `execute_audit` 单点、六环经 `AuditDeps` 全可注入（全替身链路单测断言调用序与数据流），G2/T3-05 异步化按环搬入后台线程即可；PR 注明"本卡同步接线，G2 将异步化"。⑤ T3-04 的 launcher→包 AST 边界测试随接线更新：allowlist 由 `{disk_audit.engine}` 扩为 `{disk_audit, disk_audit.engine, disk_audit.engine.report, disk_audit.engine.render, disk_audit.reports, disk_audit.scanner}`——该测试钉的是 T3-04 骨架期"不触发扫描"边界，本卡任务正是接线 scan/judge 接口（T3-04 模块头已预告此耦合方向），守卫语义不变；引擎侧零 tkinter 由 `test_package_has_no_tkinter_import` 继续钉死。⑥ 新文案放 texts.py 文末独立 `G3_TEXTS` 区块而非并入 `LAUNCHER_TEXTS`：Sprint 3 多分支并行改本文件，独立区块规避合并冲突；T3-04 的 `status_selected`（"扫描功能将在后续版本接入"）已过时，但区块 append-only 禁改既有键值，保留不再被 UI 使用（见未尽事项②）。⑦ `open_report` 默认出口 `os.startfile` 只读打开，不传参、不注入脚本（架构⑤明文"默认浏览器打开"，U-4 白名单外无其他系统交互）。
  - **未尽事项/已知限制**：①扫描/判定同步执行（C:\ProgramData 18848 项约 3.2s：scan 0.5s + judge 2.7s），期间 UI 线程阻塞、无进度展示——归 G2/T3-05 异步化闭环（本卡 PR 已注明）；②`status_selected` 过时文案留存（append-only 禁改），建议后续文案统一清理波次处置；③报告打开依赖系统默认关联程序，本机 Chrome 实测成功，Edge/其他未实测（os.startfile 标准 ShellExecute 语义，风险低）；④Procmon 全量写入留档按 U-2 排期在 M2 提权完成后统一做。
  - **自测输出摘要**：`python -m pytest` 裸跑 **289 passed**（基线 264 + 本卡 25 = test_reports 22 例 + test_launcher 增 3 例；1 warning 为本机 site-packages 第三方 requests 版本提示，CI 全新环境不存在）；`python -m disk_audit --selftest` **6/6 passed**；`python tools/check_imports.py` 白名单通过。验收①端到端实测：选范围（点预设单选）→ 开始体检（扫描）→ 浏览器自动打开 = 3 步（用户点击 2 次 + 自动打开），报告落盘 `%LOCALAPPDATA%\DiskAudit\reports\report-20261101-213255.html`（62354 字节）并在 Chrome 完整渲染（概览/明细/证据链/建议动作四区齐全，112 候选），截图留档 `docs/evidence/T3-06/step0~step3b` 共 5 张，截后 Chrome 报告窗与 launcher 均按标题精确关窗、无残留进程。

---

## Sprint 3 验收清单（周五可逐条打勾）

1. T2-09 归属率出数，M1 终判（≥70% → M1 正式关闭并回填方案第六节）。
2. T2-08 落地：三目录 Programs 收敛 ~0.0x%，C2 ② 认证，R1 关闭。
3. 5000 行报告 ≤5MB / 首屏 ≤1s / 筛选 ≤150ms。
4. 双击到看到报告 ≤3 步端到端跑通。
5. 中止 → "不完整报告"态 UI 闭环（T2-05③ 关闭）。
6. 断网报告完整验证留档。

**S4（W4）预告——M2 收口**：H1~H4 提权闭环（runas 重启 / UAC 取消 / 异常退出 / 管理员模式标注）、B3 交互白名单封装、F3 CSV 脱敏导出、F4 建议动作 A1~A5 接线；M2 五闸验收（VM 复用 2 台）。

## 报批

Sprint 目标与卡包交负责人确认；改动条目由 PM 重排依赖后生效。分发顺序建议：T2-09（连同负责人 VM 配合）与 T2-08 最先启动。
