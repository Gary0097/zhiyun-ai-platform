# -*- coding: utf-8 -*-
"""paperless 合同 AI 管线代理（复刻原版 contract-ui 上传链路）。

原版机制（contract-ui/src/features/upload/uploadFlow.ts + OrderCenterPage ComparisonTab）：
  1) POST /api/documents/post_document/  multipart 上传（带 department）
  2) 轮询 GET /api/tasks/?task_id=       SUCCESS→related_document；
     FAILURE 且 result 含 "duplicate of ...#N" → 复用已存在文档 N
  3) POST /api/contracts/                 为文档补建合同档案（extract_ai 懒创建默认
     general 会 403，必须先按账号可访问部门建档）
  4) POST /api/contracts/extract_ai/      OCR + LLM 要素抽取
本模块在 order-center 服务端代理以上四步，浏览器同源调用 /api/contracts/*。
"""
import json
import os
import re
import threading
import urllib.error
import urllib.parse
import urllib.request

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

PAPERLESS_URL = os.environ.get("PAPERLESS_URL", "http://host.docker.internal:8199")
PAPERLESS_USER = os.environ.get("PAPERLESS_USER", "hub")
PAPERLESS_PASSWORD = os.environ.get("PAPERLESS_PASSWORD", "Hbd437f302a0894f1b80")
PAPERLESS_DEPARTMENT = os.environ.get("PAPERLESS_DEPARTMENT", "procurement")
_TIMEOUT = 120

router = APIRouter()
_lock = threading.Lock()
_token_cache = {"token": None}


class _PlError(Exception):
    def __init__(self, status, detail):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _login_token() -> str:
    with _lock:
        if _token_cache["token"]:
            return _token_cache["token"]
        body = json.dumps({"username": PAPERLESS_USER, "password": PAPERLESS_PASSWORD}).encode()
        req = urllib.request.Request(
            PAPERLESS_URL + "/api/token/", data=body,
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                _token_cache["token"] = json.loads(resp.read())["token"]
        except Exception as e:  # noqa: BLE001
            raise _PlError(502, "paperless 登录失败：%s" % e) from e
        return _token_cache["token"]


def _call(method, path, payload=None, raw_body=None, ctype="application/json", retry_auth=True):
    url = PAPERLESS_URL + path
    headers = {"Authorization": "Token %s" % _login_token()}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = ctype
    elif raw_body is not None:
        data = raw_body
        headers["Content-Type"] = ctype
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            body = resp.read()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        if e.code == 401 and retry_auth:
            with _lock:
                _token_cache["token"] = None
            return _call(method, path, payload, raw_body, ctype, retry_auth=False)
        detail = ""
        try:
            detail = json.loads(e.read() or b"{}").get("detail", "")
        except Exception:  # noqa: BLE001
            pass
        raise _PlError(e.code, detail or ("paperless HTTP %s" % e.code))
    except _PlError:
        raise
    except Exception as e:  # noqa: BLE001
        raise _PlError(502, "paperless 不可达（%s）：%s" % (PAPERLESS_URL, e)) from e


class ExtractBody(BaseModel):
    document: int
    reprocess: bool = False


@router.post("/api/contracts/upload")
async def contracts_upload(file: UploadFile = File(...), title: str = Form("")):
    """原版第 1 步：multipart 直传 paperless，返回 celery 任务号。"""
    try:
        content = await file.read()
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"detail": "读取文件失败：%s" % e}, status_code=400)
    if not content:
        return JSONResponse({"detail": "文件为空"}, status_code=400)
    boundary = "ocplboundary7f3a9c"
    name = os.path.basename(file.filename or "contract.pdf")
    title = (title or "").strip() or os.path.splitext(name)[0]
    parts = []
    for field, value in (("document", (name, content)),
                         ("title", (None, title.encode())),
                         ("department", (None, PAPERLESS_DEPARTMENT.encode()))):
        disp = 'form-data; name="%s"' % field
        if value[0]:
            disp += '; filename="%s"' % value[0].replace('"', "")
        parts.append(("--%s\r\nContent-Disposition: %s\r\n\r\n" % (boundary, disp)).encode()
                     + value[1] + b"\r\n")
    body = b"".join(parts) + ("--%s--\r\n" % boundary).encode()
    try:
        task_id = _call("POST", "/api/documents/post_document/",
                        raw_body=body, ctype="multipart/form-data; boundary=%s" % boundary)
    except _PlError as e:
        return JSONResponse({"detail": e.detail}, status_code=e.status)
    return {"task_id": task_id, "title": title}


@router.get("/api/contracts/task")
def contracts_task(task_id: str):
    """原版第 2 步：任务状态；FAILURE+重复文档时解析出可复用的文档号。"""
    try:
        tasks = _call("GET", "/api/tasks/?task_id=%s" % urllib.parse.quote(task_id))
    except _PlError as e:
        return JSONResponse({"detail": e.detail}, status_code=e.status)
    t = (tasks or [{}])[0]
    result = str(t.get("result") or "")
    dup = re.search(r"duplicate of .*#(\d+)", result, re.I)
    return {"status": t.get("status"),
            "related_document": t.get("related_document"),
            "duplicate_document": int(dup.group(1)) if dup else None,
            "result": result[:300]}


@router.post("/api/contracts/extract")
def contracts_extract(body: ExtractBody):
    """原版第 3+4 步：确保合同档案存在（按可访问部门）→ AI 要素抽取。"""
    try:
        profiles = _call("GET", "/api/contracts/?document=%d&page_size=1" % body.document)
        if not (profiles.get("results") or []):
            doc = _call("GET", "/api/documents/%d/" % body.document)
            _call("POST", "/api/contracts/", {
                "document": body.document,
                "department": PAPERLESS_DEPARTMENT,
                "contract_name": doc.get("title") or "",
                "deliverables": [],
            })
        result = _call("POST", "/api/contracts/extract_ai/", {
            "document": body.document,
            "reprocess_document": body.reprocess,
        })
    except _PlError as e:
        return JSONResponse({"detail": e.detail}, status_code=e.status)
    contract = result.get("contract") or {}
    payload = contract.get("extracted_payload") or (result.get("suggested") or {}).get("payload") or {}
    return {"document": body.document,
            "contract_id": contract.get("id"),
            "department": contract.get("department"),
            "ai_status": contract.get("ai_status"),
            "elements": payload,
            "suggested": result.get("suggested"),
            "meta": result.get("meta")}
