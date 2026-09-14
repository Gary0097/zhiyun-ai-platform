# 2.2.1 升级验证

关联：#142；基于 #141 的帮助适配分支。

运行时锁从 2.2.0 升至 2.2.1，Git 标签 v2.2.1 对应 cae5773707b26ab2fd00903f84b712387894b256。版本来自 PyPI 正式包；来源发布说明：https://github.com/agentscope-ai/QwenPaw/releases/tag/v2.2.1 。

本次仅升级运行时、版本指引与相应门禁，保留安装目录、账号、工作区以及上一轮普通用户帮助适配。没有捆绑 Creator 或业务应用，也没有把上游新增能力作为全部实测通过的交付承诺。

## 验证

- Windows 项目隔离运行环境安装成功，CLI 返回 2.2.1。
- 对 2.2.1 实际 Console 应用品牌补丁成功。
- `node apps/zhizaoyunAIOS/scripts/test-patch-console-ui.mjs`：78 项通过。
- `node scripts/verify-release.mjs`：完整门禁通过。
- 本机 `/api/version` 返回 `2.2.1`；`/api/auth/status` 返回认证启用、已有用户；帮助页面 HTTP 200，用户指引保留。升级前后 auth.json 摘要一致（不记录凭据或摘要值）。
- 本机升级首次启动中，飞书 lark_oapi 大量模块导入阻塞了 HTTP 响应；采样栈显示导入持续前进，首次启动耗时需计入验收。
- Linux 继续由 setup-ai-os.sh / setup-hub.sh 读取同一版本锁，本轮未进行 Linux 实机升级。
- Hub、多模型真实对话、全界面与完整升级/卸载验收仍需单独验证；本轮没有构建或发布 EXE/ZIP。

## 本机恢复方法

升级前把旧运行环境、启动脚本、版本锁和帮助源保留在安装目录 upgrade-backups 下，并在服务停止后备份 workspace。

如需回退：停止本安装目录服务，先保存升级后新增数据；将新版运行环境移到另外的保留目录，将备份 runtime 恢复到 apps/zhizaoyunAIOS/runtime/zhizaoyunAIOS，并恢复版本锁、scripts 和 docs/console-help。原虚拟环境须回到原安装路径。只有确需恢复旧数据且已保存新增数据时才恢复 workspace 快照，避免丢失升级后的工作。最后从原安装目录运行 start-ai-os.cmd。

原安装器版本记录继续保留用于追溯；运行时升级不等于重新构建安装器。
