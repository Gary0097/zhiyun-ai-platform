# -*- coding: utf-8 -*-
"""干净环境核心 E2E（PRD §17.13/14：双平台执行相同用例，输出与数据结构一致）。

纯标准库，无浏览器/模型依赖：登录 → 插件装载 → 数据核心健康 →
Schema 动态字段 + 导入 + 撤销 → 工作室鉴权与工件 → 统一数据中心 401。
在 Windows/Linux 产出同一结构的结果 JSON（--json 输出）。
"""
import argparse
import json
import platform
import sys
import time
import urllib.error
import urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:8088"


def call(path, body=None, method=None, token=None, timeout=30):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method or ("POST" if data else "GET"))
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.status, json.loads(response.read().decode())


def status_of(path, token=None, method="POST", body=None):
    try:
        code, _ = call(path, body=body if body is not None else {}, method=method, token=token)
        return code
    except urllib.error.HTTPError as exc:
        return exc.code


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", dest="as_json", action="store_true", help="以 JSON 输出机器可比对结果")
    args = parser.parse_args()

    checks = []

    def check(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": str(detail)[:160]})
        if not args.as_json:
            print(("PASS " if ok else "FAIL ") + name + ((" | " + str(detail)) if not ok else ""))

    # 0) 服务版本
    try:
        code, version = call("/api/version")
        check("服务启动与版本", code == 200 and version.get("version", "").startswith("2.2"), version)
    except Exception as exc:  # noqa: BLE001
        check("服务启动与版本", False, exc)

    # 1) 管理员登录
    token = ""
    try:
        code, body = call("/api/zhiyun-auth/login", {"username": "admin", "password": "ZhizaoYun@2026"})
        token = body.get("token", "")
        check("管理员登录", code == 200 and bool(token))
    except Exception as exc:  # noqa: BLE001
        check("管理员登录", False, exc)

    # 2) 插件全量装载
    try:
        code, plugins = call("/api/plugins", token=token, method="GET")
        expected = {"zhiyun-data-core", "zhiyun-auth", "zhiyun-audit", "zhiyun-app-discovery", "zhiyun-order-studio",
                    "zhiyun-data-studio", "zhiyun-sales-studio", "zhiyun-finance-studio", "zhiyun-people-studio",
                    "zhiyun-supply-studio", "zhiyun-service-studio", "zhiyun-integration-hub"}
        loaded = {p["id"] for p in plugins if p.get("loaded")}
        check("12 个核心应用装载", expected <= loaded, sorted(expected - loaded))
    except Exception as exc:  # noqa: BLE001
        check("12 个核心应用装载", False, exc)

    # 3) 数据核心健康
    try:
        code, health = call("/api/zhiyun-data-core/health", token=token, method="GET")
        check("数据核心健康", code == 200 and health.get("status") == "available", health.get("status"))
    except Exception as exc:  # noqa: BLE001
        check("数据核心健康", False, exc)

    # 4) Schema 动态字段 + 导入 + 撤销（§6.7）
    entity = "cleanenv_%d" % int(time.time())
    batch_id = ""
    try:
        call("/api/zhiyun-data-core/schemas", {
            "entity": entity, "label": "干净环境验收",
            "fields": [{"name": "order_no", "label": "订单号", "field_type": "text", "required": True},
                       {"name": "amount", "label": "金额", "field_type": "number", "required": True}]}, token=token)
        call("/api/zhiyun-data-core/schemas/%s/fields" % entity,
             {"name": "region", "label": "区域", "field_type": "text", "required": False}, token=token)
        code, batch = call("/api/zhiyun-data-core/imports/%s/commit?data_mode=production" % entity,
                           {"rows": [{"订单号": "CE-1", "金额": "10", "区域": "华东"}],
                            "mapping": {"订单号": "order_no", "金额": "amount", "区域": "region"},
                            "source_name": "clean-env"}, token=token)
        batch_id = batch.get("batch_id", "")
        code2, records = call("/api/zhiyun-data-core/records/%s?data_mode=production&limit=5" % entity, token=token, method="GET")
        ok = code == 200 and code2 == 200 and any(r["data"].get("region") == "华东" for r in records.get("records", []))
        check("动态字段导入与读取", ok)
        if batch_id:
            call("/api/zhiyun-data-core/batches/%s/rollback" % batch_id, {"confirmed": True}, token=token)
            _, after = call("/api/zhiyun-data-core/records/%s?data_mode=production&limit=5" % entity, token=token, method="GET")
            check("批次撤销", not after.get("records"))
    except Exception as exc:  # noqa: BLE001
        check("动态字段导入与读取", False, exc)

    # 5) 工作室鉴权（RBAC）与真实工件
    try:
        anon = status_of("/api/zhiyun-sales-studio/artifacts/bi", body={"orders": []})
        code, art = call("/api/zhiyun-sales-studio/artifacts/bi", {"orders": [
            {"date": "2026-08-01", "product": "电机", "category": "动力", "region": "华东", "quantity": 5, "unit_price": 100}]}, token=token)
        check("工作室匿名 401 / 带令牌出工件", anon == 401 and code == 200 and bool(art.get("id")), (anon, code))
    except Exception as exc:  # noqa: BLE001
        check("工作室匿名 401 / 带令牌出工件", False, exc)

    # 6) 数据中心端点分层鉴权
    try:
        anon_list = status_of("/api/zhiyun-data-core/entities", token=None, method="GET")
        member_sim = None
        check("数据中心匿名 401", anon_list == 401, anon_list)
    except Exception as exc:  # noqa: BLE001
        check("数据中心匿名 401", False, exc)

    passed = sum(1 for c in checks if c["ok"])
    result = {"platform": platform.system().lower(), "passed": passed, "total": len(checks), "checks": checks,
              "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")}
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print("\nSUMMARY[%s]: %d/%d passed" % (result["platform"], passed, len(checks)))
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
