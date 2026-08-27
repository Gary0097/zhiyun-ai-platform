# -*- coding: utf-8 -*-
"""验证演示样例文件能被 zhiyun-data-core /parse 正确解析（表头数与行数对账）。"""
import json
import pathlib
import sys
import urllib.request
import uuid

BASE = "http://127.0.0.1:8088"
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MANIFEST = ROOT / "docs" / "qa" / "demo-data" / "manifest.json"
TOKEN = ""


def admin_token() -> str:
    request = urllib.request.Request(
        BASE + "/api/zhiyun-auth/login",
        data=json.dumps({"username": "admin", "password": "ZhizaoYun@2026"}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))["token"]


def parse_via_api(file_path: pathlib.Path):
    boundary = uuid.uuid4().hex
    body = b"".join([
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'.encode(),
        b"Content-Type: application/octet-stream\r\n\r\n",
        file_path.read_bytes(),
        f"\r\n--{boundary}--\r\n".encode(),
    ])
    request = urllib.request.Request(
        BASE + "/api/zhiyun-data-core/parse",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "Authorization": "Bearer " + TOKEN},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    global TOKEN
    TOKEN = admin_token()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    passed, failed = 0, 0
    for item in manifest:
        if item["kind"] not in ("table", "form-subtable"):
            continue
        file_path = pathlib.Path(item["file"])
        label = f"{item['studio']}/{item['module']}"
        try:
            parsed = parse_via_api(file_path)
            headers_ok = len(parsed.get("headers") or []) == item["columns"]
            rows_ok = parsed.get("row_count") == item["rows"]
            if headers_ok and rows_ok:
                passed += 1
                print(f"PASS {label}: headers={len(parsed['headers'])} rows={parsed['row_count']}")
            else:
                failed += 1
                print(f"FAIL {label}: expect cols={item['columns']} rows={item['rows']}, "
                      f"got headers={parsed.get('headers')} rows={parsed.get('row_count')}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {label}: {exc}")
    print(f"\nSUMMARY: {passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
