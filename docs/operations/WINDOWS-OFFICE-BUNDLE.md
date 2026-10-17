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

## 2026-10-17 Windows 实包验收记录

- 交付版本：2.2.1-office-1.6.0；安装包产品源码提交 `2161a13c41fe95dbccf6abc8bfeb6ad122cca6bd`。后续提交仅包含验收脚本代理修正、报告和版本清单。
- EXE：944.30 MiB，SHA-256 `43f8d668b2f5f4524354dace52c577d91f5fbc7cacbcc244ffe69533a6b87ce3`。
- ZIP：944.24 MiB，SHA-256 `175741ccf11a577105b2badfe2036d39145f9bc3086d7301f71c44844d40cefd`。EXE 末尾载荷与该 ZIP 哈希一致；ZIP 完整 CRC 校验通过，无重复 MSI。
- 最终验收使用全新中文含空格目录、系统最小 PATH、断网代理与 UV_OFFLINE，成功解压 77,439 文件并完成运行时和办公安装。只豁免本机回环地址，以便检测本地页面；原验收脚本遗漏 NO_PROXY 导致计时误报，修正后完整重跑通过。
- 七组实际文件测试通过：Word、Excel、PPT、PDF、本地中文 OCR、文件/数据/图像处理、LibreOffice 转换与重算。包括 Word/PPT 导出 PDF、Excel 公式及缓存值验证。
- ONNX 实际加载安装目录 Python 自带 MSVCP，两个 Python 缓存名称均包含 VC DLL，不依赖宿主预装运行库。
- 重复 setup 使用标记快速返回；缺失标记时启动只提示、安装阶段离线恢复；删除受管 docx 文件后主动离线修复恢复成功。
- 首次完整启动到 HTTP 200 为 29.687 秒，第二次 18.763 秒（当前 Windows 主机实测，包含运行时诊断和服务启动）；两次启动没有改写办公依赖标记。匿名 token 验证均返回 401。
- 完整 `verify-release.mjs` 门禁通过，包含现有 Windows 安装器回归；当前分支包含最新 master。此次没有进行独立干净虚拟机或图形向导人工验收。
- 模型账号/权重不入包；云 OCR、联网研究、桌面 GUI 和模型对话不计入本轮离线文件能力通过项。此前模型对话验收见 PR #160。
