---
name: office-computer
description: "电脑操作技能。需要在用户电脑上完成本地任务的场合使用：文件与文件夹的批量整理、重命名、归档、去重；跨目录查找与内容检索；批量格式转换（图片/音频/文档）；定时与开机自启配置；系统信息查询与常见故障排查；调用本机程序完成 Office 自动化等。网页内的操作优先用 office-browser 技能。触发词：整理文件、批量重命名、找文件、清理磁盘、开机启动、系统设置、控制面板、任务管理器、环境变量、快捷方式。"
metadata:
  version: "1.0.0"
  qwenpaw:
    emoji: "🖥️"
---

# 办公技能 · 电脑操作

## 1. 能力边界（先读）

本技能通过 shell 工具在本机执行命令完成操作：

- **首选命令行/脚本**：文件整理、批量重命名、格式转换、信息查询——命令与脚本
  可复述、可验证，永远优先于模拟点击。
- **桌面 GUI 自动化**：仅当智造云 AIOS 运行在 QwenPaw Desktop 且安装了
  Computer Use 插件时可用（对话中输入 `/computer_use` 启动）。浏览器控制台
  环境下没有 GUI 自动化能力，此类需求改用命令行等效方案，并明确告知用户。
- **敏感操作必须先确认**：删除、移动大量文件、改注册表/系统配置、结束进程、
  卸载软件——先列出将要执行的操作清单，用户确认后再动手。

## 2. 操作纪律

1. **先勘察后动手**：`dir/ls`、`Get-ChildItem` 看清目录结构与数量规模再批量操作。
2. **破坏性操作可恢复**：
   - 批量移动/重命名前列出"旧路径 → 新路径"清单；
   - 删除一律先进回收站等效方案：移动到 `回收暂存_<日期>/` 目录而不是直接删除，
     除非用户明确要求永久删除；
   - 注册表修改前先导出备份（`reg export`）。
3. **幂等可重跑**：批量操作写成脚本，重跑不产生重复结果（先判断目标是否存在）。
4. **跨平台**：Windows 用 PowerShell，Linux/macOS 用 bash；同一任务给出对应平台命令。
5. **汇报结果**：每步操作后报告实际影响的文件数与样例路径，失败项逐条列出。

## 3. 常见任务配方

### 文件批量整理

```powershell
# 勘察：按扩展名统计
Get-ChildItem -Path . -Recurse -File | Group-Object Extension | Sort-Object Count -Descending
# 归档：按类型移动到子目录（-WhatIf 先演练）
Get-ChildItem -File -Filter *.pdf | ForEach-Object { Move-Item $_.FullName -Destination "PDF归档\" }
```

### 批量重命名

```powershell
# 预览（-WhatIt）：确认清单无误后去掉 -WhatIf 正式执行
Get-ChildItem -File -Filter "IMG_*.jpg" | Rename-Item -NewName { "团建_$($_.BaseName).jpg" } -WhatIf
```

### 查找文件 / 内容检索

```powershell
Get-ChildItem -Path D:\ -Recurse -Filter "*合同*" -ErrorAction SilentlyContinue | Select-Object FullName, Length, LastWriteTime
Select-String -Path ".\*.log" -Pattern "ERROR" | Select-Object -First 20
```

### 定时与自启（Windows）

- 定时任务：`schtasks /Create /SC DAILY /TN "每日日报" /TR "..." /ST 09:00`
  （QwenPaw 自身的定时任务优先用内置 cron 技能）；
- 开机自启：把快捷方式放进 `shell:startup` 对应目录。

### 格式转换

- 图片批转：Python + Pillow（`pip install Pillow`）；
- 音视频：ffmpeg；文档：LibreOffice `--convert-to`。

## 4. Office 本地自动化

优先用 Python 直改文件（office-word/office-excel/office-ppt 技能的脚本路线）；
必须驱动 Office 程序本体时（如打印、另存特殊格式），Windows 可用 COM：
`New-Object -ComObject Word.Application`（要求本机装有 Office 且允许弹窗场景，
执行前告知用户会短暂启动 Office 程序）。

## 5. 系统排查

- 空间：`Get-PSDrive` / `df -h`；大文件排行：按 Length 排序取前 20；
- 进程与端口：`Get-Process`、`Get-NetTCPConnection -LocalPort <端口>`；
- 环境变量：`[Environment]::GetEnvironmentVariable('PATH','User')`——修改前打印原值。

## 6. 交付前检查单

- [ ] 破坏性操作均已确认并留有可恢复手段；
- [ ] 批量操作结果已抽样验证（打开/查看 2–3 个产物）；
- [ ] 失败项与跳过项如实报告，没有静默吞错；
- [ ] 涉及系统设置变更的，已说明如何还原。

## 相关技能

- `office-browser`：网页内操作（网页下载、在线系统填报）走浏览器自动化；
- `office-excel` / `office-word`：文件内容级处理；
- `office-computer` 不管网页——"帮我在网页上点一下"请转 `office-browser`。
