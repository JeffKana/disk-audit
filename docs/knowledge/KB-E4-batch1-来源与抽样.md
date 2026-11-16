# KB-E4 首批（20 条）来源与抽样

- 任务：T6-03-KB1（契约 KB1-v1）；批准：PM source-gate KB1-APPROVED-20-v1（2026-11-16）
- 基线：c6d40ed4503dbe3d295a85c88eac74345df73f47；本批 503 → 523 条；N=20，全部抽样
- 性质：知识库数据扩容与来源索引，不是产品功能验收，也不代表 800–1000 目标或 M4 完成
- 脱敏：本文只保留公开产品名、官方 URL 与目录名；不含本机用户名、原始扫描路径、CSV 原文或任何令牌

## 1. 来源方法与证据分级

1. 差集：项目归档 CSV（500 行历史观测）与既有 503 条精确名/别名比对，未命中 183 条全部属排除类
   （Appx 包目录、容器、Microsoft 受保护目录、.ini、泛化名、安装目录），因此本批新增不取自 CSV 长尾。
2. 公开来源：逐产品读取官方文档/官方仓库文件的完整正文，命中 Windows AppData/Roaming/LOCALAPPDATA 路径句；
   仓库类来源先解析默认分支与 commit，再按固定 commit 取文件。
3. 证据级：
   - 官方文档整页正文命中：12 条
   - 官方仓库固定 commit 文件：3 条（neovim、drawio-desktop、Zettlr）
   - 官方措辞限定（部分版本）：1 条（MobaXterm）
   - 官方页检索摘录 + PM 复核：2 条（KiCad、MuseScore）
   - 官方正文 + PM 一手快照：1 条（Anki）
   - 沿用前一轮官方正文抓取：1 条合并计数（Notepad++ 等，见 §3 逐条 URL）
4. 字段纪律：全部 name 小写、category 统一“已安装应用”（静态归属，不证明宿主安装/运行/可删）、
   lifecycle 全部“未知”、source 全部“公开软件名”、regex_family 全部 null；仅 Neovim 使用经批准的唯一精确别名 nvim-data。

## 2. 敏感提示

- 新增条目中 Anki、KeePassXC、MobaXterm、Syncthing、Prism Launcher、WinMerge、draw.io 的 notes 含“仅诊断，不读取内容”。
- 既有 .azure / .docker 两条仅追加同一提示，分类、lifecycle、source 等其余字段不变。
- 敏感提示只影响披露文案，不改变任何匹配或删除策略。

## 3. 20 条清单（全量抽样）

