# -*- coding: utf-8 -*-
"""智能订单处理中心 - FastAPI 入口。
核心功能（客户订单自动格式化 / 多模板支持与适配）由两个 WeKnora 智能体驱动：
  1) 订单语义解析智能体：原始订单（PDF/文本等）→ 标准化工单 JSON
  2) 模板适配智能体：判模板分类 + 匹配设备与物料清单（依据 8001 知识库主数据）
之后由本服务生成给财务的 Excel 订单（订单信息 / 物料明细 / 解析说明）。
接入方式与「合同管理/管理协同中心」一致：/sso-token 免登录，Hub iframe 内嵌。
"""
import base64
import hashlib
import hmac
import io
import json
import os
import time
from datetime import datetime

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from . import db, excelgen, extract, weknora
from . import paperless_proxy

SECRET = os.environ.get("OC_SECRET", "order-center-sso-secret-20260918")
STATIC_DIR = os.environ.get("OC_STATIC", os.path.join(os.path.dirname(__file__), "..", "static"))
SHARED_USER = {"name": "hub", "display": "智能订单处理中心（共享坐席）"}

app = FastAPI(title="智能订单处理中心", docs_url=None, redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
db.init_db()
app.include_router(paperless_proxy.router)


# ---------- 认证 ----------
def issue_token(user: str, days: int = 7) -> str:
    payload = f"{user}|{int(time.time()) + days * 86400}"
    sig = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    return base64.urlsafe_b64encode(f"{payload}|{sig}".encode()).decode()


def verify_token(token: str):
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        user, exp, sig = raw.rsplit("|", 2)
        if int(exp) < time.time():
            return None
        expect = hmac.new(SECRET.encode(), f"{user}|{exp}".encode(), hashlib.sha256).hexdigest()[:32]
        return user if hmac.compare_digest(sig, expect) else None
    except Exception:  # noqa: BLE001
        return None


@app.middleware("http")
async def auth_guard(request: Request, call_next):
    path = request.url.path
    open_paths = ("/sso-token", "/api/login", "/api/health", "/login")
    if path.startswith("/api") and not any(path.startswith(p) for p in open_paths):
        token = request.headers.get("X-Token", "")
        if not verify_token(token):
            # 下载类链接无法携带请求头，允许 ?token= 传入
            qt = request.query_params.get("token", "")
            if not (qt and verify_token(qt)):
                return JSONResponse({"detail": "unauthorized"}, status_code=401)
    return await call_next(request)


@app.get("/sso-token")
def sso_token():
    return {"token": issue_token(SHARED_USER["name"]), "user": SHARED_USER}


@app.get("/api/health")
def health():
    ready = {}
    try:
        ids = weknora.agent_ids(force=True)
        for k, n in weknora.AGENT_NAMES.items():
            ready[k] = bool(ids.get(n))
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "weknora": weknora.health(), "agents": ready,
            "kb": weknora.KB_NAME, "time": datetime.now().isoformat(timespec="seconds")}


@app.get("/api/meta")
def meta():
    try:
        ids = weknora.agent_ids()
    except Exception:  # noqa: BLE001
        ids = {}
    agents = [{"key": k, "name": n, "id": ids.get(n), "ready": bool(ids.get(n))}
              for k, n in weknora.AGENT_NAMES.items()]
    return {"agents": agents, "kb": weknora.KB_NAME,
            "templates": ["食品", "医药", "电子", "化工", "宠物", "制造"],
            "stats": db.stats()}


