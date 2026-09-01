# -*- coding: utf-8 -*-
"""智能分析驾驶舱（模块成熟度首个落地项：智能 + 分析 + 可视化 + 数据流转）。

在企业库统一时间口径（与 analytics.build_trends 同源）之上产出：
  1. 趋势结论：近 7 天 vs 前 7 天环比（会话/Token/活跃用户/任务完成），
     生成可直接放进经营周报的中文结论与贡献部门归因；
  2. 异常检测：日活序列 z-score，|z| ≥ 2 标记为异常日并区分
     突增/骤降（附工作日/周末语境，避免把周末低谷误报为异常）；
  3. TopN 榜单：最活跃智能体 / 用户 / 部门（按会话数 + Token 加权）；
  4. 数据流转：输入侧（上传/导入/生成）→ 消费侧（下载/导出/工单引用）
     的通道计数，回答“数据从哪来、到哪去”。
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any


def _avg(vals):
    return sum(vals) / len(vals) if vals else 0.0


def _std(vals):
    if len(vals) < 2:
        return 0.0
    mu = _avg(vals)
    return math.sqrt(sum((v - mu) ** 2 for v in vals) / (len(vals) - 1))


def _pct(cur, prev):
    if prev <= 0:
        return None
    return round((cur - prev) / prev * 100, 1)


def build_insights(conn, *, env_id: str, data_mode: str,
                   start_date: str, end_date: str) -> dict[str, Any]:
    end = date.fromisoformat(end_date[:10])
    start = date.fromisoformat(start_date[:10])
    # 环比窗口固定看最近 14 天：后 7 天 vs 前 7 天
    # 等长 7 天窗口（含端点）：当前 = end-6..end，对照 = end-13..end-7
    win_end = end
    win_mid = end - timedelta(days=6)
    win_start = end - timedelta(days=13)
    scope = max(start, win_start)

    base = "WHERE env_id = ? AND data_mode = ?"
    args = (env_id, data_mode)

    def day_series(sql, a=()):
        rows = conn.execute(sql, a).fetchall()
        return {r[0]: r[1] for r in rows}

    sessions_by_day = day_series(
        f"SELECT substr(started_at,1,10) d, COUNT(*) n FROM sessions {base} "
        "AND started_at >= ? GROUP BY d", args + (scope.isoformat(),))
    tokens_by_day = day_series(
        f"SELECT day, SUM(tokens) n FROM token_usage {base} "
        "AND day >= ? GROUP BY day", args + (scope.isoformat(),))

    tasks_done = day_series(
        f"SELECT substr(finished_at,1,10) d, COUNT(*) n FROM tasks {base} "
        "AND status='success' AND finished_at >= ? GROUP BY d", args + (scope.isoformat(),))

    def window(series, a, b):
        a_s, b_s = a.isoformat(), b.isoformat()
        return sum(v for k, v in series.items() if a_s <= k <= b_s)

    # 活跃智能体按“窗口整体一次 DISTINCT”统计：按日 DISTINCT 求和会重复计
    # 跨天出现的同一智能体，环比口径系统性偏高。
    def active_agents(a, b):
        row = conn.execute(
            f"SELECT COUNT(DISTINCT agent_id) n FROM sessions {base} "
            "AND started_at >= ? AND started_at < ?", args + (a.isoformat(), b.isoformat())).fetchone()
        return row["n"]

    cur = {"sessions": window(sessions_by_day, win_mid, win_end),
           "tokens": window(tokens_by_day, win_mid, win_end),
           "users": active_agents(win_mid, win_end + timedelta(days=1)),
           "tasks": window(tasks_done, win_mid, win_end)}
    prev = {"sessions": window(sessions_by_day, win_start, win_mid - timedelta(days=1)),
            "tokens": window(tokens_by_day, win_start, win_mid - timedelta(days=1)),
            "users": active_agents(win_start, win_mid),
            "tasks": window(tasks_done, win_start, win_mid - timedelta(days=1))}

    label = {"sessions": "会话量", "tokens": "Token 消耗", "users": "活跃智能体", "tasks": "完成任务"}
    trends = []
    for key in ("sessions", "tokens", "users", "tasks"):
        p = _pct(cur[key], prev[key])
        if p is None:
            trends.append({"metric": label[key], "current": cur[key], "previous": prev[key],
                           "change_pct": None, "text": f"{label[key]}近 7 天 {cur[key]}（前 7 天无数据）"})
        else:
            direction = "上升" if p >= 0 else "下降"
            trends.append({"metric": label[key], "current": cur[key], "previous": prev[key],
                           "change_pct": p,
                           "text": f"{label[key]}近 7 天 {cur[key]}，环比{direction} {abs(p)}%"})

    # 归因：环比变化最大的部门（按部门会话占比）
    dept_rows = conn.execute(
        f"SELECT app_id, COUNT(*) n FROM sessions {base} "
        "AND started_at >= ? GROUP BY app_id ORDER BY n DESC LIMIT 5",
        args + (win_mid.isoformat(),)).fetchall()
    top_dept = [dict(name=r["app_id"] or "未知应用", sessions=r["n"]) for r in dept_rows]

    # ── 异常检测：全期日活 z-score（区分周末语境） ──
    all_days = sorted(sessions_by_day.keys())
    vals = [sessions_by_day[d] for d in all_days]
    mu, sigma = _avg(vals), _std(vals)
    anomalies = []
    for d in all_days:
        z = (sessions_by_day[d] - mu) / sigma if sigma > 0 else 0
        if abs(z) >= 2:
            weekend = date.fromisoformat(d).weekday() >= 5
            kind = "突增" if z > 0 else "骤降"
            ctx = "（周末，低谷属正常）" if (weekend and z < 0) else ""
            anomalies.append({"date": d, "sessions": sessions_by_day[d], "z": round(z, 2),
                              "kind": kind, "context": ctx})

    # ── TopN：智能体 / 用户 / 部门 ──
    def topn(sql, name_key):
        rows = conn.execute(sql, args + (start.isoformat(),)).fetchall()
        return [dict(name=r[name_key] or "-", sessions=r["n"], tokens=r["t"]) for r in rows]

    top_agents = topn(
        f"SELECT agent_id as name, COUNT(*) n, 0 as t FROM sessions {base} "
        "AND started_at >= ? GROUP BY agent_id ORDER BY n DESC LIMIT 5", "name")
    top_users = topn(
        f"SELECT user_id as name, COUNT(*) n, 0 as t FROM sessions {base} "
        "AND started_at >= ? GROUP BY user_id ORDER BY n DESC LIMIT 5", "name")
    top_depts = topn(
        f"SELECT app_id as name, COUNT(*) n, 0 as t FROM sessions {base} "
        "AND started_at >= ? GROUP BY app_id ORDER BY n DESC LIMIT 5", "name")
    top_depts = topn(
        f"SELECT app_id as name, COUNT(*) n, 0 as t FROM sessions {base} "
        "AND started_at >= ? GROUP BY app_id ORDER BY n DESC LIMIT 5", "name")

    # ── 数据流转：输入通道 vs 消费通道 ──
    inflow = {}
    try:
        for row in conn.execute(
                f"SELECT source_type, COUNT(*) n FROM data_records {base} GROUP BY source_type", args):
            inflow[row["source_type"] or "unknown"] = row["n"]
    except Exception:  # noqa: BLE001 — 纯会话型环境无该表
        inflow = {}
    if not inflow:
        inflow["会话产生"] = conn.execute(
            f"SELECT COUNT(*) n FROM sessions {base}", args).fetchone()["n"]
    outflow = {"downloads": conn.execute(
        f"SELECT COUNT(*) n FROM file_downloads {base} AND downloaded_at >= ?",
        args + (start.isoformat(),)).fetchone()["n"]}
    # 工单/业务事件引用（消费下游）
    try:
        outflow["business_events"] = conn.execute(
            f"SELECT COUNT(*) n FROM business_events {base} AND day >= ?",
            args + (start.isoformat(),)).fetchone()["n"]
    except Exception:  # noqa: BLE001 — 表可能尚未迁移
        pass

    flow_summary = (
        f"数据输入 {sum(inflow.values())} 条（" +
        "、".join(f"{k} {v}" for k, v in sorted(inflow.items(), key=lambda kv: -kv[1])) +
        f"）；消费侧下载 {outflow.get('downloads', 0)} 次、业务事件引用 {outflow.get('business_events', 0)} 次。"
    )

    # ── 总结论（智能摘要） ──
    headline_parts = [t["text"] for t in trends]
    summary = "；".join(headline_parts) + "。"
    if top_dept:
        summary += f"主要贡献应用：{top_dept[0]['name']}（{top_dept[0]['sessions']} 次会话）。"
    if anomalies:
        a0 = anomalies[0]
        summary += f"检测到 {len(anomalies)} 个异常日（最近：{a0['date']} {a0['kind']}{a0['context']}）。"

    return {
        "range": {"start_date": start_date, "end_date": end_date},
        "compare_window": {"current": [win_mid.isoformat(), win_end.isoformat()],
                           "previous": [win_start.isoformat(), (win_mid - timedelta(days=1)).isoformat()]},
        "summary": summary,
        "trends": trends,
        "top_apps_recent": top_dept,
        "anomalies": anomalies,
        "top_agents": top_agents,
        "top_users": top_users,
        "top_apps": top_depts,
        "data_flow": {"inflow": inflow, "outflow": outflow, "summary": flow_summary},
    }
