# 2.2.2 Windows 完整发行与 Hub 转换验收

Issue #164，目标版本 `2.2.2-office-1.6.1`。

Hub 原生 LocalProcessRuntimeProvisioner 清洗父进程环境；仅设置 SOFFICE/PATH 无法让成员继承安装目录的 LibreOffice。Windows AppContainer 的只读资源也不包括 extras。

本次不修改上游内核或放宽隔离：安装阶段将完整 LibreOffice 放入 Hub venv/aios-libreoffice，在 Hub venv/Scripts 安装 soffice.exe 原生调用入口。上游原生 PATH 已包含该 Scripts，现有只读根也已包含 venv。转换入口直接调用随包 soffice.com，不经 shell，每次创建并清理独立的成员临时配置。Hub 办公依赖与单机分开预装、分别记录标记。完整 Windows 安装器同时配置单机和 Hub；普通启动使用标记快速返回。

发布前必须通过：全新离线安装、Windows 原生 AppContainer 内两个合成成员的 Word/PPT 转 PDF 与 Excel 重算、并发配置隔离及跨成员文件读取拒绝。测试必须以管理员权限运行，不允许模拟隔离成功或禁用 AppContainer。测试入口 `scripts/test-hub-office-windows.py`，使用安装包 Hub Python，要求专用合成验收目录标记。

已有 Release 不覆盖；新版本发布后才备份升级 H 盘，并保留生产模型配置、账号、主密钥和工作区。最终验收结果将在测试后补录。
