#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统计计算辅助：均值 / 线性回归斜率 / 变化率

用法:
  python3 datahub/calc.py 0.469421 0.676166 0.9           # 直接给一串数
  python3 datahub/calc.py "1,2,3,4"                        # 逗号分隔
  python3 datahub/calc.py --file values.json               # JSON 数组或 {"values":[...]}
输出 JSON: {"n":..,"mean":..,"slope":..,"first":..,"last":..,"change_rate":..}
说明: slope 为对序列下标做最小二乘线性回归的斜率（14 点回归等直接用本工具）。
"""
import json
import sys


def parse_nums(args):
    nums = []
    for a in args:
        a = a.strip().strip("[]")
        if not a:
            continue
        for part in a.replace(",", " ").split():
            nums.append(float(part))
    return nums


def mean(xs):
    return sum(xs) / len(xs) if xs else None


def slope(xs):
    n = len(xs)
    if n < 2:
        return None
    xm = (n - 1) / 2.0
    ym = mean(xs)
    num = sum((i - xm) * (v - ym) for i, v in enumerate(xs))
    den = sum((i - xm) ** 2 for i in range(n))
    return num / den if den else None


def main():
    args = sys.argv[1:]
    nums = None
    if args and args[0] == "--file":
        with open(args[1], encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data = data.get("values") or data.get("data") or []
        nums = [float(x) for x in data]
        args = args[2:]
    if nums is None:
        nums = parse_nums(args)
    out = {"n": len(nums)}
    if nums:
        out["mean"] = round(mean(nums), 6)
        out["first"] = nums[0]
        out["last"] = nums[-1]
        out["change_rate"] = round((nums[-1] - nums[0]) / nums[0], 6) if nums[0] else None
        out["slope"] = round(slope(nums), 6)
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