# ---------- 核心：上传订单 → 解析 → 模板/物料适配 ----------
def run_pipeline(text, filename, source_type):
    """返回 (record_id, parsed, adapted, notes)。"""
    notes = []
    parse_q = ("请解析下面这份客户订单，严格按系统提示输出 JSON（只输出 JSON）：\n"
               "---- 原始订单文本 ----\n" + text)
    parsed_raw, _ = weknora.agent_answer("parser", parse_q)
    parsed = weknora.parse_json_answer(parsed_raw)
    parsed.setdefault("待人工确认", [])
    if parsed.get("原始单据来源") in (None, "", "文本录入") and source_type:
        parsed["原始单据来源"] = source_type

    adapted = {}
    try:
        adapt_q = ("订单解析结果（JSON）：\n%s\n\n请完成模板分类、设备匹配与物料清单生成，"
                   "严格按系统提示输出 JSON（只输出 JSON）。" % json.dumps(parsed, ensure_ascii=False))
        adapted_raw, _ = weknora.agent_answer("adapter", adapt_q)
        adapted = weknora.parse_json_answer(adapted_raw)
    except weknora.WeKnoraError as e:
        notes.append("模板适配失败：%s" % e)

    prod = adapted.get("匹配产品") or {}
    qty = parsed.get("数量")
    cost = adapted.get("预估物料成本")
    warnings = []
    for w in list(parsed.get("待人工确认") or []) + list(adapted.get("待人工确认") or []) + notes:
        w = str(w).strip()
        if w and w not in warnings:
            warnings.append(w)
    so, mo = db.make_numbers()
    rec = {
        "id": db.new_id(),
        "so_no": so, "mo_no": mo,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source_filename": filename or "文本录入",
        "source_type": source_type or parsed.get("原始单据来源") or "文本录入",
        "raw_text": text,
        "parsed_json": json.dumps(parsed, ensure_ascii=False),
        "adapted_json": json.dumps(adapted, ensure_ascii=False),
        "template": adapted.get("模板分类") or "",
        "customer": parsed.get("客户名称") or "",
        "product": prod.get("产品名称") or parsed.get("设备型号建议") or "",
        "quantity": qty if isinstance(qty, (int, float)) else None,
        "unit": parsed.get("单位") or "",
        "due_date": parsed.get("交期") or "",
        "cost": cost if isinstance(cost, (int, float)) else None,
        "status": "待确认" if (warnings and not adapted) else ("有疑点" if warnings else "已生成"),
        "warnings": json.dumps(warnings, ensure_ascii=False),
    }
    db.save_order(rec)
    return rec["id"], parsed, adapted, warnings


def import_machine_orders(rows, filename):
    """机器下单表批量入库：每行一单，订单编号取表内「生产编号」，重复编号跳过。"""
    existing = db.existing_so_nos()
    now = datetime.now().isoformat(timespec="seconds")
    imported, skipped = [], 0
    for r in rows:
        so = r["production_no"]
        if so in existing:
            skipped += 1
            continue
        existing.add(so)
        parsed = {
            "客户名称": r["customer"], "品名": r["packaged_goods"] or r["device"],
            "设备型号建议": r["device"], "数量": r["quantity"], "单位": r["unit"],
            "交期": r["due_date"], "收货地址": r["address"],
            "联系人": r["contact"], "联系方式": r["phone"],
            "合同编号": r["contract_no"], "业绩金额": r["amount"],
            "原始单据来源": "机器下单表直导",
            "解析说明": "结构化表格直导（未走 LLM）：字段按表头映射；订单编号采用表内「生产编号」。",
        }
        adapted = {
            "模板分类": r["machine_type"],
            "判类依据": "机器下单表「下单类型」列",
            "匹配产品": {"产品名称": r["device"] or r["machine_type"]},
            "物料清单": [],
            "核对提示": [],
        }
        rec = {
            "id": db.new_id(),
            "so_no": so, "mo_no": so,
            "created_at": now,
            "source_filename": filename or "机器下单表",
            "source_type": "机器下单表直导",
            "raw_text": json.dumps({k: r[k] for k in ("production_no", "contract_no", "machine_type",
                                                      "customer", "device", "quantity", "due_date")},
                                   ensure_ascii=False),
            "parsed_json": json.dumps(parsed, ensure_ascii=False),
            "adapted_json": json.dumps(adapted, ensure_ascii=False),
            "template": r["machine_type"],
            "customer": r["customer"],
            "product": r["device"] or r["machine_type"],
            "quantity": r["quantity"],
            "unit": r["unit"],
            "due_date": r["due_date"],
            "cost": None,
            "status": "已生成",
            "warnings": json.dumps([], ensure_ascii=False),
        }
        db.save_order(rec)
        imported.append({
            "so_no": so, "customer": r["customer"], "product": rec["product"],
            "quantity": r["quantity"], "unit": r["unit"], "due_date": r["due_date"],
            "template": r["machine_type"], "contract_no": r["contract_no"],
        })
    batch = {"filename": filename or "机器下单表", "total": len(rows),
             "imported": len(imported), "skipped": skipped,
             "orders": imported[:50],
             "note": "订单编号已采用表内「生产编号」列；重复生产编号自动跳过"}
    first = db.get_order_by_so(imported[0]["so_no"]) if imported else None
    return {"batch": batch, "id": first["id"] if first else None,
            "parsed": {}, "adapted": {}, "warnings": [], "order": first}


