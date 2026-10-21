# -*- coding: utf-8 -*-
"""离线验证 Data Core v2 -> v3 迁移：用真实库做一致快照后模拟升级。

不会触碰线上库，仅验证新代码能安全地把旧 schema 升到 v3 并查询。
"""
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins" / "zhiyun-data-core"
sys.path.insert(0, str(PLUGIN))

from data_core import DataCore, SCHEMA_VERSION  # noqa: E402

SRC = r"C:\AI\zhiyun-ai-os-workspace\zhiyun-ai-platform\apps\qwenpaw-embedded\workspace\workspace\data-core\data-core.sqlite"


def snapshot_v2(src: Path) -> Path:
    """用 sqlite backup API 做一致快照，避免 WAL 下主文件拷贝不一致。"""
    fd, tmp = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    target = Path(tmp)
    src_con = sqlite3.connect(str(src))
    dst_con = sqlite3.connect(str(target))
    try:
        src_con.backup(dst_con)
    finally:
        src_con.close()
        dst_con.close()
    return target


def col_has_data_mode(db: Path) -> bool:
    con = sqlite3.connect(str(db))
    try:
        rows = con.execute("PRAGMA table_info(data_records)").fetchall()
        return any(r[1] == "data_mode" for r in rows)
    finally:
        con.close()


def main() -> int:
    src = Path(SRC)
    if not src.exists():
        print("FAIL | 源库不存在: " + str(src))
        return 1

    # 1) 快照旧库，确认它是 v2
    snap = snapshot_v2(src)
    try:
        con = sqlite3.connect(str(snap))
        ver = con.execute("SELECT value FROM data_core_meta WHERE key='schema_version'").fetchone()[0]
        con.close()
        print(f"INFO | 快照库 schema_version={ver}  (期望 2)")

        if col_has_data_mode(snap):
            print("FAIL | 快照已含 data_mode，不是需要升级的 v2 库")
            return 1

        # 2) 用新代码打开快照 -> 触发迁移
        core = DataCore(snap)
        con = sqlite3.connect(str(snap))
        ver = con.execute("SELECT value FROM data_core_meta WHERE key='schema_version'").fetchone()[0]
        mig = [r[0] for r in con.execute("SELECT version FROM data_core_migrations ORDER BY version").fetchall()]
        con.close()
        assert int(ver) == SCHEMA_VERSION, f"升级后 schema_version 应为 {SCHEMA_VERSION}，实际 {ver}"
        assert 3 in mig, f"迁移日志缺少 v3: {mig}"
        assert col_has_data_mode(snap), "data_records 缺 data_mode 列"
        print(f"PASS | v2->v3 迁移成功 schema_version={ver} migrations={mig}")

        # 3) 旧数据默认归入 demo，且可用 data_mode 过滤查询
        entities = core.list_entities()
        demo_total = sum(e["demo_count"] for e in entities)
        prod_total = sum(e["production_count"] for e in entities)
        print(f"INFO | 默认迁移实体数={len(entities)} demo={demo_total} production={prod_total}")
        assert all(set(e) >= {"demo_count", "production_count"} for e in entities), "list_entities 缺 mode 计数"

        recs = core.list_records("orders", limit=5, data_mode="demo")
        print(f"INFO | demo orders 查询返回 {len(recs)} 条")
        for r in recs:
            assert r["data_mode"] == "demo", f"记录 mode 非 demo: {r['record_id']}"
        print("PASS | data_mode=demo 过滤正常，旧记录默认 demo")

        # 4) 新写入 demo 与 production 隔离
        core.generate_orders(count=3, seed=7, data_mode="demo")
        core.generate_orders(count=2, seed=8, data_mode="production")
        demo_after = sum(e["demo_count"] for e in core.list_entities())
        prod_after = sum(e["production_count"] for e in core.list_entities())
        print(f"INFO | 新增后 demo={demo_after} production={prod_after}")
        assert demo_after == demo_total + 3, "demo 写入未落入 demo 计数"
        assert prod_after == prod_total + 2, "production 写入未落入 production 计数"
        print("PASS | demo/production 环境写入隔离正常")

        print("RESULT | ALL_PASS")
        return 0
    finally:
        try:
            snap.unlink(missing_ok=True)
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
