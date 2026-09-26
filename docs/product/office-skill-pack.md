# AIOS 办公专属默认技能包（aios-office 分支）

> 版本：1.3.0 ｜ 分支：`aios-office` ｜ 参考 ZCode 办公模式设计，桥接 ZCode 官方办公技能

## 0. 版本演进：完全体 Harness（对标 WorkBuddy/Kimi，token 更省、效果更强）

### v1.3.0：办公回复规范（输出纪律 = 最大头的 token 节省）

- **检索开箱即用**（源码核实+实测）：`web_search` 默认走 Tavily **keyless**
  （免 Key，实测可达），`web_fetch` 纯 HTTP 直抓——查资料/搜图链路零配置可用；
  需更稳可配 anysearch（匿名免费额度 + 自动注册，控制台工具设置）。
- **OFFICE.md 办公回复规范**：在 default 工作区预置 375 字符的精炼规范
  （安全三行 + 回复精炼 + 文件交付 + 事实纪律 + 能力路由），并把
  `system_prompt_files` 固定为 OFFICE.md+SOUL.md+PROFILE.md——实测 default
  工作区原本没有任何工作区注入，现在以约 250 token/轮的固定成本换
  「先结论、不复述、单条 ≤300 字、细节写文件」的**输出纪律**（输出 token
  通常数倍于输入，这是最大头的节省）；若日后经模板新建 agent，注入上限
  约 2400 字符 < 泛用默认 4300。用户自定义注入列表或修改 OFFICE.md 一律
  保留现场。真实运行时渲染验证：仅 `# OFFICE.md` 注入、375 字符。

### v1.2.0：完全体基座

- **token 优化**：QwenPaw 技能注入机制为渐进式披露——每轮固定注入的只有
  `name + description + dir`（preload=false 时正文不进上下文，按需经 Skill 工具
  读取）。v1.2.0 把 11 项技能 description 全部压到 ≤71 字符（总计 2047→673
  字符，固定开销降约 70%；发布门禁强制 ≤110 字符预算），正文保留完整工作流
  ——比"全量注入文档"的常见做法（数千至数万 token/轮）低一个量级。
- **ZCode 默认办公技能桥接（完全体）**：`link-zcode-skills.mjs` 在启动期检测
  本机 ZCode 安装（`~/.zcode/cli/plugins/cache/zcode-plugins-official`），把
  presentations/spreadsheets/documents/pdf/browser-use/computer-use 插件的最新
  版本技能目录注册为 QwenPaw 外部技能根（`config.json → skill_paths`，共 7 项
  ZCode 技能：pptx/xlsx/docx/pdf/control-browser/web-gui-tester/computer-use）。
  原地只读引用、不复制（ZCode 技能为专有授权内容，不得再分发）；未装 ZCode
  的机器静默跳过；外部根排在主池之后，同名时主池优先，office-* 与内置技能
  不受影响。agent 由 office-* 轻量路由，需要深度能力时直接用 ZCode 全流程
  技能（含其脚本资产）。
- **文件卡片下载 404 修复**：上游 `filePreviewUrl` 把本地路径原样拼进 URL，
  文件名含 `#`/字面 `%xx` 时被截断或双重解码 → 404。品牌补丁注入定向编码
  （`%`→`%2525` 抵消服务端两次解码，`#`→`%23`、`?`→`%3F` 避免分隔符截断），
  已实测中文/空格/`#`/`%20`/`50%BE` 文件名全部 200（`?` 为 Windows 非法文件名
  字符，不存在该场景）。防回归：补丁目标为必需项 + 门禁检查。
- **启动提速（实测 40-45s → 21s 到 HTTP 200）**：
  - `patch-console-ui.mjs` 全量补丁（重写+重压缩+文档生成）实测约 17s——
    新增内容签名快跳（`<venv>/qwenpaw/.aios-console-patch.sig`），签名一致
    时整体跳过（<0.5s）；
  - 品牌插件安装子进程实测约 11s——`start.mjs` 版本门控（workspace 标记
    `.brand-plugin.version`，版本未变跳过；文件同步本就由 ensure-workspace
    版本门控完成）；
  - 办公依赖预装标记快路径 <50ms；首次启动仍需一次性全量补丁/安装/依赖
    下载（QwenPaw 首启另有约 44s 一次性迁移，属上游行为）。

## 1. 这是什么

`aios-office` 分支在智造云 AIOS 2.2.1 标准形态之上，预置了一套**办公专属默认技能包**：
用户完成一键安装并启动后，11 项办公能力已进入技能池与全部智能体工作区，并**默认启用**，
无需在控制台手动导入或开启。常用 Python 依赖（文档读写/PDF/OCR）也由启动器**预装**到
项目运行环境，技能执行不再临时 `pip install` 浪费时间。

| 技能 | 能力 | 说明 |
| --- | --- | --- |
| `office-ppt` | PPT | 幻灯片制作/编辑/美化/导出与视觉校对（python-pptx 工作流） |
| `office-excel` | EXCEL | 表格读写/清洗/公式/图表/格式互转（openpyxl/pandas 工作流） |
| `office-word` | WORD | 文档生成/编辑/样式体系/公文模板/导出 PDF（python-docx 工作流） |
| `office-pdf` | PDF | PDF 识别（文本/表格/图片提取）、合并拆分/加密/水印、生成与转换 |
| `office-ocr` | OCR | 扫描件/图片文字识别；复杂版面走 MinerU 云端（免费额度）/MCP，本地 RapidOCR 兜底 |
| `office-file-reader` | 文件读取 | 任意文件读取分流入口（编码检测、大文件分段、类型路由） |
| `office-computer` | 电脑操作 | 文件批量整理、重命名、格式转换、系统配置与排查（shell/PowerShell） |
| `office-browser` | 浏览器操控 | 网页浏览、自动填表、抓取、截图验证（内置 browser 工具，感知→操作→验证） |
| `office-image-search` | 搜图 | 图源检索、授权确认、下载校验、素材清单交付 |
| `office-research` | 查资料 | 多来源检索、交叉验证、来源标注、调研资料卡 |
| `office-content` | 制作内容 | 方案/文案/汇报材料的全流程编排，调度上述技能取数、找图、成稿 |

