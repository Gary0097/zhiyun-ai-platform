# 应用发现 PawApp

`zhiyun-app-discovery` 是 AI-OS V6.4 Phase 0 的系统应用，提供同一份真实应用能力索引给应用搜索页、HTTP API 和全局 Agent。

## 能力

- 本地关键词、别名、同义词和模糊检索，不依赖模型或公网。
- `GET /zhiyun-app-discovery/search?q=交付风险` 搜索接口。
- `/apps/app-discovery` 可视化搜索页。
- `find_paw_apps` Agent Tool；无结果时明确返回缺失能力，不虚构应用。
- 预置 PRD V6.4 的 8 个独立 PawApp、原生 Workspace Knowledge Base 及其功能映射。

目录中的 `available` 表示能力已规划且项目入口可展示，不表示应用已经安装。后续独立仓库发布 PawApp 时，安装器负责将状态、版本、健康状态和入口刷新到本地目录。

## 验证

```bash
cd plugins/zhiyun-app-discovery
python -m unittest -v test_search_engine.py
```
