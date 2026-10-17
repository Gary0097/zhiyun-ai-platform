# Windows 办公版验收与演示分支合并评估

日期：2026-10-17（上海时间）。跟踪：#157。

结论：文件处理与浏览器/检索数据路径已实际验证；不能据此宣称模型对话办公全流程已验收。
办公技能包修订为 1.5.1，系统与 QwenPaw 运行时仍为 2.2.1。

## 环境与证据范围

- Windows，Node 24.19.0，项目隔离 CPython 3.12.13，QwenPaw 2.2.1。
- 基线 `aios-office`：`7dbb6356ea542ad4a7579caa074f8803359472fa`。
- `master`：`e3115bf28446544b49175c214820074fec4dfb00`；办公分支已包含它，无需再次合并。
- 使用明确标注的合成数据；未使用客户文档、聊天记录或模型密钥。
- Office 转换使用临时目录解包的 LibreOffice 26.8.1，不安装到系统，不接管现有 WPS 会话。
  产品仍需自行配置 LibreOffice/Office/WPS 才能重算与转换；本次未把 LibreOffice 打进安装包。
- 结构检查、渲染检查和模型调度分开报告。生成的中文 Word 与两份 PPT 已转图目视核对。

## 十一项办公能力

| 技能 | 实际验证 | 结果与边界 |
| --- | --- | --- |
| Word | 中文/东亚字体、标题样式、表格、图片、页码域、新建/副本编辑/重读、PDF 导出 | 通过；修订跟踪、复杂目录、多节长文、旧 .doc 未验收 |
| PDF | 中英文嵌字、文本/表格提取、合并/拆分/旋转、水印、加解密、逐页渲染、扫描件分流、内容重建 Word | 通过；重建不等于精确版式还原，复杂表单/签名未验收 |
| Excel | 公式保存、格式、冻结、筛选、图表、打印标题、中文 CSV、保留编号前导零、副本编辑；LibreOffice 重算后合计 85、公式仍存在 | 通过；大型工作簿、宏、复杂透视表、动态数组兼容性未验收 |
| PPT | 16:9、中文、图片、原生图表、备注、边界检查、副本编辑、PDF 导出、渲染核对 | 通过；动画/视频/母版复杂编辑未验收 |
| OCR | 图片扫描 PDF → 200 DPI 整页渲染 → 本地 RapidOCR，识别中英文及 85.00 金额 | 通过清晰合成样本；低清/倾斜/手写/复杂表格准确率未验收；云端未测试 |
| 文件读取 | 中文编码探测、CSV/HTML 转换、Office/PDF 按格式读取 | 数据路径通过；补充 UTF-16/32 BOM、旧格式与宏文档处理说明 |
| 电脑操作 | 文件副本归档、完整性校验；Windows 外来服务占用端口时拒绝启动且不终止该服务 | 文件/启动路径通过；没有操控用户桌面，不代表 Desktop GUI 插件已验收 |
| 浏览器 | 调用原生 Browser SDK 的 guest 身份；独立本地网页打开、快照、输入框填值、按钮点击、结果快照 | 通过；真实业务站点登录/下载/验证码未验收 |
| 查资料 | 直接调用运行时 web_fetch 读取 python-docx 官方文档；web_search 返回文档链接 | 通过本次联网样本；供应商限流/网络状态会影响结果 |
| 搜图 | Pillow 图片校验；授权页访问与更换来源；Feather 原始 LICENSE 读取成功 | 部分通过；Unsplash 授权页 HTTP 401，未绕过；未验收完整选图→原图下载→商业授权链 |
| 制作内容 | Word/PPT/Excel/PDF 成品数据路径、11 项技能预置与回复规范注入 | 模型调度未验收：隔离环境无活动模型；内容质量不能以脚本测试替代 |

体检通过仅代表技能清单、启用状态、依赖、规范、桥接和补丁正常，不是上表所有边界都已验证。

## 修复

1. 依赖完成标记绑定 Python/venv 配置与包目录指纹；运行时丢失/重建、旧标记不能再直接跳过。
2. 依赖探测核对发行包版本与模块存在性；体检复用同一依赖清单，避免漏查新依赖。
3. uv 使用项目 `runtime/cache/uv`；离线 pip 回退禁止联网。全新 venv 用该缓存 `--offline` 安装 39 个包成功。
4. 增加 pypdfium2，修正 Pillow 直接渲染 PDF、提取图片代替整页渲染的错误说明。
5. Excel 指引明确要求重算后核对缓存与公式；无引擎时必须标为未验证。
6. 浏览器示例使用实际 SDK 的 Browser.connect/open/snapshot/语义定位，去除 Playwright 风格的不存在接口。
7. 图片校验不再用 20KB 阈值误判小图；新增受阻换源说明。文件读取先识别 Unicode BOM。
8. 依赖回归测试改用临时夹具，不再改写真实安装目录的标记。

