---
name: ops-runbook
description: 平台与环境故障运行手册（全体角色，通用版）。凡遇到"git push/fetch 失败"、"CI run 不触发或 PR head 不更新"、"原生命令挂起"、"编码/乱码错误"、"需要绕过故障通道应急合入"时必须使用——即使没说"故障"两个字。覆盖：故障分级、通道降级链、Git Data API 应急合入、树哈希终验、环境事实登记义务。
---

# Skill: ops-runbook · 平台与环境故障运行手册（全体角色）

## 目标

平台/环境故障不阻塞项目超过一个工作窗口：故障分级识别、通道降级链、应急操作的合规边界、**事实回填义务**（排障一次、全员复用）。

## 触发场景

- git push/fetch 失败或超时；CI run 不触发、PR head 不更新；本地命令挂起；编码/乱码类报错；大文件下载截断；需要应急合入已验收内容。

## 输入

- 故障现象（报错原文/超时点/影响面）；当前待完成的 git/CI 操作。

## 输出

- 故障分级结论 + 通道选择 + 完成的操作（或升级上报）；**环境基线/rules-map 的事实回填**（新增坑、根因、修复）。

## 核心步骤

### 1. 故障分级识别（先例现象 → 判据）

| 级别 | 现象（先例实录） | 判据 |
| --- | --- | --- |
| L1 单命令挂起 | 原生命令无输出挂住；`git push` 报 SSH 22/HTTPS 443 超时 | 换通道重试一次即分辨 |
| L2 事件管道不响应 | **推送到达远端分支**（branch API 可见新 tip）但 **PR head 不更新、synchronize run 为 0** | branch API 与 PR API 交叉比对 |
| L3 端点级故障 | github.com 443 全断而 **api.github.com 可达**（rate_limit 探测） | 两端点分别探测 |
| L4 全断 | API 也超时；大文件流式下载持续截断 | rate_limit 亦超时 |
| L5 本地环境故障 | 原生 exe 全体挂起（ASCII 目录复现=与目录名无关）；编码错误（runner stdout 默认代码页）；PATH/HOME 异常 | 对照实验 + 环境变量逐一 unset |

### 2. 通道降级链（L1~L3 时依序尝试）

```
SSH 22 → HTTPS 443（git 操作，公开仓库 fetch 免凭据）
       → api.github.com REST（可达时：Git Data API 全套替代 git 操作）
       → 代理（客户端在运行时才注入；未运行时注入反而拒连——先探测再注入）
```

- 公开仓库 fetch 免凭据：`git fetch https://github.com/<owner>/<repo>.git "refs/heads/*:refs/remotes/origin/*" --prune`
- 推送经 HTTPS 需凭据（gh keyring / credential helper）；gh CLI 本身走 api.github.com，通常先于 git 端点恢复。

### 3. Git Data API 应急合入（L2/L3 时，合规边界见 ci-cd-ops）

前提：待合内容已通过验收、本地全量测试跑绿。步骤：

1. **本地解突**：merge 目标 main → 冲突处理（texts/资源类 append-only 用逐行状态机；**测试/代码交织冲突按语义解**，纯拼接会拆断函数）→ 全量测试跑绿。
2. **确定性重建校验**：解突后的基线必须**新鲜**——fetch 失败时禁止用过期 main 解突（先例：基于过期 main 的解突作废重来）。
3. **API 落分支**（api.github.com）：
   - 逐变更文件 `POST /git/blobs`（base64）
   - `POST /git/trees`（`base_tree`=当前 main 树 + 变更文件条目）
   - `POST /git/commits`（`parents` 必须是 **40 位完整 sha**；parent = 当前 main）
   - `PATCH /git/refs/heads/<分支>`（force=true，非快进更新）
4. **CI 照常触发**（ref 更新触发 pull_request synchronize）→ 等全绿。
5. **API merge**：`PUT /pulls/{n}/merge`。
6. **终验不依赖下载**：**树哈希比对**——tree sha 只由内容决定；服务端 main 树 == 本地已测状态树 ⇒ 内容逐字节一致（大文件下载截断时的替代终验）。
7. **留痕**：全过程写入验收报告"合入记录"+"应急路径合规性"小节；故障现象回填本手册与环境基线。

### 4. 辅助触发技巧（L2 时）

- 推送到达但 PR 不更新：追加一个空提交（`--allow-empty`，注明"重新触发 synchronize，内容无变化"）再推。
- PR API 短时缓存：branch API 与 PR API 结论矛盾时，以 branch API + check-runs 为准，等缓存过期。

### 5. 环境事实登记义务（本技能的核心价值）

每次排障成功后，**强制回填**两处：①本手册对应级别的新现象/新坑；②项目《环境基线》变更记录。先例登记项：中文计算机名 → HOSTNAME 乱码 → git 启动 DNS 超时（修补 env.sh）；runner stdout 默认 cp1252（PYTHONUTF8 双保险）；MSYS_NO_PATHCONV 漏置的 guest 命令 30s 超时；代理未运行时注入反而拒连。**排障不回填 = 故障必然重演。**

## 可复用要点

- **先探测后降级**：rate_limit / branch API / PR API 交叉比对，区分"L2 管道不响应"与"L3 端点故障"——处置完全不同。
- **内容终验用树哈希**，不依赖任何下载通道。
- **应急操作的合规边界**永远先于应急本身（CI 照常绿才合、留痕、追认入报告）。
- **命令与 payload 走临时文件**：Windows 命令行长度上限（WinError 206）会打断大 payload 的 API 调用。
- **本地锚定**：通道中断时把未推提交先落到本地命名分支（防 detached HEAD 丢失），恢复后按锚点续推。

## 项目参数定制位

- 通道清单（代理地址/镜像/内部 git 备源）；凭据获取方式（gh keyring / credential helper）。
- 平台特定坑清单（先例为 Windows/MSYS/GitHub——迁移到其他平台时替换为该平台实录）。
- 环境事实登记的落点文件名。

## 与其他 Skill 的边界

应急合入的前置是内容**已经**通过验收与本地测试（accept-verify）；合入后的状态回填走 accept-verify 的验收后动作；门禁设计与合规边界定义在 ci-cd-ops。
