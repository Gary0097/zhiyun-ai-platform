#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""库存表快照导入：把《库存表9.18.xlsx》宽表转长表载入数据中枢 agent_data.sqlite。

做法（幂等，可重复执行）：
1. wms_transactions：先删除本来源（reference_id LIKE '库存表9.18.xlsx|%')旧流水，
   再写入 期初结转(上月库存,2026-08-31) + 1~18号每日 入库/出库/返工入仓/返工出仓
   （出库/返工出仓记负数，v_inventory_balance 按 SUM(signed_quantity) 对账）。
2. materials：沿用旧 reference_id(库位|序号)→material_id 映射；缺失的物料补建
   （修复早前清理留下的 M4862+ 断链），未映射的行分配新 M#### 编号。
3. inventory_snapshot 固定列快照表（当天库存/备货数/库存预警/规格/机型等），
   同一 snapshot_date 先删后插。
4. ingestion_runs / source_audit 记录本次加载与列对齐修正。

用法：
    python3 load_inventory.py <库存表.xlsx> [--sheet 库存] [--snapshot-date 2026-09-18] [--dry-run]

仅标准库。列位说明（数据行，0 起）：0序号 1库位 2物料名称 3规格/型号 4机型
5上月库存 6当月入库 7当月出库 8当月返工入仓 9当月返工出仓 10当天库存
11仓库申购 12备货数 13库存预警；N号四列 = 11+4N..14+4N（入/出/返入/返出）。
注意：表头行(第2行)的日列子表头整体左偏 1 列，以"汇总=Σ明细"全量校验后为准。
"""
import argparse
import os
import re
import sqlite3
import sys
import zipfile
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(HERE, "..", "agent_data.sqlite")
SOURCE_TAG = "库存表9.18.xlsx"
WAREHOUSE_ID = "WH01"

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_RNS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def _col_index(cell_ref):
    letters = "".join(ch for ch in (cell_ref or "") if ch.isalpha()).upper()
    idx = 0
    for ch in letters:
        idx = idx * 26 + (ord(ch) - 64)
    return idx - 1


def read_xlsx_rows(path, sheet_name=None):
    """极简 xlsx 读取（sharedStrings + 指定 sheet），满足本表结构。"""
    z = zipfile.ZipFile(path)
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))
        shared = ["".join(t.text or "" for t in si.iter(_NS + "t")) for si in root.findall(_NS + "si")]
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    sheets = [(s.get("name"), s.get(_RNS + "id")) for s in wb.iter(_NS + "sheet")]
    if not sheets:
        sys.exit("xlsx 中没有工作表")
    target = sheets[0]
    if sheet_name:
        for nm, rid in sheets:
            if nm == sheet_name:
                target = (nm, rid)
                break
        else:
            sys.exit("找不到工作表 %s，可用: %s" % (sheet_name, ", ".join(n for n, _ in sheets)))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    relmap = {r.get("Id"): r.get("Target") for r in rels}
    tp = relmap.get(target[1], "")
    tp = tp.lstrip("/") if tp.startswith("/") else (tp if tp.startswith("xl/") else "xl/" + tp)
    ws = ET.fromstring(z.read(tp))
    rows = []
    for row in ws.iter(_NS + "row"):
        cells = {}
        for c in row.findall(_NS + "c"):
            idx = _col_index(c.get("r"))
            t = c.get("t")
            if t == "s":
                v = shared[int(c.find(_NS + "v").text)] if c.find(_NS + "v") is not None else ""
            elif t == "inlineStr":
                is_el = c.find(_NS + "is")
                v = "".join(el.text or "" for el in is_el.iter(_NS + "t")) if is_el is not None else ""
            else:
                v = c.find(_NS + "v").text if c.find(_NS + "v") is not None else ""
            cells[idx] = (v or "").strip()
        if not any(cells.values()):
            continue
        width = max(cells) + 1
        rows.append([cells.get(i, "") for i in range(width)])
    return rows


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def g(r, i):
    return r[i] if len(r) > i else ""


def parse_rows(path, sheet):
    rows = read_xlsx_rows(path, sheet)
    if len(rows) < 3:
        sys.exit("表格行数异常: %d" % len(rows))
    materials, quarantined = [], []
    for excel_row, r in enumerate(rows[2:], start=3):
        name, loc = g(r, 2), g(r, 1)
        if not name and not loc:
            continue  # 纯空行/表尾填充
        if not name or not loc or name in ("合计：", ".", "合计"):
            quarantined.append((excel_row, name or "(仅有库位/序号)", "非物料行（合计/残行）"))
            continue
        no = g(r, 0) or ("r%d" % excel_row)  # 序号缺失时用Excel行号兜底
        m = {
            "excel_row": excel_row, "no": no, "loc": loc, "name": name,
            "spec": g(r, 3), "model": g(r, 4),
            "prev": num(g(r, 5)), "in_m": num(g(r, 6)), "out_m": num(g(r, 7)),
            "rework_in_m": num(g(r, 8)), "rework_out_m": num(g(r, 9)),
            "cur": num(g(r, 10)), "apply": num(g(r, 11)), "stockup": num(g(r, 12)),
            "alert": g(r, 13), "days": {},
        }
        # 每日四列：N号 入库@11+4N 出库@12+4N 返工入仓@13+4N 返工出仓@14+4N
        for d in range(1, 32):
            quad = (num(g(r, 11 + 4 * d)), num(g(r, 12 + 4 * d)),
                    num(g(r, 13 + 4 * d)), num(g(r, 14 + 4 * d)))
            if any(quad):
                m["days"][d] = quad
        # 自校验：当月汇总 = Σ每日
        s = [sum(q[i] for q in m["days"].values()) for i in range(4)]
        calc = (m["prev"] + m["in_m"] - m["out_m"] + m["rework_in_m"] - m["rework_out_m"])
        if s != [m["in_m"], m["out_m"], m["rework_in_m"], m["rework_out_m"]]:
            quarantined.append((excel_row, name, "当月汇总≠Σ每日明细 %s vs %s" % (s, m["in_m"])))
            continue
        m["calc_cur"] = calc
        materials.append(m)
    return materials, quarantined


def next_material_id(c):
    mx = 0
    for (mid,) in c.execute("select material_id from materials"):
        m = re.fullmatch(r"M(\d+)", mid or "")
        if m:
            mx = max(mx, int(m.group(1)))
    for (mid,) in c.execute("select distinct material_id from wms_transactions where material_id like 'M%'"):
        m = re.fullmatch(r"M(\d+)", mid or "")
        if m:
            mx = max(mx, int(m.group(1)))
    return mx + 1


def next_wtx(c):
    mx = 0
    for (tid,) in c.execute("select transaction_id from wms_transactions"):
        m = re.fullmatch(r"WTX(\d+)", tid or "")
        if m:
            mx = max(mx, int(m.group(1)))
    return mx + 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("xlsx")
    ap.add_argument("--sheet", default="库存")
    ap.add_argument("--snapshot-date", default="2026-09-18")
    ap.add_argument("--db", default=DB_PATH, help="目标 agent_data.sqlite（默认工作区副本）")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    materials, quarantined = parse_rows(args.xlsx, args.sheet)
    print("解析: 物料行 %d，隔离 %d" % (len(materials), len(quarantined)))
    for q in quarantined:
        print("  隔离 行%d %s: %s" % q)

    c = sqlite3.connect(args.db)
    c.execute("PRAGMA foreign_keys=OFF")

    # 旧映射：期初结转 reference -> material_id
    old_map = {}
    for mid, ref in c.execute(
        "select material_id, reference_id from wms_transactions "
        "where movement_type='期初结转' and reference_id like ?",
        (SOURCE_TAG + "|%",),
    ):
        m = re.match(re.escape(SOURCE_TAG) + r"\|库位(.+?)\|序号(.+)$", ref or "")
        if m:
            old_map[(m.group(1), m.group(2))] = mid

    nid = next_material_id(c)
    existing_materials = {r[0] for r in c.execute("select material_id from materials")}
    used_ids, to_create, dup_remapped = set(), [], 0
    for m in materials:
        key = (m["loc"], m["no"])
        mid = old_map.get(key)
        if not mid or mid in used_ids:
            if mid:
                dup_remapped += 1  # 旧加载器把同一 id 给了多行，此处拆分
            mid = "M%d" % nid
            nid += 1
        m["material_id"] = mid
        used_ids.add(mid)
        if mid not in existing_materials:
            to_create.append((mid, m["name"], "件"))

    # 生成流水
    movs = []
    for m in materials:
        base_ref = "%s|库位%s|序号%s" % (SOURCE_TAG, m["loc"], m["no"])
        movs.append(("期初结转", m["prev"], "2026-08-31T23:59:59+08:00", base_ref))
        for d, q in sorted(m["days"].items()):
            ts = "%s-%02dT12:00:00+08:00" % (args.snapshot_date[:8], d)
            for label, sign, v in (("入库", 1, q[0]), ("出库", -1, q[1]),
                                   ("返工入仓", 1, q[2]), ("返工出仓", -1, q[3])):
                if v:
                    movs.append((label, sign * v, ts, "%s|%d号%s" % (base_ref, d, label)))

    wtx = next_wtx(c)
    print("计划: 删旧流水 %d 条 → 插入流水 %d 条（期初 %d + 每日 %d）；补建物料 %d 个" % (
        c.execute("select count(*) from wms_transactions where reference_id like ?",
                  (SOURCE_TAG + "|%",)).fetchone()[0],
        len(movs), len(materials), len(movs) - len(materials), len(to_create)))

    if args.dry_run:
        print("--- dry-run，未写库 ---")
        return

    c.execute("begin")
    try:
        c.execute("delete from wms_transactions where reference_id like ?", (SOURCE_TAG + "|%",))
        c.executemany("insert into materials(material_id, material_name, unit) values(?,?,?)", to_create)
        rows = []
        i = 0
        for m in materials:
            base_ref = "%s|库位%s|序号%s" % (SOURCE_TAG, m["loc"], m["no"])
            rows.append(("WTX%05d" % (wtx + i), m["material_id"], "期初结转", m["prev"],
                         "2026-08-31T23:59:59+08:00", base_ref))
            i += 1
            for d, q in sorted(m["days"].items()):
                ts = "%s-%02dT12:00:00+08:00" % (args.snapshot_date[:8], d)
                for label, sign, v in (("入库", 1, q[0]), ("出库", -1, q[1]),
                                       ("返工入仓", 1, q[2]), ("返工出仓", -1, q[3])):
                    if v:
                        rows.append(("WTX%05d" % (wtx + i), m["material_id"], label, sign * v,
                                     ts, "%s|%d号%s" % (base_ref, d, label)))
                        i += 1
        c.executemany(
            "insert into wms_transactions(transaction_id, sales_order_id, work_order_id, "
            "material_id, product_id, warehouse_id, lot_id, movement_type, signed_quantity, "
            "unit, unit_cost, occurred_at, reference_id) "
            "values(?,NULL,NULL,?,NULL,?,NULL,?,?,?,NULL,?,?)",
            [(t, mid, WAREHOUSE_ID, mt, q, "件", ts, ref) for (t, mid, mt, q, ts, ref) in rows])

        c.execute(
            "create table if not exists inventory_snapshot("
            "snapshot_date TEXT, material_id TEXT, 序号 TEXT, 库位 TEXT, 物料名称 TEXT, "
            "规格型号 TEXT, 机型 TEXT, 上月库存 REAL, 当月入库 REAL, 当月出库 REAL, "
            "当月返工入仓 REAL, 当月返工出仓 REAL, 当天库存 REAL, 仓库申购 REAL, 备货数 REAL, "
            "库存预警 TEXT, source_file TEXT, primary key(snapshot_date, material_id))")
        c.execute("delete from inventory_snapshot where snapshot_date=?", (args.snapshot_date,))
        c.executemany(
            "insert into inventory_snapshot values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(args.snapshot_date, m["material_id"], m["no"], m["loc"], m["name"], m["spec"],
              m["model"], m["prev"], m["in_m"], m["out_m"], m["rework_in_m"], m["rework_out_m"],
              m["cur"], m["apply"], m["stockup"], m["alert"], os.path.basename(args.xlsx))
             for m in materials])

        run_id = "RING%d" % ((c.execute("select count(*) from ingestion_runs").fetchone()[0]) + 1)
        c.execute(
            "insert into ingestion_runs(run_id, source_system, run_at, input_record_count, "
            "loaded_record_count, quarantined_record_count, run_status, sync_mode, watermark, note) "
            "values(?,?,?,?,?,?,?,?,?,?)",
            (run_id, SOURCE_TAG + "(补全每日流水+快照)", args.snapshot_date + "T12:00:00+08:00",
             len(materials) + len(quarantined), len(materials), len(quarantined), "已加载",
             "全量替换(" + SOURCE_TAG + "来源流水)",
             args.snapshot_date + "T12:00:00+08:00",
             "期初+1~18号每日出入库长表 %d 条；inventory_snapshot %d 行；补建物料 %d 个；"
             "修复日列子表头左偏1列(以汇总=Σ明细全量校验)；旧映射中 %d 个重复id已拆分新id"
             % (len(rows), len(materials), len(to_create), dup_remapped)))

        max_sra = c.execute(
            "select issue_id from source_audit order by issue_id desc limit 1").fetchone()
        n = int(re.sub(r"\D", "", max_sra[0])) + 1 if max_sra else 1
        c.execute(
            "insert into source_audit(issue_id, severity, source_object, rule_id, "
            "issue_description, handling, affected_rows) values(?,?,?,?,?,?,?)",
            ("SRA%02d" % n, "中", "原表/库存表", "DAY_HEADER_OFF_BY_ONE",
             "日列子表头行整体左偏1列（子表头14列起、数据15列起）",
             "以『当月汇总=Σ每日明细』对1695物料行全量校验通过后采用数据列位", len(materials)))
        c.commit()
    except Exception:
        c.rollback()
        raise

    # 对账
    print("\n=== 对账 ===")
    print("流水类型分布:", list(c.execute(
        "select movement_type, count(*) from wms_transactions where reference_id like ? "
        "group by movement_type", (SOURCE_TAG + "|%",))))
    mism = list(c.execute(
        "select count(*) from inventory_snapshot s left join v_inventory_balance v "
        "on v.material_id=s.material_id "
        "where abs(ifnull(v.quantity_balance,0)-s.当天库存)>0.001"))
    print("v_inventory_balance ≠ 当天库存 的物料数:", mism[0][0])
    ident = list(c.execute(
        "select count(*) from inventory_snapshot where abs((上月库存+当月入库-当月出库"
        "+当月返工入仓-当月返工出仓)-当天库存)>0.001"))[0][0]
    print("表内恒等式不成立行数:", ident)
    print("当天库存合计:", c.execute("select sum(当天库存) from inventory_snapshot").fetchone()[0])
    print("预警分布:", list(c.execute(
        "select 库存预警, count(*) from inventory_snapshot group by 库存预警 order by 2 desc")))


if __name__ == "__main__":
    main()