class TextBody(BaseModel):
    text: str = ""
    source_type: str = "文本录入"
    filename: str = ""


@app.post("/api/orders/extract")
async def extract_order(request: Request,
                        file: UploadFile | None = File(default=None),
                        text: str = Form(default=""),
                        source_type: str = Form(default=""),
                        filename: str = Form(default="")):
    """支持 multipart 文件上传或表单文本；也支持 JSON {text}。"""
    content_type = request.headers.get("content-type", "")
    raw_text = ""
    fname = filename
    stype = source_type
    try:
        if "multipart/form-data" in content_type:
            if file is not None and file.filename:
                data = await file.read()
                fname = fname or file.filename
                # 机器下单表（表头含「生产编号」）：逐行直导，订单编号 = 生产编号
                mo_rows = extract.machine_order_rows(file.filename, data)
                if mo_rows:
                    return import_machine_orders(mo_rows, fname)
                raw_text = extract.extract(file.filename, data)
                if not stype:
                    stype = _guess_source(file.filename)
            elif text.strip():
                raw_text = text.strip()
        else:
            body = TextBody(**await request.json())
            raw_text = (body.text or "").strip()
            fname = fname or body.filename
            stype = stype or body.source_type
    except extract.ExtractError as e:
        return JSONResponse({"detail": str(e)}, status_code=400)
    if not raw_text:
        return JSONResponse({"detail": "请上传订单文件或粘贴订单文字"}, status_code=400)
    try:
        oid, parsed, adapted, warnings = run_pipeline(raw_text, fname, stype)
    except weknora.WeKnoraError as e:
        return JSONResponse({"detail": "智能体解析失败：%s" % e}, status_code=502)
    return {"id": oid, "parsed": parsed, "adapted": adapted, "warnings": warnings,
            "order": db.get_order(oid)}


def _guess_source(filename):
    low = (filename or "").lower()
    if low.endswith(".pdf"):
        return "PDF订单"
    if any(low.endswith(x) for x in (".jpg", ".jpeg", ".png", ".webp")):
        return "微信截图订单"
    if "合同" in (filename or "") or "contract" in low:
        return "合同扫描件"
    if any(low.endswith(x) for x in (".xlsx", ".xlsm", ".csv")):
        return "表格订单"
    return "文本录入"


# ---------- 订单底表 ----------
@app.get("/api/orders")
def orders_list(limit: int = 200):
    return {"orders": db.list_orders(limit), "stats": db.stats()}


@app.get("/api/orders/{oid}")
def order_detail(oid: str):
    rec = db.get_order(oid)
    if not rec:
        return JSONResponse({"detail": "订单不存在"}, status_code=404)
    return rec


@app.post("/api/orders/{oid}/push-erp")
def order_push_erp(oid: str):
    """推送订单到 ERP：标记推送状态并记录时间（幂等，重复推送返回当前状态）。"""
    r = db.push_erp(oid)
    if not r:
        raise HTTPException(status_code=404, detail="order not found")
    return {"ok": True, "id": r["id"], "so_no": r["so_no"],
            "erp_status": "已正确推送", "erp_pushed": r["erp_pushed"],
            "erp_pushed_at": r["erp_pushed_at"]}


