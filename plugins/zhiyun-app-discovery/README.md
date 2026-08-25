# 应用与项目中心 PawApp

`zhiyun-app-discovery` 是 AI-OS 的事实入口：它展示当前真实安装的应用、检索 PRD 规划能力，并公开 31 项功能的可审计交付进度。

## 页面

- **我的应用**：只显示当前真实安装的 PawApp 和系统组件；按功能大类分组展示（数据分析、订单管理、售后服务、供应链、销售客户、财务、组织协同、系统集成、知识库、系统组件）。每张应用卡片内列出其真实能力（`capabilities`），可直接点击功能名称跳转到对应应用；有页面的应用同时提供“打开”按钮。
- **应用搜索**：检索已安装应用与规划能力。尚未创建的应用明确显示“未开发”，没有虚假仓库链接或入口。
- **项目进度**：逐项展示 31 项 PRD 功能的承载应用、状态、百分比和验收差距。

> 相关应用级需求文档见仓库 `docs/apps/` 目录（每个功能应用一份独立需求/开发文档），产品级总体 PRD 见 `docs/product/AI-OS-PRD-V6.4-QwenPaw-PawApps.md`。

## 接口与 Agent

- `GET /zhiyun-app-discovery/catalog`：应用事实目录（含 `category`、`route`、`capabilities`）。
- `GET /zhiyun-app-discovery/search?q=交付风险`：能力搜索。
- `GET /zhiyun-app-discovery/progress`：31 项功能进度及汇总。
- `find_paw_apps`：全局 Agent Tool；规划能力可以被发现，但不会被描述成当前可用。

## 状态口径

- `installed`：已安装，可在当前 AI-OS 中使用。
- `planned`：已进入 PRD，但承载应用尚未开发。
- 功能进度以可验收结果计算，不以目录、空页面或仓库名称代替完成度。

## 验证

```bash
cd plugins/zhiyun-app-discovery
python -m unittest -v test_search_engine.py
python -m py_compile app_discovery_plugin.py search_engine.py
node --check ui/index.js
```
