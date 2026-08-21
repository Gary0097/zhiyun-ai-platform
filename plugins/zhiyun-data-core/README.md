# AI-OS Data Core

Data Core 是全部业务 PawApp 共用的数据服务。应用只能通过 `/zhiyun-data-core` API 访问共享数据，不直接打开 SQLite 文件。

## 当前能力

- 数据库默认位于 `~/.qwenpaw/workspace/data-core/data-core.sqlite`。
- 可通过 `ZHIYUN_DATA_CORE_DIR` 调整数据库目录。
- 内置订单 Schema，支持用户新增、重命名和停用字段。
- 导入数据必须先预检；有字段或类型错误时拒绝提交。
- 真实数据和模拟数据都记录来源、批次和创建时间。
- 模拟数据按批次撤销，不影响真实数据。
- SQLite WAL 模式兼容 Windows 10/11 与 Ubuntu 22.04/24.04。

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
| GET | `/zhiyun-data-core/records/orders` | 查询订单记录 |
| POST | `/zhiyun-data-core/batches/{id}/rollback` | 撤销导入或模拟批次 |

本阶段 API 接收前端解析后的 Excel/CSV 行数据。文件选择、工作表选择和列映射 UI 在 Data Studio 独立仓库实现，Data Core 负责统一校验、来源记录和事务写入。

## 验证

```bash
cd plugins/zhiyun-data-core
python -m unittest -v test_data_core.py
```