| # | name | product | vendor | category | lifecycle | source | 目录依据 | 官方来源 | 证据级 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | notepad++ | Notepad++ | Don Ho | 已安装应用 | 未知 | 公开软件名 | %AppData%\Notepad++\ | https://npp-user-manual.org/docs/config-files/ | official-doc-fulltext |
| 2 | alacritty | Alacritty | Alacritty | 已安装应用 | 未知 | 公开软件名 | %APPDATA%\alacritty | https://alacritty.org/config-alacritty.html | official-doc-fulltext |
| 3 | audacity | Audacity | Muse Group | 已安装应用 | 未知 | 公开软件名 | C:\Users\<user>\AppData\Roaming\audacity\ | https://support.audacityteam.org/au3/troubleshooting/resetting-audacity | official-doc-fulltext |
| 4 | winmerge | WinMerge | WinMerge Project | 已安装应用 | 未知 | 公开软件名 | %APPDATA%\WinMerge\WinWebDiff | https://manual.winmerge.org/en/Configuration.html | official-doc-fulltext |
| 5 | prismlauncher | Prism Launcher | Prism Launcher | 已安装应用 | 未知 | 公开软件名 | %APPDATA%/PrismLauncher | https://www.prismlauncher.org/wiki/getting-started/data-location/ | official-doc-fulltext |
| 6 | scooter software | Beyond Compare | Scooter Software | 已安装应用 | 未知 | 公开软件名 | C:\Users\<username>\AppData\Roaming\Scooter Software\Beyond Compare 5 | https://www.scootersoftware.com/v5help/where_settings_are_stored.html | official-doc-fulltext |
| 7 | mobaxterm | MobaXterm | Mobatek | 已安装应用 | 未知 | 公开软件名 | %AppData%\MobaXterm | https://mobaxterm.mobatek.net/documentation.html | official-doc-fulltext-qualified |
| 8 | kicad | KiCad | KiCad | 已安装应用 | 未知 | 公开软件名 | %APPDATA%\kicad\8.0 | https://docs.kicad.org/8.0/zh/kicad/kicad.html | official-page-excerpt |
| 9 | musescore | MuseScore | Muse Group | 已安装应用 | 未知 | 公开软件名 | %APPDATA%\MuseScore\MuseScore4.ini | https://musescore.org/zh-hans/print/book/export/html/329749 | official-page-excerpt |
| 10 | anki2 | Anki | Anki | 已安装应用 | 未知 | 公开软件名 | %APPDATA%\Anki2 | https://docs.ankiweb.net/manual/files | official-doc-fulltext+pm-seed |
| 11 | helix | Helix | Helix | 已安装应用 | 未知 | 公开软件名 | %AppData%\helix\config.toml | https://docs.helix-editor.com/configuration.html | official-doc-fulltext |
| 12 | nushell | Nushell | Nushell | 已安装应用 | 未知 | 公开软件名 | C:\Users\<user>\AppData\Roaming\nushell | https://www.nushell.sh/book/configuration.html | official-doc-fulltext |
| 13 | nvim | Neovim | Neovim | 已安装应用 | 未知 | 公开软件名 | ~/AppData/Local/nvim | https://raw.githubusercontent.com/neovim/neovim/4cda11d38564a4f1e3ceddad90cec5ddf16b9217/runtime/doc/starting.txt | official-repo-pinned |
| 14 | stellarium | Stellarium | Stellarium | 已安装应用 | 未知 | 公开软件名 | C:\Users\<user>\AppData\Roaming\Stellarium | https://stellarium.org/doc/1.x/fileStructure.html | official-doc-fulltext |
| 15 | zed | Zed | Zed Industries | 已安装应用 | 未知 | 公开软件名 | $env:LOCALAPPDATA\Zed | https://zed.dev/docs/reference/all-settings | official-doc-fulltext |
| 16 | qgis | QGIS | QGIS | 已安装应用 | 未知 | 公开软件名 | %AppData%\Roaming\QGIS\QGIS3\profiles\ | https://docs.qgis.org/3.40/en/docs/user_manual/introduction/qgis_configuration.html | official-doc-fulltext |
| 17 | draw.io | draw.io Desktop | draw.io (JGraph) | 已安装应用 | 未知 | 公开软件名 | C:\Users\<user>\AppData\Roaming\draw.io\ | https://raw.githubusercontent.com/jgraph/drawio-desktop/0623fb3c1523639b06600d5c33e3a127bf82aa1c/README.md | official-repo-pinned |
| 18 | zettlr | Zettlr | Zettlr | 已安装应用 | 未知 | 公开软件名 | %AppData%/Zettlr | https://raw.githubusercontent.com/Zettlr/Zettlr/cc8ebaf5bffe210c4d8e376e730a66b84e8f4c64/README.md | official-repo-pinned |
| 19 | syncthing | Syncthing | Syncthing | 已安装应用 | 未知 | 公开软件名 | %LOCALAPPDATA%\Syncthing | https://docs.syncthing.net/users/config.html | official-doc-fulltext |
| 20 | keepassxc | KeePassXC | KeePassXC Team | 已安装应用 | 未知 | 公开软件名 | %AppData%\KeePassXC\keepassxc.ini | https://keepassxc.org/docs/KeePassXC_UserGuide | official-doc-fulltext |

## 4. 排除与父子处理

- KiCad 只登记父目录 kicad（8.0 版本子目录不单列）；QGIS 只登记 qgis（QGIS3 不单列）；
  Beyond Compare 只登记父目录 scooter software；KeePassXC / MuseScore 只取 ini 的父目录。
- Neovim 的 data/state 目录以精确别名 nvim-data 归属同一条目，不另计条数；nvim-data-backup 不命中。
- MobaXterm 官方措辞限定“部分版本”，notes 保留该限定，不推全版本、本机安装或在用/停用。
- QGIS 文档原文 %AppData%\Roaming 组合存在表述歧义；本文只把它作为官方原文与目录名依据，
  不声明该组合是可执行的本机路径，也不据此修改匹配规则。
- MiKTeX（%USERPROFILE%\Roaming）、Kdenlive（仅到根）、Joplin（%USERPROFILE%\.config）、
  OpenSCAD（未明示子目录）等未纳入本批。

## 5. 去重与分布

- 523 条精确名/别名重复 0；新增 21 个 name/alias 键与旧库精确碰撞 0；新增归一化键 0 冲突。
- 父子包含对：按作者口径（小写原串子串，短名≥3）基线 117 组、扩后仍 117 组；按产品 judge._norm（保留中文）口径为 119 组；两种口径新增均为 0 组。
- 已知 10 组归一化风险（sqlyog/unrealengine/conda/jupyter/ollama/nuget/docker/android/atom/claude）
  为基线既有，本批不改动、不伪称总冲突为 0。
- 分布：source（本机实测 291 / 公开软件名 232）、lifecycle（未知 522 / 已停止 1）、
  category 全部落在既有 12 类内，无超纲分类。

## 6. 未达目标

- 当前知识库共 523 条：距 F1 的 800 条目标差 277 条，距 1000 条目标差 477 条。
- 本批批准 20 条，本批目标上限 100 条，因此本批剩余 80 条（100−20）未达；
  80 仅指本批目标的剩余，不是距 800–1000 的缺口。
- 原 MVP 阈值、八机回归与零误判门槛不因本批改变。

## 7. 复现索引

- 逐条证据与检索过程：任务证据目录 T6-03-KB1 下的 source-candidates-v3.md / raw/cache/ / raw/research-log-v3.md。
- 校验：python tools/validate_knowledge.py knowledge/entries.json；查重见任务证据 raw/dedup_kb.py 输出。
