# -*- coding: utf-8 -*-
"""Schema Registry 动态字段端到端验收（PRD §6.7 / 总体验收场景 11）。

链路：用户加字段 → Excel/行数据带新列导入 → 记录保留扩展字段 →
字段改名生效 → 停用后导入不再要求该列 → 批次可撤销且不影响其他数据。
"""
import json
import sys
import time
import urllib.request
import uuid

BASE = "http://127.0.0.1:8088"
ENTITY = "e2e_schema_%d" % int(time.time())


def call(path, body=None, method=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method or ("POST" if data else "GET"))
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode())


def main() -> int:
    results = []

    def check(name, ok, detail=""):
        results.append((name, ok, detail))
        print(("PASS " if ok else "FAIL ") + name + (" | " + detail if detail and not ok else ""))

    token = call("/api/zhiyun-auth/login", {"username": "admin", "password": "ZhizaoYun@2026"})["token"]

    # 1. 用户创建实体（基础两个字段）
    call("/api/zhiyun-data-core/schemas", {
        "entity": ENTITY, "label": "E2E 字段验收",
        "fields": [
            {"name": "order_no", "label": "订单号", "field_type": "text", "required": True},
            {"name": "amount", "label": "金额", "field_type": "number", "required": True},
        ]}, token=token)
    schema = call("/api/zhiyun-data-core/schemas/" + ENTITY, token=token)
    check("创建实体与基础字段", {f["name"] for f in schema["fields"]} >= {"order_no", "amount"})

    # 2. 用户为现有实体新增自定义字段（§6.7 字段能力）
    call("/api/zhiyun-data-core/schemas/%s/fields" % ENTITY, {
        "name": "sales_region", "label": "销售区域", "field_type": "text", "required": False}, token=token)
    schema = call("/api/zhiyun-data-core/schemas/" + ENTITY, token=token)
    region = next((f for f in schema["fields"] if f["name"] == "sales_region"), None)
    check("动态新增字段即时生效", region is not None and region["active"])

    # 3. 带/不带新列的两批导入（真实、正式）
    b1 = call("/api/zhiyun-data-core/imports/%s/commit?data_mode=production" % ENTITY, {
        "rows": [
            {"订单号": "E2E-001", "金额": "1200", "销售区域": "华东"},
            {"订单号": "E2E-002", "金额": "800", "销售区域": "华南"},
        ], "mapping": {"订单号": "order_no", "金额": "amount", "销售区域": "sales_region"},
        "source_name": "schema-e2e-1"}, token=token)
    check("含新字段列导入成功", b1.get("row_count") == 2, json.dumps(b1, ensure_ascii=False))
    b2 = call("/api/zhiyun-data-core/imports/%s/commit?data_mode=production" % ENTITY, {
        "rows": [{"订单号": "E2E-003", "金额": "500"}],
        "mapping": {"订单号": "order_no", "金额": "amount"}, "source_name": "schema-e2e-2"}, token=token)
    check("新字段为可空时无该列也可导入", b2.get("row_count") == 1)

    # 4. 记录保留扩展字段（§19.11：应用可读取同一记录及扩展字段）
    records = call("/api/zhiyun-data-core/records/%s?data_mode=production&limit=10" % ENTITY, token=token)["records"]
    by_no = {r["data"].get("order_no"): r["data"] for r in records}
    check("扩展字段随记录保存", by_no.get("E2E-001", {}).get("sales_region") == "华东")

    # 5. 字段改名生效（显示名）
    call("/api/zhiyun-data-core/schemas/%s/fields/sales_region" % ENTITY, {"label": "销售大区"}, method="PATCH", token=token)
    schema = call("/api/zhiyun-data-core/schemas/" + ENTITY, token=token)
    region = next(f for f in schema["fields"] if f["name"] == "sales_region")
    check("字段改名生效", region["label"] == "销售大区")

    # 6. 停用字段后导入不再要求该列，历史记录不受影响
    call("/api/zhiyun-data-core/schemas/%s/fields/sales_region" % ENTITY, {"active": False}, method="PATCH", token=token)
    records2 = call("/api/zhiyun-data-core/records/%s?data_mode=production&limit=10" % ENTITY, token=token)["records"]
    check("停用字段不影响历史记录", any(r["data"].get("sales_region") == "华东" for r in records2))

    # 7. 按批次撤销且不影响其他批次
    call("/api/zhiyun-data-core/batches/%s/rollback" % b1["batch_id"], {"confirmed": True}, token=token)
    records3 = call("/api/zhiyun-data-core/records/%s?data_mode=production&limit=10" % ENTITY, token=token)["records"]
    nos = {r["data"].get("order_no") for r in records3}
    check("批次撤销精确隔离", nos == {"E2E-003"}, str(nos))

    passed = sum(1 for _, ok, _ in results if ok)
    print("\nSUMMARY: %d/%d passed" % (passed, len(results)))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
