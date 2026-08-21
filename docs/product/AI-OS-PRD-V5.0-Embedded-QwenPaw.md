# 智造云 AI-OS 产品需求文档 V5.0

> 产品基线：QwenPaw `release/v2.1.0` / `e4995dcf516d27400fbc33891aa3dcbcf79acc7a`  
> 架构状态：嵌入式重构基线  
> 更新日期：2026-08-21  
> 替代范围：PRD V4.0 中“独立企业服务、iframe、Enterprise Gateway”目标架构

## 1. 产品决策

智造云 AI-OS 直接以 QwenPaw 为系统主体，不再把 QwenPaw 当成外部插件、聊天页面或旁路运行时。

- QwenPaw 提供桌面、对话、Agent、Workspace、文件、记忆、Skills、Plugins、MCP、Cron 和 PawApp 容器。
- 功能清单中的企业模块全部打包为 PawApp，安装后成为系统桌面应用。
- 应用数据、执行日志、审计日志、产物和知识文件全部保存在当前 Workspace。
- 原 Node 企业后台只作为存量数据迁移来源，不再承接新增功能。
- 原 HTTP Enterprise Gateway、iframe 对话和 DeepSeek Harness 路线停止开发。

## 2. 产品形态

```text
智造云 AI-OS（QwenPaw 下游发行版）
├── QwenPaw Console / Desktop / Chat
├── Agent Workspace
│   ├── data/ai-os.sqlite
│   ├── logs/runtime.jsonl
│   ├── logs/audit.jsonl
│   ├── files/
│   ├── knowledge/
│   ├── artifacts/
│   ├── sessions/
│   └── memory/
└── PawApps
    ├── 任务与项目中心
    ├── 企业知识助手
    ├── AI-OS 监视器
    ├── 订单与交付风险
    ├── 库存与采购
    ├── 客户与售后
    ├── 邮件营销数字员工
    ├── 售前报价数字员工
    └── 财务票据数字员工
```

## 3. 部署与数据边界

V5.0 首期采用“一家企业一个 AI-OS 实例、一个主 Workspace”的隔离方式。Workspace 即企业数据边界、备份边界和迁移边界。

- 不依赖浏览器传入的 `user_id` 判断企业身份。
- 不在一个 Workspace 中混放多家企业的业务数据。
- 多企业由独立实例或独立 Workspace 隔离，禁止跨 Workspace 直接读数据库。
- Workspace 下载、备份和恢复必须包含数据库、日志、文件、知识与产物。

## 4. Workspace 数据规范

| 路径 | 内容 | 规则 |
| --- | --- | --- |
| `data/ai-os.sqlite` | 业务表、任务、Execution、Tool 索引 | SQLite WAL；应用按前缀建表 |
| `logs/runtime.jsonl` | Agent、Tool、任务运行事件 | 只追加；每行一个 JSON 对象 |
| `logs/audit.jsonl` | 高风险操作与数据变更 | 只追加；包含前后值摘要与操作者 |
| `files/` | 用户上传和业务原件 | 保留原文件名、哈希和来源 |
| `knowledge/` | 企业知识源文件和索引元数据 | 回答必须可定位来源 |
| `artifacts/` | 报价、报告、图片、表格等产物 | 记录创建应用、会话和 Trace |

`ctx.storage` 只用于 PawApp 的轻量界面状态和偏好，不得保存正式订单、工单、票据或审计事实。

## 5. PawApp 应用包规范

每个企业功能必须是一个可独立安装和卸载的 PawApp 包：

```text
pawapps/<app-id>/
├── plugin.json
├── backend/main.py
├── ui/index.js
├── migrations/
├── fixtures/
├── tests/
└── README.md
```

每个应用必须声明：

- 应用 ID、版本、图标、前后端入口和 QwenPaw 兼容版本。
- 提供的 Tool 名称、输入 Schema、只读/写入属性和风险等级。
- 数据表前缀、迁移版本和卸载时的数据保留策略。
- 输入、运行状态、结构化输出、Artifact 和 Trace 展示。
- Happy Path、模型错误、Tool 错误和业务校验失败验收。

## 6. 统一执行与日志

所有 PawApp 执行必须生成唯一 `trace_id`，并遵循：

```text
用户输入/应用操作
→ app_execution(running)
→ Tool 事件
→ 数据或 Artifact
→ app_execution(success/failed/stopped)
→ runtime.jsonl
```