## Windows 启动

优化：端口空闲时以本机 TCP 探测跳过昂贵的 PowerShell/NetTCPIP 查询；端口占用时仍执行原有归属判断。
doctor 复用已经核验的 CLI 版本结果，避免重复启动 CLI。未削弱认证、端口保护或更改内核。

优化后的连续三次入口 → HTTP 200：**6.413 / 11.429 / 6.414 秒**，中位数 **6.414 秒**。
该结果不含首次下载安装依赖；不等于智能体/模型全部就绪。机器后台负载会影响时间，不能承诺固定秒数。
原始首次初始化曾为 16.352 秒；其他修改前样本为 18.265 / 12.106 秒，缓存/后台负载不同，不能作为严格同比提速比例。

认证状态启用，匿名 `/api/auth/verify` 返回 401。上游默认允许 loopback 主机免鉴权访问部分 API，
因此没有把本机 `/api/agents` 返回 200 误判成认证被关闭；局域网/代理鉴权不在此次覆盖内。

Linux：保留 .sh 入口，环境指纹支持 lib/python*/site-packages；发布门禁检查通过。
当前 Windows 主机未实际运行 Linux，不能声称 Linux 实机验收通过。

## 演示版合并

目标 `zhizaoyun-demo-20261008`：`ada051fd223912e8940c729c9804e737fc487d42`。

- `git merge-tree --write-tree HEAD origin/zhizaoyun-demo-20261008` 成功，无文本冲突；未写入共享分支。
- 相对 master 增加约 4,934 个变更文件、1,619,521 行；包含工作区快照、聊天/任务数据、数据库及 secrets 路径。
  未读取或复用这些凭据，也未把快照合并进办公修复。
- 演示版新增 7 个业务插件，与当前办公发行版只允许 aios-brand 的门禁不兼容。
  Git 无冲突不能等同运行和发布兼容；整体合并会破坏现有产品边界。
- 对演示分支 `zhizaoyun/order-center/excelgen.py` 单独加载合成输入验证，三张表（订单信息、物料明细、解析说明）
  正确生成，物料合计与订单成本均为 85。源码没有复制进办公包。
- 后续建议：先清理演示版运行数据/密钥路径，业务服务按可选独立组件交付，补 Windows 部署、端口、认证、数据隔离测试，
  再建立集成 PR。此次未将业务服务、SSO 或多租户系统标记为可合并上线。

## 复现

在仓库根目录，使用项目 Python（Windows 为 apps/zhizaoyunAIOS/runtime/zhizaoyunAIOS/venv/Scripts/python.exe）：

```powershell
node scripts/verify-release.mjs
node apps/zhizaoyunAIOS/scripts/check-office-pack.mjs --json
node apps/zhizaoyunAIOS/scripts/test-ensure-office-deps.mjs
# OFFICE_TEST_PYTHON 指向项目解释器可额外核验“已安装但版本过低”回归
# SOFFICE 指向独立 soffice.exe 时测试转换/重算；未配置则按实际状态报告未测试
python scripts/test-office-capabilities.py --output <专用合成样本目录>
python scripts/test-office-connected.py <专用联网结果目录>
python scripts/benchmark-office-start.py --output <专用启动结果目录> --runs 3
python scripts/test-demo-office-compatibility.py --output <专用演示兼容结果目录>
# 外来进程保护测试必须用安装树外的系统 Python，确保模拟的服务确实不属于本平台
python scripts/test-office-startup-safety.py
```

能力测试 7 组通过；联网测试 4 组通过，Unsplash 1 组外部受阻（退出码 2），没有全部伪报为通过。
Browser 工具成功后，独立 Python 进程退出时偶见上游 asyncio subprocess 清理警告；保留为已知限制，未修改内核。
完整发布门禁、Windows 安装/恢复/路径回归、外来进程保护与办公体检通过。

## 回退

回退本 PR 提交即可恢复启动器/技能指引；下次启动重建依赖标记。新增 pypdfium2 可保留，不影响旧包。
未迁移用户数据库或工作区，未发布新系统 Release，未更改共享分支历史。测试数据与临时 LibreOffice 均在本机独立目录。
