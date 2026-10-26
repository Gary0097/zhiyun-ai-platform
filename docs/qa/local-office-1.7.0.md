# 本地轻量办公版 1.7.0

Issue #169，2026-10-26。用户授权补齐 Word、Excel、PPT、PDF，保留现有模型、账号及工作区，完成测试后发布 Windows 安装包。

## 产品与数据边界

使用官方 QwenPaw 2.2.2.post1（上游标签 v2.2.2.post1，提交 b6715daabaa4f966626317452980fb84b8be9ab9），不修改核心。Windows 安装器清单版本为 2.2.2.1，避免把 PEP 440 post 版本直接作为 Windows 数字版本。

`--local-office` 构建的安装包只安装单机运行时，不预装第二份 Hub venv。Hub 脚本保留，可在需要时主动安装。Python 办公库、LibreOffice、docx/pptxgenjs/sharp 的 npm 锁定依赖在构建/安装阶段准备，运行期间不调用 npm、pip 或 uv 下载。

本地接入配置 `apps/zhizaoyunAIOS/runtime/local-instance.json` 只保存工作区、凭据目录和登录开关，不包含密钥。`connect-existing.ps1` 必须在原服务停止后显式执行，直接沿用原目录，不移动用户数据。安装器重复修复保留已保存的接入路径；普通启动不重复写工作区。品牌只同步自有 aios-brand，办公技能使用已有的同名内容保护和禁用状态保护；接入保留原始 AGENTS.md 和 system_prompt_files，不为省 token 替换用户提示词。

默认新安装启用原生登录。用户针对当前 H:\Qwenpaw（无账号、原本免登录）明确选择“沿用本机免登录，仅允许本机访问”。该模式必须显式传 `-LocalNoAuth`，发现 auth.json 时拒绝关闭登录，所有接入启动均固定绑定 127.0.0.1，不能用于 Hub/局域网。

## 模型与启动

模型快配 1.2.0 保留已有供应商配置、留空密钥、高级参数与智能体独立模型。修复免费/OAuth 服务没有 API Key 时被旧列表过滤的问题；不复制或显示凭据。

接入启动器只检查端口及锁定运行时版本，然后启动官方服务。不在启动时扫描/安装办公库，不重复同步技能/品牌、不启动额外服务。以 `/api/healthz` 证明智能体就绪，首页 HTTP 200 不能代替就绪。遇到其他占用端口的实例明确退出，不结束其他程序。

## 验收口径

核心安装校验、原生聊天和基线数据已记录在本机 audit-20261026。备份为 H:\Qwenpaw-backups\20261026-local-office169；不上传该备份、个人数据或模型凭据。

办公检查使用 scripts/test-office-capabilities.py 验证真实文件数据、转换与公式重算；npm 模块另做实际文件生成检查。隔离测试副本必须重映射 config.json/agent.json 内的绝对工作区路径，否则复制目录并不能隔离用户数据。渲染后的视觉检查、实际模型工具调用及完整离线安装结果在最终交付时报告，未通过的项目不能归为通过。

完整发布门禁包含本地接入的账号保护、丢失目录拒绝以及模型/提示词保留测试。Windows EXE/ZIP 验收必须使用最终提交构建的归档，不将源码运行结果冒充安装包验收。Linux 保留现有安装与启动入口，本次未做 Linux 实机或 Windows 干净虚拟机验收。

## 接入与回退

备份原工作区与凭据；停止原服务；安装新版到独立可写目录，然后执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File connect-existing.ps1 -Workspace C:\Users\本人\.qwenpaw -SecretDir C:\Users\本人\.qwenpaw.secret
```

仅明确选择本机免登录且原本没有账号的安装可追加 `-LocalNoAuth`。接入不更改原模型凭据。新安装、已有账号及 Hub 继续使用原生登录。

回退时停止新版服务，使用原 H:\Qwenpaw\.venv\Scripts\qwenpaw.exe app 及原工作区/凭据启动；需要恢复数据时使用同一时间点的完整备份。旧运行时保持不动，不在升级中删除，避免破坏用户恢复路径。
