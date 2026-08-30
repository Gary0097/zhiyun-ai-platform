# -*- coding: utf-8 -*-
"""Isolated end-to-end verification of the Enterprise Seeder (Epics 1-6).

Runs the one-shot initialization against a throwaway SQLite database so the
live service is untouched, then asserts:

  1. One init produces the full entity graph (org -> users -> agents -> skills
     -> apps -> data sources -> sessions -> tasks -> token -> logs -> files).
  2. Demo AND Production environments are created and fully isolated.
  3. Time Machine: a date-window query returns only in-window rows.
  4. Stats are traceable: token_usage sums equal business_events token sums
     and task counts equal tasks rows for the same env/data_mode.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path


def _stub_qwenpaw(workdir: Path) -> None:
    import types
    qwenpaw = types.ModuleType("qwenpaw")
    qwenpaw.__path__ = []
    plugins = types.ModuleType("qwenpaw.plugins")
    plugins.__path__ = []
    constant = types.ModuleType("qwenpaw.constant")
    constant.WORKING_DIR = workdir
    api = types.ModuleType("qwenpaw.plugins.api")
    api.PluginApi = object
    sys.modules["qwenpaw"] = qwenpaw
    sys.modules["qwenpaw.plugins"] = plugins
    sys.modules["qwenpaw.constant"] = constant
    sys.modules["qwenpaw.plugins.api"] = api


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    plugin_root = Path(__file__).resolve().parents[2] / "plugins" / "zhiyun-enterprise-seeder"
    tmp = Path(tempfile.mkdtemp(prefix="seed_verify_"))
    enterprise_dir = tmp / "enterprise"
    workdir = tmp / "work"
    enterprise_dir.mkdir(parents=True, exist_ok=True)
    workdir.mkdir(parents=True, exist_ok=True)

    os.environ["ZHIYUN_ENTERPRISE_DIR"] = str(enterprise_dir)
    os.environ["QWENPAW_WORKING_DIR"] = str(workdir)
    _stub_qwenpaw(workdir)

    sys.path.insert(0, str(plugin_root))
    import enterprise_plugin as ep  # noqa: E402

    today = date.today().isoformat()
    results = []

    def report(name: str, ok: bool, detail: str = "") -> None:
        results.append((name, ok, detail))
        print(("PASS" if ok else "FAIL") + " | " + name + ((" | " + detail) if detail else ""))

    # ---- 1. One-shot init for demo and production ----
    summaries = {}
    for mode in ("demo", "production"):
        s = ep._generate_enterprise({
            "template": "manufacturing", "enterprise": "灵泽万川智造云科技",
            "start_date": "2025-12-01", "end_date": today,
            "scale": 40, "departments": 6, "agents": 12,
            "activity": "medium", "data_mode": mode, "seed": 20260825,
        })
        summaries[mode] = s
        print(f"  [{mode}] env_id={s['env_id']} days={s['days']} users={s['org_users']} "
              f"agents={s['agents']} sessions={s['sessions']} tasks={s['tasks']} tokens={s['token_total']}")

    db = sqlite3.connect(str(enterprise_dir / "enterprise.db"))
    db.row_factory = sqlite3.Row

    meta = {}
    for mode in ("demo", "production"):
        row = db.execute(
            "SELECT env_id, tenant_id, data_mode, enterprise, start_date, end_date FROM enterprise_meta WHERE data_mode=? ORDER BY id DESC LIMIT 1",
            (mode,)
        ).fetchone()
        meta[mode] = dict(row) if row else None
        report(f"{mode}: enterprise_meta 存在", row is not None,
               (row["enterprise"] + " " + row["start_date"] + "~" + row["end_date"]) if row else "missing")
        if row:
            report(f"{mode}: 起始日期为 2025-12-01", row["start_date"] == "2025-12-01", row["start_date"])
            report(f"{mode}: 结束日期为今天或晚于今天", row["end_date"] >= today, f"{row['end_date']} vs {today}")

    # ---- 2. Entity completeness ----
    entities = [
        "departments", "roles", "org_users", "agents", "skills", "apps",
        "data_sources", "agent_tools", "agent_app_access", "sessions",
        "tasks", "token_usage", "operation_logs", "login_activity",
        "files", "file_downloads", "business_events",
    ]
    for mode in ("demo", "production"):
        env = meta[mode]["env_id"] if meta[mode] else ""
        for ent in entities:
            n = db.execute(
                f"SELECT COUNT(*) AS c FROM {ent} WHERE env_id=? AND data_mode=?", (env, mode)
            ).fetchone()["c"]
            report(f"{mode}: {ent} 非空", n > 0, f"count={n}")

    # ---- 3. Time Machine window filter (March 2026 on demo) ----
    demo_env = meta["demo"]["env_id"]
    try:
        rows = db.execute(
            "SELECT started_at FROM sessions WHERE env_id=? AND data_mode='demo' AND substr(started_at,1,10) BETWEEN '2026-03-01' AND '2026-03-31' ORDER BY started_at",
            (demo_env,)
        ).fetchall()
        if rows:
            lo = min(r["started_at"][:10] for r in rows)
            hi = max(r["started_at"][:10] for r in rows)
            in_window = lo >= "2026-03-01" and hi <= "2026-03-31"
            report("Time Machine: 2026-03 窗口会话仅落在窗口内", in_window, f"{lo}~{hi} count={len(rows)}")
        else:
            report("Time Machine: 2026-03 窗口存在会话", False, "no rows in window")
    except Exception as exc:
        report("Time Machine: 2026-03 窗口会话仅落在窗口内", False, str(exc))

    # ---- 4. Dual-state isolation ----
    prod_env = meta["production"]["env_id"]
    demo_sessions = db.execute(
        "SELECT COUNT(*) AS c FROM sessions WHERE env_id=? AND data_mode='demo'", (demo_env,)
    ).fetchone()["c"]
    prod_sessions = db.execute(
        "SELECT COUNT(*) AS c FROM sessions WHERE env_id=? AND data_mode='production'", (prod_env,)
    ).fetchone()["c"]
    crossing = db.execute(
        "SELECT COUNT(*) AS c FROM sessions WHERE env_id=? AND data_mode='production'", (demo_env,)
    ).fetchone()["c"]
    report("双态隔离: demo/production 各自有会话", demo_sessions > 0 and prod_sessions > 0,
           f"demo={demo_sessions} prod={prod_sessions}")
    report("双态隔离: demo env 不泄漏 production 记录", crossing == 0, f"crossing={crossing}")

    # ---- 5. Stats traceability (demo) ----
    sum_token_usage = db.execute(
        "SELECT COALESCE(SUM(tokens),0) AS s FROM token_usage WHERE env_id=? AND data_mode='demo'", (demo_env,)
    ).fetchone()["s"]
    sum_bus_events = db.execute(
        "SELECT COALESCE(SUM(tokens),0) AS s FROM business_events WHERE env_id=? AND data_mode='demo'", (demo_env,)
    ).fetchone()["s"]
    sum_bus_task = db.execute(
        "SELECT COALESCE(SUM(tokens),0) AS s FROM business_events WHERE env_id=? AND data_mode='demo' AND event_type='task'", (demo_env,)
    ).fetchone()["s"]
    sum_task_token = db.execute(
        "SELECT COALESCE(SUM(tokens),0) AS s FROM tasks WHERE env_id=? AND data_mode='demo'", (demo_env,)
    ).fetchone()["s"]
    task_rows = db.execute(
        "SELECT COUNT(*) AS c FROM tasks WHERE env_id=? AND data_mode='demo'", (demo_env,)
    ).fetchone()["c"]
    calls_in_token = db.execute(
        "SELECT COALESCE(SUM(calls),0) AS s FROM token_usage WHERE env_id=? AND data_mode='demo'", (demo_env,)
    ).fetchone()["s"]
    report("统计可追溯: token_usage.token == business_events(全量).token", sum_token_usage == sum_bus_events,
           f"token_usage={sum_token_usage} events={sum_bus_events}")
    report("统计可追溯: token_usage.token == business_events(仅task).token", sum_token_usage == sum_bus_task,
           f"token_usage={sum_token_usage} bus_task={sum_bus_task}")
    report("统计可追溯: business_events(仅task).token == tasks.token", sum_bus_task == sum_task_token,
           f"bus_task={sum_bus_task} tasks={sum_task_token}")
    report("统计可追溯: tasks 行数 == token_usage.calls", task_rows == calls_in_token,
           f"tasks={task_rows} calls={calls_in_token}")

    # ---- 6. Agent -> Skill -> Tool -> App binding exists ----
    bindings = db.execute(
        "SELECT COUNT(*) AS c FROM agent_tools WHERE env_id=? AND data_mode='demo'", (demo_env,)
    ).fetchone()["c"]
    agent_skill = db.execute(
        "SELECT COUNT(*) AS c FROM skills WHERE env_id=? AND data_mode='demo'", (demo_env,)
    ).fetchone()["c"]
    report("Epic2: Agent->Skill->Tool 绑定落地", bindings >= 0 and agent_skill > 0,
           f"skills={agent_skill} agent_tools={bindings}")

    db.close()
    passed = sum(1 for *_, ok, _ in results if ok)
    total = len(results)
    print("\n" + "=" * 70)
    print(f"RESULT: {passed}/{total} checks passed")
    out = {
        "generated_at": date.today().isoformat(),
        "tmp_db": str(enterprise_dir / "enterprise.db"),
        "summaries": summaries,
        "checks": [{"name": n, "ok": ok, "detail": d} for (n, ok, d) in results],
        "passed": passed,
        "total": total,
    }
    out_dir = Path(__file__).resolve().parents[2] / "docs" / "qa"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "enterprise-fresh-init-verify.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"report: {out_dir / 'enterprise-fresh-init-verify.json'}")
    shutil.rmtree(tmp, ignore_errors=True)
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
