---
summary: "智能采购智能体长期记忆"
---

# MEMORY

## 固定事实

- 快照时间：2026-09-18 08:00 +08:00（从 calc_params.snapshot_at 读取）。
- 计算副本：`procurement/agent_data.sqlite`（只读）。
- 知识库：《金汉隆-智能采购》（按名称检索即可，kb_search.py 自动解析 id）。
- Mock 推送：http://127.0.0.1:18765/api/mock/wechat/push（WB_MANAGEMENT，幂等）。
- 演示分支：标准件=在途覆盖→建议量 0；钣金件=无合格候选→转人工；DNX/防护罩=价格校验提示比价。

## 工具设置

- query.py：只读 SQL（SELECT/PRAGMA）；kb_search.py：知识库问数。
- 输出文件写入 `procurement/output/`。

## 经验

- （随使用补充：口径例外、已知数据坑、人工复核案例）
