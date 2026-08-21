# Data Studio 独立 PawApp 接入

Data Studio 保持独立 GitHub 仓库交付，AI-OS 主仓库只保存 `pawapps.lock.json`，不复制应用源码。

启动流程：

1. 校验 QwenPaw 2.1.0；
2. 校验 PawApp 锁文件；
3. 将应用同步到 `apps/qwenpaw-embedded/runtime/pawapps/`；
4. 校验锁定提交及 `plugin.json` 的应用 ID；
5. 依次安装 Data Core 和 Data Studio；
6. 启动 QwenPaw 单进程。

锁文件使用完整提交 SHA，确保 Windows、Linux 安装相同版本。锁定版本已存在时不访问网络，可离线启动；应用源码和运行数据均不提交到主仓库。
