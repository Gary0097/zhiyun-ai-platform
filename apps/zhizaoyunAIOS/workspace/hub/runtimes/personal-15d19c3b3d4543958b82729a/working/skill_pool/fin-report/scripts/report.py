#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""财务报表工具：收支明细 → 科目汇总 / 月度对比 / 利润简表。

输入 CSV/TSV（文件或 stdin），表头：日期, 类型(收入/支出), 科目, 摘要, 金额
（日期支持 2026-09-01 / 2026/9/1 / 2026.9.1；类型可写 收入/支出/收/支）

用法:
  python3 report.py 明细.csv [--out 报表.csv] [--top 10]
"""
import argparse
import csv
import io
import sys
from collections import defaultdict

ALIAS = {"日期": "date", "时间": "date",
         "类型": "type", "收支": "type", "方向": "type",
         "科目": "subject", "类别": "subject", "项目": "subject",
         "摘要": "note", "说明": "note", "备注": "note",
         "金额": "amount", "数额": "amount"}


def fnum(v):
    try:
        return float(str(v).replace(",", "").replace("¥", "").strip())
    except (TypeError, ValueError):
        return 0.0


def norm_date(s):
    s = str(s).strip().replace("/", "-").replace(".", "-")
    p = s.split("-")
    if len(p) >= 2:
        try:
            y, m = int(p[0]), int(p[1])
            return f"{y:04d}-{m:02d}"
        except ValueError:
            return None
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--out", default=None)
    ap.add_argument("--top", type=int, default=10)
    a = ap.parse_args()

    raw = open(a.input, encoding="utf-8-sig").read() if a.input != "-" else sys.stdin.read()
    delimiter = "\t" if "\t" in raw.splitlines()[0] else ","
    rows = []
    for r in csv.DictReader(io.StringIO(raw), delimiter=delimiter):
        m = {ALIAS.get(str(k).strip(), str(k).strip()): v for k, v in r.items() if k}
        if not m.get("amount"):
            continue
        t = str(m.get("type", "")).strip()
        if any(k in t for k in ("收", "入")):
            sign = 1
        elif any(k in t for k in ("支", "出")):
            sign = -1
        else:
            continue
        rows.append({"month": norm_date(m.get("date")) or "",
                     "subject": str(m.get("subject") or "未分类").strip(),
                     "note": str(m.get("note") or "").strip(),
                     "amount": sign * fnum(m.get("amount"))})
    if not rows:
        print("未识别到有效明细（需列：日期/类型/科目/金额）")
        return

    by_sub = defaultdict(float)
    by_month = defaultdict(lambda: [0.0, 0.0])
    for r in rows:
        by_sub[r["subject"]] += r["amount"]
        mslot = by_month[r["month"] or "未知月份"]
        if r["amount"] > 0:
            mslot[0] += r["amount"]
        else:
            mslot[1] += -r["amount"]

    income = sum(v for v in by_sub.values() if v > 0)
    expense = -sum(v for v in by_sub.values() if v < 0)
    profit = income - expense

    print(f"明细 {len(rows)} 笔 | 收入 ¥{income:,.2f} | 支出 ¥{expense:,.2f} | 结余 ¥{profit:,.2f}")
    print("\n【按科目】")
    for k, v in sorted(by_sub.items(), key=lambda x: x[1]):
        print(f"  {'收入' if v > 0 else '支出'} {k}: ¥{abs(v):,.2f}")
    print("\n【按月】")
    for k in sorted(by_month):
        inc, exp = by_month[k]
        print(f"  {k}: 收入 ¥{inc:,.2f} | 支出 ¥{exp:,.2f} | 结余 ¥{inc - exp:,.2f}")
    print("\n【支出 TOP%d】" % a.top)
    for k, v in sorted(((k, -v) for k, v in by_sub.items() if v < 0),
                       key=lambda x: -x[1])[:a.top]:
        print(f"  {k}: ¥{v:,.2f}（占支出 {v / expense * 100:.1f}%）" if expense else f"  {k}")

    if a.out:
        with open(a.out, "w", encoding="utf-8-sig", newline="") as fp:
            w = csv.writer(fp)
            w.writerow(["区块", "项目", "金额"])
            w.writerow(["汇总", "收入", f"{income:.2f}"])
            w.writerow(["汇总", "支出", f"{expense:.2f}"])
            w.writerow(["汇总", "结余", f"{profit:.2f}"])
            for k, v in sorted(by_sub.items(), key=lambda x: x[1]):
                w.writerow(["按科目", k, f"{abs(v):.2f}"])
            for k in sorted(by_month):
                inc, exp = by_month[k]
                w.writerow(["按月", f"{k} 收入", f"{inc:.2f}"])
                w.writerow(["按月", f"{k} 支出", f"{exp:.2f}"])
                w.writerow(["按月", f"{k} 结余", f"{inc - exp:.2f}"])
        print(f"\n报表已写入: {a.out}")


if __name__ == "__main__":
    main()
