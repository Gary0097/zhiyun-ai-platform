#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回填 9 个月(2026-01-01~2026-09-19)每日经营简报历史归档:
  - output/daily_brief_YYYY-MM-DD.md   每日简报(与 daily_brief.run 同口径)
  - output/daily_brief_history.csv     三指标逐日序列
  - output/daily_brief_9m_summary.md   月度汇总
只读数据库, 不写 claim/ledger(那些属于真实推送审计, 不伪造)。
"""
import csv
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import daily_brief  # noqa: E402

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent_data.sqlite")
OUT = daily_brief.out_dir()


def main():
    d0, d1 = date(2026, 1, 1), date(2026, 9, 19)
    rows, monthly = [], {}
    d = d0
    while d <= d1:
        r = daily_brief.run(DB, d.isoformat())
        with open(os.path.join(OUT, "daily_brief_%s.md" % d), "w", encoding="utf-8") as f:
            f.write(r["brief"] + "\n")
        rows.append([d.isoformat(), r["completed_orders"], r["new_abnormal_work_orders"],
                     r["open_abnormal_work_orders_eod"], r["reimbursement_count"],
                     r["reimbursement_amount"]])
        m = d.isoformat()[:7]
        cur = monthly.setdefault(m, [0, 0, 0, 0.0])
        cur[0] += r["completed_orders"]
        cur[1] += r["new_abnormal_work_orders"]
        cur[2] += r["reimbursement_count"]
        cur[3] += r["reimbursement_amount"]
        d += timedelta(days=1)

    with open(os.path.join(OUT, "daily_brief_history.csv"), "w", newline="",
              encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["日期", "签收完成单数", "新增异常工单", "日末未关闭工单",
                    "报销笔数", "报销金额"])
        w.writerows(rows)

    lines = ["# 经营简报 9 个月使用数据汇总(2026-01-01 ~ 2026-09-19)", "",
             "| 月份 | 全量交付(单) | 新增异常工单(单) | 报销(笔) | 报销金额(元) |",
             "|---|---|---|---|---|"]
    for m in sorted(monthly):
        v = monthly[m]
        lines.append("| %s | %d | %d | %d | %.2f |" % (m, v[0], v[1], v[2], v[3]))
    lines += ["", "共 %d 个报告日; 逐日明细见 daily_brief_history.csv, 每日全文见 daily_brief_*.md" % len(rows)]
    with open(os.path.join(OUT, "daily_brief_9m_summary.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
