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
  - **做了什么**：新增 `disk_audit/elevated.py`（spec 写入/原子消费/校验、runas 命令构造、R9 只读证据装配、admin- 前缀报告落盘、done 标记、提权编排 run_elevated_rescan 退出码三态 0/4/5）；`launcher.py` 新增宿主侧发起链（`_shell_execute_runas` 单点 → `_launch_elevated_self` → `request_admin_rescan`，仅由范围区新按钮"以管理员身份重扫"单击回调 `_on_admin_rescan` 调用）、`_elevated_deps`（提权流水线装配：save=admin- 前缀、prune/open 双 no-op、judge 只装配 winreg 只读证据源）、`--elevated-rescan` CLI 分支 `_cmd_elevated_rescan`（复用 execute_audit，不进 UI）；`texts.py` 文末追加 H1_TEXTS 区块（append-only）；新增 `tests/test_elevated.py` 52 例（spec 往返/校验反例/一次性消费/runas 参数断言/编排三态/R9 证据降级/防重生 AST 断言/注入式全链）；真机操作单 `docs/evidence/T4-01/真机验收操作单.md`。
  - **实现决策及依据**：①**防重生四道结构性防线**（超出卡面自保，前两次执行曾产生 python 进程自重生链 34 进程、根因未确证）：自重启单点化（全仓库 ShellExecuteW 仅 `launcher._shell_execute_runas`，提权分支 `_cmd_elevated_rescan`/`_elevated_deps`/`execute_audit` 及 elevated.py 全模块 AST 断言零 ShellExecuteW/WinExec/os.system/os.popen/subprocess/os.startfile）；spec 一次性消费（os.rename 原子认领即焚，Windows 同目录目标存在即 FileExistsError，并发双实例必有一个被拒；重复/陈旧/无请求一律 EXIT_BAD_REQUEST=4 拒绝退出，单测覆盖"同一 spec 第二次执行被拒绝"）；UI 仅单击触发（request_admin_rescan 调用点唯一且仅在 _on_admin_rescan，AST 断言每环引用数=1，无重试/轮询路径）；测试与自动化零循环触发。②**R9 证据降级**：提权实例只装配零子进程的 winreg 只读证据源（注册表卸载项/自启动），Appx/进程/服务三源（需 powershell 外部程序）不采集并按方案口径"该证据源不可用"降级披露（方案八节安全边界"提权进程不执行任何外部程序"+R9 行+卡面"代码路径不得出现网络/子进程调用"；披露经 reason/done 标记 evidence_note 字段，供 T4-04 报告标注承接）。③**admin- 前缀落盘**：先经 reports.save_report 守卫写入再同目录改名（写入位不变 U-2；不触碰 reports.py 逻辑），admin- 名不匹配淘汰正则=独立记录（S-3，清理归 T4-04/M3）。④**CLI 固定位**：`--elevated-rescan` 不接受 spec 路径参数，固定读 `tmp\spec.json`（减小提权面；卡面允许"spec路径或固定位"）。⑤**依赖倒置**：elevated.py 不 import launcher（run_elevated_rescan 经 audit/deps 双注入复用 execute_audit，防循环 import）。⑥E-5 取消/发起失败仅透传返回码（>32 已发起；1223=取消），不弹框不重试（卡面"本卡只留接口位"）。⑦UI 入口常显（不按"存在跳过条目"条件显隐）：M2 闸④只要求入口存在；E-4 启动器侧"未扫描条目数"展示属既有范围外，记未尽事项。
  - **未尽事项/已知限制**：①提权实例证据降级后，判定层无法区分"证据源不可用"与"无匹配"（judge.py 四区结构不触碰），KB"已停止"层的"无匹配进程/服务/自启动"证据项在提权报告中语义弱化——建议另立任务（judge 感知 available 或 T4-04 报告字段披露）；②E-4"启动器同时展示未扫描条目数"未实现（需宿主侧最近一次扫描状态，与 H 系列记录接线归后续卡）；③提权实例与宿主无进程级等待通道（ShellExecuteW 不返回句柄），H3 需经 done 标记轮询或改 CreateProcess（接口已留：done 三态+退出码 0/4/5）；④真实 UAC 端到端由主会话按操作单执行；⑤验收④（netstat 抽查）已列入操作单由真机验收执行。
  - **自测输出摘要**：`python -m pytest` 裸跑 **368 passed**（基线 316 + 本卡 52，0 failed）；`python -m disk_audit --selftest` 6/6 passed；`tools/check_imports.py` 白名单通过；真实 CLI 冒烟：陈旧 spec 被拒（"请求已超时效（2046s > 600s）"）退出码 4、消费即焚、零扫描零 UAC、无 done。验收①③单测全绿；**验收②未由执行侧执行**（真实 UAC 触发移交主会话按 `docs/evidence/T4-01/真机验收操作单.md` 执行，终态以该次留档为准）；验收④netstat 抽查列入操作单真机执行；验收⑤待远端 CI。


---

## T4-02 · H2 UAC 取消处理（待办 H2，栈 T4-01）

