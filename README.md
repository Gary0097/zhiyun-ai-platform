# Zhiyun AI-OS

智造云 AI-OS 以 **QwenPaw 2.1.0** 为唯一运行内核、桌面交互和 Agent 容器。主仓库只负责系统插件、统一工作区、版本锁与跨平台启动；业务能力由独立 PawApp 仓库交付。

## 唯一启动入口

- Windows：`start-ai-os.cmd`
- Ubuntu / Linux：`./start-ai-os.sh`
- 地址：`http://127.0.0.1:8088`

无需也禁止启动 8390、DeepSeek Harness 或旧 enterprise 服务。详细步骤见 [快速部署](docs/operations/QUICKSTART.md)。

## 当前组成

- QwenPaw 2.1.0：对话、Agent、文件与知识库、插件宿主
- 系统插件：Logo、日志审计、应用发现、Data Core
- Data Studio：数据导入、订单看板、风险、趋势、日报和跨部门分析
- Order Studio：订单格式化、模板适配、合同审查与一致性验证
- 高风险控制：审计全部 Tool 调用，并硬阻断系统盘递归删除、磁盘格式化、破坏性 Git 重写和整库/整表删除
- Workspace：数据库、日志、知识库和用户数据的唯一持久化位置

外部 PawApp 由 `apps/qwenpaw-embedded/pawapps.lock.json` 锁定到确定提交。不要直接修改 `runtime/pawapps` 或 `~/.qwenpaw/plugins` 中的安装副本。

## 发布验收

```bash
node scripts/verify-release.mjs
```

发布门禁会验证纯 QwenPaw 架构、版本锁、启动器、内外部 PawApp 版本/治理类型、78项 Python 测试和 Windows/Linux 入口。遗留架构的移除记录见 [迁移说明](docs/migration/LEGACY_REMOVAL.md)。
