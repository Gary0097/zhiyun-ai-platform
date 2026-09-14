# 快速开始

使用智造云AIOS 启动器或本项目脚本安装，运行时按版本锁管理。不要在系统 Python 中执行未锁版本的 pip 安装来替代发行版安装。

| 方式 | 入口 | 前置条件 |
| --- | --- | --- |
| Windows 图形安装包 | setup.exe，完成后使用桌面快捷方式 | 对应版本的验收合格安装包 |
| Windows 源码联网安装 | install-oneclick.cmd | Node.js 20+、网络 |
| Linux 联网安装 | setup-ai-os.sh、start-ai-os.sh | Node.js 20+、curl、网络 |
| 团队 Hub | start-hub.cmd 或 start-hub.sh | 见 Hub 部署 |

## Windows

运行安装向导，完成后使用“智造云 AI-OS”快捷方式，或在安装目录运行：

```cmd
start-ai-os.cmd
```

源码联网安装使用：

```cmd
install-oneclick.cmd
```

后台加载可能需要数分钟。托盘显示运行状态；失败时查看安装目录 launcher-service.log，不要连续启动多个实例。

## Linux

在完整项目目录执行：

```bash
node --version
bash setup-ai-os.sh
bash start-ai-os.sh
```

Node.js 需要 20 或以上。脚本管理项目 Python 环境，无需修改系统 Python。Windows 离线包中的 Node、Python 和缓存不能作为 Linux 离线环境使用。

## 登录和模型

打开 http://127.0.0.1:8088/，首次自行注册账号，没有预置 admin 密码。升级保留已有账号，不会重新生成默认密码。

登录后配置模型供应商或本地模型，完成真实对话后再配置频道和技能。未配置模型时不能把空白或错误结果当成接入成功。

## 数据与升级

默认工作区在安装目录 apps/zhizaoyunAIOS/workspace，凭据在其 secret 目录。升级前备份整个工作区，详见[配置与工作目录](./config)。Hub 使用独立账号体系，详见[Hub 部署](./hub)。候选版的验证范围以对应发布说明为准。
