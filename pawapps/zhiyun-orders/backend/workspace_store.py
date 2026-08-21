"""Workspace-local SQLite and append-only logs for the orders PawApp."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_workspace() -> Path:
    from qwenpaw.config.context import get_current_workspace_dir

    root = get_current_workspace_dir()
    if not root:
        raise RuntimeError("当前请求没有可信 QwenPaw Workspace 上下文")
    return Path(root).expanduser().resolve()


def ensure(root: Path) -> tuple[Path, Path]:
    root = root.expanduser().resolve()
    data = root / "data"
    logs = root / "logs"
    data.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    database = data / "ai-os.sqlite"
    with connect(database) as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS orders_order (
              id INTEGER PRIMARY KEY, order_no TEXT NOT NULL UNIQUE,
              customer TEXT NOT NULL, product TEXT NOT NULL, quantity REAL NOT NULL,
              amount REAL NOT NULL, due_date TEXT NOT NULL, status TEXT NOT NULL,
              current_node TEXT NOT NULL, progress INTEGER NOT NULL,
              delay_hours INTEGER NOT NULL DEFAULT 0, risk_level TEXT NOT NULL,
              risk_reason TEXT, updated_at TEXT NOT NULL, data_origin TEXT NOT NULL DEFAULT 'manual'
            );
            CREATE INDEX IF NOT EXISTS idx_orders_risk ON orders_order(risk_level, due_date);
            """
        )
        _seed(db)
    return database, logs


@contextmanager
def connect(database: Path) -> Iterator[sqlite3.Connection]:
    db = sqlite3.connect(database)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    try:
        yield db
        db.commit()
    finally:
        db.close()


def _seed(db: sqlite3.Connection) -> None:
    if db.execute("SELECT COUNT(*) FROM orders_order").fetchone()[0]:
        return
    rows = [
        ("SO-2026-1001", "华南汽车集团", "主轴组件 S-200", 120, 102000, "2026-09-15", "生产中", "生产", 45, 0, "黄色", "关键工序进度偏慢"),
        ("SO-2026-1002", "华东重工", "精密齿轮箱 G-50", 40, 128000, "2026-09-12", "生产中", "质检", 70, 0, "绿色", "进度正常"),
        ("SO-2026-1003", "北方轨道交通", "伺服支架 X-8", 500, 48000, "2026-08-25", "已完成", "发货", 100, 0, "绿色", "已完成"),
        ("SO-2026-1004", "华南汽车集团", "矿用减速机 K-7", 15, 237000, "2026-08-23", "生产中", "计划", 10, 36, "红色", "已延迟 36 小时且生产尚未开始"),
        ("SO-2026-1005", "华东重工", "高压配电柜 D-3", 8, 336000, "2026-08-30", "生产中", "包装", 90, 0, "绿色", "接近完成"),
        ("SO-2026-1006", "北方轨道交通", "冲压模具 M-12", 3, 204000, "2026-08-27", "生产中", "生产", 55, 12, "黄色", "存在 12 小时延迟"),
    ]
    db.executemany(
        """INSERT INTO orders_order
        (order_no,customer,product,quantity,amount,due_date,status,current_node,progress,delay_hours,risk_level,risk_reason,updated_at,data_origin)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'fixture')""",
        [(*row, now()) for row in rows],
    )


def append_runtime(logs: Path, event: dict[str, Any]) -> None:
    payload = {"timestamp": now(), **event}
    line = (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
    fd = os.open(logs / "runtime.jsonl", os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        os.write(fd, line)
        os.fsync(fd)
    finally:
        os.close(fd)
