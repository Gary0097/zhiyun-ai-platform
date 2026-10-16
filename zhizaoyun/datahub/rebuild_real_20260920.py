#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""金汉隆 AI 数据中枢 · 真实数据重建（批次 20260920）

用本机真实提取数据（/root/crm_*.json、erp_*.json、import_*.db）与
《数据模型映射》《源表画像》中的真实统计，替换 agent_data.sqlite 中的
模拟数据（mock_seed=20260918 / 扩量精修版生成）。

原则：
- 只写入可从真实来源推导的内容；来源文件、工作表、行号随行记录。
- 真实源缺失的域（工时/考勤/MES/OA/报销/物流轨迹/质检明细/供应商档案）
  清空并保留表结构，等待对应真实文件上传。
"""
import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
from datetime import datetime, timedelta

ROOT = "/data/actions/zhizaoyun-datahub"
DB = os.path.join(ROOT, "agent_data.sqlite")
RUNTIME_DB = ("/root/zhiyun-ai-platform/apps/zhizaoyunAIOS/workspace/hub/runtimes/"
              "personal-49e1b686b8034127aaeb292f/working/workspaces/datahub-agent/datahub/agent_data.sqlite")
SNAPSHOT = "2026-09-20T08:00:00+08:00"
IMPORTED_AT = "2026-09-20T08:00:00+08:00"

SRC = {
    "contract": "/root/crm_contract.json",            # 合同表 BiTable 导出
    "machine": "/root/crm_machine_orders.json",        # 机器下单表 BiTable 导出
    "aftersales": "/root/crm_aftersales.json",         # 售后申请表 BiTable 导出
    "production": "/root/erp_production.json",         # 生产进度总表（部分提取）
    "procurement": "/root/erp_procurement.json",       # 采购总表提取
    "inventory": "/root/erp_inventory.json",           # 库存表提取
    "morders": "/root/import_morders.db",              # 机器下单表已解析库
    "tickets": "/root/import_tickets.db",              # 售后工单已解析库
}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def to_str(v):
    """BiTable 字段值可能为 None/str/list/dict，统一转纯文本。"""
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        parts = []
        for x in v:
            if isinstance(x, dict):
                parts.append(str(x.get("text") or x.get("name") or x.get("value") or ""))
            else:
                parts.append(to_str(x))
        return " ".join(p for p in parts if p).strip()
    if isinstance(v, dict):
        return str(v.get("text") or v.get("name") or v.get("value") or "").strip()
    return str(v).strip()


def to_num(v):
    s = to_str(v).replace(",", "").replace("￥", "").replace("¥", "")
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group()) if m else None


def parse_date(s):
    # BiTable 导出的日期常为 Unix 时间戳（秒）
    if isinstance(s, (int, float)) and 946684800 < s < 4102444800:
        return datetime.utcfromtimestamp(s) + timedelta(hours=8)
    s = to_str(s)
    if not s:
        return None
    if s.isdigit() and 946684800 < int(s) < 4102444800:
        return datetime.utcfromtimestamp(int(s)) + timedelta(hours=8)
    s = s.split(".")[0].split("+")[0].strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            d = datetime.strptime(s[:19] if " " in s else s[:10], fmt)
            if 2000 <= d.year <= 2027:      # 1900 序列值按无日期处理
                return d
            return None
        except ValueError:
            continue
    return None


def d2s(d, end_of_day=False):
    if not d:
        return None
    if end_of_day:
        d = d + timedelta(hours=23, minutes=59, seconds=59)
    return d.strftime("%Y-%m-%dT%H:%M:%S+08:00")


def rev_fields(doc):
    return {name: fid for fid, name in doc["fields"].items()}


def main():
    contract_doc = json.load(open(SRC["contract"], encoding="utf-8"))
    machine_doc = json.load(open(SRC["machine"], encoding="utf-8"))
    production_doc = json.load(open(SRC["production"], encoding="utf-8"))
    procurement_doc = json.load(open(SRC["procurement"], encoding="utf-8"))
    inventory_doc = json.load(open(SRC["inventory"], encoding="utf-8"))

    cF = rev_fields(contract_doc)
    mF = rev_fields(machine_doc)

    mo_con = sqlite3.connect(f"file:{SRC['morders']}?mode=ro", uri=True)
    mo_con.row_factory = sqlite3.Row
    mo_rows = [dict(r) for r in mo_con.execute("SELECT * FROM mo ORDER BY so_no")]
    mo_con.close()
    tk_con = sqlite3.connect(f"file:{SRC['tickets']}?mode=ro", uri=True)
    tk_con.row_factory = sqlite3.Row
    ticket_rows = [dict(r) for r in tk_con.execute("SELECT * FROM tickets")]
    tk_con.close()

    # 机器下单表原始行按 item_id 索引，补充 下单时间/生产编号/出货/验收 等真实字段
    mo_raw = {str(r.get("item_id")): r for r in machine_doc["rows"]}

    # 备份
    for p in (DB, RUNTIME_DB):
        if os.path.isfile(p):
            shutil.copy2(p, p + ".bak-mock-20260919")
    con = sqlite3.connect(DB)
    cur = con.cursor()

    W = []  # 统计汇总

    # ---------- 1. 基础维表 ----------
    cur.execute("DELETE FROM workcenters")
    workcenters = [
        ("WC01", "多列装配", "D03"),   # 来源：生产进度表9.16.xlsx·多列装配排产
        ("WC02", "电工", "D02"),       # 来源：电工排产
        ("WC03", "调试", "D03"),       # 来源：调试排产
        ("WC04", "装盒部", "D03"),     # 来源：装盒部排产
    ]
    cur.executemany("INSERT INTO workcenters VALUES (?,?,?)", workcenters)

    # 员工 = 真实业务员（合同表+机器下单表+生产总表）
    names = set()
    for r in contract_doc["rows"]:
        n = to_str(r.get(cF["业务员"]))
        if n:
            names.add(n)
    for r in production_doc["rows"]:
        if len(r) > 2 and to_str(r[2]):
            names.add(to_str(r[2]))
    for r in mo_rows:
        if r.get("rep"):
            names.add(r["rep"])
    cur.execute("DELETE FROM employees")
    cur.executemany("INSERT INTO employees VALUES (?,?,?,?,?,?)",
                    [(f"E{i:03d}", n, "D06", None, None, None)
                     for i, n in enumerate(sorted(names), 1)])
    W.append(f"employees: {len(names)} 名真实业务员")

    # 客户 = 合同表公司名称（去重，保留省/市/行业/级别/业务员）
    cust = {}
    for r in contract_doc["rows"]:
        nm = to_str(r.get(cF["公司名称"]))
        if not nm:
            continue
        if nm not in cust:
            cust[nm] = {
                "province": to_str(r.get(cF.get("省", ""))) or None,
                "city": to_str(r.get(cF.get("市", ""))) or None,
                "industry": to_str(r.get(cF.get("行业", ""))) or None,
                "tier": to_str(r.get(cF.get("客户级别", ""))) or None,
                "owner": to_str(r.get(cF["业务员"])) or None,
            }
    for r in mo_rows:
        nm = (r.get("customer") or "").strip()
        if nm and nm not in cust:
            cust[nm] = {"province": None, "city": None, "industry": None,
                        "tier": None, "owner": r.get("rep") or None}
    cust_ids = {nm: f"C{i:04d}" for i, nm in enumerate(sorted(cust), 1)}
    cur.execute("DELETE FROM customers")
    cur.executemany("INSERT INTO customers VALUES (?,?,?,?,?,?,?)",
                    [(cust_ids[nm], nm, v["province"], v["city"], v["industry"],
                      v["tier"], v["owner"]) for nm, v in cust.items()])
    W.append(f"customers: {len(cust)} 家真实客户（合同表+机器下单表去重）")

    # 产品：保留原 16 个真实机型档案（含标准工时），再补充机器下单表真实设备名
    old_products = cur.execute("SELECT product_id, product_name, product_family, unit,"
                               " output_basis, standard_hours_per_unit FROM products").fetchall()
    prod_by_name = {r[1]: r for r in old_products}
    for r in mo_rows:
        nm = (r.get("product") or "").strip()
        if nm and nm not in prod_by_name:
            prod_by_name[nm] = ("R%03d" % (len(prod_by_name) + 1), nm, None,
                                r.get("unit") or "台",
                                "设备或配件；不以客户包装物为产量", None)
    # 生产总表真实类别（单列/双列/多列/小立式/装盒线/水平给袋/装盒机/理料线）
    cat_prod = {}
    for r in production_doc["rows"]:
        cat = to_str(r[3]) if len(r) > 3 else ""
        if cat and cat + "机" not in prod_by_name and cat not in cat_prod:
            pid = "R%03d" % (len(prod_by_name) + len(cat_prod) + 1)
            cat_prod[cat + "机"] = (pid, cat + "机", cat, "台",
                                    "设备或配件；不以客户包装物为产量", None)
    all_products = list(prod_by_name.values()) + list(cat_prod.values())
    prod_ids = {r[1]: r[0] for r in all_products}
    cur.execute("DELETE FROM products")
    cur.executemany("INSERT INTO products VALUES (?,?,?,?,?,?)", all_products)
    W.append(f"products: {len(all_products)} 个真实产品/机型（原16档案 + 机器下单设备名 + 生产类别）")

    # ---------- 2. 合同表（真实 6881 行，新表） ----------
    cur.execute("DROP TABLE IF EXISTS contracts")
    cur.execute("""CREATE TABLE contracts (
        id INTEGER PRIMARY KEY,
        contract_no TEXT, customer_id TEXT, customer_name TEXT, sales_owner TEXT,
        signed_at TEXT, contract_amount REAL, received_amount REAL,
        final_payment REAL, unpaid_amount REAL, machine_qty REAL,
        purchase_status TEXT, source_file TEXT, source_row INTEGER,
        imported_at TEXT)""")
    n_contract = 0
    for i, r in enumerate(contract_doc["rows"], 1):
        no = to_str(r.get(cF["合同编号"]))
        nm = to_str(r.get(cF["公司名称"]))
        if not no and not nm:
            continue
        sd = parse_date(r.get(cF["成交日期"]))
        cur.execute("INSERT INTO contracts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (i, no or None, cust_ids.get(nm), nm or None,
                     to_str(r.get(cF["业务员"])) or None,
                     d2s(sd), to_num(r.get(cF["合同金额（元）"])),
                     to_num(r.get(cF["已收款金额（元）"])),
                     to_num(r.get(cF["尾款（元）"])),
                     to_num(r.get(cF["未收款（元）"])),
                     to_num(r.get(cF["机器台数"])),
                     to_str(r.get(cF["购买状态"])) or None,
                     "合同表_20260920072414.xlsx", i, IMPORTED_AT))
        n_contract += 1
    W.append(f"contracts: {n_contract} 行真实合同（合同表_20260920072414.xlsx）")

    # ---------- 3. 订单（真实：机器下单 2322 + 生产总表 95） ----------
    cur.execute("DELETE FROM stage_nodes")
    cur.execute("DELETE FROM work_orders")
    cur.execute("DELETE FROM orders")

    order_rows = []
    for r in mo_rows:
        raw = mo_raw.get(str(r.get("item_id")), {})
        created = parse_date(raw.get(mF.get("下单时间", ""))) or parse_date(r.get("created_at"))
        so = r["so_no"]
        order_rows.append({
            "so": so, "contract_no": r.get("contract_no") or None,
            "customer_id": cust_ids.get((r.get("customer") or "").strip()),
            "product_id": prod_ids.get((r.get("product") or "").strip()),
            "packaged": to_str(raw.get(mF.get("包装产品", ""))) or None,
            "qty": int(r["quantity"]) if r.get("quantity") else 1,
            "unit": r.get("unit") or "台", "amount": r.get("cost"),
            "created": d2s(created) or "2026-09-18T00:00:00+08:00",
            "due": d2s(parse_date(r.get("due_date"))),
            "owner": r.get("rep") or to_str(raw.get(mF.get("业务员", ""))) or None,
            "origin": "真实:机器下单表_20260920072729.xlsx",
            "sheet": "机器下单表_20260920072729.xlsx", "srow": None,
            "src": "CRM机器下单",
            "raw": raw, "cat": None, "status": r.get("status"),
        })

    prod_orders = []
    seen_prod = set()
    for idx, r in enumerate(production_doc["rows"], 1):
        so = to_str(r[4]) if len(r) > 4 else ""
        if not so or so in seen_prod:   # 同一生产订单跨行只保留首行（映射文档规则）
            continue
        seen_prod.add(so)
        created = parse_date(r[1])
        due = parse_date(r[7]) if len(r) > 7 else None
        cat = to_str(r[3]) if len(r) > 3 else ""
        project = to_str(r[5]) if len(r) > 5 else ""
        qty = to_num(r[6]) if len(r) > 6 else None
        try:
            qty = int(qty) if qty else 1
        except (TypeError, ValueError):
            qty = 1
        prod_orders.append({
            "so": so, "row": r, "idx": idx, "created": created, "due": due,
            "cat": cat, "project": project, "qty": qty,
            "status": to_str(r[8]) if len(r) > 8 else "",
            "days": to_num(r[11]) if len(r) > 11 else None,
            "biz": to_str(r[2]) if len(r) > 2 else "",
        })

    for p in prod_orders:
        order_rows.append({
            "so": p["so"], "contract_no": None, "customer_id": None,
            "product_id": prod_ids.get((p["cat"] + "机") if p["cat"] else ""),
            "packaged": p["project"] or None, "qty": p["qty"], "unit": "台",
            "amount": None,
            "created": d2s(p["created"]) or "2026-01-01T00:00:00+08:00",
            "due": d2s(p["due"]), "owner": p["biz"] or None,
            "origin": "真实:生产进度表9.16.xlsx·生产进度总表",
            "sheet": "生产进度表9.16.xlsx|生产进度总表", "srow": p["idx"],
            "src": "生产进度总表", "raw": None, "cat": p["cat"],
            "status": p["status"],
        })

    seen = set()
    for o in order_rows:
        if o["so"] in seen:
            o["so"] = o["so"] + "-R"
        seen.add(o["so"])
        cur.execute("""INSERT INTO orders (sales_order_id, order_line_id, work_order_id,
            contract_no, customer_id, product_id, packaged_goods, quantity, unit,
            contract_amount, created_at, promised_delivery_at, delivery_basis,
            route_id, fulfillment_mode, order_source, source_risk_flag,
            source_risk_reason, sales_owner, source_sheet, source_row,
            is_effective, data_origin, snapshot_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)""",
                    (o["so"], None, None, o["contract_no"], o["customer_id"],
                     o["product_id"], o["packaged"], o["qty"], o["unit"],
                     o["amount"], o["created"], o["due"],
                     "全量签收", None, "自产", o["src"], None, None,
                     o["owner"], o["sheet"], o["srow"], o["origin"], SNAPSHOT))
    W.append(f"orders: {len(order_rows)} 行真实订单（机器下单 {len(mo_rows)} + 生产总表 {len(prod_orders)}）")

    # ---------- 4. 工单 + 工序节点（真实 95 单，状态映射） ----------
    # source_status 保留生产总表"当天状态"原文，映射仅用于展示（PRD 4.4）
    cols_sn = [c[1] for c in cur.execute("PRAGMA table_info(stage_nodes)").fetchall()]
    if "source_status" not in cols_sn:
        cur.execute("ALTER TABLE stage_nodes ADD COLUMN source_status TEXT")
        cols_sn.append("source_status")
    # 状态 → 各节点完成位相（PLAN/PROCESS/QC/SHIP/SIGN）
    STAGE_MAP = {
        "待图纸": 0, "待确认": 0, "待业务确认": 0, "待回料": 0, "待物料验收": 0,
        "待组装": 1, "组装中": 1, "待调试": 1, "调试中": 1,
        "待验收": 2, "待出货": 3,
    }
    STAGES = [("PLAN", "计划", 1, "D01"), ("PROCESS", "加工", 2, "D03"),
              ("QC", "质检", 3, "D04"), ("SHIP", "发货", 4, "D05"),
              ("SIGN", "签收", 5, "D05")]

    def wc_of(p):
        st, cat = p["status"], p["cat"] or ""
        if st in ("待调试", "调试中"):
            return "WC03"
        if "装盒" in cat:
            return "WC04"
        return "WC01"

    snap_dt = datetime.fromisoformat(SNAPSHOT)
    n_wo = n_sn = 0
    for p in prod_orders:
        if p["so"] not in seen:
            continue
        wo = "WO-" + p["so"]
        cur.execute("INSERT INTO work_orders VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (wo, p["so"], None, prod_ids.get((p["cat"] + "机") if p["cat"] else ""),
                     p["qty"], "台", "自产", d2s(p["created"]),
                     d2s(p["due"]), wc_of(p), "生产进度总表"))
        n_wo += 1
        phase = STAGE_MAP.get(p["status"])
        if phase is None:      # 未知真实状态：仅生成计划节点，其余待补
            phase = 0
        plan_days = p["days"] if p["days"] and p["days"] > 0 else None
        for k, (code, name, seq, dept) in enumerate(STAGES):
            if k < phase:
                st = "已完成"
            elif k == phase:
                st = "进行中" if code != "PLAN" or p["status"] in (
                    "待图纸", "待确认", "待业务确认", "待回料", "待物料验收") else "进行中"
            else:
                st = "未开始"
            if code == "PLAN":
                ps = d2s(p["created"])
                pe = d2s(p["created"] + timedelta(days=plan_days), True) if plan_days else None
                wc = None
            elif code == "PROCESS":
                ps = pe = None
                wc = wc_of(p)
            elif code == "SHIP":
                ps = None
                pe = d2s(p["due"], True)
                wc = None
            else:
                ps = pe = None
                wc = None
            cur.execute("""INSERT INTO stage_nodes (stage_id, work_order_id, sales_order_id,
                stage_code, stage_name, sequence, department_id, workcenter_id,
                planned_start_at, planned_end_at, actual_start_at, actual_end_at,
                stage_status, owner_employee_id, updated_at, source_status)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (f"SN-{p['so']}-{code}", wo, p["so"], code, name, seq,
                         dept, wc, ps, pe, None, None, st, None, IMPORTED_AT,
                         p["status"] or None))
            n_sn += 1
    W.append(f"work_orders: {n_wo} · stage_nodes: {n_sn}（生产总表真实状态映射）")

    # ---------- 5. 采购行（真实 9556） + 物料 ----------
    hdr = procurement_doc["hdr"]
    col = {n: i for i, n in enumerate(hdr) if n}
    cur.execute("DELETE FROM procurement_lines")
    materials = {}
    mat_ids = {}

    def mat_id(name, spec=""):
        key = (name, spec)
        if key not in mat_ids:
            mid = f"M{len(mat_ids) + 1:04d}"
            mat_ids[key] = mid
            materials[key] = mid
        return mat_ids[key]

    order_id_set = seen
    n_pl = 0
    for i, r in enumerate(procurement_doc["rows"], 1):
        name = r[col["物料名称"]] if "物料名称" in col and len(r) > col["物料名称"] else ""
        name = to_str(name)
        if not name:
            continue
        spec = to_str(r[col["材料"]]) if "材料" in col and len(r) > col["材料"] else ""
        mid = mat_id(name, spec)
        proj = to_str(r[col["项目"]]) if "项目" in col and len(r) > col["项目"] else ""
        m = re.search(r"KL\d{6}-\d{3}-[A-Z]", proj)
        so = m.group() if m and m.group() in order_id_set else None
        qty = to_num(r[col["数量"]]) if "数量" in col and len(r) > col["数量"] else None
        cur.execute("""INSERT INTO procurement_lines VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (f"PL{i:05d}", so, None, mid, None,
                     int(qty) if qty else None, int(qty) if qty else None,
                     d2s(parse_date(r[col["需求日期"]])) if "需求日期" in col and len(r) > col["需求日期"] else None,
                     None,
                     d2s(parse_date(r[col["下单日期"]])) if "下单日期" in col and len(r) > col["下单日期"] else None,
                     None, None,
                     r[col["单位"]] if "单位" in col and len(r) > col["单位"] else None))
        n_pl += 1
    cur.execute("DELETE FROM materials")
    cur.executemany("INSERT INTO materials VALUES (?,?,?)",
                    [(mid, name + (f"（{spec}）" if spec else ""), "件")
                     for (name, spec), mid in mat_ids.items()])
    W.append(f"procurement_lines: {n_pl} 行真实采购（8月金汉隆采购总表220726(1).xlsx）"
             f" · materials: {len(mat_ids)}")

    # ---------- 6. 库存期初（真实 1697） ----------
    ihdr = inventory_doc["hdr"]
    icol = {n: j for j, n in enumerate(ihdr) if n}
    cur.execute("DELETE FROM warehouses")
    cur.execute("INSERT INTO warehouses VALUES ('WH01','金汉隆仓库（库存表9.18）','原材料/配件')")
    cur.execute("DELETE FROM wms_transactions")
    n_wms = 0
    for j, r in enumerate(inventory_doc["rows"], 1):
        name = to_str(r[icol["物料名称"]]) if "物料名称" in icol else ""
        if not name:
            continue
        spec = to_str(r[icol["规格/型号"]]) if "规格/型号" in icol else ""
        mid = mat_id(name, spec)
        loc = to_str(r[icol["库位"]]) if "库位" in icol else ""
        opening = to_num(r[icol["上月库存"]]) if "上月库存" in icol else None
        if opening is None:
            continue
        cur.execute("""INSERT INTO wms_transactions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (f"WTX{j:05d}", None, None, mid, None, "WH01", None,
                     "期初结转", int(opening) if opening else 0,
                     "件", None, "2026-08-31T23:59:59+08:00",
                     f"库存表9.18.xlsx|库位{loc}|序号{j}"))
        n_wms += 1
    W.append(f"wms_transactions: {n_wms} 行期初结转（库存表9.18.xlsx 上月库存列，宽表转长表）")

    # ---------- 7. 发货（真实：机器下单表 出货/交付/验收 日期） ----------
    cur.execute("DELETE FROM shipments")
    cur.execute("DELETE FROM routes")
    n_sh = 0
    for r in mo_rows:
        raw = mo_raw.get(str(r.get("item_id")), {})
        disp = parse_date(raw.get(mF.get("出货日期", "")))
        recv = parse_date(raw.get(mF.get("实际交付日期", "")))
        accept = parse_date(raw.get(mF.get("成功验收日期", "")))
        if not (disp or recv or accept):
            continue
        # 签收依据：实际交付或成功验收任一回填；仅出货未回填=已发货未回签（源表回填率低属实现状）
        done_at = recv or accept
        status = "已签收" if done_at else "已发货"
        cur.execute("""INSERT INTO shipments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (f"SH-{r['so_no']}", r["so_no"], None, None, None, None,
                     r["quantity"] or 1, r["unit"] or "台", d2s(disp), None,
                     d2s(done_at), None, status))
        n_sh += 1
    W.append(f"shipments: {n_sh} 行真实发货（机器下单表 出货日期/实际交付/成功验收）")

    # ---------- 8. 售后工单 → exceptions（真实 3176） ----------
    cur.execute("DELETE FROM exceptions")
    cur.executemany("""INSERT INTO exceptions VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    [(f"EX-{t['ticket_no']}", None, None, "售后申请", None,
                      (t.get("created_at") or "")[:10] + "T00:00:00+08:00"
                      if t.get("created_at") else None,
                      (t.get("updated_at") or "")[:10] + "T00:00:00+08:00"
                      if t.get("updated_at") else None,
                      t.get("status"), (t.get("description") or "")[:200] or None,
                      t["ticket_no"]) for t in ticket_rows])
    W.append(f"exceptions(售后): {len(ticket_rows)} 行真实售后工单")

    # ---------- 9. 无真实来源的模拟域：清空 ----------
    for t in ("labor_logs", "attendance", "mes_events", "oa_forms", "expenses",
              "logistics_events", "quality_inspections", "quality_issues",
              "source_documents", "suppliers", "equipment"):
        n = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        cur.execute(f"DELETE FROM {t}")
        W.append(f"{t}: 清空 {n} 行模拟数据（待真实来源接入）")

    # ---------- 10. 采集批次：14 个真实源文件 ----------
    cur.execute("DELETE FROM ingestion_runs")
    ing = [
        ("RING01", "合同表_20260920072414.xlsx", "2026-09-20T07:24:00+08:00",
         6881, n_contract, 0, "已完成", "全量", "BiTable导出，落入 contracts"),
        ("RING02", "机器下单表_20260920072729.xlsx", "2026-09-20T07:27:00+08:00",
         2328, len(mo_rows), 2328 - len(mo_rows), "已完成", "全量",
         "BiTable导出，落入 orders/shipments；重复无效行6条隔离"),
        ("RING03", "盒子下单表_20260920072747.xlsx", None, 0, 0, 0,
         "待文件上传", "-", "画像约数千行，文件未上传服务器"),
        ("RING04", "配件下单表_20260920072758.xlsx", None, 0, 0, 0,
         "待文件上传", "-", "画像约数千行，文件未上传服务器"),
        ("RING05", "金汉隆出仓单_20260920072740.xlsx", None, 0, 0, 0,
         "待文件上传", "-", "部分记录缺合同/项目字段，需人工匹配队列"),
        ("RING06", "生产进度表9.16.xlsx", "2026-09-16T00:00:00+08:00",
         1228, len(prod_orders), 1228 - len(prod_orders), "部分提取", "增量",
         "生产进度总表1228行中已结构化95行；电工/调试/装盒/装配排产表待接入"),
        ("RING07", "8月金汉隆采购总表220726(1).xlsx", "2026-07-26T00:00:00+08:00",
         9556, n_pl, 0, "已完成", "全量",
         "2026采购总表+售后下单采购表提取，落入 procurement_lines"),
        ("RING08", "库存表9.18.xlsx", "2026-09-18T00:00:00+08:00",
         2143, n_wms, 2143 - n_wms, "部分提取", "全量",
         "2143行中有效物料1697行转期初长表；按日宽表列待转事务流水"),
        ("RING09", "供应商列表_20260920072827.xlsx", None, 0, 0, 0,
         "待文件上传", "-", "画像约百行"),
        ("RING10", "价格表_20260920072814.xlsx", None, 0, 0, 0,
         "待文件上传", "-", "画像约数百行，成本/报价多为长文本需拆分"),
        ("RING11", "产品名称_20260919101024.xlsx", "2026-09-19T10:10:00+08:00",
         1084, 0, 0, "分析完成", "-",
         "1084条已完成六类分类映射；API导入待系统Sort1/Unitjb后执行"),
        ("RING12", "机型一级分类_20260919101004.xlsx", "2026-09-19T10:10:00+08:00",
         0, 0, 0, "分析完成", "-", "编码含末尾制表符需清洗"),
        ("RING13", "机型二级类目_20260919101013.xlsx", "2026-09-19T10:10:00+08:00",
         0, 0, 0, "分析完成", "-", "现按名称关联一级，需换稳定ID"),
        ("RING14", "一级产品属性_20260919101046.xlsx", None, 0, 0, 0,
         "待文件上传", "-", "与二级产品品类同属属性维表"),
        ("RING15", "ERP 系统", None, 0, 0, 0, "待接入", "-",
         "未连接ERP；原模拟数据已清空，禁止伪造接入成功"),
        ("RING16", "MES 系统", None, 0, 0, 0, "待接入", "-",
         "未连接MES；mes_events 已清空待接入"),
        ("RING17", "WMS 系统", None, 0, 0, 0, "待接入", "-",
         "库存期初来自库存表Excel；WMS系统未连接"),
        ("RING18", "OA 系统", None, 0, 0, 0, "待接入", "-",
         "未连接OA；oa_forms/expenses 已清空待接入"),
        ("RING19", "WeChat OCR", None, 0, 0, 0, "待OCR", "-",
         "微信图片订单OCR未完成，保持待OCR状态"),
    ]
    ing_rows = []
    for row in ing:
        rid, src, run_at, inp, loaded, quar, status, mode, note = row
        ing_rows.append((rid, src, run_at, inp, loaded, quar, status, mode,
                         run_at or "1970-01-01T00:00:00+08:00", note))
    cur.executemany("INSERT INTO ingestion_runs VALUES (?,?,?,?,?,?,?,?,?,?)", ing_rows)

    # ---------- 11. 真实画像与分类统计（附件事实） ----------
    cur.execute("DROP TABLE IF EXISTS source_file_profile")
    cur.execute("""CREATE TABLE source_file_profile (
        source_file TEXT, sheet TEXT, real_rows INTEGER, real_columns INTEGER,
        business_key TEXT, model_targets TEXT, status TEXT)""")
    profile = [
        ("库存表9.18.xlsx", "库存", 2143, 257, "库位+物料+规格", "inventory_txn", "部分提取1697"),
        ("生产进度表9.16.xlsx", "生产进度总表", 1228, 71, "生产订单+工序", "work_order;stage_nodes", "部分提取95"),
        ("生产进度表9.16.xlsx", "多列装配排产", 20, 12, "生产订单+工序", "stage_nodes", "待接入"),
        ("生产进度表9.16.xlsx", "电工排产", 1005, 12, "生产订单+工序", "stage_nodes", "待接入"),
        ("生产进度表9.16.xlsx", "调试排产", 918, 26, "生产订单+工序", "stage_nodes", "待接入"),
        ("生产进度表9.16.xlsx", "装盒部排产", 1113, 12, "生产订单+工序", "stage_nodes", "待接入"),
        ("生产进度表9.16.xlsx", "5-7月出货", 133, 71, "生产订单", "shipment", "待接入"),
        ("生产进度表9.16.xlsx", "配件单", 47, 11, "配件订单", "order_line", "待接入"),
        ("生产进度表9.16.xlsx", "机架库存数量表", 23, 7, "物料", "inventory", "待接入"),
        ("8月金汉隆采购总表220726(1).xlsx", "2026采购总表+售后下单采购表", 9556, None,
         "序号+项目+图号", "procurement_lines", "已导入9556"),
        ("8月金汉隆采购总表220726(1).xlsx", "售后下单采购表", 531, 20, "序号+项目+图号", "procurement_lines", "已含在上行"),
        ("合同表_20260920072414.xlsx", "Worksheet", 6881, None, "合同编号(非唯一)", "contracts;party;contact", "已导入6881"),
        ("机器下单表_20260920072729.xlsx", "Worksheet", 2328, None, "数据唯一编号+合同编号", "orders;shipments", "已导入2322"),
        ("盒子下单表_20260920072747.xlsx", "Worksheet", None, None, "数据唯一编号+合同编号", "order;order_line;shipment", "待上传"),
        ("配件下单表_20260920072758.xlsx", "Worksheet", None, None, "数据唯一编号+合同编号", "order;order_line;payment", "待上传"),
        ("金汉隆出仓单_20260920072740.xlsx", "Worksheet", None, None, "数据唯一编号+生产编号", "shipment;inventory_txn", "待上传"),
        ("供应商列表_20260920072827.xlsx", "Worksheet", None, None, "数据唯一编号", "supplier", "待上传"),
        ("价格表_20260920072814.xlsx", "Worksheet", None, None, "数据唯一编号", "quote;price", "待上传"),
        ("产品名称_20260919101024.xlsx", "Worksheet", 1084, None, "数据唯一编号", "product", "分类完成，待API导入"),
        ("机型一级分类_20260919101004.xlsx", "Worksheet", None, None, "数据唯一编号", "product_category", "分析完成"),
        ("机型二级类目_20260919101013.xlsx", "Worksheet", None, None, "数据唯一编号", "product_category", "分析完成"),
        ("一级产品属性_20260919101046.xlsx", "Worksheet", None, None, "数据唯一编号", "product_attribute", "待上传"),
        ("二级产品品类_20260919101051.xlsx", "Worksheet", None, None, "数据唯一编号", "product_category", "待上传"),
    ]
    cur.executemany("INSERT INTO source_file_profile VALUES (?,?,?,?,?,?,?)", profile)

    cur.execute("DROP TABLE IF EXISTS product_classification_stats")
    cur.execute("""CREATE TABLE product_classification_stats (
        category_code TEXT, category_name TEXT, product_count INTEGER, note TEXT)""")
    cur.executemany("INSERT INTO product_classification_stats VALUES (?,?,?,?)", [
        ("01", "整机与产线", 695, "《企业产品结构梳理》03产品逐行初分"),
        ("02", "配套装置与功能模块", 213, None),
        ("03", "零部件", 122, None),
        ("04", "包装材料与标识耗材", 22, None),
        ("05", "工装模具与印刷版辊", 12, None),
        ("06", "服务与费用", 4, None),
        ("99", "待确认隔离区", 41, "不建议导入正式目录"),
    ])

    # 真实数据源登记（含哈希）
    cur.execute("DROP TABLE IF EXISTS real_data_sources")
    cur.execute("""CREATE TABLE real_data_sources (
        source_file TEXT, sha256 TEXT, record_count INTEGER,
        imported_at TEXT, loaded_into TEXT)""")
    for key, path in SRC.items():
        if os.path.isfile(path):
            cnt = {"contract": len(contract_doc["rows"]), "machine": len(machine_doc["rows"]),
                   "aftersales": len(json.load(open(SRC['aftersales'], encoding='utf-8'))["rows"]),
                   "production": len(production_doc["rows"]),
                   "procurement": len(procurement_doc["rows"]),
                   "inventory": len(inventory_doc["rows"]),
                   "morders": len(mo_rows), "tickets": len(ticket_rows)}[key]
            cur.execute("INSERT INTO real_data_sources VALUES (?,?,?,?,?)",
                        (os.path.basename(path), sha256(path), cnt, IMPORTED_AT,
                         {"contract": "contracts", "machine": "orders;shipments",
                          "aftersales": "exceptions(参考)", "production": "orders;stage_nodes",
                          "procurement": "procurement_lines", "inventory": "wms_transactions",
                          "morders": "orders", "tickets": "exceptions"}[key]))

    # 字段映射（真实，来自梳理文档）
    cur.execute("DELETE FROM source_mappings")
    sm = [
        ("合同表_20260920072414.xlsx", "合同编号", "contracts", "contract_no", "混合格式不可转数字", "已完成"),
        ("合同表_20260920072414.xlsx", "公司名称/省/市/行业/客户级别", "customers", "customer_name等", "去重建客户档", "已完成"),
        ("合同表_20260920072414.xlsx", "成交日期", "contracts", "signed_at", "空值按无日期", "已完成"),
        ("合同表_20260920072414.xlsx", "合同金额/已收款/尾款/未收款", "contracts", "金额字段", "长文本拆数值", "已完成"),
        ("机器下单表_20260920072729.xlsx", "数据唯一编号+合同编号", "orders", "sales_order_id/contract_no", "业务关联键", "已完成"),
        ("机器下单表_20260920072729.xlsx", "下单时间/交货日期", "orders", "created_at/promised_delivery_at", "序列值清洗", "已完成"),
        ("机器下单表_20260920072729.xlsx", "出货日期/实际交付/成功验收", "shipments", "dispatched_at/received_at/status", "空值不发货", "已完成"),
        ("盒子下单表_20260920072747.xlsx", "全部字段", "order/order_line", "attributes", "待文件上传", "待上传"),
        ("配件下单表_20260920072758.xlsx", "付款三段", "payment_milestones", "-", "待文件上传", "待上传"),
        ("生产进度表9.16.xlsx", "生产订单", "orders/work_orders", "order_no", "同单跨表去重", "部分完成"),
        ("生产进度表9.16.xlsx", "当天状态", "stage_nodes", "stage_status", "状态→节点位相映射", "部分完成"),
        ("生产进度表9.16.xlsx", "客户交期/要求交货天数", "stage_nodes", "planned_end_at", "1900值剔除", "部分完成"),
        ("8月金汉隆采购总表220726(1).xlsx", "图号+物料名称+材料", "materials", "material_id", "物料识别候选键", "已完成"),
        ("8月金汉隆采购总表220726(1).xlsx", "数量/单位/下单日期/需求日期", "procurement_lines", "-", "空数量跳过", "已完成"),
        ("库存表9.18.xlsx", "上月库存", "wms_transactions", "期初结转", "宽表转长表", "部分完成"),
        ("库存表9.18.xlsx", "库位A1-1-1", "reference_id", "-", "业务编码保留", "部分完成"),
        ("金汉隆出仓单_20260920072740.xlsx", "合同编号+生产编号+下单时间", "shipments", "-", "缺合同号进待匹配队列", "待上传"),
        ("产品名称_20260919101024.xlsx", "数据唯一编号", "product.source_record_id", "-", "去末尾制表符", "待API导入"),
        ("价格表_20260920072814.xlsx", "成本/报价长文本", "quote", "数值/单位/附件", "三类拆分，待上传"),
        ("供应商列表_20260920072827.xlsx", "供应商名称", "suppliers", "-", "清理建别名表，待上传"),
    ]
    cur.executemany("INSERT INTO source_mappings VALUES (?,?,?,?,?,?)",
                    [(f"SM{i:02d}",) + tuple(r[:5]) for i, r in enumerate(sm, 1)])

    # 原表审计（真实结构问题，来自核对结论）
    cur.execute("DELETE FROM source_audit")
    sa = [
        ("高", "原表/合同表", "NON_UNIQUE_CONTRACT", "合同编号非唯一（如20251217出现2次）", "不可仅按合同编号JOIN，需订单号/工单号", None),
        ("高", "原表/合同表", "DUPLICATE_PARTY", "重复客户与多业务员字段并存", "导入前客户/合同去重", None),
        ("高", "原表/生产进度表", "EXCEL_DATE_SERIES", "日期序列值与00:00:00混用", "1900年日期按无日期处理", None),
        ("高", "原表/生产进度表", "CROSS_SHEET_ORDER", "同一生产订单出现在多个排产表", "以生产订单+工序为事件键，防重复工单", None),
        ("中", "原表/库存表", "WIDE_TABLE_BY_DAY", "按日分列宽表257列", "转长表inventory_txn，禁止继续扩列", None),
        ("中", "原表/出仓单", "MISSING_CONTRACT_NO", "部分记录缺项目/合同字段", "进入人工匹配队列并生成告警", None),
        ("中", "原表/价格表", "AMOUNT_AS_TEXT", "金额混长文本与截图", "拆数值、单位、附件三类字段", None),
        ("中", "原表/产品分类", "BIZ_CODE_NOT_SYSTEM_ID", "01.01等为业务编码非系统Sort1", "API导入前需换真实分类/单位ID", None),
    ]
    cur.executemany("INSERT INTO source_audit VALUES (?,?,?,?,?,?,?)",
                    [(f"SRA{i:02d}",) + tuple(r) for i, r in enumerate(sa, 1)])

    # ---------- 12. configuration ----------
    cur.execute("DELETE FROM configuration WHERE config_key='mock_seed'")
    cur.execute("UPDATE configuration SET config_value=?, description='真实批次快照（14个业务表导出时点）'"
                " WHERE config_key='snapshot_at'", (SNAPSHOT,))
    cur.execute("INSERT OR REPLACE INTO configuration VALUES ('data_mode','业务数据导入（批次20260920）','核心域已由真实提取数据替换，虚拟域已清空')")
    cur.execute("INSERT OR REPLACE INTO configuration VALUES ('source_dataset','金汉隆14个业务表导出','清单见 ingestion_runs / source_file_profile')")
    cur.execute("INSERT OR REPLACE INTO configuration VALUES ('acceptance_backfill_note','交付/验收回填率低（536/2328），已出货未回签订单在未交付口径中如实展示','源表实现状，非数据丢失')")

    con.commit()

    # 校验
    ok = cur.execute("PRAGMA integrity_check").fetchone()[0]
    checks = {
        "orders": cur.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
        "orders_real": cur.execute(
            "SELECT COUNT(*) FROM orders WHERE data_origin LIKE '真实%'").fetchone()[0],
        "contracts": cur.execute("SELECT COUNT(*) FROM contracts").fetchone()[0],
        "stage_nodes": cur.execute("SELECT COUNT(*) FROM stage_nodes").fetchone()[0],
        "customers": cur.execute("SELECT COUNT(*) FROM customers").fetchone()[0],
        "orphan_stage": cur.execute(
            "SELECT COUNT(*) FROM stage_nodes n LEFT JOIN orders o USING(sales_order_id)"
            " WHERE o.sales_order_id IS NULL").fetchone()[0],
        "orphan_proc": cur.execute(
            "SELECT COUNT(*) FROM procurement_lines p LEFT JOIN orders o"
            " ON p.sales_order_id=o.sales_order_id"
            " WHERE p.sales_order_id IS NOT NULL AND o.sales_order_id IS NULL").fetchone()[0],
    }
    con.close()

    # 同步运行时副本
    shutil.copy2(DB, RUNTIME_DB)

    print("integrity:", ok)
    print(json.dumps(checks, ensure_ascii=False, indent=1))
    print("\n".join(W))


if __name__ == "__main__":
    main()
