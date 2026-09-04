# 智造云 AIOS

基于 **原版 QwenPaw 2.2.0 + QwenPaw Hub** 的智造云品牌发行版：开箱即用的企业智能体操作系统。

> 产品定义：[`docs/product/PRD-V7.0-AIOS-2.2.0.md`](docs/product/PRD-V7.0-AIOS-2.2.0.md)

## 品牌与外观自定义

控制台的品牌（Logo、主题色、登录页封面）在每次启动时由 `apps/zhizaoyunAIOS/scripts/patch-console-ui.mjs`
应用到 QwenPaw 控制台。默认使用仓库 `branding/` 下的灵泽万川资产；终端用户可在
Workspace 品牌目录（`~/.qwenpaw/branding/`）放置以下文件进行整机自定义，重启服务后生效：

- `logo.json` — 自定义 Logo：`{"path": "~/.qwenpaw/branding/my-logo.png", "mime": "image/png"}`
  （替换 favicon、启动页、登录页与聊天头像全部默认 Logo）；
- `theme.json` — 自定义主题与封面：
  `{"primary": "#0086AD", "primaryHover": "#00A3C4", "primaryActive": "#00688A", "loginLogoHeight": 88, "loginBg": "cover.jpg"}`
  （`loginBg` 为 branding 目录内任意 jpg/png，替换登录页背景渐变为封面图）。

## 项目介绍

智造云 AIOS 2.2.0 是一台"智造云牌"的 QwenPaw 智能体计算机：

- **原版内核**：QwenPaw 2.2.0（智能体运行时 + 控制台 + Agent 容器），不改内核行为，随锁文件整体升级
- **原生登录**：单机用 QwenPaw 原生认证（首个用户控制台注册）；多用户用 QwenPaw Hub 账号体系
- **模型账号集中管理**：管理员在 Hub 服务器端凭据保险库统一录入供应商 API Key，按用户运行环境自动注入——员工全程零接触 Key
- **智造云品牌**：控制台与 Hub 界面全套"智造云 AIOS"标识与齿轮 Logo
- **无捆绑业务应用**：应用体系与系统解耦，独立交付、可选加装（历史 19 个业务应用见各应用仓库）
- **数据留在本机**：工作区、数据库、凭据全部保存在安装目录（云端模型的对话内容会发送给所选供应商，机密场景请用 Ollama/LM Studio 本地模型）

## 快速运行

### 单机模式（端口 8088）

```cmd
:: 首次：安装运行环境（需 Node.js 20+）
install-oneclick.cmd

:: 之后：启动
start-ai-os.cmd
```

打开 http://127.0.0.1:8088 → 注册首个登录账号 → 设置 → 模型 配置供应商 → 开始对话。

### Hub 多用户模式（端口 8000，推荐团队使用）

```cmd
start-hub.cmd   :: 首次自动安装 Hub 环境（qwenpaw[hub]==2.2.0）
```

1. 打开 http://127.0.0.1:8000 注册管理员（首个账号）
2. 管理界面「凭据管理」录入模型供应商 Key（如 `DASHSCOPE_API_KEY`）
3. 「用户管理」创建员工账号；关闭自助注册（`hub.yaml` → `registration.enabled: false`）
4. 员工访问 `http://<服务器IP>:8000` 登录，直接选择模型使用

## 架构

```
智造云 AIOS 2.2.0
├─ QwenPaw 2.2.0（原版内核；版本锁 apps/zhizaoyunAIOS/qwenpaw.lock.json）
│  ├─ 单机控制台  http://127.0.0.1:8088（原生登录 QWENPAW_AUTH_ENABLED）
│  └─ QwenPaw Hub http://<host>:8000（多用户账号 + 凭据保险库集中管 Key）
├─ 品牌化 patch-console-ui.mjs（智造云 AIOS 文案 + branding/ 资产）
└─ 启动/安装脚本（Windows .cmd + Linux .sh 双平台）
```

本仓库只包含：启动器、品牌资产、安装脚本、文档与版本锁。
**不含任何业务应用**——应用以独立仓库存在，后续可选加装。

## 常用入口

| 命令 | 用途 |
| --- | --- |
| `start-ai-os.cmd/.sh` | 启动单机服务（8088） |
| `start-hub.cmd/.sh` | 启动多用户 Hub（8000，首次自动装环境） |
| `setup-ai-os.ps1/.sh` | 安装/修复单机运行环境 |
| `setup-hub.ps1/.sh` | 安装/修复 Hub 运行环境 |
| `diagnose-ai-os.cmd/.sh` | 启动诊断 |
| `node scripts/verify-release.mjs` | 发布门禁 |

## 文档

- 产品需求：[PRD V7.0（智造云 AIOS 2.2.0）](docs/product/PRD-V7.0-AIOS-2.2.0.md)
- 使用说明：[docs/user-manual](docs/user-manual/README.md)（v1.x 手册，2.2.0 版重写中）
- QwenPaw 官方文档：https://qwenpaw.agentscope.io/

## 国内镜像（Gitee）

仓库同步于 Gitee：`zhiyun-ai-platform`（发布渠道见 dist/ 与 Releases）。