技能之间互为引用（如 `office-content` 编排 `office-research` 取数、`office-image-search`
配图、`office-word`/`office-ppt` 成稿；`office-file-reader` 把文件分流到
`office-pdf`/`office-ocr` 与各文档技能），与 QwenPaw 内置技能（pptx/docx/xlsx/pdf/browser 等）
**名称不冲突**：内置技能按原样可用，办公技能包在其之上提供办公场景的工作流与规范。

### 依赖预装（解决执行期临时装包慢）

`skills/office/requirements-office.txt` 声明常用办公依赖（python-docx、openpyxl、
python-pptx、pdfplumber、pypdf、fpdf2、Pillow、chardet、markdownify、pandas、
rapidocr-onnxruntime），由 `apps/zhizaoyunAIOS/scripts/ensure-office-deps.mjs` 在
**启动期幂等安装**到项目 venv：

- 标记文件 `<runtime>/office-deps.ok` 记录清单内容哈希，未变化时启动开销 <50ms；
- 清单变化或有包缺失时自动用 uv 补装（一次性，约 1–3 分钟），复验通过才落标记；
- 运行环境尚未安装时优雅跳过（首次 setup 后的下次启动自动补装）；
- 安装失败只告警、不阻断启动（技能文档内保留按需安装兜底）；
- 离线安装包（OFFLINE-PACKAGE）优先走 uv `--offline` 本地缓存。

### OCR 路线（office-ocr 技能内置，按优先级自动选择）

1. **文档解析 MCP 工具**：控制台配置了 MinerU MCP 等文档解析服务时直接调用（零安装）；
2. **MinerU 云端 API**（复杂版面首选）：`pip install "mineru>=4"` 仅装轻量 CLI，
   `MINERU_API_KEY`（mineru.net 注册申请，注册送免费额度），`mineru parse 文件 --remote`
   （文件上传云端，需用户同意；`mineru usage --json` 查额度）；
3. **本地 RapidOCR**（默认兜底）：已预装 `rapidocr_onnxruntime`，离线可用，零等待；
4. 本地 MinerU 完整版（`mineru[core]`，含模型重依赖）：仅在用户明确要求时安装。

## 2. 预置机制

技能包源文件位于仓库 `skills/office/`（随分支分发，打包发布时自动进入安装包）。
启动链路在服务拉起前完成两件事：

1. **技能预置**：`apps/zhizaoyunAIOS/scripts/provision-office-skills.mjs`
   - **单机模式**：`start-ai-os.cmd/.sh` → `ensure-workspace.mjs` 末尾动态调用预置脚本；
   - **Hub 多用户模式**：`start-hub.ps1/.sh` 在 hub-config 之后调用预置脚本（同一工作区）。
2. **依赖预装**：`ensure-office-deps.mjs`（由 `ensure-workspace.mjs` 一并调用）把
   `requirements-office.txt` 幂等安装到项目 venv（见上文"依赖预装"）。
3. **ZCode 技能桥接**：`link-zcode-skills.mjs`（同一挂接点）检测并注册本机
   ZCode 办公插件技能为外部技能根（见 §0）。

预置动作（幂等，每次启动执行）：

1. 读取 `skills/office/office-pack.json` 清单，校验 11 个技能目录与 `SKILL.md`
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

> **免 Git 推荐**：[Releases `aios-office-v1.4.0`](https://github.com/Gary0097/zhiyun-ai-platform/releases/tag/aios-office-v1.4.0)
> ——发布 zip 含完整办公版（技能包+预装依赖清单+文档），下载解压后运行 `install-oneclick` 即用。

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
对话即可直接使用（控制台「工作区 → 技能」可见 11 项 office-* 技能，默认启用）。
团队多用户：管理员运行 `start-hub.cmd`，员工工作区同样自动预置。

仅重新预置技能包（改包后不重启服务时手动执行）：

```bash
node apps/zhizaoyunAIOS/scripts/provision-office-skills.mjs
node apps/zhizaoyunAIOS/scripts/provision-office-skills.mjs --check   # 只校验，不写文件
```

## 4. 验证与测试

发布门禁 `node scripts/verify-release.mjs` 在 aios-office 分支上额外覆盖：

- `skills/office/office-pack.json` 存在且声明 11 项技能，各技能 `SKILL.md` 齐全；
- **token 预算**：每项技能 description 长度 ≤110 字符（每轮固定注入成本）；
- `provision-office-skills.mjs --check` 与 `test-provision-office-skills.mjs`；
- `ensure-office-deps.mjs --check` 与 `test-ensure-office-deps.mjs`；
- `link-zcode-skills.mjs --check` 与 `test-link-zcode-skills.mjs`；
- 品牌补丁必须包含文件预览 URL 编码修复（`%2525`）与内容签名快跳；
  `test-patch-console-ui.mjs`（95 项断言）含修复注入/回退门禁/快跳断言；
- `start.mjs` 必须版本门控品牌插件安装；`ensure-workspace.mjs` 必须挂接
  技能预置/依赖预装/ZCode 桥接三者。

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
