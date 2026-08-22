# AI-OS Data Core

v0.3.0 支持用户在“统一数据中心”创建部门数据表，自定义初始字段、字段类型和必填规则。新数据表与订单表共享同一个 Workspace SQLite 数据库、导入批次、真实/模拟来源和回滚机制，为跨部门数据融合提供统一结构基础。

v0.4.0 为任意数据表增加 Excel/CSV 导入：文件解析后自动匹配同名字段或显示名称，用户可人工调整映射，必须通过预览校验后才写入真实数据批次。单文件最大 20MB、最多读取 10000 行。

v0.5.0 内置“生产日报”指标模板，包含日期、部门、产量/产值、工时、人数、成本和损耗字段；统一数据中心可以一键生成可撤销的模拟生产数据，用于直接验收 Data Studio 跨部门指标。

v0.6.0 提供受限的订单查询接口，Data Studio 可以按关键词、订单号、客户、状态和真实/模拟来源读取进度看板数据。接口不接受 SQL，单次最多返回 200 条记录。

统一数据库服务，同时提供可视化数据浏览入口 `/apps/data-core`。

可验收功能：

- “统一数据中心”页面展示数据表、记录总数、真实/模拟数据数量；
- 动态读取 Schema Registry，将用户自定义字段同步显示为表格列；
- 预览最近 100 条数据，并按真实数据/模拟数据筛选；
- 查看字段名称、类型、必填、启用及内置状态；
- 页面内一键生成 20 条可回滚模拟订单，生成后立即刷新。

Data Core 是全部业务 PawApp 共用的数据服务。应用只能通过 `/zhiyun-data-core` API 访问共享数据，不直接打开 SQLite 文件。

## 当前能力

- 数据库默认位于 `~/.qwenpaw/workspace/data-core/data-core.sqlite`。
- 可通过 `ZHIYUN_DATA_CORE_DIR` 调整数据库目录。
- 内置订单 Schema，支持用户新增、重命名和停用字段。
- 导入数据必须先预检；有字段或类型错误时拒绝提交。
- 真实数据和模拟数据都记录来源、批次和创建时间。
- 模拟数据按批次撤销，不影响真实数据。
- SQLite WAL 模式兼容 Windows 10/11 与 Ubuntu 22.04/24.04。
- AI 对话可调用 `query_enterprise_orders` 查询真实/模拟订单，不再扫描工作区猜测数据来源。
- AI 可在用户明确要求时调用 `generate_simulated_orders` 写入可撤销的模拟订单批次。

## Agent 工具

| 工具 | 用途 | 边界 |
| --- | --- | --- |
| `query_enterprise_orders` | 按关键词、订单号、客户、状态、数据来源查询 | 不接受 SQL，最多返回 200 条 |
| `generate_simulated_orders` | 生成测试或演示订单 | 仅模拟数据，返回可撤销批次 ID |

## HTTP API

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/zhiyun-data-core/health` | 数据库健康状态 |
| GET | `/zhiyun-data-core/schemas/orders` | 读取字段定义 |
| POST | `/zhiyun-data-core/schemas/orders/fields` | 新增字段 |
| PATCH | `/zhiyun-data-core/schemas/orders/fields/{name}` | 重命名或停用字段 |
| POST | `/zhiyun-data-core/imports/orders/preview` | 导入映射与校验预览 |
| POST | `/zhiyun-data-core/imports/orders/commit` | 写入已通过校验的数据 |
| POST | `/zhiyun-data-core/simulate/orders` | 生成关联模拟订单 |
| GET | `/zhiyun-data-core/orders` | 按关键词、订单号、客户、状态和来源查询订单，最多 200 条 |
| GET | `/zhiyun-data-core/records/orders` | 查询订单记录 |
| POST | `/zhiyun-data-core/batches/{id}/rollback` | 撤销导入或模拟批次 |

本阶段 API 接收前端解析后的 Excel/CSV 行数据。文件选择、工作表选择和列映射 UI 在 Data Studio 独立仓库实现，Data Core 负责统一校验、来源记录和事务写入。

## 验证

```bash
cd plugins/zhiyun-data-core
python -m unittest -v test_data_core.py
```
