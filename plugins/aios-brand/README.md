# aios-brand — 智造云AIOS 品牌层（前端扩展插件）

issue #126：把品牌化从「对宿主构建产物做字符串手术」迁移到 QwenPaw 2.2.0 官方
前端扩展点（`window.QwenPaw.*`），使 QwenPaw 运行时升级时品牌层无需重构。

## 能力与实现方式

| 能力 | 官方扩展点 |
|---|---|
| 顶栏 Logo | `Q.slot.replace('header.logo')` |
| 帮助中心页面 + 侧边栏菜单 | `Q.route.add` + `Q.menu.add`（iframe 内嵌 `/aios-docs.html`） |
| 蓝绿主题（antd CSS 变量族） | 运行时注入 `style#aios-brand-theme` |
| 聊天主色 | `Q.chat.theme.set({ colorPrimary })` |
| 隐藏顶栏外链（GitHub / 文档资料） | 文本观察器（MutationObserver），不依赖压缩类名 |
| 模型快配（2.2.2 起） | 官方 `route` / `menu` / `host.fetch`，界面按需加载 |

主题色与 Logo 由启动器补丁同步的自定义配置（`workspace/branding/theme.json`、
`logo.json`）仍然生效于静态资产层；本插件的固定色值为默认蓝绿。

## 分发

`ensure-workspace.mjs` 在每次启动时把本目录同步到
`workspace/plugins/aios-brand`（版本变化时覆盖），QwenPaw 控制台经
`/frontend_plugin` 自动加载 `dist/index.js`。无需 `qwenpaw plugin install`。

## 升级免疫性

本插件只调用官方文档（`docs/console-help/src/plugins.zh.md`）承诺的扩展 API，
不匹配任何压缩后代码模式；QwenPaw 升级仅需保持 `qwenpaw_version.min` 满足。
残留限制：控制台**文案**品牌化（QwenPaw→智造云AIOS）仍由
`patch-console-ui.mjs` 兜底（i18n 在宿主 bundle 内，无官方覆盖点）。

## 模型快配

侧栏“模型快配”将原生服务配置、连接检测、模型列表和应用范围收拢到一个页面：

1. 选择已有服务，或填写新兼容服务的名称、地址和密钥，无需自己编写提供商 ID。
2. 点“保存并获取模型”，可搜索列表或手填服务端模型 ID。完整 `/v1/chat/completions` 地址会识别为基础地址。
3. 选择“全局默认”或“仅当前智能体”后应用。智能体已有单独模型不会被全局选择覆盖。

Ollama / LM Studio 复用原生本地提供商，支持不填密钥；新建通用兼容服务需填写密钥。编辑已有服务时密钥留空表示保持原值，界面不回显密钥，不把凭据保存到浏览器存储。高级请求头和生成参数仍由原生页面管理，快捷保存不会清空它们。

使用官方同源请求及原生凭据、权限、模型存储，不添加另一套后端或修改核心。Hub 集中供给环境不开放此向导的写入，转到原生模型管理。原生激活模型可能启动能力探测，页面明确提示；连接成功和模型设置成功不代表推理测试通过。

模型模块只在打开页面时加载，列表最多渲染 100 项；已有模型使用原生分页搜索，远端模型发现仅在用户点击时执行。批量配置、供应商专属高级选项仍在“全部供应商 / 高级模型设置”。
