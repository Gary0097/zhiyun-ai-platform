# AI-OS Windows / Linux 快速部署

AI-OS 采用 QwenPaw 2.1.0 单进程运行，默认地址为 `http://127.0.0.1:8088`，不需要启动 8390 企业服务。主仓库负责启动和系统插件，独立 PawApp 会按 `apps/qwenpaw-embedded/pawapps.lock.json` 的固定提交自动同步。

当前发布树只包含QwenPaw方案。不要使用旧目录名或历史文档推断启动入口；即使本地文件夹仍叫 `deepseek-harness`，只要其Git远端是本仓库，也应从仓库根目录运行下列脚本。

## 首次准备

两种系统都需要 Node.js 18+、Git、Python，以及已安装并初始化的 QwenPaw 2.1.0。请确认以下命令可运行：

```text
node --version
git --version
qwenpaw --version
python -c "import qwenpaw"
```

Linux 若命令名为 `python3`，启动器会自动使用它。若 QwenPaw 安装在其他 Python 环境，可显式设置 `PYTHON`。

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

首次启动会同步外部 PawApp 并安装插件，因此取决于 GitHub 网络速度；后续锁定版本已经落盘时不会重复下载。

## 一键诊断

启动失败时，先运行：

```bat
diagnose-ai-os.cmd
```

或：

```bash
./diagnose-ai-os.sh
```

诊断覆盖 Node.js、Git、QwenPaw CLI、Python 环境、目录权限、PawApp 落盘情况和 8088 端口。`PawApp 尚未同步` 是首次启动提醒，不会阻止启动；红色失败项必须先处理。

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

## 常见问题

- `qwenpaw` 找不到：QwenPaw 未安装或其可执行目录不在 PATH。
- Python 无法导入 `qwenpaw`：CLI 与 `PYTHON` 指向了不同环境；把 `PYTHON` 设置为安装 QwenPaw 的解释器。
- PawApp 同步失败：检查 Git、GitHub 网络和目标目录；不要手工修改 `runtime/pawapps` 中的锁定代码。
- Windows出现 `.git/objects/pack` 拒绝访问：说明仍在运行旧版同步器；拉取最新master后重新启动，新版安装源不会携带`.git`。
- Agent看不到Studio工具：确认Data Studio至少为v0.7.1、Order Studio至少为v0.5.1，并检查启动日志无治理类型冲突。
- 8088 已监听：可能 AI-OS 已经启动；先访问页面确认，再决定是否停止旧进程。
- 不要启动 8390：该服务已退出当前目标架构。
