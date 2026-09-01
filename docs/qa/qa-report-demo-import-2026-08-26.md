# QA 报告：五大 Studio 直导数据演示链路（2026-08-26）

> 范围：sales / finance / people / supply / service 五大模板 Studio 的「导入 Excel/CSV → 表格填充 → 运行 → 结果审阅」端到端闭环，以及演示环境可启动性。
> 环境：`http://127.0.0.1:8088`，QwenPaw 2.1.0，Windows（H:\zhiyunAIOS 工作区），Studio 0.2.2（rowfix 热同步）。
> 证据：`docs/qa/demo-import-probe.json`、`docs/qa/screenshots/demo-import/*.png`。

## 一、结论

| 项 | 结果 |
| --- | --- |
| API 层 `/parse` 样例解析（14 个 CSV） | **14/14 通过** |
| 浏览器 E2E 导入闭环（13 个表格模块） | **13/13 通过** |
| 真实 UI 登录（物理点击） | 通过（修复后） |
| Console 单次执行（PluginLoader 轮数） | 1 轮（修复前 2 轮） |

## 二、本轮发现并修复的缺陷

| # | 等级 | 现象 | 根因 | 修复 |
| --- | --- | --- | --- | --- |
| 1 | **P0** | 真实用户无法登录（点击登录无响应） | 宿主把 `zhiyun-auth/ui/index.js` 动态加载两次，挂载函数无幂等保护，产生两个重叠登录层，上层按钮无事件 | `plugins/zhiyun-auth/ui/index.js` mount 加幂等保护（`#zhiyun-auth-root` 已存在则跳过） |
| 2 | **P1** | 整个 console 双重执行：PluginLoader 跑两轮、登录层×2、新手引导×2、应用容器错位（直连 URL 显示"该应用尚未加载"） | console 懒加载块（ACPDrawer）以**不带 `?v=`** 的原路径动态 import 入口 chunk，而我们 patch-console-ui 给 index.html 入口加了 `?v=`，两个 URL 模块身份不同 → 模块执行两次 | `patch-console-ui.mjs` 改为**移除** `?v=`（资源服务带 ETag，缓存代价可接受）；check 模式同步改为校验无 `?v=` |
| 3 | **P1** | 导入提示"已导入 0 行"，表格仍空 | `zhiyun-data-core /parse` 返回的行是按表头文本为键的对象数组，Studio UI 按矩阵下标取值 → 全部为空 | 5 个 Studio `rowsFromParsed` 兼容字典行/数组行（各仓 PR #4，0.2.1 → 0.2.2） |
| 4 | P3 | 浏览器控制台 404：`/api/api/zhiyun-logo/config` | logo 插件 UI 拼接了双 `/api` 前缀 | 记录待修（不影响功能） |

## 三、验证方法与证据

1. **样例生成**：`node scripts/qa/generate_demo_data.cjs` 从五仓模块定义提取 columns+sample，生成 16 个演示文件（14 CSV + 2 TXT）到 `docs/qa/demo-data/`，表头与列名完全一致。
2. **API 层**：`python scripts/qa/verify_demo_import.py` 逐文件 POST `/api/zhiyun-data-core/parse`，断言表头数与行数。**14/14 通过**。
3. **浏览器 E2E**：`python scripts/qa/demo_import_probe.py`（Playwright + 真实 Chrome）：真实 UI 登录 → 等待 PluginLoader 完成 → 逐模块切换 → `set_input_files` 上传 → 校验绿色来源标签与表格行数 → 点击运行 → 校验结果非空/无错误 → 截图。**13/13 通过**。
   - 覆盖模块：sales(bi/customers/performance)、finance(expense/finance)、people(permission/contact/anniversary/hr)、supply(supplier/replenishment/risk)、service(knowledge)。
   - form 型模块（finance 成本预测、people 审批路径、service 售后工单）与 text 型模块（service 应答/意图）用「一键填入示例 / 载入示例文本」演示，不在导入范围（设计如此）。
   - 截图示例：`zhiyun-sales-studio-bi.png`（KPI 营收 ¥317,640、月度趋势、Top 排名、待审阅工件审阅条完整）。

## 四、探测脚本沉淀（可重复回归）

- `scripts/qa/generate_demo_data.cjs`：样例文件生成器（模块定义变化后重跑）。
- `scripts/qa/verify_demo_import.py`：API 层对账。
- `scripts/qa/demo_import_probe.py`：浏览器 E2E（含登录回归、tour 遮罩处理、模块切换校验）。

## 五、已知限制（演示口径）

1. **模型 provider 不可达**（本地 GGUF 连接失败）：data-studio / 应用中心 / 数据核心 / 审计中心的"问 Agent"实时对话不可用；五大 Studio 的问 Agent 抽屉为本地模块执行流，**不依赖模型，可正常演示**。演示剧本已绕开实时对话环节。
2. **宿主新手引导遮罩**每次进入应用出现（可手动关闭）；探测脚本以 DOM 移除处理。根治需宿主侧记忆引导完成状态（遗留 P3）。
3. 直连 URL 进入应用需等 PluginLoader 完成（约 5-10 秒）；从侧边栏「应用」进入为推荐路径。
4. `zhiyun-logo/config` 404（双 /api 前缀，P3 待修）。
5. 导入为"填入输入表格"演示口径（PRD Data Core 持久化导入为后续 Phase B 范围）。

## 六、运行态版本说明

演示机运行态五仓已热同步至 **0.2.2**（rowfix），`.pawapp-commit` 仍指向 0.2.1 合并 SHA；待五仓 PR #4 合并后，由锁更新 PR 将正式 SHA 固化，恢复"运行态 = 锁定源"的一致性。
