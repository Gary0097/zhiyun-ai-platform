# 国内拉取与测试指引（智造云 AIOS 2.2.0）

> 面向在国内网络环境拉取本仓库并部署测试的同事。
> 本仓库只含启动器、品牌资产、脚本与文档（无捆绑业务应用），
> 克隆体量很小；真正的下载大头是首次启动时的运行时依赖（Python 解释器与
> qwenpaw wheel），因此加速方案分「拉仓库」与「装依赖」两层。
>
> 安全约定：系统**不存在预置默认账号密码**，任何口令不得写入本仓库、
> 文档或工单；测试临时口令一律走内部渠道传达。

## 一、拉取方案（按推荐顺序）

### 方案 1：离线包（最稳，适合内网 / 一次分发）

在一台能联网的机器上执行一次：

```cmd
git clone https://github.com/Gary0097/zhiyun-ai-platform.git
cd zhiyun-ai-platform
node scripts\make-release-package.mjs --offline
```

注意：打包机需先成功运行过一次 `start-hub.cmd`（qwenpaw[hub] 依赖进入
本地缓存后才能打离线包，打包脚本会自动校验）。产物在 `dist/` 下为自解压
安装包，U 盘拷贝给同事，解压后运行 `install-oneclick.cmd` 即可，
**全程无需联网**。

### 方案 2：镜像加速克隆（日常开发推荐）

任选一个 GitHub 加速前缀（某个前缀失效时换另一个即可）：

```bash
git clone --depth 1 https://ghfast.top/https://github.com/Gary0097/zhiyun-ai-platform.git
# 备选前缀：https://gh-proxy.com/ 、https://ghproxy.net/
```

`--depth 1` 浅克隆足够运行与测试；需要提交代码时再补全历史
（`git fetch --unshallow`）。

### 方案 3：Gitee 同步镜像（团队长期使用，一次性配置）

1. 在 gitee.com 选择「从 URL 导入仓库」，填入 GitHub 仓库地址；
2. 之后同事直接克隆 Gitee 地址；
3. 需要双向同步时，在 GitHub 仓库追加第二个 remote 定期 push。

## 二、依赖下载国内加速（关键步骤）

首次启动会联网安装 Python 解释器与 qwenpaw 包，建议把下列环境变量
写入系统环境变量（一劳永逸）：

| 下载项 | 环境变量 | 推荐值 |
| --- | --- | --- |
| qwenpaw Python 包（PyPI） | `UV_INDEX_URL` | `https://pypi.tuna.tsinghua.edu.cn/simple`（清华）或 `https://mirrors.aliyun.com/pypi/simple/`（阿里） |
| uv 托管 Python 解释器 | `UV_PYTHON_INSTALL_MIRROR` | `https://npmmirror.com/mirrors/python-build-standalone/` |

此外，同事机器需要安装 **Node.js**（启动器依赖），国内从 npmmirror 下载：
`https://npmmirror.com/mirrors/node/`。

配置完成后正常启动：

```cmd
start-ai-os.cmd      :: 单机版，控制台 http://127.0.0.1:8088
start-hub.cmd        :: 多用户版，控制台 http://127.0.0.1:8000（局域网同事访问 http://<本机局域网IP>:8000）
```

## 三、测试账号（重要：无默认口令）

系统采用「首个注册即管理员」机制：

- **单机版（8088）**：打开登录页点「创建账号」，注册的第一个账号即本机
  管理员，之后所有访问均需登录。
- **多用户 Hub 版（8000）**：管理员先在本机注册首个账号（自动成为
  管理员）；其他同事直接访问 `http://<服务器局域网IP>:8000` 自行注册
  （Hub 启动器会自动检测本机局域网 IPv4），或由管理员在 Hub 管理界面
  统一创建账号分配。
- 原生 Hub「凭据管理」按登录账号的个人租户加密存储并注入该租户运行环境。
  管理员录入的凭据不会自动共享给员工；统一供给与员工零接触密钥流程尚未完成验收（#138）。

测试结束后的重置方式（回到全新账号状态）：

| 形态 | 操作 | 影响范围 |
| --- | --- | --- |
| 单机版 | 删除 `apps\zhizaoyunAIOS\workspace\secret\` 下的 `auth.json` | 仅清除本地登录账号 |
| Hub 版 | 删除 `apps\zhizaoyunAIOS\workspace\hub\` 数据目录 | 清除全部 Hub 账号与凭据库，**删除前确认无需保留测试数据** |

## 四、常见问题

- **启动时下载缓慢/超时**：确认第二节两个 `UV_*` 环境变量已生效
  （`echo %UV_INDEX_URL%`）；离线包场景不受影响。
- **Hub 局域网无法访问**：检查 Windows 防火墙放行 8000 端口；Linux
  需安装 Bubblewrap（`apt install bubblewrap`）供 Local 运行环境隔离。
- **忘记管理员密码**：按上表重置后重新注册首个账号即可。
