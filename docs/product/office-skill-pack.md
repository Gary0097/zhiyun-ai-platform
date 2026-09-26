# AIOS 办公专属默认技能包（aios-office 分支）

> 版本：1.0.0 ｜ 分支：`aios-office` ｜ 参考 ZCode 办公模式设计

## 1. 这是什么

`aios-office` 分支在智造云 AIOS 2.2.1 标准形态之上，预置了一套**办公专属默认技能包**：
用户完成一键安装并启动后，8 项办公能力已进入技能池与全部智能体工作区，并**默认启用**，
无需在控制台手动导入或开启。

| 技能 | 能力 | 说明 |
| --- | --- | --- |
| `office-ppt` | PPT | 幻灯片制作/编辑/美化/导出与视觉校对（python-pptx 工作流） |
| `office-excel` | EXCEL | 表格读写/清洗/公式/图表/格式互转（openpyxl 工作流） |
| `office-word` | WORD | 文档生成/编辑/样式体系/公文模板/导出 PDF（python-docx 工作流） |
| `office-computer` | 电脑操作 | 文件批量整理、重命名、格式转换、系统配置与排查（shell/PowerShell） |
| `office-browser` | 浏览器操控 | 网页浏览、自动填表、抓取、截图验证（内置 browser 工具，感知→操作→验证） |
| `office-image-search` | 搜图 | 图源检索、授权确认、下载校验、素材清单交付 |
| `office-research` | 查资料 | 多来源检索、交叉验证、来源标注、调研资料卡 |
| `office-content` | 制作内容 | 方案/文案/汇报材料的全流程编排，调度上述技能取数、找图、成稿 |

技能之间互为引用（如 `office-content` 编排 `office-research` 取数、`office-image-search`
配图、`office-word`/`office-ppt` 成稿），与 QwenPaw 内置技能（pptx/docx/xlsx/pdf/browser 等）
**名称不冲突**：内置技能按原样可用，办公技能包在其之上提供办公场景的工作流与规范。

## 2. 预置机制

技能包源文件位于仓库 `skills/office/`（随分支分发，打包发布时自动进入安装包）。
启动链路在服务拉起前调用 `apps/zhizaoyunAIOS/scripts/provision-office-skills.mjs`：

- **单机模式**：`start-ai-os.cmd/.sh` → `ensure-workspace.mjs` 末尾动态调用预置脚本；
- **Hub 多用户模式**：`start-hub.ps1/.sh` 在 hub-config 之后调用预置脚本（同一工作区）。

预置动作（幂等，每次启动执行）：

1. 读取 `skills/office/office-pack.json` 清单，校验 8 个技能目录与 `SKILL.md`
   frontmatter（name 与目录一致、description 非空）；
2. 把技能目录复制到 `$QWENPAW_WORKING_DIR/skill_pool/`（技能池，全部工作区可复用），
   并以 `skill-pool-manifest.v1` 格式登记池清单条目；
3. 把技能目录复制到 `$QWENPAW_WORKING_DIR/workspaces/<agent_id>/skills/`（每个现有
   智能体工作区），并以 `workspace-skill-manifest.v1` 格式在工作区 `skill.json` 写入
   `enabled: true, channels: ["all"]` 条目——QwenPaw 2.2.1 的清单调和逻辑会保留该状态；
4. 同步状态（内容哈希）记录在 `<工作区>/.office-pack.json`：内容未变化不重写任何文件。

数据安全边界：

- **用户自建同名技能不覆盖**：目标目录存在但没有本包同步记录 → 跳过并告警；
- **用户修改过的预置技能保留现场**：同步后被用户改过（哈希与记录不一致）→ 跳过更新；
- **用户的启用/禁用选择被尊重**：用户在控制台禁用某项办公技能后，预置不会重新启用；
- 预置失败只告警、不阻断服务启动（重跑 `start-ai-os` 可重试）。

技能包升级：修改 `skills/office/` 内容并提升 `office-pack.json` 的 `version`，
下次启动自动把未被动过的副本更新到新版本。

## 3. 一键完整下载使用

办公版完整内容都在 `aios-office` 分支上，两种一键方式任选：

```cmd
:: 方式 A：Git 一键拉取（Windows；Linux/macOS 用 install-oneclick.sh）
git clone -b aios-office https://github.com/Gary0097/zhiyun-ai-platform.git
cd zhiyun-ai-platform
install-oneclick.cmd
```

方式 B：免 Git 下载分支压缩包
`https://github.com/Gary0097/zhiyun-ai-platform/archive/refs/heads/aios-office.zip`，
解压后运行 `install-oneclick.cmd`（Linux 运行 `install-oneclick.sh`）。

一键安装完成并启动后：打开 http://127.0.0.1:8088 → 注册首个账号 → 配置模型供应商 →
对话即可直接使用（控制台「工作区 → 技能」可见 8 项 office-* 技能，默认启用）。
团队多用户：管理员运行 `start-hub.cmd`，员工工作区同样自动预置。

仅重新预置技能包（改包后不重启服务时手动执行）：

```bash
node apps/zhizaoyunAIOS/scripts/provision-office-skills.mjs
node apps/zhizaoyunAIOS/scripts/provision-office-skills.mjs --check   # 只校验，不写文件
```

## 4. 验证与测试

发布门禁 `node scripts/verify-release.mjs` 在 aios-office 分支上额外覆盖：

- `skills/office/office-pack.json` 存在且声明 8 项技能，各技能 `SKILL.md` 齐全；
- `provision-office-skills.mjs --check`（frontmatter 合法性）；
- `test-provision-office-skills.mjs`：首装（池+工作区+默认启用）、幂等重跑、
  用户自建同名技能保护（conflict）、用户修改保护（user-modified）、
  版本升级更新、新智能体工作区覆盖、用户禁用不被覆盖、
  ensure-workspace 启动挂接（含技能包缺失时静默跳过）、CLI `--check`；
- `ensure-workspace.mjs`、`start-hub.ps1`、`start-hub.sh` 均挂接预置脚本（防回归）。

## 5. 平台影响与回滚

- **Windows / Linux**：预置为纯 Node 文件操作，两平台同一实现；`.cmd`/`.sh`、
  `.ps1`/`.sh` 入口全部保留并已挂接。中文与空格安装路径已按仓库惯例处理
  （逐文件复制，不用 `fs.cpSync`；拒绝符号链接）。
- **回滚方法**：切回 `master` 分支即恢复标准形态；已安装环境中移除办公技能，
  在控制台删除对应 office-* 技能或删除 `<工作区>/skill_pool/office-*` 与
  各 `workspaces/*/skills/office-*` 目录及清单条目即可，其余数据不受影响。

## 6. 设计说明

- 参考 ZCode 办公模式（pptx/xlsx/docx/浏览器/电脑操作/搜图等技能的"工作流+校验+
  交付清单"范式），适配 QwenPaw 2.2.1 技能系统（技能池 → 工作区副本 → skill.json
  清单调和）；
- 技能均为指导型 SKILL.md（不声明 `metadata.requires`，避免因缺少二进制/环境变量被
  运行时跳过），依赖检查内置于各技能工作流（如 `pip install python-pptx`）；
- 与内置技能的关系：内置 `pptx/docx/xlsx/browser` 等仍按 QwenPaw 原样提供，
  办公技能包提供办公场景的编排与规范，二者共存不冲突。
