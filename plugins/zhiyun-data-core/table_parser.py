# -*- coding: utf-8 -*-
"""Safe CSV/XLSX parser for generic Data Core imports."""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

MAX_ROWS = 10000


def _clean_rows(rows: list[list[Any]]) -> tuple[list[str], list[dict[str, Any]]]:
    if not rows:
        raise ValueError("文件中没有数据")
    headers = [str(value or "").strip() for value in rows[0]]
    active = [header for header in headers if header]
    if not active:
        raise ValueError("第一行必须是字段名称")
    if len(active) != len(set(active)):
        raise ValueError("字段名称不能重复")
    records = []
    for values in rows[1 : MAX_ROWS + 1]:
        if not any(value not in (None, "") for value in values):
            continue
        records.append({header: values[index] if index < len(values) else None for index, header in enumerate(headers) if header})
    return active, records


def parse_table(filename: str, content: bytes) -> dict[str, Any]:
    suffix = Path(filename).suffix.casefold()
    if suffix == ".csv":
        matrix = list(csv.reader(io.StringIO(content.decode("utf-8-sig"))))
        headers, rows = _clean_rows(matrix)
        return {"filename": filename, "sheet": None, "headers": headers, "rows": rows, "row_count": len(rows)}
    if suffix == ".xlsx":
        from openpyxl import load_workbook

        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        sheet = workbook[workbook.sheetnames[0]]
        headers, rows = _clean_rows([list(row) for row in sheet.iter_rows(values_only=True)])
        return {"filename": filename, "sheet": sheet.title, "headers": headers, "rows": rows, "row_count": len(rows)}
    raise ValueError("仅支持 .xlsx 和 .csv 文件")