- **目标**：UAC 取消 → 保留原报告、不重试、无错误弹窗，仅提示"已取消，结果未变更"（E-5）。
- **输入指针**：方案 E-5、T4-01 产物、`launcher.py` 提示文案机制。
- **实现约束**：`ShellExecuteW` 返回 `ERROR_CANCELLED` 判定精确（不得把其他失败误判为取消）；提示为非阻塞状态栏文案（沿用 G2 状态栏）；**不弹错误对话框**（E-5 明文）。
- **验收标准**：①取消路径单测（注入 ERROR_CANCELLED）；②本机端到端：UAC 弹窗点否 → 状态栏提示 + 原报告不变（截图留档）；③重试计数为零断言（无自动重试路径）；④远端 CI 绿。
- **依赖**：T4-01（栈式）。
- **执行记录**：
  - **做了什么**：`launcher.py` 新增纯函数 `admin_rescan_status_text`（ShellExecuteW 返回码 → 状态栏文案三态映射：`ERROR_CANCELLED(1223)`→H2 取消文案、`>32`→H1"已发起"、其余 ≤32→H2 独立失败文案并如实披露返回码），`_on_admin_rescan` 尾部由 T4-01 占位的"仅 >32 提示"改为三态一律经该纯函数写入状态栏（G2 非阻塞先例，零弹窗）；`texts.py` 文末 append-only 追加 H2_TEXTS 区块（`status_admin_cancelled`/`status_admin_launch_failed` 两键，上方既有内容零改动）；新增 `tests/test_launcher_h2.py` 27 例（判定精确含反例/零弹窗 AST/零重试 AST+行为/取消后原报告与 done 零变更/回调接线/H2 文案区块）；新增 `docs/evidence/T4-02/` 注入式端到端留档（方法+观测 JSON+截图 `注入式取消-状态栏截图.png`）。
  - **实现决策及依据**：①**判定精确的分支顺序关键点**：`ERROR_CANCELLED(1223)` 数值上 >32，是 Win32">32=已发起"惯例的例外——取消判定必须**先于** >32 判定；T4-01 占位实现先判 >32 会把取消误判为"已发起"（E-5 违规），测试先行跑红（注入 1223 期望取消文案、实得"已发起"文案）捕获后修正（依据：Win32 ShellExecuteW 返回值语义 + elevated.py 接口约定 4 + E-5）。②**取消与"其他失败"严格分流**：仅 1223 显示 E-5 文案（原文短语"已取消，结果未变更"完整保留为文案子串），其余 ≤32 值（NotFound=2/AccessDenied=5 等）走独立失败文案、不冒充取消——X-4"管理员重扫失败，已保留上次结果"完整失败语义归 T4-03（任务卡设计节明文"本卡只保证不误判归取消"）。③**判定收敛为模块级纯函数**（无 Tk/无 I/O，AST 断言其调用集 ⊆ {format}、零自启动引用）：T4-01 既有 AST 契约（`request_admin_rescan` 引用数==1 且调用点唯一在 `_on_admin_rescan`，tests/test_elevated.py）锁死"把调用抽出发起工厂"的重构路径，故采用"回调保持单点调用 + 判定外提纯函数"的最小改动形态（任务卡"改动收窄到取消回调与状态栏文案"）。④**零重试双保险断言**：AST（回调恰一次发起 + 零循环/零 after 调度/零线程引用）+ 行为（替身调用计数在呈现环节前后恒为 1）。⑤**测试落新文件** `tests/test_launcher_h2.py`（匹配卡面 tests/test_launcher*.py 新区块；规避 Sprint 红线"改既有测试语义与新增测试不得同文件并行"与 T4-03/T4-04 并行同文件冲突）。⑥**文案措辞**：取消文案"管理员重扫已取消，结果未变更。"（E-5 原文短语完整子串 + 主体语境）；失败文案"管理员重扫未能发起（返回码 {code}），结果未变更。"（事实性披露，不预支 X-4 措辞）。⑦**验收②注入式替代**：本宿主管理员会话 runas 静默通过、UAC 弹窗物理不可复现（T4-01 事故取证 host_is_admin:true），以"真启动 launcher UI + 替身返回 1223 + 真实点击回调 + 状态栏控件实时读取 + 截图"替代，`disk_audit.TMP_DIR` 重定向演示目录（真实 `%LOCALAPPDATA%\DiskAudit\` 零触碰），终态以 R-M2 VM 复验为准（留档 `docs/evidence/T4-02/注入式取消端到端留档.md`，报 PM 认定）。
  - **未尽事项/已知限制**：①真实 UAC"弹窗点否"路径由 R-M2 VM 复验覆盖（VM 恢复 UAC 提示模式后测）；②发起失败（≤32 且非 1223）的完整 X-4 语义（"已保留上次结果"提示、宿主等待提权实例退出码）归 T4-03，本卡仅保证独立状态栏文案不冒充取消；③Win32 未 document 的其他 >32 非 1223 返回码按"已发起"口径处理，若 R-M2/VM 实测发现异常返回值另立任务。
  - **自测输出摘要**：`python -m pytest` 裸跑 **395 passed**（基线 368 + 本卡 27，0 failed）；`python -m disk_audit --selftest` **6/6 passed**；`tools/check_imports.py` 白名单通过；注入式端到端：状态栏控件实时文本="管理员重扫已取消，结果未变更。"、发起计数=1（verb=runas）、零 done 标记、零弹窗、零残留进程（tasklist 核对）、真实数据目录零触碰（截图 `docs/evidence/T4-02/注入式取消-状态栏截图.png`）；验收①③单测全绿；验收②注入式替代 + R-M2 覆盖（报 PM 认定）；验收④待远端 CI。

---

## T4-03 · H3 提权进程异常退出（待办 H3，栈 T4-01）

- **目标**：提权实例崩溃/被杀 → 保留普通模式既有报告，提示"管理员重扫失败，已保留上次结果"（X-4）。
- **输入指针**：方案 X-4、T4-01 产物。
- **实现约束**：宿主侧等待提权实例退出码；异常退出（非 0 且非取消）→ 既有报告/体检记录**零改动**；提示走状态栏（同 H2 风格）；崩溃现场信息记 tmp\\ 日志（U-2 合规位）供排查。
- **验收标准**：①注入提权实例异常退出单测；②本机端到端：宿主报告 hash 前后一致（零改动断言）+ 提示留档；③远端 CI 绿。
- **依赖**：T4-01（栈式）。
- **执行记录**：
  - **做了什么**：宿主侧等待通道按任务卡**方案 A** 落地（`launcher.py`）：`_shell_execute_runas` 由 ShellExecuteW 升级为 **ShellExecuteExW + SEE_MASK_NOCLOSEPROCESS**（成功时 `SHELLEXECUTEINFO.hProcess` 即提权实例句柄；函数名保留作 AST 单点锚点），发起返回码在函数内**归一化为 ShellExecuteW 风格**（成功哨兵 33 / 取消 1223 / 其余=GetLastError 错误码）——T4-02 `admin_rescan_status_text` 及其全部既有测试零改动通过；新增等待链：`wait_admin_rescan_exit`（WaitForSingleObject 上限 15 分钟 → GetExitCodeProcess → 读 done 标记，Win32 调用全部可注入替身）+ `_watch_admin_rescan_async`（后台 daemon 线程等待，UI 零阻塞，G2 run_audit_async 先例）+ 纯函数 `_admin_rescan_failed`/`admin_rescan_finish_text`（X-4 判定与呈现同一事实源）+ `_write_admin_rescan_failure_log`（tmp 日志 `admin_rescan_failure.log`：时间戳+request_id+退出码+等待摘要+done.error 并入，写入口可注入、写失败不阻断呈现）；`request_admin_rescan` 增可选 `wait_completion`/`after` 接线（缺省 None 保持 T4-01 火后不管语义；取消 1223 与发起失败不进等待链——T4-02 语义不重做）；`_on_admin_rescan` 传入呈现回调（`_on_admin_rescan_finished` 经 `_dispatch_admin_finish`/root.after 派发主线程）；`texts.py` 文末 append-only 追加 H3_TEXTS 区块（`status_admin_rescan_failed`=X-4 原文"管理员重扫失败，已保留上次结果。"/`status_admin_rescan_completed` 两键）；新增 `tests/test_launcher_h3.py` 53 例（参数化计；X-4 判定含反例/等待替身注入零真实等待/日志内容与写失败降级/发起链接线/超时与取消不进等待链/报告 hash 零改动/done 不写不删/AST 零弹窗零重试等待链零自启动/归一化回归）；`tests/test_elevated.py` 仅双禁最小修改（`test_shell_execute_w_exists_only_in_launcher_single_point` 禁令扩为 ShellExecuteW/ShellExecuteExW 双禁，修改处注明依据 H3 卡面，其余用例零改动）；新增 `docs/evidence/T4-03/` 注入式端到端留档（方法+观测 JSON+截图 `注入式异常退出-状态栏截图.png`）。`disk_audit/elevated.py` **零改动**（退出码契约够用，规避与 H4 并行分支冲突面）。
  - **实现决策及依据**：①**等待通道方案 A**（任务卡三选一倾向 A，采纳）：ShellExecuteW 不返回进程句柄，无法区分"硬杀无痕迹"与"长扫描未完成"（方案 B done 轮询判定不精确，否）；CreateProcess 重写发起链破坏 T4-01 verbs="runas" 契约面（方案 C，否）；ExW+NOCLOSEPROCESS 对外返回码归一化后 T4-02 判定面零改动（卡面关键约束达成）。②**等待超时上限自决 15 分钟（900000ms）**：卡面建议值；普通模式全盘扫描实测分钟级（方案 X4 风险项"全盘 > 60s → 降级目录级"口径），15 分钟远超常规扫描预算并给慢盘/大目录留余量；超时**不清杀**提权实例（可能仍在运行，日志如实标注"可能仍在运行"），呈现按 X-4（R10 零假设：超时与崩溃同一文案，不咬定"崩溃"，细节进日志）。③**退出码域无"取消"语义**：发起阶段 1223（UAC 取消）不进等待链（T4-02 已实现不重做）；提权实例退出码 0=成功/4=拒绝/5=流水线失败（elevated.py 契约），硬杀=任意非 0 值（含 1223/4294967295）一律非 0 即异常→X-4（单测反例面覆盖）。④**exit 0 但 done 缺失/未完成 → 防御性按 X-4 处置**：契约违背场景不虚报成功（R10），细节进日志（event=exit0_done_invalid）；测试反例覆盖。⑤**句柄不 CloseHandle**：宿主单次用户触发流程，等待后即弃，宿主进程退出统一回收，无累积风险（不扩大方案范围）。⑥**发起失败 >32 且非 1223 的 Win32 错误码**按 T4-02 既有记录口径透传（其实测罕见；T4-02 执行记录已明文"另立任务"承接口径，本卡不改 T4-02 判定面）。⑦**等待线程化**：15 分钟同步等待会冻结 Tk 主循环，故等待入后台 daemon 线程+root.after 派发（G2 run_audit_async 先例）；回调内保持零循环/零 after/零线程引用，T4-02 全部 AST 断言零改动通过。⑧**测试落新文件** `tests/test_launcher_h3.py`（H2 先例：规避与 H4 并行分支同文件冲突）。⑨**验收②注入式替代**：本宿主管理员会话不可复现真实"杀提权进程"且被禁止触发 UAC，以"真启动 launcher UI（真实 mainloop）+ 替身句柄/退出码 5 + 真实回调链与等待链 + 状态栏控件实时读取 + 真实 reports 目录逐文件 sha256 前后一致 + 截图"替代（`disk_audit.TMP_DIR` 重定向演示目录，真实 `%LOCALAPPDATA%\DiskAudit\` 零触碰）；驱动 v1 手动 update() 泵下 `_tkinter` 拒绝跨线程 after 派发（呈现未落定），v2 修正为 mainloop 事件流后全链走通——驱动层问题非产品问题（生产 mainloop 运行中派发与 G2 先例同款），如实留档 `docs/evidence/T4-03/注入式异常退出端到端留档.md`。
  - **未尽事项/已知限制**：①真实提权实例被杀/崩溃的物理场景由单测注入矩阵（退出码 4/5/1/2/259/1223/4294967295/超时/WAIT_FAILED/GetExitCodeProcess 失败）覆盖，VM 实杀复验若需要另立任务；②等待超时后提权实例可能仍在运行并最终写 done/admin- 报告（宿主不消费，呈现按 X-4）——done 标记的后续消费语义归 T4-04/M3；③发起失败 >32 且非 1223 码按 T4-02 既有口径呈现"已发起"（承接口径，若实测出现另立任务）；④发起成功但句柄不可用（ExW 返回成功而 hProcess=NULL，DDE 类启动理论场景）时回退 T4-01 火后不管语义（不等待、不日志），实测未出现；⑤双击重扫按钮可在等待期内再次发起（每次点击=新请求，T4-01 既有语义，本卡未加等待期按钮锁——如需 UX 收敛另立任务）。
  - **自测输出摘要**：`python -m pytest` 裸跑 **448 passed**（基线 395 + 本卡 53 例参数化计，0 failed，约 6s）；`python -m disk_audit --selftest` **6/6 passed**；T4-02 全部既有测试（tests/test_launcher_h2.py 27 例）零改动通过；注入式端到端：状态栏控件实时文本="管理员重扫失败，已保留上次结果。"、发起计数=1（verb=runas、参数含 --elevated-rescan）、真实 reports 10 文件 sha256 前后零差异（零改动断言）、真实 tmp 无 spec/done、演示 tmp 仅 spec.json+失败日志、零弹窗、零残留进程（tasklist 核对）（截图 `docs/evidence/T4-03/注入式异常退出-状态栏截图.png`）；验收①②单测+端到端全绿；验收③待远端 CI。

---

## T4-04 · H4 管理员模式标注与独立记录（待办 H4，栈 T4-01）

- **目标**：管理员模式报告显著标注（S-3）；作为独立体检记录，不与普通记录自动对比（M3 预备）。
- **输入指针**：方案 S-3、F1 定稿版本语义（docs/schemas/report-v1.schema.json）、`engine/render.py` 页眉、`engine/report.py`。
- **实现约束**：报告数据结构新增管理员模式字段**必须遵循 F1 定稿版本语义**（新增字段是否触发版本升级按定稿规则判定，升级则同步 I3"旧记录不可比"联动预留）；render 页眉徽标（管理员模式，POC 配色类）；**体检记录管理本身属 I1/M3**——本卡只做到"输出结构可区分 + 不写普通记录键"，记录存储联动在 M3。
- **验收标准**：①新增字段过定稿 schema 校验（或按版本语义升版后校验）；②render 管理员模式徽标 DOM 断言；③管理员/普通报告在输出结构上可区分（单测）；④普通模式输出不受影响（回归）；⑤远端 CI 绿。
- **依赖**：T4-01（栈式）。
- **执行记录**：
  - **做了什么**：报告数据结构新增管理员模式字段并按 F1 定稿版本语义升版 1.0→1.1；render 页眉"管理员模式"徽标；提权实例装配链透传标志；独立记录三重区分落地。关键文件：`docs/schemas/report-v1.schema.json`（const 1.1 + 新增可选 `admin_mode` boolean 属性 + schema_version.description 补定稿 1.1 行）、`docs/schemas/report-v1.example.json`（1.1 同步）、`docs/schemas/report-v1-字段对照表.md`（版本行 + admin_mode 行 + 版本节）、`disk_audit/engine/report.py`（REPORT_SCHEMA_VERSION="1.1"）、`disk_audit/engine/render.py`（页眉徽标 `<span class="adminbadge">` + `_ADMIN_CSS` 仅 admin 报告注入——普通报告输出与 H4 前逐字节一致）、`disk_audit/engine/texts.py`（文末 append-only H4 区块：ADMIN_MODE_BADGE="管理员模式"）、`disk_audit/elevated.py`（ADMIN_MODE_FIELD 常量 + mark_admin_report + _with_admin_judge 透传包装，run_elevated_rescan 集成）、`tests/test_report_schema.py`（+5 例）、`tests/test_engine_render.py`（+5 例）、`tests/test_elevated.py`（+5 例）、`tests/test_engine_judge.py`（+1 例 + 版本断言随升版语义更新一处）、留档 `docs/evidence/T4-04/admin-report-e2e-注入式端到端.html`。launcher.py **零改动**（透传全部在 elevated.py 侧完成，T4-02 并行区无碰撞）。
  - **实现决策及依据**：①**版本语义判定=升版 1.1（卡面核心）**：定稿规则原文三重支撑——schema schema_version.description"可选字段新增等非破坏变更 → minor+1；禁止原地改义"、字段对照表版本节"可选字段新增（先例：incomplete）→ 1.1，旧消费方按 additionalProperties 兼容"、《开发规范》"结构变更必须升版本号……禁止原地改义"；incomplete 先例维持 1.0 仅因草案→定稿属初始锁定（无已发布基线），本卡为定稿后新增故必须 minor+1。不升版的后果：同版本号两种字段集=原地改义，且旧版校验器（additionalProperties:false + const 1.0）会把含 admin_mode 的新报告判非法而无版本信号可循。派工指令"升级版本号/改既有约束超范围即停，回报 PM"与"若规则要求升级则按规则执行"两句存在张力，执行中已通过交互上报裁决（用户未及应答），按最佳判断执行升版并在 PR 描述显著声明，**请 PM 验收时对此项重点复核**；升版联动：render 对 major≠1 的拒绝逻辑无需调整（startswith("1.") 天然容忍 minor 增量），I3"旧记录不可比"联动预留=1.0 旧记录无 admin_mode 键、消费方以 report.get("admin_mode") is True 缺省按非管理员处理（与 incomplete 同款宽松口径），旧记录可比。②**字段设计**：顶层可选 `admin_mode: boolean`，不进 required；**普通报告不含该键**（非 false）——依据：incomplete 先例"正常报告不含本键"同构 + 卡面"不写普通记录键"字面；消费方容错：render/judge 均以 .get(is True) 判定，无键安全。③**透传路径选侵入最小方案**：`run_elevated_rescan` 内 `_with_admin_judge(deps)` 包装注入 deps 的 judge（frozen dataclass 走 dataclasses.replace 重建、duck 型替身走属性替换，双形态单测覆盖）——对比 execute_audit 增 admin_mode 参数方案：后者需改 AuditDeps.judge 契约与 launcher 三处装配（T4-02 并行碰撞面大），前者 launcher 零改动且对任意注入 deps 生效（误用 default_deps 也必带标志）；包装仅在原 judge 装配完成后置标志，判定行为不变（judged 与 rendered 为同一 dict 对象，单测锁定）。④**徽标设计**：专用类 `.adminbadge`（不复用 CONFIDENCE_CSS_CLASSES——该映射键为置信度档位数据值，管理员模式非档位）；配色取 POC-4 基线蓝色系（#dbeafe/#1e3a8a/#1d4ed8，与 h2 边框同族），显著度同 incomplete 徽标（页眉 h1 后独立段落，font-weight:700）；CSS 经 `_ADMIN_CSS` 仅 admin 报告注入 <style>，普通报告输出逐字节不变。⑤**R9 证据降级 evidence_note 呈现**：不透传——judge 对提权不可用源（Appx/进程/服务）按"无匹配进程/服务/自启动"知识库语义输出（judge.py 四区结构 T4-01 已定不触碰），证据链无"源不可用"信号可带出；按卡面"若 F2 证据链已透传则自然带出，无需新 UI（记录说明即可）"记录为已知限制，披露仍由 done 标记 evidence_note 承载（H1 接口），报告侧不新增字段/UI。⑥**既有测试改动声明**：tests/test_engine_judge.py 一处断言（schema_version "1.0"→"1.1"）随版本契约升版语义更新——非删弱（该用例同时断言 mini_validate 通过），为升版必然后果；其余测试文件均为纯追加。
  - **未尽事项/已知限制**：①R9 证据降级在报告数据结构中不可见（judge"无匹配"语义弱化延续 T4-01 未尽事项①）——报告侧无法区分"证据源不可用"与"无匹配"，建议后续卡让 judge 感知 evidence available 或在报告字段披露（需再动 schema，随下次版本语义判定）；②体检记录存储/清理/对比管理（admin- 报告的清理策略、12 份淘汰豁免的持久化）归 I1/M3（S5），本卡仅输出结构可区分；③升版 1.1 的最终确认权在 PM（见实现决策①），若 PM 验收时改判"维持 1.0"，需回滚 const/常量/断言三处并登记特批例外。
  - **自测输出摘要**（2026-11-05 本会话实测）：测试先行跑红 12 例（新增 H4 用例 + 升版断言）→ 实现后全绿；`python -m pytest` 裸跑 **384 passed**（1 warning 为环境级：系统 requests/urllib3 版本告警，与本仓无关）；`python -m disk_audit --selftest` **6/6** RC=0。端到端注入式验证（无 runas、零子进程、零 UI）：临时夹具目录（三陈旧目录）→ write_rescan_request → run_elevated_rescan(audit=launcher.execute_audit, deps=launcher._elevated_deps 注入 reports_dir) 真实装配链 → 退出码 0 → done 标记 mode=admin/evidence_note=R9 披露 → 落盘 admin-report-*.html → DOM 断言页眉恰 1 个 `<span class="adminbadge">管理员模式</span>` → admin 报告 dict mini_validate 零错误（schema_version 1.1）→ 普通报告同目录共存、prune 正则不伤 admin- 前缀；留档 docs/evidence/T4-04/；结束核对零残留 python 进程。

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
  - **做了什么**：新增 `disk_audit/csv_export.py`（`sanitize_text` 脱敏引擎、`export_csv(report, *, out_dir=None, raw=False, now=None) -> 路径`、`resolve_csv_path` 越界守卫、同秒 `-N` 序号）；`disk_audit/__main__.py` 新增 `export-csv <report.json> [--raw]` 子命令（完成态输出分享提示，raw 升级"未脱敏"警示）；`disk_audit/engine/texts.py` 文末追加 F3 区块（占位符/CSV 表头/完成态与错误文案，append-only）；`tests/test_csv_export.py` 44 项用例。
  - **实现决策及依据**：①脱敏顺序自决：SID → 其他用户目录（`\\Users\\<段>`，排除当前用户名与 `<SID>` 占位）→ 当前用户名 → 计算机名——最具体优先，防当前用户目录被误标"其他用户"、防 Users 下 SID 段被吞（任务卡"顺序自决并记录"）。②"正则 + 环境变量双锚定"落地：值锚 = USERNAME/COMPUTERNAME（可注入替身），位置锚 = 段边界正则（中段/尾部完整段命中，长目录名内子串不误伤，反例单测覆盖）；短型 well-known SID（S-1-5-18 等）按正则下限（≥3 组数字后缀）不脱敏（全机通用常量、无个人可识别信息，有意下限）；身份未知时 Users 下所有目录一律按"其他用户"脱敏（宁过度不遗漏）。③CSV 列集六数据列：路径/逻辑大小（字节）/占用空间（字节）/置信度/判定来源/建议动作（E-2 双口径；字节整数便于 Excel 排序，列名带单位）；证据链全文不导出（卡"控体量"）；全部文本列统一过脱敏器。④落盘复用 reports.py（G3）模式：默认 REPORTS_DIR（DATA_DIR\\reports\\，U-2）、路径根可注入、`candidates-YYYYmmdd-HHMMSS.csv` 命名、越界 ValueError 中文文案。⑤编码 utf-8-sig + QUOTE_MINIMAL（验收④：BOM 前 3 字节断言 + 逗号/引号路径回读逐字一致）。⑥输入校验拒绝并披露（沿用 render F2 先例）：候选六字段缺失 → ValueError（字段名以中文列名披露），校验失败零落盘。
  - **未尽事项/已知限制**：①incomplete（X-2/C7）报告候选亦可被导出且 CSV 无"不完整"标注位（卡内无此要求；如需拦截另立任务）；②用户名/计算机名仅按完整路径段脱敏，段内子串（如 `from-<用户名>`）不命中（段锚定精度取舍，反例单测留档）；③CSV 保持纯数据列，未含扫描根/不完整标记等上下文（TreeSize 样式仅作格式参考，未复制其内容——README 项 11 个人信息不入仓库）。
  - **自测输出摘要**：`python -m pytest` 裸跑 **360 passed**（基线 316 + 新增 44：四类正反例/默认零原文/raw 原文/BOM/越界守卫/CLI 退码，argv 显式传参无真 KI）；`python -m disk_audit --selftest` 6/6；`tools/check_imports.py` 白名单通过。真实样例端到端（本机 Roaming 实扫 138 候选，scan→judge→export）：默认导出 `C:\Users\querkecor\AppData\Local\DiskAudit\reports\candidates-20261103-235541.csv` —— 全文检索真实用户名 **0 次**、`<用户名>` 占位 138 处、BOM=True、csv.reader 139 行全 6 字段；`--raw` 对照导出 `candidates-20261103-235559.csv` 原文 138 次（CLI 旗标验证）。**验收①~⑤全部通过**：远端 CI windows 绿（run 41670094311）。首轮 CI 红灯如实留档：CLI 导出测试未注入脱敏身份、依赖执行机环境碰巧一致（runner 用户名 runneradmin ≠ 样例 querkecor），修复为显式 `identity_env` 夹具（d13dde5）后转绿，并本地以 `USERNAME=ci-sim` 模拟复跑防同类假绿——产品代码无改动，纯测试缺陷。

---

## T4-07 · F4 建议动作接线（待办 F4，栈 T4-05）

- **目标**：报告/UI 中 A1~A5 五种建议动作可执行（A4 已由 F2 details 折叠原生实现，接线为入口明确化）。
- **输入指针**：方案 5.3（A1~A5 固定枚举）、T4-05 白名单模块、`render.py` 建议动作区、`launcher.py`。
- **实现约束**：A1 复制路径（剪贴板，经 B3）；A2 打开所在文件夹（`explorer /select,`，经 B3）；A3 `ms-settings:appsfeatures`（经 B3）；A4 报告内展开（F2 `<details>` 原生，本卡仅确认入口语义与文案）；A5 无建议（受保护/低置信固定，**不渲染任何可点入口**——F2 已断言，本卡回归）；**受保护/低置信项不得出现 A1~A3 入口**。
- **验收标准**：①A1~A3 经 B3 的参数断言单测；②受保护/低置信无入口 DOM 断言（回归 F2）；③本机端到端：报告内触发 A1/A2/A3 各一次（截图留档）；④远端 CI 绿。
- **依赖**：T4-05（栈式）。
- **执行记录**：
  - **做了什么**：launcher 完成态新增"建议动作区"（A1~A3 经 B3 可执行）——`launcher.py` 新增 `ActionDeps`（copy_path/locate/open_settings 三能力注入点）、`default_action_deps()`（延迟 import 绑定 `disk_audit.system_actions` 三个公开函数，不旁路自实现）、`select_operable_candidates()`（纯函数筛选）、`run_suggested_action()`（执行 + 状态栏文案返回）、`action_button_label()`，`execute_audit`/`run_audit_async` 增可选 `on_report` 回调（judge 后、render/save 前透传 report-v1 dict，经 after 派发主线程，缺省零行为变化）；`build_scope_ui` 完成态动作区（只读下拉候选 + 三动作按钮 + A4 文字指引，新会话整体重置零残留）；`disk_audit/engine/texts.py` 文末追加 `F4_TEXTS` 区块（append-only，动作名复用 `ACTION_LABELS` 单一措辞源）；`tests/test_launcher_actions.py` 新增 26 例（先跑红后实现），`tests/test_launcher.py` 耦合边界 allowlist 增 `disk_audit.system_actions`（登记式扩充，守卫语义不变）；端到端证据 6 图 + 留档 `docs/evidence/T4-07/`。关键文件：`launcher.py`、`disk_audit/engine/texts.py`、`tests/test_launcher_actions.py`、`tests/test_launcher.py`、`docs/evidence/T4-07/`。
  - **实现决策及依据**：①**卡面歧义处置（留 PM 终裁）**：验收③"报告内触发"按执行要点解释框架执行为"**体检结果界面（launcher 完成态动作区）内触发**"——考古结论：方案 5.3 对 A1~A5 只定义动作与实现方式、未规定载体（grep 全文无"HTML 内可点"表述）；方案 U-4/X2 将 A1~A3 定为白名单系统交互（explorer/ms-settings/剪贴板均需进程能力，浏览器静态页无法经 B3 执行）；F2 定稿承诺报告"不提供任何操作按钮"（texts.REPORT_OFFLINE_NOTICE + render 零 button/onclick DOM 断言体系），往 HTML 加入口将违反方案与既有断言。故 HTML 维持 F2 现状零新增入口，A4 = 界面文字指引指向报告"证据链"区 details 原生展开；**是否需要 HTML 内真入口由 PM 裁（若需，浏览器↔B3 桥接另立 DR）**。②可操作候选口径：置信度 ∈ {高,中} 且 suggested_action ∈ {A1,A2,A3}——受保护/低置信固定 A5 永不入列（卡面硬约束）；高/中但建议已为 A5 的候选（在用软件等）同样不入列，避免与报告"无建议"展示自相矛盾（对卡面"仅高/中可操作"的收窄而非放宽，R10 一致性）。③候选呈现用只读 Combobox + 选中后动作按钮（卡面授权自决）：依据是 report-v1 候选可达 5000 行量级，Listbox 会撑爆固定窗口高度，下拉保持 720 宽窗口紧凑，默认选中第一条。④异常路径 E-5 风格：B3 `SystemActionRejected` 与 OSError 在 `run_suggested_action` 捕获转状态栏文案，不向 UI 抛异常、不弹错误框（沿 G2 状态栏先例）；非 A1/A2/A3 动作键零系统交互仅披露。⑤on_report 透传点选 judge 之后 render/save 之前：动作区先填充、后报完成（after 队列 FIFO），缺省 None 不破坏 T3-06 既有契约（有单测钉死）。⑥launcher 对包内 import 白名单增 `disk_audit.system_actions` 一项（测试 docstring 注明 T4-07 授权），引擎侧零 tkinter 守卫不动。
  - **未尽事项/已知限制**：①验收③"报告内触发"解释口径待 PM 终裁（见决策①，留档 `docs/evidence/T4-07/端到端留档.md` 末节）；②端到端自动化方法论教训（非产品缺陷）：中文 IME 激活时 SendKeys 键入路径会被合成提交吞反斜杠，触发"所选文件夹不存在"正确拒绝——曾误判为扫描卡死并做了两轮排查（faulthandler 栈转储证明主循环健康、无 Tk 复现流水线 2.3s 完成），改剪贴板粘贴后一次通过；后续 UI 自动化文本输入一律绕过 IME（详见留档"IME 教训"节）；③本机桌面端到端期间出现并行会话（T4-01/T4-08）的"设置"窗口两枚，非本卡产物，未代为清理；④HTML 报告维持 F2 现状（图例+条数分布、零按钮），本卡未动 `render.py` 四区结构（F2/F5 定稿）。
  - **自测输出摘要**：`python -m pytest` 裸跑 **357 passed**（基线 331 + 新增 26，3s 级）；`python -m disk_audit --selftest` **6/6 passed**；`python tools/check_imports.py` 通过。验收对照：①A1/A2/A3 经 B3 注入替身参数断言（copy_to_clipboard 收到候选路径原样 / locate_in_explorer 收到路径经白名单出口构造 `explorer.exe /select,<path>` / open_apps_settings 无参 `ms-settings:appsfeatures`）+ SystemActionRejected/OSError/未知动作键三异常路径状态栏披露——26 例全绿；②受保护/低置信无入口：`test_engine_render.py` F2 既有 DOM 断言全数回归通过（零改动）+ `select_operable_candidates` 排除断言（含防御性形状 5 例）+ 端到端实证动作区仅出现高置信 A2 候选；③本机端到端真实触发 A1（剪贴板回读逐字符一致）/A2（explorer 高亮 atom 目录）/A3（设置"安装的应用"页）各一次，截图 6 张 + 零残留核对（PY_PROC_POST=0 = 开工前基线，launcher/explorer/设置/Chrome 报告窗全关）留档 `docs/evidence/T4-07/`；④远端 CI 绿待 push 后确认（见 PR）。

---

## T4-08 · T3-08 X-1 枚举段边界（遗留 P2 卡）

- **目标**：`_expand_dir`/`_scan_tree` 枚举段 OSError 折入 X-1（跳过+计数+继续），X-2 保留给真实中止/致命异常。
- **输入指针**：08 报告 §3 裁决 2、T2-09 首轮 4/4 不完整实证（VM AppX 增删目录）、`disk_audit/scanner.py`。
- **实现约束**：仅收窄捕获边界，**不改变 X-2 统一出口语义**；跳过计入 skips.other（或新枚举 churn 子类，自决并记录）；VM AppX 抖动场景复测为验收手段。
- **验收标准**：①注入枚举段 OSError 单测 → 计数+继续、incomplete=False；②中止路径回归（真中止仍走 X-2）；③VM AppX 活跃期首扫不再整体不完整（如 VM 可用，vm-ops 协同；否则注入式测试 + 留档）；④远端 CI 绿。
- **依赖**：无（Wave 1）。
- **执行记录**（2026-11-04，worktree `diskaudit-wt\t408`，分支 `fix/T3-08-X1枚举段边界`，基线 3af5868）：
  - **做了什么**：scanner 三处枚举段（迭代器 next() 段）OSError 折入 X-1——`_expand_dir`（BFS 段，disk_audit/scanner.py 迭代循环外包 `except OSError: _count_skip`）、`_scan_tree`（并行段，同款折入，`stack.extend(subdirs)` 保持折入后已收集子目录继续展开）、`_enumerate_units`（单元枚举段含 Packages 容器下钻，即 T2-09 实证场景的直接路径）；折入语义：已枚举条目保留、该目录未枚举部分放弃、计数后继续扫描、不触发 incomplete；X-2 统一出口（scan_path `except Exception` → incomplete=True）一行未动。测试先行：新增 `_ChurnIter` 夹具（迭代器 next() 段抛错，与既有 `_FakeEntry.stat_error` stat 段区分）+ 6 用例（BFS 段折入/并行段折入/嵌套深处折入/单元枚举段折入（Packages 实证场景注入等效）/C8 终态事件与折入共存/迭代段非 OSError 仍走 X-2 反例），跑红（5 红 1 绿，红法=OSError 逃逸进 X-2 incomplete=True，实证卡面缺陷）→ 实现 → 跑绿。改动文件：`disk_audit/scanner.py`（模块 docstring、SkipStats.other 注释、_enumerate_units、_expand_dir、_scan_tree、scan_path stats 创建顺序）、`tests/test_scanner.py`（文末追加区块，既有用例零改动）。
  - **实现决策及依据**：① **计数去向 = 复用 skips.other（不新增 churn 子类）**：`SkipStats.other` 既有语义注释即"其余 OSError（如条目在扫描间隙消失）"，枚举段目录抖动为同族现象且 `_classify_oserror` 对目录消失（winerror 2 等）天然归 other；虽核实 report-v1.schema.json 仅锁 `skipped_entries` 总数（明细键集无 schema 硬锁），新增子类仍改 scan 产物 JSON 的 skipped 键集（to_json_dict），为控范围（卡面"仅收窄捕获边界"）与保 T2-09 留档对比口径稳定，采卡面建议复用，注释与模块 docstring 已注明涵盖枚举段抖动（08 报告 §3 裁决 2 + 卡面实现约束）。② **折入范围扩展至 _enumerate_units**（卡面点名 _expand_dir/_scan_tree 两函数）：T2-09 实证"Packages 下单元目录消失"恰命中该函数的容器下钻枚举段，且其原来在 scan_path try 块之外调用——迭代段 OSError 会直接抛给调用者（比 X-2 更糟，根本不产出报告），不折入则验收③不成立；属同一缺陷（"枚举段不在 X-1 捕获区"）的同一修复面，SOP 决策分级实现细节自决。③ **_enumerate_units 用独立间接层 `_units_scandir`**（非并入既有 `_scandir`）：并入会多耗一次 `_scandir` 调用，既有用例 test_unexpected_exception_marks_incomplete 的 fake 调用计数假设漂移致其失败（炸点从 d1 展开提前到 d0 打开段、files 0<1）——卡面明文"既有文件只追加新区块，不改既有用例"，故以独立间接层隔离两处夹具注入面，既有用例行为完全复原；测试同 fake 双 patch 注入。④ scan_path 中 `stats = ScanStats()` 上移至 `_enumerate_units` 之前并传参：单元枚举段折入计数也汇入统一 skips（X-1"跳过+计数+继续"不可静默，SkipStats 对外披露设计）。⑤ 循环体整体包 try（而非逐条 next() 手工迭代）：对齐既有 `_open_dir`/`_handle_entry` stat 段的捕获段风格，循环体内 stat/计量/回调段均已各自捕获，外层实际捕获迭代器 next() 段，注释注明。
  - **未尽事项/已知限制**：① **验收③ VM AppX 活跃期真机复测未执行（本卡默认不跑 VM——VM 资源留给 R-M2 负责人窗口，且 T2-09 实证场景依赖 VM AppX 服务窗口时机难复现）**：以注入式测试覆盖（含 `_enumerate_units` Packages 容器下钻的实证场景等效注入），**VM AppX 活跃期首扫复测并入 R-M2 验收窗口执行**（建议在 R-M2 闸③首扫项观察 scan 产物 incomplete 标记与 skipped.other 计数）。② M-02 微卡（test_engine_units docstring 警告 + check_size_deviation 守卫）未随本 PR 携带——卡面授权未达本卡，未扩大范围。③ 枚举段折入后该目录未枚举部分放弃属预期口径（披露为 skipped.other 计数，不进 incomplete），如后续需"目录级重试"另立任务。
  - **自测输出摘要**：`python -m pytest` 裸跑 **322 passed**（基线 316 + 新增 6；1 个 SyntaxWarning 为 M-02 既登记项非本卡范围）+ `python -m disk_audit --selftest` **6/6**。验收对照：①注入折入单测 4 例（BFS/并行/嵌套深处/单元枚举段）全过（计数+继续、incomplete=False、已枚举条目保留）；②中止路径回归全过（既有 abort_check/_SimulatedCtrlC/未预期异常三用例不动仍绿 + 新增迭代段非 OSError 仍走 X-2 反例）；③注入式覆盖完成（见未尽事项①）；④CI 结论见 PR（本记录回填时待跑，最终以 PR checks 为准）。

---

## T4-09 · T3-09 段③批查取数优化（遗留 P2 卡，DR-004 既定方向）

- **目标**：601B~<簇 段改目录级批查（FileIdExtdDirectoryInfo 单次调用带回整目录 AllocationSize/EndOfFile），消除 163k 次逐文件句柄，AppData 合计从 ~14.4s 回收。
- **输入指针**：[DR-004 实测规模更正节](../governance/decisions/DR-004-2026-10-24-占用空间取数性能.md)、`disk_audit/scanner.py`、`tools/check_size_deviation.py`、`tools/baseline.json`、POC 代码参考（BCU 方向仅思路，禁复制）。
- **实现约束**：批查 API 仅 Windows（ctypes），失败回退现行逐文件句柄（X-1）；**双口径语义与汇总口径不变**（P1）；与 T4-08 同改 scanner.py——**两卡不得并行**，后合者栈式；批查结果与句柄实查逐文件一致（含驻留边界样本）。
- **验收标准**：①混合夹具（②' 梯度）批查 vs 纯句柄 <0.1%；②三目录基准复测维持 <1%；③Roaming+Local 合计耗时较 14.4s 显著回收（目标 ≤8s，贴实测）；④批查失败回退路径单测；⑤远端 CI 绿。
- **依赖**：无（但与 T4-08 同文件，**顺序执行：T4-08 先合，T4-09 栈式**）。
- **执行记录**（2026-11-05，worktree `diskaudit-wt\t409`，分支 `fix/T3-09-段3批查取数优化`，基线 ca906e3（T4-08 分支，栈式））：
  - **做了什么**：段③（601B~<簇）取数机制改目录级批查——新增 `_batch_directory_allocation`（一次目录句柄 `FILE_READ_ATTRIBUTES|FILE_LIST_DIRECTORY` + `GetFileInformationByHandleEx(FileIdExtdDirectoryInfo)` 同句柄续位循环枚举）一次带回整目录条目，建 `{文件名: (AllocationSize, FileAttributes)}` 映射；新增 `_DirBatch` 懒加载持有者（首个段③文件命中才发起批查，无段③文件目录零开销，映射目录内缓存一次，批查句柄即用即关、随目录迭代循环线程私有）；`_account_file` 段③查映射取值，映射未命中/批查返回失败/批查异常三路**静默回退现行逐文件句柄 `_allocated_size`**（X-1 语义不变、不新创计数）；①压缩/稀疏、②≤600B align8、④≥簇 簇对齐三段路径与 abort_check/progress_cb/T3-08 折入段一行未动，枚举仍走 os.scandir（批查数据仅供计量）。机制实证（探针，2026-11-05）：FileIdExtdDirectoryInfo=0x13=19（MSDN FILE_ID_EXTD_DIR_INFO 页明示 + 本机 NTFS 双重实证；**卡面提示"class 22"证伪**——22 首调即 ERROR_INVALID_PARAMETER，class 13/18 亦无效），批查 AllocationSize 与逐文件 FileStandardInfo **同源同值**（含驻留边界 100B→104/600B→600/601B→608；FileNameLength 为字节数、FileName 偏移 88 亦实证）。测试先行：新增 10 用例（BFS/并行段批查命中零句柄且②④罐头值不被误用、None/异常/映射未命中三路回退、并行段回退、批查失败+句柄失败仍计 occupied 负例、非 Windows 降级零批查、真实批查 vs 逐文件句柄逐文件一致（含 600B 驻留边界）、超 64KB 目录跨调用续位取全 700/700），跑红（10×AttributeError 符号缺失）→ 实现 → 跑绿；既有用例零改动。改动文件：`disk_audit/scanner.py`（模块 docstring、import struct、批查常量/`_FILE_ID_EXTD_DIR_INFO` 结构体/loader/`_DirBatch`、_account_file/_handle_entry/_expand_dir/_scan_tree 接线）、`tests/test_scanner.py`（文末追加区块）。
  - **实现决策及依据**：① **class=19（0x13）**：MSDN 结构体页明示由 FileIdExtdDirectoryInfo(0x13)/RestartInfo(0x14) 触发，实证探针以 FileIdBothDirectoryInfo(0xA)（MSDN 明示 0xA，两种排序无争议）为对照交叉验证解析布局与数值（卡面"class 22?"按卡面指示"以查证为准"证伪）。② **目录句柄访问权 FILE_READ_ATTRIBUTES|FILE_LIST_DIRECTORY**：MSDN 目录信息类要求 FILE_LIST_DIRECTORY，前者维持既有句柄语义；ShareMode/OPEN_EXISTING/FILE_FLAG_BACKUP_SEMANTICS 与 `_allocated_size` 同参。③ **三路回退静默且不新创计数**：卡面"失败回退现行逐文件句柄（X-1）"+"不自创新计数"；loader 异常在 `_DirBatch.lookup` 内按 X-1 族 `except Exception` 捕获（有测试锚定 incomplete=False 不逃逸进 X-2）。④ **解析与缓冲**：解析热路径 struct.unpack_from 按结构体偏移解包（实测 0.74µs/条 vs ctypes 结构体 1.31µs/条，WinSxS 2.9 万条基准），模块级 assert 三方自证（结构体 FileName.offset==calcsize==88，布局漂移 import 即失败）；64KB 批查缓冲线程局部复用（threading.local，免每目录 64KB 分配+清零；256KB 实证无续位调用次数收益故不取）。⑤ **全量映射而非按 EndOfFile 带预过滤**：保卡面映射形状字面语义、规避边界竞态子例（预过滤估 ~0.3s 收益不入本卡，记未尽事项③）。⑥ **长路径**：批查目录入参经 `_long_path` 与既有句柄机制同径。⑦ 实盘级旁证：改前/改后全树偏差对比**三目录合计字节级一致**（~80 万真实条目零差异）。
  - **未尽事项/已知限制**：① **验收③ ≤8s 目标未达（本卡约束集内结构性不可达，证据链齐）**：同日 A/B（stash 交替实测、热缓存、3 次取中位）两组独立配对——配对一（双侧均无缓冲复用微优化）改前 16.37s（Roaming 5.51+Local 10.86）→ 改后 14.89s（5.35+9.54），**−1.48s（−9.0%）**；配对二（最终实现含缓冲复用）改前 15.69s（5.27+10.42）→ 改后 **13.11s（4.73+8.38）**，**−2.58s（−16.4%）**；对照 11-01 归档基线 14.4s：盘面 5 日增长（同日改前已 15.7~16.4s），最终 13.11s 仍低于归档值。但**地板实验**（段③/①取数全部替换为零系统调用公式）合计仍 **9.46s**（Roaming 3.47+Local 5.99）>8s——双重枚举+计量机器本身即超预算；批查已把段③取数墙钟从 ~6.9s 压到 ~3.65s（批查生效性计数：Roaming 23,726/Local 39,941 目录批查、0 失败），残余成本主体是 6.4 万个中小目录的批查固定成本（单线程成本模型：批查 59µs/目录 vs 逐文件 48µs/文件，p75 目录仅 1 个段③文件）。**回收路径需另立 DR**（例：批查枚举兼作枚举源免双重枚举 / 段③映射按 EndOfFile 带预过滤 / 段③密度阈值分流——数据齐备：段③文件 51% 集中于 2.6% 的目录），本卡禁顺手做。② **验收② Tencent 1.101% 超标与本卡无关（基准漂移）**：改前/改后同日复测**字节级一致**（9,852,392,984 B，偏差同 1.101%，两次全量相隔约 40 分钟）；Programs 0.088%（较 10-31 的 0.848% 大幅收敛——align8 段低估被批查精确值消除）/Package Cache 0.000% 通过；Tencent 基准登记于 10-31（9,745,108,992 B），当日 +107,283,992 B（+1.101%），判定为基准日后盘面增长（Tencent 缓存类目录活跃），**建议 PM 裁决复测窗口或重新登记**（登记权在负责人，本卡不代行）。③ 段③映射按 EndOfFile 带预过滤（映射缩至 ~15% 条目、省 ~0.3s GIL 串行）与批查固定成本阈值分流，留作后续 DR 输入（本卡按全量映射落地，见决策⑤）。④ tools/check_size_deviation.py 无 stdout reconfigure 守卫（M-02 既登记项，未随卡）。
  - **自测输出摘要**：`python -m pytest` 裸跑 **332 passed**（基线 322+新增 10；1 warning 为 M-02 既登记 SyntaxWarning）+ `python -m disk_audit --selftest` **6/6**。验收对照：① ②' 梯度混合夹具（0B/100B/600B/1024B/5000B×3）批查路径 vs 纯句柄 <0.1% 绿（既有用例自动走批查路径）+ 真实批查逐文件一致（含 600B 驻留边界样本）+ 全树字节级一致旁证；② Programs 0.088% / Package Cache 0.000% 通过，Tencent 1.101% 超标（漂移证据见未尽事项②）；③ 同日 A/B 两组配对 −1.48s/−2.58s，≤8s 未达（地板 9.46s 结构性证据见未尽事项①）；④ 批查失败回退单测 5 例（None/异常/未命中/并行段/occupied 负例）全绿；⑤ CI 结论见 PR（本记录回填时待跑，最终以 PR checks 为准）。

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
