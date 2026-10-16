#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""金汉隆机械 · 智能采购日报（采购风险 + 补货建议）——每日自动汇报

产出（三路）：
  1) output/daily/采购日报-YYYYMMDD.md（归档；含两张汇总表 CSV）
  2) Mock 微信推送 http://127.0.0.1:18765/api/mock/wechat/push（MOCK_MANAGEMENT，幂等）
  3) 上传到 WeKnora《金汉隆-智能采购》知识库（8001 可见、可检索、可问答）
     - 日报 md：429 限流退避重试 3 次
     - 汇总表（供应商评估/物料补货）：缺失或 failed 时重传（先清 failed 再传，防堆积）

数据源：同目录 agent_data.sqlite（只读计算副本）。
"""
import datetime
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.environ.get("PURCHASE_DB", os.path.join(BASE, "agent_data.sqlite"))
OUTDIR = os.environ.get("PURCHASE_OUT", os.path.join(BASE, "output", "daily"))
WX_PUSH = os.environ.get("MOCK_PUSH_URL", "http://127.0.0.1:18765/api/mock/wechat/push")
WEKNORA = os.environ.get("WEKNORA_BASE", "http://127.0.0.1:18000")
KB_NAME = os.environ.get("WEKNORA_KB_NAME", "金汉隆-智能采购")
WEK_EMAIL = os.environ.get("WEKNORA_EMAIL", "")
WEK_PASSWORD = os.environ.get("WEKNORA_PASSWORD", "")
SUMMARIES = ["供应商评估汇总_supplier_score_summary.csv", "物料补货汇总_replenishment_summary.csv"]
BJ = datetime.timezone(datetime.timedelta(hours=8))


def q(sql):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(sql)]
    finally:
        con.close()


def post_json(url, body, token=None, timeout=30):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                 headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def wek_login():
    return post_json(WEKNORA + "/api/v1/auth/login", {"email": WEK_EMAIL, "password": WEK_PASSWORD})["token"]


def wek_get(url, token, timeout=20):
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode())


def wek_kb(token):
    kbs = wek_get(WEKNORA + "/api/v1/knowledge-bases", token)["data"]
    return next((k for k in kbs if k["name"] == KB_NAME), None)


def wek_items(token, kb_id):
    r = wek_get(WEKNORA + f"/api/v1/knowledge-bases/{kb_id}/knowledge?page=1&page_size=100", token)
    d = r.get("data")
    return d if isinstance(d, list) else (d or {}).get("items") or []


def wek_upload(token, kb_id, fn, content, ctype="application/octet-stream"):
    boundary = "----daily-%d" % int(time.time() * 1000 % 10**9)
    raw = b"".join([
        ("--%s\r\n" % boundary).encode(),
        ('Content-Disposition: form-data; name="file"; filename="%s"\r\n' % fn).encode("utf-8"),
        ("Content-Type: %s\r\n\r\n" % ctype).encode(),
        content,
        ("\r\n--%s--\r\n" % boundary).encode(),
    ])
    req = urllib.request.Request(WEKNORA + "/api/v1/knowledge-bases/" + kb_id + "/knowledge/file",
                                 data=raw, method="POST",
                                 headers={"Authorization": "Bearer " + token,
                                          "Content-Type": "multipart/form-data; boundary=" + boundary})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def wek_delete(token, kb_id, ids):
    return post_json(WEKNORA + "/api/v1/knowledge/batch-delete", {"ids": ids, "kb_id": kb_id}, token)


def build_report():
    snap = q("SELECT 参数值 v FROM calc_params WHERE 参数名='snapshot_at'")[0]["v"]
    snap_date = snap.split(" ")[0]
    alerts = q("SELECT * FROM v_inventory_alert ORDER BY 缺口数量 DESC")
    advice = q("SELECT * FROM v_replenishment_advice ORDER BY 建议补货量 DESC, 缺口数量 DESC")
    top1 = {r["物料名称"]: r for r in q("SELECT * FROM v_supplier_recommendation WHERE 排名=1")}
    overdue = q(f"""SELECT a.到货单号, a.采购单号, o.供应商, a.物料名称, a.到货数量, o.承诺到货日期
        FROM arrival_records a JOIN purchase_orders o ON o.采购单号 = a.采购单号
        WHERE a.状态='在途' AND date(o.承诺到货日期) < date('{snap_date}')
        ORDER BY o.承诺到货日期 LIMIT 12""")
    late30 = q(f"""SELECT 供应商名称, COUNT(*) 延期批次 FROM v_ontime_detail
        WHERE 是否准时='延期' AND date(到货日期) >= date('{snap_date}', '-30 day')
        GROUP BY 供应商名称 ORDER BY 延期批次 DESC LIMIT 3""")
    urgent = [a for a in alerts if a["预警状态"] == "紧急"]
    need_order = [a for a in advice if a["建议补货量"] > 0]
    manual = [a for a in advice if a["物料名称"] not in top1]
    transit_ok = [a for a in advice if a["建议补货量"] == 0]
    compare = [top1[a["物料名称"]] for a in advice
               if top1.get(a["物料名称"]) and top1[a["物料名称"]].get("价格校验不通过") == "是"]
    today = datetime.datetime.now(BJ).strftime("%Y-%m-%d")

    L = []
    L.append(f"# 金汉隆机械 · 智能采购日报（{today}）")
    L.append("")
    L.append(f"> 生成：{datetime.datetime.now(BJ).strftime('%Y-%m-%d %H:%M')}（北京时间）自动汇报 ｜ 数据快照：{snap} ｜ 单位：件 ｜ 来源：采购计算副本（只读）")
    L.append("")
    risks = []
    if alerts:
        names = "、".join(f"{a['物料名称']}（可用 {a['可用天数']} 天）" for a in alerts)
        risks.append(f"**库存风险**：{len(alerts)} 个物料低于安全库存（{len(urgent)} 个紧急）——{names}。")
    overdue_order = [a for a in advice if a["建议下单日期"] and a["建议下单日期"] < snap_date and a["建议补货量"] > 0]
    if overdue_order:
        risks.append("**断料风险**：" + "、".join(a["物料名称"] for a in overdue_order) + " 建议下单日已逾期，需立即执行。")
    if manual:
        risks.append("**供应商风险**：" + "、".join(a["物料名称"] for a in manual) + " 无合格候选供应商（近期供应商均未达准入线）→ 转人工/引入新供应商。")
    for r in compare:
        risks.append(f"**比价提示**：{r['物料名称']} 首选 {r['供应商名称']} 单价高于候选池最低价超 10% 且评分接近 → 建议先比价。")
    if late30:
        risks.append("**供应商延期**（近30天）：" + "、".join(f"{r['供应商名称']}({r['延期批次']}批)" for r in late30) + "。")
    if overdue:
        risks.append(f"**在途逾期**：{len(overdue)} 个在途批次已超承诺到货日（最早 {overdue[0]['承诺到货日期']}，{overdue[0]['供应商']} {overdue[0]['物料名称']}）→ 催货跟踪。")
    L.append(f"## 一、风险摘要（{len(risks)} 项）")
    L.append("")
    for i, r in enumerate(risks, 1):
        L.append(f"{i}. {r}")
    L.append("")
    L.append("## 二、补货建议")
    L.append("")
    if need_order:
        L.append("| 物料 | 建议补货量 | 主荐供应商 | 综合评分 | 提示 | 补货点ROP | 建议下单日 | 预计耗尽日 |")
        L.append("|---|---|---|---|---|---|---|---|")
        for a in need_order:
            r = top1.get(a["物料名称"])
            sup = f"{r['供应商名称']}（{r['供应商编码']}）" if r else "无合格候选 → 转人工"
            score = r["综合评分"] if r else "—"
            tip = "建议比价" if (r and r.get("价格校验不通过") == "是") else ("转人工" if not r else "—")
            L.append(f"| {a['物料名称']} | **{a['建议补货量']}** | {sup} | {score} | {tip} | {a['补货点ROP']} | {a['建议下单日期']} | {a['预计耗尽日期']} |")
    else:
        L.append("（今日无需下单）")
    L.append("")
    if transit_ok:
        L.append("## 三、在途覆盖（暂无需下单）")
        L.append("")
        for a in transit_ok:
            L.append(f"- {a['物料名称']}：现有 {a['当前库存']} + 在途 {a['在途数量']} ≥ 补货点 {a['补货点ROP']}，在途已覆盖。")
        L.append("")
    L.append("## 四、口径附注")
    L.append("")
    L.append("日均消耗=近30天领用均值；准时率=近180天按期到货批次占比；合格率=近180天检验合格数量占比；")
    L.append("补货量=向上取整((日均消耗×提前期+安全库存−现有−在途)/包装批量)×包装批量（下限MOQ）；候选准入=准时率≥0.70 且 合格率≥0.965。")
    return today, "\n".join(L), {
        "预警SKU": len(alerts), "需下单": len(need_order), "在途覆盖": len(transit_ok),
        "转人工": len(manual), "比价提示": len(compare), "在途逾期": len(overdue),
    }


def push_mock(today, stats):
    content = (f"【智能采购日报 {today}】风险与补货建议：\n"
               f"· 低库存 {stats['预警SKU']} 个 / 需下单 {stats['需下单']} 个 / 在途覆盖 {stats['在途覆盖']} 个\n"
               f"· 转人工 {stats['转人工']} 个；比价提示 {stats['比价提示']} 个；在途逾期 {stats['在途逾期']} 批\n"
               f"完整日报见《金汉隆-智能采购》知识库或采购看板。")
    body = {"idempotency_key": f"purchase-daily-{today}", "content": content, "recipient_group": "MOCK_MANAGEMENT"}
    req = urllib.request.Request(WX_PUSH, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def build_summaries():
    import csv
    paths = []
    rows = q("""SELECT s.供应商编码, s.供应商名称, s.所在地, s.供应类别, s.近180天到货批次,
                s.准时率, s.合格率, s.价格竞争力, ROUND(s.综合评分,4) 综合评分,
                CASE WHEN s.准时率 >= 0.70 AND s.合格率 >= 0.965 THEN '达标' ELSE '未达标' END 准入判定
                FROM v_supplier_score s WHERE s.近180天到货批次 > 0 ORDER BY s.综合评分 DESC""")
    p1 = os.path.join(OUTDIR, SUMMARIES[0])
    with open(p1, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    paths.append(p1)
    adv = q("SELECT * FROM v_replenishment_advice ORDER BY 建议补货量 DESC, 缺口数量 DESC")
    top1 = {r["物料名称"]: r for r in q("SELECT * FROM v_supplier_recommendation WHERE 排名=1")}
    out = []
    for a in adv:
        t = top1.get(a["物料名称"])
        out.append({"物料名称": a["物料名称"], "当前库存": a["当前库存"], "在途数量": a["在途数量"],
                    "安全库存阈值": a["安全库存阈值"], "可用天数": a["可用天数"], "日均消耗": a["日均消耗"],
                    "补货点ROP": a["补货点ROP"], "建议补货量": a["建议补货量"],
                    "主荐供应商": (t["供应商名称"] if t else "无合格候选（转人工）"),
                    "主荐评分": (t["综合评分"] if t else ""),
                    "提示": ("建议比价" if (t and t.get("价格校验不通过") == "是") else ("转人工" if not t else ""))})
    p2 = os.path.join(OUTDIR, SUMMARIES[1])
    with open(p2, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)
    paths.append(p2)
    return paths


def kb_sync_report(today, report_md):
    last = None
    for attempt in range(1, 4):
        try:
            token = wek_login()
            kb = wek_kb(token)
            if not kb:
                return {"skipped": "KB not found"}
            fn = f"采购日报-{today}.md"
            items = wek_items(token, kb["id"])
            if any(it.get("file_name") == fn and it.get("parse_status") == "completed" for it in items):
                return {"kb_id": kb["id"], "file": fn, "status": "completed(exists)"}
            wek_upload(token, kb["id"], fn, report_md.encode("utf-8"), "text/markdown")
            time.sleep(2)
            items = wek_items(token, kb["id"])
            hit = next((it for it in items if it.get("file_name") == fn), None)
            return {"kb_id": kb["id"], "file": fn, "status": (hit or {}).get("parse_status", "submitted")}
        except urllib.error.HTTPError as e:
            txt = e.read().decode("utf-8", "replace")[:160]
            if e.code == 409 or "exist" in txt.lower():
                return {"file": f"采购日报-{today}.md", "status": "already_exists"}
            last = f"http_{e.code}: {txt}"
        except Exception as e:
            last = str(e)[:160]
        time.sleep(20)
    return {"status": f"failed_after_retries: {last}"}


def kb_sync_summaries():
    """汇总表缺失/failed 时重传；先清理同名的 failed 条目，避免堆积（嵌入限流时每天自动再试）。"""
    try:
        token = wek_login()
        kb = wek_kb(token)
        if not kb:
            return {"skipped": "KB not found"}
        items = wek_items(token, kb["id"])
        result = {}
        for fn in SUMMARIES:
            path = os.path.join(OUTDIR, fn)
            if not os.path.isfile(path):
                continue
            states = [it for it in items if it.get("file_name") == fn]
            if any(it.get("parse_status") == "completed" for it in states):
                result[fn] = "completed(exists)"
                continue
            dead = [it["id"] for it in states if it.get("parse_status") == "failed"]
            if dead:
                wek_delete(token, kb["id"], dead)
                time.sleep(1)
            with open(path, "rb") as f:
                wek_upload(token, kb["id"], fn, f.read(), "text/csv")
            result[fn] = "submitted(processing)"
        return result
    except Exception as e:
        return {"failed": str(e)[:160]}


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    today, report_md, stats = build_report()
    path = os.path.join(OUTDIR, f"采购日报-{today}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(report_md)
    print(f"[日报] 已生成 {path} ({len(report_md)} bytes) | {json.dumps(stats, ensure_ascii=False)}")
    try:
        build_summaries()
        print("[汇总表] 已生成（供应商评估/物料补货）")
    except Exception as e:
        print(f"[汇总表] 生成失败: {e}", file=sys.stderr)
    try:
        print(f"[Mock推送] {json.dumps(push_mock(today, stats), ensure_ascii=False)}")
    except Exception as e:
        print(f"[Mock推送] 失败: {e}", file=sys.stderr)
    print(f"[KB日报] {json.dumps(kb_sync_report(today, report_md), ensure_ascii=False)}")
    print(f"[KB汇总] {json.dumps(kb_sync_summaries(), ensure_ascii=False)}")


if __name__ == "__main__":
    main()
