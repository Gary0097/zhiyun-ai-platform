#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""人力资源入离职模拟数据生成（演示用，批次 20260920）。

为《金汉隆-数据中枢》补充人力资源分析域的两张模拟表：
- hiring_records  入职记录（46 条，E052-E097，2025-01 ~ 2026-09）
- turnover_records 离职记录（24 条，全部来自上述新入职人员，自洽）

规则：
- 与 employees 花名册不冲突：离职人员均在 E052+ 新入职段，现有 E001-E051 不动；
- 试用期口径一致：probation_result=试用期离职 ⇔ turnover 中 leave_date ≤ 试用期届满；
- 2026-08/09 入职且试用期未满者 probation_result=试用中（不在离职表）；
- tenure_months = 入职到离职的整月数；辞退(违反制度)交接=否。
固定随机种子，可重复。同步写入两份 agent_data.sqlite 并导出知识库 xlsx。

运行：/root/zy-xlsx-venv/bin/python gen_hr_turnover.py  （需 openpyxl 导出）
"""
import csv
import datetime as dt
import os
import random
import sqlite3

SEED = 20260920
SNAP = dt.date(2026, 9, 18)
DBS = [
    "/root/zhiyun-ai-platform/apps/zhizaoyunAIOS/workspace/hub/runtimes/"
    "personal-49e1b686b8034127aaeb292f/working/workspaces/datahub-agent/datahub/agent_data.sqlite",
    "/data/actions/zhizaoyun-datahub/agent_data.sqlite",
]
UPLOAD_TABLES = "/data/actions/weknora/mcp-server/datahub_uploads/tables"
DOCS = [
    "/data/actions/weknora/mcp-server/datahub_uploads/docs",
    "/root/zhiyun-ai-platform/apps/zhizaoyunAIOS/workspace/hub/runtimes/"
    "personal-49e1b686b8034127aaeb292f/working/workspaces/datahub-agent/datahub/docs",
]

DEPT_POS = {
    "D02": ("加工部", ["数控操作员", "普工", "机加工技工"], 14),
    "D03": ("装配部", ["装配技工", "电工", "调试员"], 12),
    "D06": ("销售部", ["销售代表", "销售内勤"], 6),
    "D05": ("仓储物流部", ["仓管员", "叉车工"], 5),
    "D04": ("质量部", ["质检员", "QC工程师"], 4),
    "D01": ("计划采购部", ["采购员", "计划员"], 3),
    "D07": ("财务行政部", ["会计", "行政专员"], 2),
}
HIRES_PER_MONTH = {  # 2025-01..2026-09
    "2025": [3, 4, 3, 2, 2, 2, 2, 2, 3, 2, 2, 1],
    "2026": [2, 1, 2, 2, 1, 2, 2, 2, 4],
}
LEAVES_PER_MONTH = {
    "2025": [1, 2, 3, 2, 1, 1, 2, 1, 1, 1, 0, 1],
    "2026": [2, 1, 0, 1, 1, 0, 1, 1, 1],
}
CHANNELS = ["内部推荐", "BOSS直聘", "人才市场", "劳务中介", "校园招聘", "58同城"]
EDU = ["初中", "高中", "中专", "大专", "本科"]
SURNAMES = "张王李赵刘陈杨黄周吴徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓曹彭曾"
GIVEN = ["伟", "芳", "娜", "敏", "静", "磊", "军", "洋", "勇", "艳", "杰", "涛", "明", "超", "霞", "平", "刚", "桂英", "秀兰", "建国", "志强", "丽华", "文博", "天宇", "欣怡", "浩然", "思远", "晓东", "红梅", "春燕"]
LEAVE_TYPES = [("主动辞职", 0.66), ("公司辞退", 0.18), ("合同到期不续签", 0.16)]
REASONS_BY_TYPE = {
    "主动辞职": ["薪酬待遇", "职业发展", "家庭原因", "返乡就业", "身体原因", "个人创业"],
    "公司辞退": ["试用期不合格", "违反公司制度", "岗位调整不达标"],
    "合同到期不续签": ["双方协商", "公司经营调整"],
}
POS_SALARY = {
    "普工": (4500, 5500), "数控操作员": (5500, 6500), "机加工技工": (6000, 7500),
    "装配技工": (5500, 7000), "电工": (6000, 7500), "调试员": (6500, 8000),
    "销售代表": (5000, 6000), "销售内勤": (4800, 5800), "仓管员": (4500, 5500),
    "叉车工": (5000, 6000), "质检员": (4800, 5800), "QC工程师": (6500, 8000),
    "采购员": (5500, 7000), "计划员": (5500, 7000), "会计": (6000, 7500), "行政专员": (4800, 5800),
}


def month_key(y, m):
    return f"{y}{m:02d}"


def gen(rng):
    # 1) 入职：按月生成，编号 E052+
    dept_pool = []
    for did, (dname, positions, n) in DEPT_POS.items():
        dept_pool += [(did, dname, positions)] * n
    rng.shuffle(dept_pool)

    hires = []
    next_id = 52
    for y in (2025, 2026):
        months = range(1, 13) if y == 2025 else range(1, 10)
        for m in months:
            for _ in range(HIRES_PER_MONTH[str(y)][m - 1]):
                did, dname, positions = dept_pool.pop()
                pos = rng.choice(positions)
                last_day = min(dt.date(y, m, 25), dt.date(2026, 9, 15))  # 不晚于快照前
                day = rng.choice([d for d in range(2, last_day.day + 1)
                                  if dt.date(y, m, d).weekday() < 5])
                hire = dt.date(y, m, day)
                lo, hi = POS_SALARY[pos]
                prob_sal = int(rng.randrange(lo, hi + 1, 100))
                formal_sal = prob_sal + rng.choice([300, 400, 500, 600, 800])
                probation_months = 3 if pos in ("QC工程师", "调试员", "会计") else rng.choice([1, 2, 3])
                hires.append({
                    "employee_id": "E%03d" % next_id, "employee_name": rng.choice(SURNAMES) + rng.choice(GIVEN),
                    "department_id": did, "department_name": dname, "position": pos,
                    "hire_date": hire.isoformat(), "probation_salary": prob_sal,
                    "formal_salary": formal_sal, "recruit_channel": rng.choice(CHANNELS),
                    "education": rng.choice(EDU), "probation_months": probation_months,
                    "probation_end": hire + dt.timedelta(days=int(probation_months * 30.5)),
                })
                next_id += 1

    # 2) 离职：按月挑人（优先近半年入职者），全部来自 hires
    by_id = {h["employee_id"]: h for h in hires}
    left = set()
    leaves = []
    for y in (2025, 2026):
        months = range(1, 13) if y == 2025 else range(1, 10)
        for m in months:
            for _ in range(LEAVES_PER_MONTH[str(y)][m - 1]):
                cands = [h for h in hires
                         if h["employee_id"] not in left
                         and h["hire_date"] < f"{y}-{m:02d}-15"
                         and h["hire_date"] < SNAP.isoformat()]
                if not cands:
                    cands = [h for h in hires if h["employee_id"] not in left]
                # 试用期离职倾向挑最近入职的，转正后离职挑资历稍长的
                early = f"{y}-{m:02d}-01"
                h = None
                if rng.random() < 0.35:
                    fresh = [c for c in cands if
                             (dt.date(y, m, 15) - dt.date.fromisoformat(c["hire_date"])).days
                             < c["probation_months"] * 31]
                    if fresh:
                        h = rng.choice(sorted(fresh, key=lambda x: x["hire_date"])[-4:])
                if h is None:
                    h = rng.choice(cands)
                left.add(h["employee_id"])
                day = rng.choice([d for d in range(2, 27)
                                  if dt.date(y, m, d).weekday() < 5
                                  and dt.date(y, m, d) > dt.date.fromisoformat(h["hire_date"])])
                leave = dt.date(y, m, day)
                in_probation = leave <= h["probation_end"]
                r = rng.random()
                acc = 0.0
                ltype = LEAVE_TYPES[0][0]
                for t, p in LEAVE_TYPES:
                    acc += p
                    if r <= acc:
                        ltype = t
                        break
                if in_probation and ltype == "合同到期不续签":
                    ltype = "公司辞退"  # 试用期内不适用到期口径
                reason = rng.choice(REASONS_BY_TYPE[ltype])
                if in_probation and reason not in ("试用期不合格", "违反公司制度", "薪酬待遇", "家庭原因"):
                    reason = "试用期不合格" if ltype == "公司辞退" else "薪酬待遇"
                tenure = (leave.year - dt.date.fromisoformat(h["hire_date"]).year) * 12 + \
                         (leave.month - dt.date.fromisoformat(h["hire_date"]).month)
                if tenure < 1 and (leave - dt.date.fromisoformat(h["hire_date"])).days >= 30:
                    tenure = 1
                leaves.append({
                    "employee_id": h["employee_id"], "employee_name": h["employee_name"],
                    "department_id": h["department_id"], "department_name": h["department_name"],
                    "position": h["position"], "hire_date": h["hire_date"],
                    "leave_date": leave.isoformat(), "tenure_months": max(tenure, 0),
                    "leave_type": ltype, "leave_reason": reason,
                    "handover_done": "否" if reason == "违反公司制度" else "是",
                })

    # 3) 回填试用期结果（口径一致）
    leave_by_id = {}
    for lv in leaves:
        h = by_id[lv["employee_id"]]
        if dt.date.fromisoformat(lv["leave_date"]) <= h["probation_end"]:
            leave_by_id[lv["employee_id"]] = lv
    for h in hires:
        if h["employee_id"] in leave_by_id:
            h["probation_result"] = "试用期离职"
        elif h["probation_end"] >= SNAP:
            h["probation_result"] = "试用中"
        else:
            h["probation_result"] = "转正"
        h["probation_end_date"] = h["probation_end"].isoformat()
    for h in hires:
        h.pop("probation_months")
        h.pop("probation_end")
    return hires, leaves


HIRE_COLS = ["employee_id", "employee_name", "department_id", "department_name", "position",
             "hire_date", "probation_salary", "formal_salary", "recruit_channel",
             "education", "probation_result", "probation_end_date"]
LEAVE_COLS = ["employee_id", "employee_name", "department_id", "department_name", "position",
              "hire_date", "leave_date", "tenure_months", "leave_type", "leave_reason",
              "handover_done"]


def write_db(path, hires, leaves):
    c = sqlite3.connect(path)
    c.execute("""CREATE TABLE IF NOT EXISTS hiring_records(
        employee_id TEXT, employee_name TEXT, department_id TEXT, department_name TEXT,
        position TEXT, hire_date TEXT, probation_salary REAL, formal_salary REAL,
        recruit_channel TEXT, education TEXT, probation_result TEXT, probation_end_date TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS turnover_records(
        employee_id TEXT, employee_name TEXT, department_id TEXT, department_name TEXT,
        position TEXT, hire_date TEXT, leave_date TEXT, tenure_months INTEGER,
        leave_type TEXT, leave_reason TEXT, handover_done TEXT)""")
    c.execute("DELETE FROM hiring_records")
    c.execute("DELETE FROM turnover_records")
    c.executemany("INSERT INTO hiring_records VALUES(%s)" % ",".join("?" * len(HIRE_COLS)),
                  [tuple(h[k] for k in HIRE_COLS) for h in hires])
    c.executemany("INSERT INTO turnover_records VALUES(%s)" % ",".join("?" * len(LEAVE_COLS)),
                  [tuple(l[k] for k in LEAVE_COLS) for l in leaves])
    n = c.execute("SELECT COUNT(*) FROM ingestion_runs").fetchone()[0]
    c.execute("INSERT INTO ingestion_runs(run_id, source_system, run_at, input_record_count, "
              "loaded_record_count, quarantined_record_count, run_status, sync_mode, watermark, note) "
              "VALUES(?,?,?,?,?,?,?,?,?,?)",
              ("RING%d" % (n + 1), "人力资源-入离职(模拟演示)", "2026-09-18T08:00:00+08:00",
               len(hires) + len(leaves), len(hires) + len(leaves), 0, "已加载", "全量写入",
               "2026-09-18T08:00:00+08:00",
               "模拟演示数据：hiring_records %d 条 / turnover_records %d 条；"
               "统计窗口 2025-01~2026-09-15；离职人员均在 E052+ 新入职段，不影响现有花名册"
               % (len(hires), len(leaves))))
    c.commit()
    return c


def export_xlsx(hires, leaves):
    from openpyxl import Workbook
    for name, cols, rows in (
            ("31_入职记录_hiring_records", HIRE_COLS, hires),
            ("32_离职记录_turnover_records", LEAVE_COLS, leaves)):
        wb = Workbook()
        ws = wb.active
        ws.title = name.split("_", 1)[1].split("_")[0]
        ws.append(cols)
        for r in rows:
            ws.append([r[k] for k in cols])
        p = os.path.join(UPLOAD_TABLES, name + ".xlsx")
        wb.save(p)
        print("exported", p)


def update_docs(hires, leaves):
    fields = {
        "hiring_records": ("31入职记录", [
            ("employee_id", "员工ID", "TEXT", "E052-E097 新入职段"),
            ("employee_name", "姓名", "TEXT", ""),
            ("department_id", "部门ID", "TEXT", "departments.department_id"),
            ("department_name", "部门名称", "TEXT", ""),
            ("position", "岗位", "TEXT", ""),
            ("hire_date", "入职日期", "TEXT", "YYYY-MM-DD；模拟窗口 2025-01~2026-09"),
            ("probation_salary", "试用期月薪", "REAL", "元/月"),
            ("formal_salary", "转正月薪", "REAL", "元/月"),
            ("recruit_channel", "招聘渠道", "TEXT", "内部推荐/BOSS直聘/人才市场/劳务中介/校园招聘/58同城"),
            ("education", "学历", "TEXT", ""),
            ("probation_result", "试用期结果", "TEXT", "转正/试用期离职/试用中"),
            ("probation_end_date", "试用期届满日", "TEXT", ""),
        ]),
        "turnover_records": ("32离职记录", [
            ("employee_id", "员工ID", "TEXT", "对应 hiring_records"),
            ("employee_name", "姓名", "TEXT", ""),
            ("department_id", "部门ID", "TEXT", ""),
            ("department_name", "部门名称", "TEXT", ""),
            ("position", "岗位", "TEXT", ""),
            ("hire_date", "入职日期", "TEXT", ""),
            ("leave_date", "离职日期", "TEXT", "YYYY-MM-DD"),
            ("tenure_months", "司龄月数", "INTEGER", "整月数"),
            ("leave_type", "离职类型", "TEXT", "主动辞职/公司辞退/合同到期不续签"),
            ("leave_reason", "离职原因", "TEXT", ""),
            ("handover_done", "是否完成交接", "TEXT", "是/否"),
        ]),
    }
    glossary = """

## 人力资源入离职口径（表 hiring_records / turnover_records，模拟演示数据）

- **入职**：hiring_records 一行一人，窗口 2025-01 ~ 2026-09；试用期 1~3 个月（技术岗 3 个月）。
- **试用期结果**：转正 / 试用期离职（离职日期 ≤ 试用期届满日，与 turnover_records 一一对应）/ 试用中（届满日晚于快照 2026-09-18）。
- **离职**：turnover_records 一行一人；**司龄 = 整月数**（不足整月按 0 计，≥30 天按 1）；类型分主动辞职 / 公司辞退 / 合同到期不续签。
- **期间离职率 = 期间离职人数 ÷ 期间平均在职人数**（期初与期末花名册的算术平均）；月度离职率 = 当月离职 ÷ 当月平均在职。
- **新进率 = 期间入职 ÷ 期初在职**；净增员 = 入职 − 离职。
- 入离职均为**模拟演示数据**（批次 20260920），离职人员全部位于 E052+ 新入职段，不影响 employees 现有花名册（E001-E051）。
"""
    for docs in DOCS:
        dict_path = os.path.join(docs, "字段字典.csv")
        with open(dict_path, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
        rows = [r for r in rows if r and r[0] not in fields]
        for table, (sheet, cols) in fields.items():
            for col, cn, t, note in cols:
                rows.append([table, sheet, "clean", col, cn, t, 0, "", 1, note or cn])
        with open(dict_path, "w", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerows(rows)
        gpath = os.path.join(docs, "业务口径要点.md")
        text = open(gpath, encoding="utf-8").read()
        marker = "## 人力资源入离职口径"
        if marker in text:
            text = text.split(marker)[0].rstrip() + "\n" + glossary
        else:
            text = text.rstrip() + "\n" + glossary
        open(gpath, "w", encoding="utf-8").write(text)
        print("docs updated:", docs)


def main():
    rng = random.Random(SEED)
    hires, leaves = gen(rng)
    active = [h for h in hires if h["employee_id"] not in {l["employee_id"] for l in leaves}]
    print(f"入职 {len(hires)} | 离职 {len(leaves)} | 新入职仍在岗 {len(active)}"
          f"（试用中 {sum(1 for h in active if h['probation_result']=='试用中')}，"
          f"已转正 {sum(1 for h in active if h['probation_result']=='转正')}）")
    from collections import Counter
    print("离职类型:", dict(Counter(l["leave_type"] for l in leaves)))
    print("部门入职分布:", dict(Counter(h["department_name"] for h in hires)))
    bad = [l for l in leaves if l["leave_date"] <= l["hire_date"]]
    assert not bad, bad
    for db in DBS:
        c = write_db(db, hires, leaves)
        n1 = c.execute("SELECT COUNT(*) FROM hiring_records").fetchone()[0]
        n2 = c.execute("SELECT COUNT(*) FROM turnover_records").fetchone()[0]
        print("db ok:", db.split("/")[-3], n1, n2)
    export_xlsx(hires, leaves)
    update_docs(hires, leaves)


if __name__ == "__main__":
    main()
