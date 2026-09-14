# Hub 部署与管理

团队入口基于 QwenPaw Hub 2.2.1，每用户有独立工作区、配置、凭据和会话。仅向可信内部团队提供服务。

## 启动

在安装目录运行，Windows Local 运行环境需要管理员权限：

```cmd
start-hub.cmd
```

Linux 需要 Node.js 20+、curl 和 Bubblewrap。Ubuntu 可先安装系统依赖，再以普通用户启动项目：

```bash
sudo apt install bubblewrap
bash setup-hub.sh
bash start-hub.sh
```

脚本安装锁定的 qwenpaw[hub]==2.2.1。不要自行升级到未经发行版验证的运行时。

## 初始化与团队访问

首次仅监听 http://127.0.0.1:8000/，首个注册账号成为管理员，没有默认密码。远程服务器可通过 SSH 转发初始化：

```bash
ssh -L 8000:127.0.0.1:8000 user@your-server
```

注册后重启 Hub，检测到有效管理员后允许局域网访问。员工通过 http://服务器IP:8000/ 登录。管理员创建账号后，可在 hub.yaml 中将 registration.enabled 设为 false 并重启。

外部域名部署需正确配置 public_base_url、TLS 和访问控制；启动脚本不等于公网部署方案。

## 模型凭据边界

原生“凭据管理”按当前账号的个人租户加密保存凭据，只注入同一租户的运行环境。管理员录入的 Key 不会自动共享给员工；宿主机环境变量也不构成全员供给。

管理员集中供给、员工免配 Key 仍是待实现与验收要求。不能按“管理员填一次，员工直接使用”部署；每个环境的模型配置与真实调用需分别确认。

## 数据与排错

默认数据在安装目录 apps/zhizaoyunAIOS/workspace/hub，备份须包括数据库及 secrets。单机 8088 与 Hub 8000 的账号分别管理。

Windows 控制台可打开不代表 Local runtime 已启动，应检查权限与实际启动结果。Linux 需要 Bubblewrap 可用；不应关闭隔离来绕过命名空间错误。
