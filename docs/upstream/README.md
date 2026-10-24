# 上游资料归档（Sprint 0 任务 0.6 / 待办 A3 · 已完成）

来源：`C:\Users\querkecor\WorkBuddy\电脑磁盘清理大师\`（只读拷贝于 2026-10-24，已校验：1103 个文件 / 62,056,470 字节与源一致，关键文件 MD5 抽查通过）。原目录未做任何改动。WorkBuddy 的 `.workbuddy\`（AI 工具内部记忆）不属于项目资料，未纳入归档；如需过程记录，原路径仍保留在源目录。

## 归档清单（对应方案定稿第十一节"协作流转"）

| # | 文件 / 目录 | 内容 | 用途 |
| --- | --- | --- | --- |
| 1 | `磁盘体检_v0.1方案_定稿_2026-10-23.html` | **当前需求与范围基线（F1）** | 唯一评审与开发依据 |
| 2 | `磁盘残留体检_v0.1落地方案_2026-10-23.html` | 历史版方案（已冻结） | 变更追溯（定稿第十三节） |
| 3 | `AppData残留识别_调研与自研可行性报告.html` | 市场调研 + 三条技术路线 + 原型实证 | 背景与难点（P0/P1/P2）依据 |
| 4 | `AppData残留识别_技术选型决策表_2026-10-23.html` | 技术选型决策记录 | 选型依据 |
| 5 | `poc\` | W0 POC 全套：实测报告 HTML、poc1~poc4 脚本与日志、PyInstaller spec、构建日志、5000 行大报告样本（poc4_bigreport.html，1.4MB）、`dist\poc2_tk\poc2_tk.exe`（VirusTotal 样本，遗留动作 U1） | 性能与包体实测数据来源；C3/C4/C5 修正的对照基线 |
| 6 | `prototype\analyze_appdata.py` | 归属判定引擎原型（约 500 行，含 ~260 条知识库与分级流水线） | Sprint 1 知识库种子迁移（E2）与引擎参考实现 |
| 7 | `prototype\uninstall.json / appx.json / processes.json / services.json / runkeys.json` | 本机证据采集结果（注册表卸载项 / 商店包 / 进程 / 服务 / 自启动，共 5 个分文件） | 证据采集结构参考（C3~C5） |
| 8 | `prototype\summary.json`、`prototype\run_log.txt` | 原型运行汇总与日志 | 口径核对 |
| 9 | `output\AppData残留候选分析_2026-10-23.csv` | 500 个判定单元逐项清单（位置/大小/分类/归属/建议/置信度/证据/判定来源） | 回归集种子与 ground truth 对照 |
| 10 | `build_decision.py`、`build_html.py` | 调研报告与决策表的 HTML 生成脚本 | 文档再生成 |
| 11 | TreeSize 导出 CSV × 2 | 位于桌面：`乔夫卡那_C_Local_详细信息.csv`、`乔夫卡那_C_Roaming_详细信息.csv` | 判定样例原始数据（**未归档**，含个人目录清单，留在原处按需引用） |

## 治理约定（详见 `../governance/项目治理.md`）

- 本目录是项目资料的**唯一归档入口**；新增上游材料必须入此目录并在本 README 登记。
- `poc\build\`、`poc\dist\` 为构建产物，**保留在本地但 git 不纳管**（`.gitignore` 已排除）；`poc2_tk.exe` 仅用于遗留动作 U1 的 VirusTotal 上传。
- 第 11 项 TreeSize CSV 含完整个人目录清单，为避免敏感数据进仓库，未拷贝；需要时从桌面原路径读取。
