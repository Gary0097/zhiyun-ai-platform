# AI-OS QwenPaw-only 目标架构

## 架构决策

QwenPaw 2.1.0 是唯一 Agent OS 内核、Web/桌面界面、插件宿主和进程入口。主项目不再包含第二套 Agent Runtime、企业网关、iframe 对话或 8390 服务。

```text
用户 / Agent
    │
    ▼
QwenPaw 2.1.0 :8088
    ├── Workspace Files / Knowledge Base
    ├── System Plugins
    │   ├── Logo
    │   ├── Audit
    │   ├── App Discovery
    │   └── Data Core (SQLite in Workspace)
    └── Locked PawApps
        ├── Data Studio
        ├── Order Studio
        ├── Integration Hub
        ├── Service Studio
        ├── Supply Studio
        ├── Sales Studio
        ├── Finance Studio
        └── People Studio
```

## 运行约束

1. 仅允许 `start-ai-os.cmd` / `start-ai-os.sh` 启动系统。
2. 业务应用必须登记在 `pawapps.lock.json` 并锁定40位提交。
3. 同步源码在临时目录检出，删除 `.git` 后再交给 QwenPaw 安装。
4. Windows Desktop版只要求 `qwenpaw` CLI可用；不强制存在可导入的Python包。
5. 数据库、日志、知识文件写入Workspace，不写入Git仓库。
6. Agent工具治理类型只能是 `file`、`internal`、`network`、`shell`。
7. 分析结果不能自动执行高风险业务动作，必须保留证据与人工确认。

## 版本与升级

主仓库是发布清单。PawApp先在独立仓库测试和合并，再将合并提交写入锁文件。升级失败时回退主仓库提交即可恢复上一组锁定版本，Workspace数据不随代码回退。
