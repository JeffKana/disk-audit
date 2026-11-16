# app-entry-v1 · 冻结程序统一入口调用说明

- 版本：app-entry-v1（对应任务 T7-01-A / 契约 T701A-v1 / 决策 DR-019）
- 模块：`disk_audit_app.py`（仓库根，包外独立入口；未来 PyInstaller 入口）
- 公开接口：`main(argv: list[str] | None = None) -> int`
- 产品版本：`0.1.0.dev0`（开发版，未发布；本入口不改版本号）

## 1. 调用形态

源代码两种等价形态（均以仓库根为工作目录）：

```bash
python disk_audit_app.py <参数...>
python -m disk_audit_app <参数...>
```

`__main__` 守卫使用 `sys.exit(main())`，进程退出码等于 `main` 返回值或后端
`SystemExit` 携带的码。编程调用 `disk_audit_app.main([...])` 直接取返回 int。

## 2. 路由口径（首 token 决定，DR-019 冻结）

参数取副本：显式 `argv` 用 `list(argv)`；`argv=None` 用 `list(sys.argv[1:])`。
绝不修改调用者列表或全局 `sys.argv`。按下表分派，副本原样交后端，不解析/改写下游参数：

| 首 token 条件 | 后端（延迟导入） | 说明 |
| --- | --- | --- |
| 无参数（空列表） | `launcher.main([])` | 现有 GUI 范围选择启动 |
| 精确 `--elevated-rescan` | `launcher.main(副本)` | 提权实例分支（旧入口原样处理） |
| 以 `--elevated-rescan=` 开头 | `launcher.main(副本)` | `=` 值由旧 store_true 拒绝（退出 2），不自创 bool 语义 |
| 其它所有非空 | `disk_audit.__main__.main(副本)` | 引擎 CLI（复用命令见下清单） |

引擎 CLI 复用：`--selftest`、`--version`、`--help`/`-h` 与四子命令
`scan`、`judge`、`render`、`export-csv`。

未知/混合/畸形参数由相应现有解析器拒绝（典型退出 2），**不回退开 GUI、不自动提权**。
近似 token（如 `--elevated-rescans`、`--elevated-rescanx`）非精确匹配，落引擎 CLI 按未知拒绝。

## 3. 返回与异常语义

- 后端返回码原样透传（GUI `0`/`3`；admin `0`/`4`/`5`；CLI `0`/`2` 等）。
- `SystemExit`、普通异常、`BaseException` 一律透传，不吞异常改成功。
- 本模块自身不额外读写文件、不联网、不查注册表、不启动进程、不触发 UAC/扫描。

## 4. 导入隔离

- 模块加载仅 import 标准库 `sys`；不拉入 `launcher`/`tkinter`/`disk_audit`。
- 引擎 CLI 分支不导入 `launcher`/`tkinter`（延迟导入 + 子进程导入禁令实证）。
- GUI/admin 分支延迟导入 `launcher`（其自身 tkinter 亦延迟，真实运行才开窗）。
- `disk_audit` 包内任何模块不得 import tkinter（开发规范 §1，import 白名单门禁）。

## 5. 自检与门禁

```bash
python disk_audit_app.py --selftest   # 真实 6 例，selftest: 6/6 passed，退出 0
python disk_audit_app.py --version    # 输出 0.1.0.dev0，退出 0
python disk_audit_app.py --help       # 含 scan/judge/render/export-csv 四子命令，退出 0
```

测试见 `tests/test_app_entry.py`（路由/透传/argv 不变性/导入禁令子进程实跑）。
本入口为源代码层验证，不构成冻结包资源/TclTk/构建产物证据；打包、干净机首跑、
发布仍属 M5 后续独立门禁。