# AI-OS QwenPaw-only 目标架构

## 架构决策

QwenPaw 2.1.0 是唯一 Agent OS 内核、Web/桌面界面、插件宿主和进程入口。主项目不再包含第二套 Agent Runtime、企业网关、iframe 对话或 8390 服务。

```text
用户 / Agent
    │
    ▼
QwenPaw 2.1.0 :8088
    ├── Workspace Files / Knowledge Base
    ├── System Plugins
    │   ├── Logo
    │   ├── Audit
    │   ├── App Discovery
    │   └── Data Core (SQLite in Workspace)
    └── Locked PawApps
        ├── Data Studio
        ├── Order Studio
        ├── Integration Hub
        ├── Service Studio
        ├── Supply Studio
        ├── Sales Studio
        ├── Finance Studio
        └── People Studio
```

## 运行约束

1. 仅允许 `start-ai-os.cmd` / `start-ai-os.sh` 启动系统。
2. 业务应用必须登记在 `pawapps.lock.json` 并锁定40位提交。
3. 同步源码在临时目录检出，删除 `.git` 后再交给 QwenPaw 安装。
4. Windows Desktop版只要求 `qwenpaw` CLI可用；不强制存在可导入的Python包。
5. 数据库、日志、知识文件写入Workspace，不写入Git仓库。
6. Agent工具治理类型只能是 `file`、`internal`、`network`、`shell`。
7. 分析结果不能自动执行高风险业务动作，必须保留证据与人工确认。

## 版本与升级

主仓库是发布清单。PawApp先在独立仓库测试和合并，再将合并提交写入锁文件。升级失败时回退主仓库提交即可恢复上一组锁定版本，Workspace数据不随代码回退。

---

## 双态运行体系（下一阶段目标）

现有架构以“一套运行实例 = 一个企业”为边界。下一阶段（Phase 4，见 `docs/product/PROJECT-PLAN.md`）在上述边界之上新增 **Demo / Production 双态**与持续仿真能力，作为平台级规范，供所有 Studio / App 复用。

### 统一数据上下文（DataContext）

所有应用查询必须经统一 DataContext，而非各页面自选数据集：

```text
User
 ↓
App
 ↓
DataContext（决定 data_mode / tenant_id / environment_id / data_source / time_range）
 ↓
Demo Dataset / Production Dataset
 ↓
Database
```

### 新增模块（Phase 4）

```text
Enterprise Seeder      # 企业、部门、用户、角色、权限、Agent、Skill、应用、会话、任务、Token、日志
Agent Factory          # 岗位模板 → 完整 Agent 配置（Prompt/模型/Skill/Tool/知识库/权限/Token/频率/成功率）
Simulation Runtime     # 业务事件 → Agent → Skill → Tool → 结果 → 日志 → Token → 用户行为 → 统计
Time Machine           # 2025-12-01 至当前历史数据 + 任意时间段同步切换
Data Import/Export SDK # .xlsx/.xls/.csv 导入导出、字段映射、预览、校验、去重、增量/覆盖
Data Integrity         # 跨模块一致性、异常检查、安全自动修复、Data Integrity Report
Real Data Profiler     # 以真实业务数据反校准仿真分布（Simulation/字段结构/频次/周期）
```

### 双态隔离

- 记录带 `tenant_id` / `environment_id` / `data_source`。
- `data_mode = demo | production`，产品前台使用「数据环境（演示环境/生产环境，或 Demo/Live）」措辞。
- 正式模式严禁读取演示记录；导入真实数据不污染 Demo 历史。

### 后端数据目录约束（保持）

- Studio 后端 SQLite 由 `*_STUDIO_DB` 环境变量注入，落在 `runtime/.qwenpaw-runtime-data/<studio>/`，不写入 Git 仓库。
- 双态体系的数据表/SDK 同样应写入 Workspace 可写目录或实例级数据目录，不写入仓库。
