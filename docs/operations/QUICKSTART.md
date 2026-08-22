# AI-OS Windows / Linux 快速部署

AI-OS 采用 QwenPaw 2.1.0 单进程运行，默认地址为 `http://127.0.0.1:8088`，不需要启动 8390 企业服务。主仓库负责启动和系统插件，独立 PawApp 会按 `apps/qwenpaw-embedded/pawapps.lock.json` 的固定提交自动同步。

当前发布树只包含QwenPaw方案。不要使用旧目录名或历史文档推断启动入口；即使本地文件夹仍叫 `deepseek-harness`，只要其Git远端是本仓库，也应从仓库根目录运行下列脚本。

## 首次准备

两种系统都需要 Node.js 18+、Git，以及已安装并初始化的 QwenPaw 2.1.0。请确认以下命令可运行：

```text
node --version
git --version
qwenpaw --version
```

Windows Desktop/打包版不要求系统 Python 能 `import qwenpaw`。只有使用 QwenPaw 源码/CLI Python 环境时，才需要设置 `PYTHON`；诊断会将 Desktop 模式显示为提醒而不是失败。

## 一键启动

Windows 在仓库根目录运行：

```bat
start-ai-os.cmd
```

Ubuntu / Linux 在仓库根目录运行：

```bash
chmod +x start-ai-os.sh diagnose-ai-os.sh
./start-ai-os.sh
```

首次启动会同步外部 PawApp 并安装插件，因此取决于 GitHub 网络速度；后续锁定版本已经落盘时不会重复下载。\n\n启动器采用“保留配置、净化插件”的兼容策略：继续使用现有 QwenPaw 模型配置、密钥和 Agent 工作区；只将已确认与当前 AI-OS 无关且不兼容的 `cospaw`、`ai_decision`、`team_chat`、`qwenpaw-creator` 移入 `disabled_plugins`。这是可恢复停用，不会删除插件或用户数据；其他未知用户插件不会被改动。Creator 在本项目中仅作为开发参考，不作为运行应用加载。

## 运行健康检查

启动完成后，启动器会自动检查8088页面和五个核心接口，并输出“AI-OS 运行健康报告”。全部通过后会明确显示“可开始测试”。也可以随时单独运行：

```bat
check-ai-os.cmd
```

或：

```bash
chmod +x check-ai-os.sh
./check-ai-os.sh
```

机器可读输出：

```bash
node apps/qwenpaw-embedded/scripts/health-report.mjs --json
```

健康检查只访问本机只读接口，不修改数据库、配置或插件。它不仅检查HTTP状态，还校验Logo数据、Data Core Schema、Studio运行版本与应用目录版本，以及31项PRD能力台账的完整性；HTTP 200但返回空壳JSON、旧版本或错误结构仍会判定失败。若失败，它会列出具体不可用模块和原因；QwenPaw自身或无关第三方插件的日志不会被误报为某个智造云业务模块健康。

## 一键诊断

启动失败时，先运行：

```bat
diagnose-ai-os.cmd
```

或：

```bash
./diagnose-ai-os.sh
```

诊断覆盖 Node.js、Git、QwenPaw CLI/可选 Python 环境、目录权限、PawApp 落盘情况和 8088 端口。`PawApp 尚未同步` 是首次启动提醒，不会阻止启动；红色失败项必须先处理。

如需机器可读结果，可运行：

```bash
node apps/qwenpaw-embedded/scripts/doctor.mjs --json
```

## 更新与回滚

日常只拉取主仓库并重新执行一键启动：

```bash
git pull --ff-only origin master
./start-ai-os.sh
```

外部应用版本由锁文件控制，不会因其仓库后续提交而自动漂移。若新版启动失败，可将主仓库回退到上一个已验收提交后重新启动；工作区数据库和日志不应提交到 Git。

## 修改 Logo

项目默认 Logo 已内置。Windows 可把 PNG/JPG/SVG/WebP 文件拖到 `set-ai-os-logo.cmd`，Linux 运行：

```bash
chmod +x set-ai-os-logo.sh
./set-ai-os-logo.sh /path/to/logo.png
```

恢复默认 Logo：Windows 运行 `node apps\qwenpaw-embedded\scripts\set-logo.mjs --reset`；Linux 运行 `./set-ai-os-logo.sh --reset`。脚本只依赖 Node.js，兼容无法 `import qwenpaw` 的 Desktop 版。

## 常见问题

- `qwenpaw` 找不到：QwenPaw 未安装或其可执行目录不在 PATH。
- Python 无法导入 `qwenpaw`：Desktop版可忽略该提醒；源码安装模式再把 `PYTHON` 指向安装了QwenPaw的解释器。
- PawApp 同步失败：检查 Git、GitHub 网络和目标目录；不要手工修改 `runtime/pawapps` 中的锁定代码。
- Windows出现 `.git/objects/pack` 拒绝访问：说明仍在运行旧版同步器；拉取最新master后重新启动，新版安装源不会携带`.git`。
- Agent看不到Studio工具：确认Data Studio至少为v0.7.2、Order Studio至少为v0.5.2，并检查启动日志无治理类型冲突。
- 8088 已监听：启动器会在安装插件前停止，避免重复实例和文件占用；先访问页面确认，再停止旧进程后重试。
- 页面能打开但模块不可用：运行 `check-ai-os.cmd` 或 `./check-ai-os.sh`，按失败模块定位，不要只依据整段启动日志猜测。
- 启动日志出现上述已停用插件：先确认是否拉取了最新 `master`，再重启；清理动作发生在 QwenPaw 启动前。\n- 需要恢复被停用插件：停止 AI-OS 后，从实际 QwenPaw 工作目录的 `disabled_plugins` 将对应备份移回 `plugins`；恢复后产生的兼容问题不属于 AI-OS 发布门禁。\n- 不要启动 8390：该服务已退出当前目标架构。
