#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""智邦国际ERP（金汉隆）开放平台 OpenApi CLI。

用法:
    python3 erp.py login
    python3 erp.py list-customers --name 关键词 [--page 1] [--rows 20] [--json]
    python3 erp.py customer-detail --ord 190 [--json]
    python3 erp.py add-customer --name 公司名 --person 联系人 --mobile 138... \
        --address 地址 [--intro 备注] [--sort "终端客户,潜在客户"] [--cate 销售人员] [--json]
    python3 erp.py import-customers 客户.xlsx|客户.csv [--sheet 表名] [--dry-run] [--sort "终端客户,潜在客户"]
    python3 erp.py call /webapi/v3/... '{"任意": "字段"}'

配置: 同目录 config.json（base_url/username/password/endpoints），可用环境变量
      ZBERP_BASE_URL / ZBERP_USERNAME / ZBERP_PASSWORD 覆盖（便于测试）。

仅依赖 Python 标准库（沙箱内系统 python3 可直接运行）。
Excel(.xlsx) 用 zipfile+ElementTree 解析；CSV 支持 UTF-8(含BOM)/GBK。
"""

import argparse
import csv
import json
import os
import random
import sys
import urllib.error
import urllib.request
import zipfile
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")

DEFAULT_ENDPOINTS = {
    "login": "/webapi/v3/ov1/login",
    "list": "/webapi/v3/sales/customer/list",
    "detail": "/webapi/v3/sales/customer/detail",
    "add": "/webapi/v3/sales/customer/add",
}

# 导入文件表头别名（顺序无关；缺联系人自动填“待补充”）
COLUMN_ALIASES = {
    "name": ["客户名称", "公司名称", "名称", "客户"],
    "person": ["联系人", "联系人姓名", "联系人员"],
    "mobile": ["手机", "手机号", "手机号码", "联系电话", "电话", "联系方式", "mobile"],
    "address": ["地址", "详细地址", "联系地址"],
    "intro": ["备注", "备注说明", "说明"],
}


def load_config():
    cfg = {}
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
    except FileNotFoundError:
        pass
    cfg["base_url"] = os.environ.get("ZBERP_BASE_URL", cfg.get("base_url", "")).rstrip("/")
    cfg["username"] = os.environ.get("ZBERP_USERNAME", cfg.get("username", ""))
    cfg["password"] = os.environ.get("ZBERP_PASSWORD", cfg.get("password", ""))
    cfg["timeout"] = float(cfg.get("timeout", 15))
    eps = dict(DEFAULT_ENDPOINTS)
    eps.update(cfg.get("endpoints") or {})
    cfg["endpoints"] = eps
    if not cfg["base_url"]:
        die("缺少 base_url：请在 %s 配置或设置 ZBERP_BASE_URL" % CONFIG_PATH)
    return cfg


def die(msg, code=1):
    print("错误: %s" % msg, file=sys.stderr)
    sys.exit(code)


def post(cfg, path, payload, timeout=None):
    url = cfg["base_url"] + path
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout or cfg["timeout"]) as resp:
            body = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        print("HTTP %s %s" % (e.code, path), file=sys.stderr)
        print(body[:2000], file=sys.stderr)
        sys.exit(2)
    except urllib.error.URLError as e:
        die(
            "无法连接 ERP（%s）：%s\n请确认服务器与内网 %s 的网络连通性。"
            % (url, e.reason, cfg["base_url"]),
            3,
        )
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        print(body[:4000])
        die("ERP 返回了非 JSON 内容（可能是登录页/验证码），路径: %s" % path, 4)


def extract_token(resp):
    for keys in (
        ("token",),
        ("data", "token"),
        ("session",),
        ("data", "session"),
        ("sessionid",),
        ("data", "sessionid"),
    ):
        node = resp
        ok = True
        for k in keys:
            if isinstance(node, dict) and k in node:
                node = node[k]
            else:
                ok = False
                break
        if ok and isinstance(node, str) and node:
            return node
    return None


def login(cfg):
    resp = post(
        cfg,
        cfg["endpoints"]["login"],
        {
            # 智邦 ov1 登录要求用户名/密码加 txt: 前缀（明文），serialnum 随机
            "username": "txt:" + cfg["username"],
            "password": "txt:" + cfg["password"],
            "serialnum": "%016d" % random.randint(0, 10**16 - 1),
        },
    )
    token = extract_token(resp)
    if not token:
        print(json.dumps(resp, ensure_ascii=False)[:2000])
        die("登录失败：响应中未找到 token 字段", 5)
    return token


def must_login(cfg):
    return login(cfg)


# ---------------------------------------------------------------- 显示工具


def pick(obj, *names, default=""):
    for n in names:
        if isinstance(obj, dict) and obj.get(n) not in (None, ""):
            return obj.get(n)
    return default


def print_table(rows, columns):
    """columns: [(标题, 取值函数)]"""
    if not rows:
        print("（无数据）")
        return
    data = [[str(c[1](r) or "") for c in columns] for r in rows]
    widths = [len(c[0]) for c in columns]
    for line in data:
        for i, cell in enumerate(line):
            widths[i] = min(max(widths[i], len(cell)), 40)
    header = " | ".join(c[0].ljust(widths[i]) for i, c in enumerate(columns))
    print(header)
    print("-+-".join("-" * w for w in widths))
    for line in data:
        print(" | ".join(line[i][: widths[i]] for i in range(len(line))))


def customer_row(c):
    return {
        "ord": pick(c, "ord", "id", "value", "customer_id"),
        "name": pick(c, "name", "customer_name", "公司名称"),
        "person": pick(c, "person_name", "person", "联系人"),
        "mobile": pick(c, "mobile", "tel", "phone", "手机号码", "联系电话"),
        "address": pick(c, "address", "详细地址"),
    }


def find_customer_rows(resp):
    """在响应里防御性地定位客户列表。"""
    candidates = []
    if isinstance(resp, dict):
        for k in ("rows", "list", "items", "data", "datas", "record"):
            v = resp.get(k)
            if isinstance(v, list):
                candidates.append(v)
            elif isinstance(v, dict):
                for kk in ("rows", "list", "items", "record", "data"):
                    if isinstance(v.get(kk), list):
                        candidates.append(v[kk])
    for lst in candidates:
        if lst and all(isinstance(x, dict) for x in lst[:3]):
            if any("name" in x or "customer_name" in x for x in lst[:5]):
                return lst
    return []


# ---------------------------------------------------------------- 命令实现


def cmd_login(cfg, args):
    token = login(cfg)
    masked = token[:4] + "*" * max(len(token) - 8, 0) + token[-4:] if len(token) > 8 else "***"
    print("登录成功 %s" % cfg["base_url"])
    print("token: %s" % masked)


def fetch_all_customers(cfg, token, name_filter=None):
    rows, page = [], 1
    while True:
        payload = {"token": token, "page": page, "rows": 50}
        if name_filter:
            payload["name"] = name_filter
        resp = post(cfg, cfg["endpoints"]["list"], payload)
        batch = find_customer_rows(resp)
        if not batch:
            if page == 1 and isinstance(resp, dict) and resp.get("error"):
                print(json.dumps(resp, ensure_ascii=False)[:500], file=sys.stderr)
            break
        rows.extend(batch)
        if len(batch) < 50:
            break
        page += 1
        if page > 200:  # 防御：最多取 1 万条
            break
    return rows


def cmd_list_customers(cfg, args):
    token = must_login(cfg)
    resp = post(
        cfg,
        cfg["endpoints"]["list"],
        {"token": token, "page": args.page, "rows": args.rows, **({"name": args.name} if args.name else {})},
    )
    if args.json:
        print(json.dumps(resp, ensure_ascii=False, indent=2))
        return
    rows = find_customer_rows(resp)
    print("共 %d 条（第 %d 页，每页 %d）" % (pick(resp, "total", "count", "records", default=len(rows)), args.page, args.rows))
    print_table(
        rows,
        [
            ("ord", lambda r: customer_row(r)["ord"]),
            ("客户名称", lambda r: customer_row(r)["name"]),
            ("联系人", lambda r: customer_row(r)["person"]),
            ("手机", lambda r: customer_row(r)["mobile"]),
            ("地址", lambda r: customer_row(r)["address"]),
        ],
    )
    if not rows:
        print(json.dumps(resp, ensure_ascii=False)[:800])


def cmd_customer_detail(cfg, args):
    token = must_login(cfg)
    ord_value = int(args.ord) if args.ord.isdigit() else args.ord
    resp = post(cfg, cfg["endpoints"]["detail"], {"token": token, "ord": ord_value})
    if args.json:
        print(json.dumps(resp, ensure_ascii=False, indent=2))
        return
    node = resp.get("data") if isinstance(resp.get("data"), dict) else resp
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(v, (str, int, float, bool)) or v is None:
                print("%-16s %s" % (k, v))
    else:
        print(json.dumps(resp, ensure_ascii=False, indent=2)[:4000])


def build_add_payload(args):
    # v3 原生写入：直传 JSON 字段 + token 放请求体；sort/sort1 传分类名称
    sort_path = args.sort or "终端客户,潜在客户"
    parts = [p.strip() for p in sort_path.split(",")] if sort_path else []
    payload = {
        "name": args.name,
        "person_name": args.person or "待补充",
        "mobile": args.mobile or "",
        "address": args.address or "",
    }
    if args.intro:
        payload["intro"] = args.intro
    if parts:
        payload["sort"] = parts[0]
        if len(parts) > 1:
            payload["sort1"] = parts[1]
    if args.cate:
        payload["cate"] = args.cate
    return payload


def add_one(cfg, token, payload):
    resp = post(cfg, cfg["endpoints"]["add"], {"token": token, **payload})
    ok = not resp.get("error") and resp.get("success") in (None, True)
    ord_ = pick(resp, "value", "ord", "id") or pick(resp.get("data") or {}, "value", "ord", "id")
    return ok, ord_, resp


def cmd_add_customer(cfg, args):
    token = must_login(cfg)
    payload = build_add_payload(args)
    ok, ord_, resp = add_one(cfg, token, payload)
    if args.json:
        print(json.dumps(resp, ensure_ascii=False, indent=2))
    if ok:
        print("新增成功: %s（ord=%s，分类: %s）" % (payload["name"], ord_, args.sort or "终端客户,潜在客户"))
    else:
        print(json.dumps(resp, ensure_ascii=False)[:1000], file=sys.stderr)
        die("新增失败: %s" % payload["name"], 6)


# ---------------------------------------------------------------- 文件读取


def read_csv_rows(path):
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "gbk", "utf-8"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        die("无法识别 CSV 编码: %s" % path)
    return [row for row in csv.reader(text.splitlines()) if any((c or "").strip() for c in row)]


_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_RNS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def _col_index(cell_ref):
    letters = "".join(ch for ch in (cell_ref or "") if ch.isalpha()).upper()
    idx = 0
    for ch in letters:
        idx = idx * 26 + (ord(ch) - 64)
    return idx - 1


def read_xlsx_rows(path, sheet_name=None):
    z = zipfile.ZipFile(path)
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))
        shared = ["".join(t.text or "" for t in si.iter(_NS + "t")) for si in root.findall(_NS + "si")]
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    sheets = [(s.get("name"), s.get(_RNS + "id")) for s in wb.iter(_NS + "sheet")]
    if not sheets:
        die("xlsx 中没有工作表: %s" % path)
    target = sheets[0]
    if sheet_name:
        for nm, rid in sheets:
            if nm == sheet_name:
                target = (nm, rid)
                break
        else:
            die("找不到工作表 “%s”，可用: %s" % (sheet_name, ", ".join(n for n, _ in sheets)))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    relmap = {r.get("Id"): r.get("Target") for r in rels}
    target_path = relmap.get(target[1], "")
    if target_path.startswith("/"):
        target_path = target_path.lstrip("/")
    elif not target_path.startswith("xl/"):
        target_path = "xl/" + target_path
    ws = ET.fromstring(z.read(target_path))
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


def map_columns(header):
    col_map = {}
    for idx, title in enumerate(header):
        t = (title or "").strip()
        for field, aliases in COLUMN_ALIASES.items():
            if t in aliases and field not in col_map:
                col_map[field] = idx
    return col_map


def parse_customer_file(path, sheet=None):
    if path.lower().endswith(".csv"):
        rows = read_csv_rows(path)
    elif path.lower().endswith(".xlsx"):
        rows = read_xlsx_rows(path, sheet)
    else:
        die("仅支持 .xlsx / .csv: %s" % path)
    if len(rows) < 2:
        die("文件没有数据行（需含表头）: %s" % path)
    col_map = map_columns(rows[0])
    if "name" not in col_map:
        die("表头中未找到“客户名称”列。识别的表头: %s" % ", ".join(h for h in rows[0] if h))
    customers, seen_in_file = [], set()
    for lineno, row in enumerate(rows[1:], start=2):
        def get(field):
            idx = col_map.get(field)
            return (row[idx].strip() if idx is not None and idx < len(row) else "") or ""
        name = get("name")
        if not name:
            continue
        if name in seen_in_file:
            print("  跳过 第%d行 %s（文件内重复）" % (lineno, name))
            continue
        seen_in_file.add(name)
        customers.append(
            {
                "name": name,
                "person_name": get("person") or "待补充",
                "mobile": get("mobile"),
                "address": get("address"),
                **({"intro": get("intro")} if get("intro") else {}),
            }
        )
    return customers


def cmd_import_customers(cfg, args):
    customers = parse_customer_file(args.file, args.sheet)
    print("文件解析: %d 个客户" % len(customers))
    token = must_login(cfg)
    existing = {customer_row(c)["name"] for c in fetch_all_customers(cfg, token)}
    print("ERP 现有客户: %d 个（用于按名称去重）" % len(existing))
    todo = [c for c in customers if c["name"] not in existing]
    skipped = [c["name"] for c in customers if c["name"] in existing]
    print("计划导入 %d，跳过（已存在）%d" % (len(todo), len(skipped)))
    for name in skipped:
        print("  跳过 %s（ERP 已存在）" % name)
    if args.dry_run or not todo:
        if args.dry_run:
            print("--- dry-run 预览，未写入 ---")
            for c in todo:
                print("  将导入 %s | %s | %s | %s" % (c["name"], c["person_name"], c["mobile"], c["address"]))
        return
    ok = fail = 0
    for c in todo:
        payload = dict(c)
        sort_path = args.sort or "终端客户,潜在客户"
        parts = [p.strip() for p in sort_path.split(",")] if sort_path else []
        if parts:
            payload["sort"] = parts[0]
            if len(parts) > 1:
                payload["sort1"] = parts[1]
        success, ord_, resp = add_one(cfg, token, payload)
        if success:
            ok += 1
            print("  成功 %s（ord=%s）" % (c["name"], ord_))
        else:
            fail += 1
            print("  失败 %s: %s" % (c["name"], json.dumps(resp, ensure_ascii=False)[:200]))
    print("导入完成: 成功 %d / 跳过 %d / 失败 %d" % (ok, len(skipped), fail))
    if fail:
        sys.exit(6)


def cmd_call(cfg, args):
    token = must_login(cfg)
    try:
        datas = json.loads(args.datas)
    except json.JSONDecodeError as e:
        die("datas 不是合法 JSON: %s" % e)
    if isinstance(datas, list):
        payload = {"session": token, "token": token, "datas": datas}
    elif isinstance(datas, dict):
        payload = {"token": token, **datas}
    else:
        die("datas 需为 JSON 对象或数组")
    resp = post(cfg, args.path, payload)
    print(json.dumps(resp, ensure_ascii=False, indent=2)[:8000])


def main():
    ap = argparse.ArgumentParser(description="智邦国际ERP（金汉隆）OpenApi CLI")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("login", help="测试连通/登录")

    p = sub.add_parser("list-customers", help="搜客户")
    p.add_argument("--name", default="")
    p.add_argument("--page", type=int, default=1)
    p.add_argument("--rows", type=int, default=20)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("customer-detail", help="客户详情")
    p.add_argument("--ord", required=True)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("add-customer", help="单个新增客户")
    p.add_argument("--name", required=True)
    p.add_argument("--person", default="")
    p.add_argument("--mobile", default="")
    p.add_argument("--address", default="")
    p.add_argument("--intro", default="")
    p.add_argument("--sort", default='', help='分类路径 "父,子"，如 "终端客户,潜在客户"')
    p.add_argument("--cate", default="", help="指定销售人员")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("import-customers", help="Excel/CSV 批量导入客户")
    p.add_argument("file")
    p.add_argument("--sheet", default="")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--sort", default="", help='分类路径 "父,子"')

    p = sub.add_parser("call", help="调用任意开放接口")
    p.add_argument("path")
    p.add_argument("datas")

    args = ap.parse_args()
    cfg = load_config()
    {
        "login": cmd_login,
        "list-customers": cmd_list_customers,
        "customer-detail": cmd_customer_detail,
        "add-customer": cmd_add_customer,
        "import-customers": cmd_import_customers,
        "call": cmd_call,
    }[args.cmd](cfg, args)


if __name__ == "__main__":
    main()
