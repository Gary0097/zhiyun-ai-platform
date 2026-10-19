# 2.2.2 Windows 完整发行与 Hub 转换验收

Issue #164，目标版本 `2.2.2-office-1.6.1`。

Hub 原生 LocalProcessRuntimeProvisioner 清洗父进程环境；仅设置 SOFFICE/PATH 无法让成员继承安装目录的 LibreOffice。Windows AppContainer 的只读资源也不包括 extras。

本次不修改上游内核或放宽隔离：安装阶段将完整 LibreOffice 放入 Hub venv/aios-libreoffice，在 Hub venv/Scripts 安装 soffice.exe 原生调用入口。上游原生 PATH 已包含该 Scripts，现有只读根也已包含 venv。转换入口直接调用随包 soffice.com，不经 shell，每次创建并清理独立的成员临时配置。Hub 办公依赖与单机分开预装、分别记录标记。完整 Windows 安装器同时配置单机和 Hub；普通启动使用标记快速返回。

发布前必须通过：全新离线安装、Windows 原生 AppContainer 内两个合成成员的 Word/PPT 转 PDF 与 Excel 重算、并发配置隔离及跨成员文件读取拒绝。测试必须以管理员权限运行，不允许模拟隔离成功或禁用 AppContainer。测试入口 `scripts/test-hub-office-windows.py`，使用安装包 Hub Python，要求专用合成验收目录标记。

已有 Release 不覆盖；新版本通过验收并发布后才升级 H 盘，并保留生产模型配置、账号、主密钥和工作区。

## 2026-10-19 实机结果：尚不可发布

- 源码发布门禁、品牌补丁回归及 GitHub Ubuntu 检查通过。最终候选离线缓存安装全部 44 个锁定办公依赖通过，EXE 构建成功；这些结果不等于完整安装验收成功。
- 干净目录使用真实安装器逻辑，在屏蔽系统 Node/Python、阻断外网的环境解压 82,108 个文件并安装单机及 Hub 运行环境。Hub 入口未转发版本输出，导致安装验收失败；诊断副本修正输出后可完成 Hub 安装。
- 单机诊断副本的 Word、Excel、PPT、PDF、本地 OCR、文件/数据/图片、办公转换与公式重算七组文件测试通过。浏览器、外网搜索、桌面控制、模型对话生成、云端 OCR 仍不在本轮文件测试的通过范围。
- 原生 Windows AppContainer 已实际复现 Hub 转换失败：CLI 两路转换超时，后续 LibreOfficeKit 诊断出现初始化异常及未生成文件。相同成员环境在隔离外能转换；仅有环境变量/路径修正不足以证明问题解决。失败即阻止发布，不能绕过官方隔离。
- 当前工作区的 LibreOfficeKit 入口仍属未通过验收的试验修改，不能按成功修复交付。必须重新构建最终包、干净安装、重新运行原生双用户转换及隔离测试，全部通过后才能合并和发布。

## 中文默认配置

安装/启动时应用中文界面与智能体语言（zh），语音/SIP 默认语言为 zh-CN，默认英文问候语和默认英语语音切换到中文。保留模型、凭据、通道启用状态及其余设置；不启用未配置的语音服务，不将配置检查当作电话服务验收。

H 盘现有 4 个配置文件已检查，其中 3 个语言默认值修正；6 个账号/密钥文件 SHA-256 不变，模型及非语言设置逐项对比通过。变更前配置另存于升级备份中的 chinese-defaults-before。完整升级备份同步后，282 个受保护文件核验一致。H 盘程序仍为 2.2.1-office-1.6.0，尚未执行 2.2.2 程序升级和启动速度验收。
