# 智造云 AI-OS

**运行在 QwenPaw 上的企业 AI 应用工作台**：一个统一桌面，一组面向真实岗位任务的业务应用，一条"导入数据 → 智能分析 → 审阅交付"的完整闭环。

[![release gate](https://github.com/Gary0097/zhiyun-ai-platform/actions/workflows/release-gate.yml/badge.svg)](https://github.com/Gary0097/zhiyun-ai-platform/actions/workflows/release-gate.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

## 项目介绍

智造云 AI-OS 面向制造型企业的日常经营场景——销售、财务、人力、供应、售后、订单与数据分析——把这些岗位里"反复手工整理 Excel、反复写分析报告"的工作，交给应用内的智能体完成：

- **直接导入数据即可使用**：每个业务表格支持「下载导入模板 → 填入真实数据 → 导入 Excel/CSV → 一键分析」，导入内容带来源标记，可继续手工修改。
- **结构化结果而非聊天文字**：每次分析产出 KPI 卡片、明细表、方法标签与 Trace 的**可审阅工件**，由具名审阅人接受/驳回后才可导出。
- **应用内真实智能体对话**：每个应用内置"问 Agent"，接入本地或云端大模型（OpenAI 兼容接口），流式回答基于本应用真实工具执行，不凭空编造。
- **数据环境双态**：统一数据中心区分「演示 / 正式」两套数据环境，互不污染；支持批次管理与撤销。
- **安全底座**：全部 Agent 工具调用进入哈希链审计；系统盘递归删除、磁盘格式化、破坏性 Git 重写、整库整表删除等灾难操作被硬阻断。

## 应用一览

| 应用 | 版本 | 能力 |
| --- | --- | --- |
| 企业数据分析中心 Data Studio | 0.9.2 | 数据接入、订单看板、交付风险预警、指标趋势、问数报告 |
| 智能订单处理中心 Order Studio | 0.7.2 | 客户订单格式化、多模板适配、合同要素提取与一致性验证、异常流程 |
| 智能销售中心 | 0.3.0 | 销售 BI、RFM 客户分层、业绩达成统计 |
| 智能财务中心 | 0.3.0 | 报销审核、财务看板、成本预测 |
| 智能人力中心 | 0.3.0 | 权限建议、通讯录检索、审批路径推荐、员工关怀、人力分析 |
| 智能供应中心 | 0.3.0 | 供应商评估、智能补货、供应链风险监控 |
| 智能售后服务中心 | 0.3.0 | 咨询应答、意图识别、售后工单派单、知识库构建 |
| 系统集成中心 Integration Hub | 0.2.1 | 文件/API/数据库连接器、字段映射、写入统一数据中心 |

系统插件：登录与权限（zhiyun-auth）、统一数据中心（zhiyun-data-core）、安全审计中心（zhiyun-audit）、应用与项目中心（zhiyun-app-discovery）、企业环境初始化器（zhiyun-enterprise-seeder）、品牌 Logo。

## 快速运行

> **登录账号：`admin` / `ZhizaoYun@2026`**（详见下方说明）

### 方式一：一键安装包（推荐）

从 GitHub Releases 下载一键安装包并解压：

**https://github.com/Gary0097/zhiyun-ai-platform/releases/latest**

- Windows：解压后双击 **`install-oneclick.cmd`** —— 自动安装运行时与锁定应用、启动服务并打开浏览器
- Ubuntu / Linux：`bash install-oneclick.sh`
- 包内含 `INSTALLER-VERSION.txt` 与 `.sha256` 校验文件；安装器按锁定的正式提交拉取运行时与应用

### 方式二：源码安装

#### 前置要求

- Windows 10/11 x64 或 Ubuntu 22.04/24.04 LTS x86_64
- [Node.js](https://nodejs.org) ≥ 20、Git
- 磁盘约 4 GB（QwenPaw 运行时与锁定应用自动下载）
- 可选：任意 OpenAI 兼容的大模型服务（LM Studio / Ollama / 云端 API），用于应用内 Agent 对话

### Windows

```powershell
git clone https://github.com/Gary0097/zhiyun-ai-platform.git  # 或直接使用一键安装包
cd zhiyun-ai-platform
.\setup-ai-os.ps1      # 首次安装：自举运行时并物化锁定的应用
.\start-ai-os.cmd      # 启动（唯一入口，服务端口 8088）
```

### Ubuntu / Linux

```bash
git clone https://github.com/Gary0097/zhiyun-ai-platform.git
cd zhiyun-ai-platform
./setup-ai-os.sh
./start-ai-os.sh
```

浏览器打开 **http://127.0.0.1:8088**。

> **默认管理员账号：`admin` / `ZhizaoYun@2026`**
> ⚠️ 首次登录后请立即在右下角用户卡 → 「账号管理」中修改密码；正式部署务必更换。

**默认管理员账号：`admin` / `ZhizaoYun@2026`**（⚠️ 首次登录后请立即在「账号管理」中修改密码；正式部署务必更换）。

离线部署：预置 `AI_OS_OFFLINE=1` 环境变量后执行安装脚本，使用提前下载的依赖缓存完成无公网安装，详见 [运维文档](docs/operations/QUICKSTART.md)。

### 配置模型（启用 Agent 对话）

1. 打开 `设置 → 模型`，选择任意 OpenAI 兼容 Provider（内置 LM Studio、Ollama、DashScope、OpenRouter 等预设）。
2. 填入服务地址与 API Key，发现模型后设为默认。
3. 之后任意应用内点「问 Agent」即为真实流式对话。未配置模型时，应用的分析功能与快捷指令不受影响。

## 5 分钟体验动线

1. 登录后从左侧「应用」打开 **智能销售中心**。
2. 在「销售BI分析」点 **下载导入模板**，填入你的订单数据（或用仓库 `docs/qa/demo-data/` 里的示例文件）。
3. 点 **导入 Excel/CSV** 上传 → 表格填充并显示来源标签。
4. 点 **生成销售BI** → 得到营收/销量/客单价 KPI、月度趋势与 Top 排名。
5. 输入审阅人姓名 → **接受** → **导出**。
6. 点右上角 **问 Agent**，直接用自然语言提问（如"分析本月销售趋势"），观察流式回答。

完整演示剧本与验收清单见 [客户演示与验收指南](docs/operations/DEMO-ACCEPTANCE-GUIDE-2026-08-26.md)。

## 架构

```text
用户 / Agent
    │
QwenPaw 2.1.0（唯一宿主，端口 8088）
    ├── Workspace 文件 / 知识库 / 会话
    ├── 系统插件（登录 · 数据核心 · 审计 · 应用中心 · 企业初始化器 · 品牌）
    └── 锁定的业务 PawApps（独立仓库 · 40 位提交锁定 · 可安装/升级/回滚）
```

- 所有业务应用使用统一 Workspace 数据核心，通过稳定数据契约共享数据
- 每个应用独立 GitHub 仓库交付，本仓库以 `pawapps.lock.json` 锁定正式合并提交
- 数据库、日志、知识文件全部落在 Workspace，升级与回滚不触碰用户数据
- 不要直接修改 `apps/qwenpaw-embedded/runtime/pawapps` 或 `~/.qwenpaw/plugins` 中的安装副本；变更请在对应应用仓库进行后更新锁文件

## 国内镜像（Gitee）

- **https://gitee.com/gary0097/zhiyun-ai-platform** —— 无需翻墙即可克隆/下载
- 一键安装包：[Gitee Release v1.0.0](https://gitee.com/gary0097/zhiyun-ai-platform/releases/v1.0.0)

## 相关仓库

| 仓库 | 说明 |
| --- | --- |
| [zhiyun-data-studio](https://github.com/Gary0097/zhiyun-data-studio) | 企业数据分析中心 |
| [zhiyun-order-studio](https://github.com/Gary0097/zhiyun-order-studio) | 智能订单处理中心 |
| [zhiyun-sales-studio](https://github.com/Gary0097/zhiyun-sales-studio) | 智能销售中心 |
| [zhiyun-finance-studio](https://github.com/Gary0097/zhiyun-finance-studio) | 智能财务中心 |
| [zhiyun-people-studio](https://github.com/Gary0097/zhiyun-people-studio) | 智能人力中心 |
| [zhiyun-supply-studio](https://github.com/Gary0097/zhiyun-supply-studio) | 智能供应中心 |
| [zhiyun-service-studio](https://github.com/Gary0097/zhiyun-service-studio) | 智能售后服务中心 |
| [zhiyun-integration-hub](https://github.com/Gary0097/zhiyun-integration-hub) | 系统集成中心 |

## 文档

- 产品需求：[AI-OS PRD V6.4](docs/product/AI-OS-PRD-V6.4-QwenPaw-PawApps.md)
- 架构：[QwenPaw-only 目标架构](docs/architecture/QWENPAW-ONLY-ARCHITECTURE.md)
- 部署运维：[快速部署](docs/operations/QUICKSTART.md) · [PawApp 升级策略](docs/operations/PAWAPP-UPGRADE-POLICY.md)
- 项目计划：[PROJECT-PLAN](docs/product/PROJECT-PLAN.md) · [双态运行体系](docs/product/AI-OS-SIMULATION-DUAL-STATE-VISION.md)
- 质量证据：`docs/qa/`（QA 报告、E2E 探测结果与截图）

## 开发与验收

```bash
node scripts/verify-release.mjs    # 发布门禁：架构/版本锁/启动器/全部 PawApp 测试
node scripts/verify-project-plan.mjs
```

发布门禁会验证纯 QwenPaw 架构、版本锁、启动器、内外部 PawApp 版本与治理类型、全部 Python 测试和 Windows/Linux 双平台入口。遗留架构的移除记录见 [迁移说明](docs/migration/LEGACY_REMOVAL.md)。

贡献流程：一个 issue 一个分支一个 PR；外部应用先在其独立仓库合并，再回本仓库更新锁提交。

## 当前状态

31 项产品能力：13 项已交付、17 项待用户实机验收、1 项（知识库）开发中。五大业务中心已完成真实 Agent 对话接入（0.3.0）；RBAC 服务端强制路由、Excel 持久化导入通道、双平台干净环境自动化验收仍在推进，详见 [PROJECT-PLAN](docs/product/PROJECT-PLAN.md)。

## 许可证

[Apache 2.0](LICENSE)
