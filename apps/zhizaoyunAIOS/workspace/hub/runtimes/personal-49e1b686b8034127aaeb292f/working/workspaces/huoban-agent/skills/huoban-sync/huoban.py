#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""伙伴云(Huoban) CRM 同步 CLI — 把伙伴云合同数据同步进销售分析平台(8302)的业绩归因。

用法:
    python3 huoban.py status                    # 查看同步状态/数据源文件/覆盖情况
    python3 huoban.py sync                      # 触发一次同步（伙伴云导出→归因表）
    python3 huoban.py report [--top 10]         # 三本账（主销售/跟单/协同贡献）排行
    python3 huoban.py orders --q 关键词 [--page 1] [--size 20]   # 归因明细检索

配置: 同目录 config.json（sales_api 地址）；仅标准库。
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))


def load_cfg():
    cfg = {"sales_api": "http://127.0.0.1:8302"}
    try:
        cfg.update(json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8")))
    except FileNotFoundError:
        pass
    cfg["sales_api"] = os.environ.get("SALES_API", cfg["sales_api"]).rstrip("/")
    return cfg


def call(cfg, method, path, body=None):
    req = urllib.request.Request(
        cfg["sales_api"] + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"},
        method=method)
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        print("HTTP %s: %s" % (e.code, e.read().decode()[:500]), file=sys.stderr)
        sys.exit(2)
    except urllib.error.URLError as e:
        print("无法连接销售分析平台（%s）：%s" % (cfg["sales_api"], e.reason), file=sys.stderr)
        sys.exit(3)


def fmt_wan(v):
    try:
        return "%.1f万" % (float(v) / 10000)
    except (TypeError, ValueError):
        return "—"


def main():
    ap = argparse.ArgumentParser(description="伙伴云CRM→销售分析平台 同步CLI")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="同步状态/数据源/覆盖情况")
    sub.add_parser("sync", help="触发同步")
    p = sub.add_parser("report", help="三本账排行")
    p.add_argument("--top", type=int, default=10)
    p = sub.add_parser("orders", help="归因明细检索")
    p.add_argument("--q", default="")
    p.add_argument("--page", type=int, default=1)
    p.add_argument("--size", type=int, default=20)
    args = ap.parse_args()
    cfg = load_cfg()

    if args.cmd == "status":
        d = call(cfg, "GET", "/api/huoban/status")
        last = d.get("last")
        print("数据源文件:", ", ".join(d.get("files") or []) or "（无）")
        print("归因表覆盖: %s/%s 条有贡献金额" % (d.get("attribution_filled"), d.get("attribution_total")))
        if last:
            print("最近同步: %s（读取 %s · 匹配 %s · 新增 %s）" %
                  (last.get("synced_at"), last.get("rows_read"), last.get("matched"), last.get("inserted")))
            print("说明:", last.get("note"))
        else:
            print("尚未同步过")
    elif args.cmd == "sync":
        d = call(cfg, "POST", "/api/huoban/sync", {})
        if d.get("error"):
            print("同步失败:", d["error"]); sys.exit(1)
        print("同步完成: 读取 %s 条 · 匹配 %s · 新增 %s" % (d.get("rows_read"), d.get("matched"), d.get("inserted")))
    elif args.cmd == "report":
        d = call(cfg, "GET", "/api/commission/report")
        print("贡献总额: %s（%s 人）" % (fmt_wan(d.get("total")), len(d.get("rows") or [])))
        for i, r in enumerate((d.get("rows") or [])[: args.top], 1):
            print("%2d. %s | %s | 订单 %s | %s" % (i, r.get("name"), r.get("role"), r.get("orders"), fmt_wan(r.get("amount"))))
    elif args.cmd == "orders":
        d = call(cfg, "GET", "/api/commission/orders?page=%d&size=%d&q=%s" %
                 (args.page, args.size, urllib.parse.quote(args.q)))
        print("共 %s 条（第 %d 页）" % (d.get("total"), args.page))
        for r in (d.get("rows") or []):
            print("  %s | %s | 主销售 %s 跟单 %s | 贡献 %s | 订单额 %s" %
                  (r.get("contract_no"), str(r.get("customer"))[:16], r.get("main_rep") or "—",
                   r.get("tracker") or "—", fmt_wan(r.get("rep_amount")), fmt_wan(r.get("amount"))))


if __name__ == "__main__":
    main()
