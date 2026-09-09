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
