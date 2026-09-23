#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""工资核算工具：考勤+薪资标准 → 工资表（加班费/缺勤/社保公积金/个税/中秋福利）。

输入 CSV/TSV（文件或 stdin），表头自动识别（支持中文别名）：
  姓名, 部门, 基本工资, 岗位工资, 出勤天数, 应出勤天数(默认21.75),
  加班_工作日(h), 加班_周末(h), 加班_法定(h), 迟到扣款,
  社保基数(默认=基本工资), 公积金基数(默认=社保基数), 专项附加扣除,
  其他加项, 其他扣款, 中秋福利

用法:
  python3 payroll.py input.csv [--out 工资表.csv] [--hf 5] [--rates 0.08,0.02,0.002,0.05]
"""
import argparse
import csv
import io
import sys

ALIAS = {
    "姓名": "name", "员工": "name", "名字": "name",
    "部门": "dept",
    "基本工资": "base", "底薪": "base", "基本薪资": "base",
    "岗位工资": "post", "岗位津贴": "post",
    "出勤天数": "attend", "出勤": "attend", "实际出勤": "attend",
    "应出勤天数": "should", "应出勤": "should", "标准出勤": "should",
    "加班_工作日": "ot_wd", "工作日加班": "ot_wd", "平时加班": "ot_wd",
    "加班_周末": "ot_we", "周末加班": "ot_we", "休息日加班": "ot_we",
    "加班_法定": "ot_hol", "法定加班": "ot_hol", "法定假日加班": "ot_hol",
    "迟到扣款": "late",
    "社保基数": "sb_base", "公积金基数": "gjj_base",
    "专项附加扣除": "special_deduct", "专项扣除": "special_deduct",
    "其他加项": "add_on", "其他扣款": "deduct", "扣款": "deduct",
    "中秋福利": "festival", "节日福利": "festival",
}

# 2026 个税月度换算税率表（起征点5000）: (上限, 税率, 速算扣除)
TAX_TABLE = [(3000, .03, 0), (12000, .10, 210), (25000, .20, 1410),
             (35000, .25, 2660), (55000, .30, 4410), (80000, .35, 7160),
             (float("inf"), .45, 15160)]


def tax_of(taxable):
    for cap, rate, quick in TAX_TABLE:
        if taxable <= cap:
            return taxable * rate - quick
    return 0.0


def fnum(v, default=0.0):
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def load_rows(path):
    raw = open(path, encoding="utf-8-sig").read() if path != "-" else sys.stdin.read()
    delimiter = "\t" if "\t" in raw.splitlines()[0] else ","
    rdr = csv.DictReader(io.StringIO(raw), delimiter=delimiter)
    rows = []
    for r in rdr:
        m = {}
        for k, v in r.items():
            if k is None:
                continue
            key = ALIAS.get(str(k).strip(), str(k).strip())
            m[key] = v
        if m.get("name"):
            rows.append(m)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--out", default=None, help="输出工资表 CSV（UTF-8 BOM，Excel 直开）")
    ap.add_argument("--hf", type=float, default=5.0, help="公积金个人比例%%（默认5）")
    ap.add_argument("--rates", default="0.08,0.02,0.002",
                    help="社保个人比例：养老,医疗,失业（默认 0.08,0.02,0.002）")
    a = ap.parse_args()

    p_yang, p_yi, p_shi = [float(x) for x in a.rates.split(",")]
    rows = load_rows(a.input)
    if not rows:
        print("未识别到数据行，请检查表头（需含：姓名/基本工资）")
        return

    out_cols = ["姓名", "部门", "基本工资", "岗位工资", "加班费", "缺勤扣款", "迟到扣款",
                "其他加项", "中秋福利", "应发合计", "社保个人", "公积金个人", "专项附加扣除",
                "计税基数", "个税", "其他扣款", "实发工资"]
    result = []
    for m in rows:
        base = fnum(m.get("base"))
        post = fnum(m.get("post"))
        should = fnum(m.get("should"), 21.75) or 21.75
        attend = fnum(m.get("attend"), should)
        ot = fnum(m.get("ot_wd")) + fnum(m.get("ot_we")) + fnum(m.get("ot_hol"))
        hour_rate = base / 21.75 / 8
        ot_pay = hour_rate * (1.5 * fnum(m.get("ot_wd")) + 2.0 * fnum(m.get("ot_we"))
                              + 3.0 * fnum(m.get("ot_hol")))
        absent = max(should - attend, 0)
        absent_cut = base / should * absent if absent else 0.0
        late = fnum(m.get("late"))
        add_on = fnum(m.get("add_on"))
        deduct = fnum(m.get("deduct"))
        festival = fnum(m.get("festival"))
        gross = base + post + ot_pay + add_on + festival - absent_cut - late
        sb_base = fnum(m.get("sb_base"), base) or base
        gjj_base = fnum(m.get("gjj_base"), sb_base) or sb_base
        sb = sb_base * (p_yang + p_yi + p_shi)
        gjj = gjj_base * a.hf / 100.0
        special = fnum(m.get("special_deduct"))
        taxable = gross - sb - gjj - 5000 - special
        tax = tax_of(taxable) if taxable > 0 else 0.0
        net = gross - sb - gjj - tax - deduct
        result.append([m.get("name"), m.get("dept") or "", f"{base:.2f}", f"{post:.2f}",
                       f"{ot_pay:.2f}", f"{absent_cut:.2f}", f"{late:.2f}", f"{add_on:.2f}",
                       f"{festival:.2f}", f"{gross:.2f}", f"{sb:.2f}", f"{gjj:.2f}",
                       f"{special:.2f}", f"{max(taxable, 0):.2f}", f"{tax:.2f}",
                       f"{deduct:.2f}", f"{net:.2f}"])

    # 汇总
    tot = [0.0] * 8
    for r in result:
        v = [float(x) for x in r[2:]]
        tot[0] += v[0] + v[1]  # 基本+岗位
        tot[1] += v[2]  # 加班费
        tot[3] += v[8]  # 应发
        tot[4] += v[9]  # 社保
        tot[5] += v[10]  # 公积金
        tot[6] += v[13]  # 个税
        tot[7] += v[15]  # 实发
    print(f"共 {len(result)} 人 | 基本+岗位 ¥{tot[0]:,.2f} | 加班费 ¥{tot[1]:,.2f} | "
          f"应发 ¥{tot[3]:,.2f} | 社保(个人) ¥{tot[4]:,.2f} | 公积金(个人) ¥{tot[5]:,.2f} | "
          f"个税 ¥{tot[6]:,.2f} | 实发合计 ¥{tot[7]:,.2f}")
    print(" | ".join(out_cols))
    for r in result:
        print(" | ".join(r))

    if a.out:
        with open(a.out, "w", encoding="utf-8-sig", newline="") as fp:
            w = csv.writer(fp)
            w.writerow(out_cols)
            w.writerows(result)
        print(f"\n工资表已写入: {a.out}（Excel 可直接打开）")


if __name__ == "__main__":
    main()
