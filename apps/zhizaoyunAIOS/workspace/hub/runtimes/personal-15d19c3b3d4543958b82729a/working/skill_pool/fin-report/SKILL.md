---
name: fin-report
description: "财务报表技能。从收支明细（CSV/Excel/粘贴表格）生成：科目汇总、月度收支对比、利润/结余简表、支出TOP排行，并导出 Excel 可打开的报表 CSV。适合月度结账、经营简报、费用分析。Use for financial reporting from transaction details: subject summary, monthly comparison, profit overview and top expenses."
metadata:
  builtin_skill_version: "1.0"
  qwenpaw:
    emoji: "📈"
    requires: {}
---

# 财务报表技能

用法（以本 SKILL.md 所在目录为根，定位 `fin-report/scripts/report.py`）：

```bash
python3 <skill目录>/scripts/report.py 明细.csv --out 报表.csv --top 10
```

## 输入格式

CSV/TSV，表头（中文名，自动识别）：`日期, 类型(收入/支出), 科目, 摘要, 金额`。
日期支持 2026-09-01 / 2026/9/1 / 2026.9.1。用户粘贴的表格文本先存成临时 CSV 再执行。

## 输出

- 终端：汇总（收入/支出/结余）、按科目、按月、支出 TOP 榜（含占比）
- `--out`：结构化报表 CSV（UTF-8 BOM，Excel 直开），回复时把路径告诉用户

## 原则

- 所有数字以脚本输出为准，禁止口算编造
- 给出 2-3 条基于数据的经营提示（如最大科目占比、环比变化）
- 数据有异常（负数收入、日期缺失）先提示用户确认
