# Windows 办公完整安装包

跟踪 #161。运行时 2.2.1，办公技能包 1.6.0，Windows 10/11 x64。

完整离线 EXE/ZIP 携带 LibreOffice 26.8.1、原始许可及源码获取说明、应用本地 VC 运行库、Node、受管 Python、QwenPaw/Hub 缓存与锁定的39个办公依赖。
不附带模型权重、供应商密钥、用户工作区、账号、第三方专有插件或客户数据。模型沿用用户自己的服务配置。

## 使用

双击 `zhiyun-ai-os-v2.2.1-office-1.6.0-setup.exe`，选择可写目录；或将完整 ZIP 解压到可写目录后运行 `install-usb.cmd`。
首次安装一次完成包校验、离线依赖配置、真实库导入与 LibreOffice 启动检查。完成后通过原启动入口使用。
已有安装覆盖升级前由现有安装器停止本安装实例，并按原规则保护 Workspace、账号和未知用户文件。

正常启动只读取本地就绪标记，不启动 pip/uv、不扫描办公依赖、不调用 LibreOffice 检查版本，也不下载。
缺失或过期时显示修复提示，不在启动时反复重试。停止服务后可重新运行完整安装程序，或运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File setup-ai-os.ps1 -RepairOffice
```

离线包自动启用离线模式。主动修复会从包内缓存重装办公库；LibreOffice 文件损坏时需要重新解压/运行完整安装程序恢复原始载荷。
`soffice` 已通过进程 PATH 提供，`SOFFICE` 指向包内程序；不修改系统文件关联，不需要额外 LibreOffice 插件或系统 Node/Python。
转换任务应使用独立 `-env:UserInstallation=file:///...` 配置，避免并发转换或已有 LibreOffice 会话互相干扰。

## 构建

1. 联网构建机准备锁定 QwenPaw 2.2.1 单机与 Hub 运行时、办公依赖缓存；用户机器不执行此步骤。
2. 执行 `node scripts/prepare-office-windows.mjs`；可用 `--msi <本地官方MSI>` 避免重复下载。
   MSI SHA-256 必须等于 `office-windows.lock.json`。行政解包不注册 LibreOffice，保留所有许可并生成完整文件哈希清单。
3. 执行 `node scripts/make-release-package.mjs 2.2.1-office-1.6.0 --offline --ref <已提交分支> --no-prune`。
   必须存在内嵌 Node、Python、uv 与完整 LibreOffice 载荷；缺失直接失败。VC 运行库同时提供给 LibreOffice 和受管 Python，供 OCR/ONNX 加载。
4. 执行 `node scripts/make-exe-installer.mjs 2.2.1-office-1.6.0` 生成 EXE 与 SHA-256。

二进制、缓存与测试数据不提交 Git；源码、版本锁、测试及操作说明通过 PR 审查。当前任务不自动发布正式 Release 或修改在线更新签名策略。

## 验收

```powershell
node scripts/verify-release.mjs
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test-office-installer.ps1 -Archive <完整ZIP> -Target <新的中文含空格测试目录>
```

安装验收使用生产安装器相同的 ExtractTo/RunRuntimeSetup 核心路径，不创建真实快捷方式/卸载注册项。
测试进程移除系统 Node/Python/uv 搜索路径、清理 PYTHONPATH/PYTHONHOME，强制 UV_OFFLINE，并将网络代理指向不可用端口。
验证真实导入、包内 VC DLL 加载、损坏标记提示、离线修复、Word/PPT 转 PDF、Excel 重算、本地 OCR，以及两次完整启动不改写依赖标记。
图形向导、快捷方式及卸载/升级数据保护由现有 Windows 安装器回归覆盖；Linux 保持原入口，不打包 Windows LibreOffice，未做 Linux 实机验收。

## 回退

撤回本 PR 并重装先前通过验收的发行包；用户 Workspace/账号不迁移、不删除。旧版系统仍可忽略新增 extras/libreoffice 目录。
版本锁不变化时重复安装走标记快路径；主动修复仅影响本安装的托管办公依赖，不改系统 Python 或用户原始文档。