@app.delete("/api/orders/{oid}")
def order_delete(oid: str):
    return {"ok": db.delete_order(oid)}


@app.get("/api/orders/{oid}/excel")
def order_excel(oid: str):
    rec = db.get_order(oid)
    if not rec:
        return JSONResponse({"detail": "订单不存在"}, status_code=404)
    buf = excelgen.build(rec)
    name = excelgen.filename(rec)
    from urllib.parse import quote
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": "attachment; filename*=UTF-8''%s" % quote(name)})


# ---------- 智能体问答（合同要素提取与比对 / 异常处理流程自动化） ----------
class ChatBody(BaseModel):
    query: str
    session_id: str = ""


@app.post("/api/chat/{kind}")
def chat(kind: str, body: ChatBody):
    kind = "qa" if kind not in weknora.AGENT_NAMES else kind
    if not body.query.strip():
        return JSONResponse({"detail": "请输入问题"}, status_code=400)
    try:
        sid = body.session_id or weknora.create_session("订单处理中心·%s" % kind)
        aid = weknora.agent_id_for(kind)
    except weknora.WeKnoraError as e:
        return JSONResponse({"detail": str(e)}, status_code=502)

    def gen():
        yield "event: session\ndata: %s\n\n" % json.dumps({"session_id": sid})
        try:
            answer, _ = weknora.agent_answer(kind, body.query, session_id=sid)
            yield "event: delta\ndata: %s\n\n" % json.dumps({"text": answer})
        except Exception as e:  # noqa: BLE001
            yield "event: error\ndata: %s\n\n" % json.dumps({"message": str(e)})
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---------- 静态前端 ----------
@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/login")
def login_page():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.post("/api/orders/manual")
async def order_manual(request: Request):
    body = await request.json()
    so = (body.get("so_no") or "").strip()
    if not so:
        from datetime import datetime as _dt2
        now2 = _dt2.now()
        seqs = _db.make_numbers(now2) if hasattr(_db, "make_numbers") else []
        so = "KL-%s-%s" % (now2.strftime("%y%m%d"), (seqs[0][-4:] if seqs else "0001"))
    if _db.get_order_by_so(so):
        return {"error": "订单编号已存在: %s" % so}
    from datetime import datetime as _dt
    now = _dt.now().isoformat(timespec="seconds")
    qty = body.get("quantity") or 1
    try:
        qty = float(qty)
    except Exception:
        qty = 1.0
    try:
        cost = float(body.get("amount") or 0)
    except Exception:
        cost = 0.0
    parsed = {"客户名称": body.get("customer") or "", "品名": body.get("product") or "",
              "设备型号建议": body.get("device") or "", "数量": qty, "单位": "台",
              "交期": body.get("due_date") or "", "合同编号": body.get("contract_no") or "",
              "业绩金额": cost, "原始单据来源": "现场录入",
              "解析说明": body.get("remark") or "现场手工录入订单"}
    adapted = {"模板分类": body.get("machine_type") or "未分类", "判类依据": "手工选择"}
    rec = {"id": _db.new_id(), "so_no": so, "mo_no": "", "created_at": now,
           "source_filename": "现场录入", "source_type": "manual",
           "raw_text": "", "parsed_json": json.dumps(parsed, ensure_ascii=False),
           "adapted_json": json.dumps(adapted, ensure_ascii=False),
           "template": body.get("machine_type") or "未分类",
           "customer": body.get("customer") or "", "product": body.get("product") or "",
           "quantity": qty, "unit": "台", "due_date": body.get("due_date") or "",
           "cost": cost, "status": "待确认", "warnings": "[]"}
    oid = _db.save_order(rec)
    return {"ok": True, "id": oid, "so_no": so}
