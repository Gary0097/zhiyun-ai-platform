# App Discovery Phase 0

## 决策

应用发现属于 QwenPaw 系统插件，不属于任一业务 PawApp。搜索页面、HTTP 调用方和全局 Agent 必须读取同一份本地能力目录，不能分别维护推荐提示词。

## 第一阶段实现

- `app_catalog.json` 是版本化的真实应用目录，记录应用、功能、入口、项目地址、平台和安装状态。
- `search_engine.py` 提供不依赖模型和网络的确定性检索。
- `/zhiyun-app-discovery/search` 为 UI 和后续宿主“应用 → 我的”搜索框提供统一 API。
- `find_paw_apps` 让全局 Agent 在回答“该用哪个应用”前检索真实目录。
- 前端路由 `/apps/app-discovery` 提供可直接验收的搜索页面。

## 后续接入

QwenPaw 宿主当前没有为“已安装应用”区域提供插件插槽，本阶段不使用 DOM 注入。宿主增加稳定插槽或 AI-OS 固定 QwenPaw 前端版本后，将同一 API 接入“应用 → 我的”的常驻搜索框；搜索算法、目录和 Agent 契约无需迁移。

安装器后续根据真实安装、升级、卸载和健康检查结果生成 Workspace 运行态覆盖文件。打包目录只声明可发布能力，不能把未安装应用标记为已安装。
