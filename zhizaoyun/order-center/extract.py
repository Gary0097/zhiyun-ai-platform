# -*- coding: utf-8 -*-
"""订单文件文本提取：PDF / txt / md / csv / xlsx / 图片（可选 OCR）。"""
import io
import os
import zipfile

MAX_CHARS = 20000


class ExtractError(Exception):
    pass


def _from_pdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except Exception as e:  # noqa: BLE001
        raise ExtractError("PDF 解析组件不可用: %s" % e)
    try:
        reader = PdfReader(io.BytesIO(data))
        parts = []
        for page in reader.pages:
            parts.append(page.extract_text() or "")
        text = "\n".join(parts).strip()
    except Exception as e:  # noqa: BLE001
        raise ExtractError("PDF 文本提取失败: %s" % e)
    if not text:
        raise ExtractError("PDF 未提取到文字（可能是扫描件/图片页），请改用图片或直接粘贴订单文字")
    return text


def _from_xlsx(data: bytes) -> str:
    try:
        import openpyxl
    except Exception as e:  # noqa: BLE001
        raise ExtractError("Excel 解析组件不可用: %s" % e)
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    lines = []
    for ws in wb.worksheets:
        lines.append("【工作表】%s" % ws.title)
        for row in ws.iter_rows(values_only=True):
            cells = [str(c).strip() for c in row if c is not None and str(c).strip()]
            if cells:
                lines.append(" | ".join(cells))
    return "\n".join(lines)


def _from_docx(data: bytes) -> str:
    try:
        import docx  # python-docx
    except Exception:  # noqa: BLE001
        # 退化：docx 是 zip，直接取 document.xml 文本
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                xml = z.read("word/document.xml").decode("utf-8", "ignore")
            import re
            text = re.sub(r"<[^>]+>", " ", xml)
            return re.sub(r"\s+", " ", text).strip()
        except Exception as e:  # noqa: BLE001
            raise ExtractError("Word 解析失败: %s" % e)
    d = docx.Document(io.BytesIO(data))
    return "\n".join(p.text for p in d.paragraphs if p.text.strip())


def extract(filename: str, data: bytes) -> str:
    """按扩展名提取文本。图片返回明确提示（由调用方决定后续策略）。"""
    ext = os.path.splitext(filename or "")[1].lower().lstrip(".")
    if ext in ("txt", "md", "markdown", "csv", "tsv", "json", "log"):
        text = data.decode("utf-8", "ignore")
    elif ext == "pdf":
        text = _from_pdf(data)
    elif ext in ("xlsx", "xlsm"):
        text = _from_xlsx(data)
    elif ext == "docx":
        text = _from_docx(data)
    elif ext in ("png", "jpg", "jpeg", "webp", "bmp", "gif"):
        raise ExtractError("图片订单暂需先转为文字：请在微信/截图工具中复制文字，或在下方「粘贴订单文字」中粘贴后解析")
    else:
        text = data.decode("utf-8", "ignore")
    text = text.strip()
    if not text:
        raise ExtractError("文件内容为空")
    return text[:MAX_CHARS]


# ---------- 机器下单表识别与逐行结构化（订单编号=生产编号） ----------
from datetime import date as _date, timedelta as _td

# 表头 → 行字段（同名列取首个；设备型号等表头含说明文字用前缀匹配）
_MO_PREFIX_FIELDS = {"设备型号": "device_model", "设备名称": "device_name",
                     "公司名称": "customer", "下单类型": "machine_type",
                     "包装产品": "packaged_goods", "数量": "quantity",
                     "交货日期": "due_date", "下单时间": "ordered_at",
                     "业绩金额": "amount"}
_MO_EXACT_FIELDS = {"生产编号": "production_no", "合同编号": "contract_no",
                    "合同信息": "contract_info", "业务员": "sales",
                    "收货地址": "address", "客户姓名": "contact",
                    "联系方式": "phone", "客户类型": "customer_type"}


def _mo_s(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def _mo_date(v):
    """Excel 序列日期(46280) / datetime / 字符串 → YYYY-MM-DD。"""
    if v is None or v == "":
        return ""
    if isinstance(v, _date):
        return v.isoformat()[:10]
    if isinstance(v, (int, float)):
        try:
            return (_date(1899, 12, 30) + _td(days=int(v))).isoformat()
        except Exception:  # noqa: BLE001
            return ""
    s = str(v).strip()
    return s[:10] if len(s) >= 10 and s[4:5] == "-" else s


def machine_order_rows(filename: str, data: bytes):
    """上传文件为「机器下单表」（表头含 生产编号）时，返回逐行结构化订单列表；否则 None。"""
    import io
    ext = os.path.splitext(filename or "")[1].lower().lstrip(".")
    if ext not in ("xlsx", "xlsm"):
        return None
    try:
        import openpyxl
    except Exception as e:  # noqa: BLE001
        raise ExtractError("Excel 解析组件不可用: %s" % e)
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    for ws in wb.worksheets:
        it = ws.iter_rows(values_only=True)
        header = next(it, None)
        if header is None:
            continue
        cols = {}
        for i, h in enumerate(header):
            name = _mo_s(h)
            if not name:
                continue
            if name in _MO_EXACT_FIELDS:
                cols.setdefault(i, _MO_EXACT_FIELDS[name])
            else:
                for prefix, field in _MO_PREFIX_FIELDS.items():
                    if name.startswith(prefix):
                        cols.setdefault(i, field)
                        break
        if "production_no" not in cols.values():
            continue
        rows = []
        for raw in it:
            if raw is None:
                continue
            r = {}
            for i, field in cols.items():
                if i < len(raw):
                    r[field] = raw[i]
            pno = _mo_s(r.get("production_no"))
            if not pno:
                continue
            customer = _mo_s(r.get("customer")) or _mo_s(r.get("contract_info")).split("-")[0]
            device = _mo_s(r.get("device_name")) or _mo_s(r.get("device_model"))
            qty = r.get("quantity")
            qty = float(qty) if isinstance(qty, (int, float)) else None
            amt = r.get("amount")
            amt = float(amt) if isinstance(amt, (int, float)) else None
            rows.append({
                "production_no": pno,
                "contract_no": _mo_s(r.get("contract_no")),
                "machine_type": _mo_s(r.get("machine_type")),
                "customer": customer,
                "device": device,
                "packaged_goods": _mo_s(r.get("packaged_goods")),
                "quantity": int(qty) if qty is not None and qty.is_integer() else qty,
                "unit": "台",
                "due_date": _mo_date(r.get("due_date")),
                "ordered_at": _mo_date(r.get("ordered_at")),
                "address": _mo_s(r.get("address")),
                "contact": _mo_s(r.get("contact")),
                "phone": _mo_s(r.get("phone")),
                "customer_type": _mo_s(r.get("customer_type")),
                "sales": _mo_s(r.get("sales")),
                "amount": amt,
            })
        if rows:
            return rows
    return None