最低字段：`timestamp`、`trace_id`、`app_id`、`event`、`status`、`duration_ms`、`session_id`、`artifact_ids`、`error_code`。

日志正文不得记录模型密钥、访问令牌、密码、完整 Cookie 或票据中的敏感原文。

## 7. 高风险操作

本期不建设 Capability 管理和 Approval 审批中心，但保留以下控制：

- 只读 Tool 默认可执行。
- 修改、删除、发送、付款、批量外发等操作必须调用 `ctx.ui.confirm`。
- 无交互通道时，高风险操作失败关闭，不允许自动放行。
- 参数白名单、单次数量上限、频率限制和幂等键。
- 变更前后摘要写入 `logs/audit.jsonl` 和数据库审计索引。

## 8. 核心应用清单

| 阶段 | 应用 | 核心闭环 |
| --- | --- | --- |
| R1 | 订单与交付风险 | 对话查询订单 → 打开应用 → 风险列表 → Trace |
| R1 | AI-OS 监视器 | 读取 Workspace 日志和数据库 → KPI/失败/Trace |
| R2 | 任务与项目中心 | 创建任务 → Agent 执行 → Checkpoint → Artifact |
| R2 | 企业知识助手 | 导入文件 → 检索回答 → 来源定位 → 更新记录 |
| R3 | 库存与采购 | 库存查询 → 低库存判断 → 补货建议 → 任务 |
| R3 | 客户与售后 | 客户问题 → 知识检索 → 工单/转人工 → 报告 |
| R4 | 售前报价数字员工 | 需求 → 配置/价格规则 → 报价文档 |
| R4 | 邮件营销数字员工 | 市场/素材 → 内容 → 发送任务 → 状态日志 |
| R4 | 财务票据数字员工 | 原件 → 识别索引 → 查询 → 报表与原件追溯 |

## 9. 验收标准

1. 用户只启动智造云 AI-OS，不需要另外启动企业后台。
2. 桌面应用可从 QwenPaw 内打开，也可从对话调用。
3. 重启后应用数据、会话、文件、日志和产物仍存在。
4. Workspace 打包恢复后，业务数据与 Trace 可以继续查询。
5. 订单演示不得扫描工作区猜测数据，必须调用订单 PawApp Tool。
6. 每次真实执行返回新的 Trace ID，失败不得显示成功。
7. 高风险写入在无确认时不得执行。

## 10. 迁移策略

### 10.1 保留

- 现有业务表结构和样例数据中的有效字段。
- 已完成的高风险控制、Trace 字段和品牌资源。
- 有真实业务闭环价值的功能逻辑与测试场景。

### 10.2 重写

- Node REST 页面改写为 PawApp Backend 与 UI。
- 企业数据库迁移到 Workspace `data/ai-os.sqlite`。
- 日志中心改为读取 Workspace SQLite 索引与 JSONL 原始日志。
- 企业 Tool 改为 PawApp 内部 Tool，不再经 HTTP Gateway。

### 10.3 退出

- `apps/enterprise` 独立服务。
- iframe 对话入口。
- DSH/DeepSeek Harness 适配器。
- QwenPaw 到企业后台的 HMAC Gateway。

## 11. 分阶段实施

### Phase R0：嵌入式基线

- 固定 QwenPaw 上游 commit、许可证和同步策略。
- 建立 Workspace 目录、SQLite、JSONL 和 PawApp 包规范。
- 更新品牌插件为系统核心应用包。

### Phase R1：第一个真实闭环

- 迁移订单数据和风险规则。
- 实现订单 PawApp、订单查询 Tool 和风险页面。
- 对话、应用、数据库、日志、Trace 完整联通。

### Phase R2：系统级应用

- 任务与项目中心、企业知识助手、AI-OS 监视器。

### Phase R3-R4：业务数字员工

- 按第 8 节顺序逐个迁移，每个应用独立验收后进入主分支。

## 12. 发布阻断条件

以下任一情况存在不得发布：仍需单独启动旧企业后台；应用只展示静态页面；业务数据写在浏览器内存或插件安装目录；Agent 看不到应用 Tool；数据库不在 Workspace 备份内；Trace 无法关联应用、Tool 和 Artifact；高风险操作可绕过确认。
