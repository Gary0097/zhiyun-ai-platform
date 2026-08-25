# -*- coding: utf-8 -*-
"""Time Machine 趋势分析（Epic 4）。

提供一套与日期无关的共享时间口径聚合：按日/周/月生成活动曲线、
工作日与周末对比、以及企业智能体/用户增长曲线。企业环境初始化器的
/analytics/trends 前端与各业务 Studio 都复用本模块，保证所有
Dashboard 在同一份时间段数据源上计算，避免各页面自行判断时间范围。
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from typing import Any

# 指标 key -> (表名, 日期列表达式)；日期列表达式已归一化为 YYYY-MM-DD。
_ACTIVITY = {
    "sessions": ("sessions", "substr(started_at, 1, 10)"),
    "tasks": ("tasks", "substr(started_at, 1, 10)"),
    "files": ("files", "substr(created_at, 1, 10)"),
    "downloads": ("file_downloads", "substr(downloaded_at, 1, 10)"),
    "logins": ("login_activity", "day"),
    "operations": ("operation_logs", "day"),
}

_SERIES_KEYS = ["sessions", "tasks", "tokens", "calls", "files", "downloads", "logins", "operations"]


def _parse_day(value):
    return date.fromisoformat(value[:10])


def _wday(value):
    """返回 0=周一 .. 6=周日。"""
    return _parse_day(value).weekday()


def _end_of_month(d):
    if d.month == 12:
        return date(d.year, 12, 31)
    return date(d.year, d.month + 1, 1) - timedelta(days=1)


def _next_month(d):
    if d.month == 12:
        return date(d.year + 1, 1, 1)
    return date(d.year, d.month + 1, 1)


def _bucket_key(value, granularity):
    d = _parse_day(value)
    if granularity == "month":
        return d.strftime("%Y-%m")
    if granularity == "week":
        iso = d.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    return value


def _bucket_label(value, granularity):
    d = _parse_day(value)
    if granularity == "month":
        return d.strftime("%Y年%m月")
    if granularity == "week":
        return value
    return d.strftime("%m-%d")


def _count_rows(conn, table, day_expr, env_id, data_mode, start, end):
    sql = (
        f"SELECT {day_expr} AS d, COUNT(*) AS v FROM {table} "
        f"WHERE env_id = ? AND data_mode = ? AND substr({day_expr}, 1, 10) BETWEEN ? AND ? "
        f"GROUP BY {day_expr}"
    )
    rows = conn.execute(sql, (env_id, data_mode, start, end)).fetchall()
    out = {}
    for r in rows:
        d = str(r["d"])[:10]
        out[d] = out.get(d, 0.0) + float(r["v"] or 0)
    return out


def _tokens_series(conn, env_id, data_mode, start, end):
    sql = (
        "SELECT day AS d, COALESCE(SUM(tokens),0) AS t, COALESCE(SUM(calls),0) AS c "
        "FROM token_usage WHERE env_id = ? AND data_mode = ? AND substr(day,1,10) BETWEEN ? AND ? "
        "GROUP BY day"
    )
    rows = conn.execute(sql, (env_id, data_mode, start, end)).fetchall()
    tok, call = {}, {}
    for r in rows:
        d = str(r["d"])[:10]
        tok[d] = tok.get(d, 0.0) + float(r["t"] or 0)
        call[d] = call.get(d, 0.0) + float(r["c"] or 0)
    return tok, call


def _daily_buckets(start, end):
    """返回 [start, end] 之间每一天的 YYYY-MM-DD，含两端。"""
    s = _parse_day(start)
    e = _parse_day(end)
    if e < s:
        s, e = e, s
    days = []
    cur = s
    while cur <= e:
        days.append(cur.isoformat())
        cur += timedelta(days=1)
    return days


def _first_activity_cumulative(conn, table, group_col, date_col, env_id, data_mode, start, end):
    """按实体的首次活跃日期做累计增长曲线。

    例如智能体增长 = 每个 agent_id 在 sessions 中最早出现的日期 <= 月末的个数；
    用户增长 = 每个 user_id 在 sessions 中最早出现的日期 <= 月末的个数。
    这样增长曲线反映的是「企业运行了多少个智能体/员工」随时间的爬升。
    """
    sql = (
        f"WITH f AS (SELECT {group_col} AS g, MIN({date_col}) AS fa FROM {table} "
        f"WHERE env_id = ? AND data_mode = ? GROUP BY {group_col}) "
        "SELECT g, fa FROM f WHERE g IS NOT NULL AND g != ''"
    )
    rows = conn.execute(sql, (env_id, data_mode)).fetchall()
    firsts = {}
    for r in rows:
        g = r["g"]
        raw = r["fa"]
        fa = str(raw)[:10] if raw is not None else ""
        if g and len(fa) == 10 and fa[4] == "-" and fa[7] == "-":
            if g not in firsts or fa < firsts[g]:
                firsts[g] = fa
    out = []
    cur = _parse_day(start).replace(day=1)
    end_ref = _parse_day(end).replace(day=1)
    end_day = _parse_day(end)
    while cur <= end_ref:
        cutoff = _end_of_month(cur)
        if cur == end_ref:
            cutoff = end_day
        elif cutoff > end_ref:
            cutoff = end_ref
        cutoff_iso = cutoff.isoformat()
        total = sum(1 for fa in firsts.values() if fa <= cutoff_iso)
        out.append({"period": cur.strftime("%Y-%m"), "label": cur.strftime("%Y年%m月"), "total": total})
        cur = _next_month(cur)
    return out


def _activity_point(b, with_label=False):
    out = {k: b.get(k, 0) for k in _SERIES_KEYS}
    if with_label:
        out["period"] = b.get("period")
        out["label"] = b.get("label")
    return out


def build_trends(conn, *, env_id, data_mode, start_date, end_date, granularity="day"):
    """构造时间趋势聚合结果。

    返回 series（按时间分桶的活动量）、workday_avg / weekend_avg（工作日与
    周末平均活跃）、growth（智能体与用户按首次活跃日期的累计增长）、summary（区间总量）。
    """
    day_metrics = {}
    for skey, (table, day_expr) in _ACTIVITY.items():
        series = _count_rows(conn, table, day_expr, env_id, data_mode, start_date, end_date)
        for d, v in series.items():
            day_metrics.setdefault(d, {})[skey] = v
    tok, call = _tokens_series(conn, env_id, data_mode, start_date, end_date)
    for d in set(tok) | set(call):
        day_metrics.setdefault(d, {})["tokens"] = tok.get(d, 0.0)
        day_metrics.setdefault(d, {})["calls"] = call.get(d, 0.0)

    buckets = {}
    for d in _daily_buckets(start_date, end_date):
        m = day_metrics.get(d, {})
        buckets[d] = {
            "sessions": int(m.get("sessions", 0)),
            "tasks": int(m.get("tasks", 0)),
            "tokens": int(m.get("tokens", 0)),
            "calls": int(m.get("calls", 0)),
            "files": int(m.get("files", 0)),
            "downloads": int(m.get("downloads", 0)),
            "logins": int(m.get("logins", 0)),
            "operations": int(m.get("operations", 0)),
            "_wday": _wday(d),
        }

    if granularity == "day":
        series = [
            {
                "period": d,
                "label": _bucket_label(d, granularity),
                "weekday": buckets[d]["_wday"],
                "weekend": int(buckets[d]["_wday"] >= 5),
                **_activity_point(buckets[d]),
            }
            for d in buckets
        ]
    else:
        grouped = {}
        for d, b in buckets.items():
            key = _bucket_key(d, granularity)
            g = grouped.setdefault(key, {"period": key, "label": _bucket_label(d, granularity)})
            for k in _SERIES_KEYS:
                g[k] = g.get(k, 0) + b[k]
        series = [_activity_point(g, with_label=True) for g in grouped.values()]

    wd_sessions = [buckets[d]["sessions"] for d in buckets if buckets[d]["_wday"] < 5]
    we_sessions = [buckets[d]["sessions"] for d in buckets if buckets[d]["_wday"] >= 5]
    wd_tokens = [buckets[d]["tokens"] for d in buckets if buckets[d]["_wday"] < 5]
    we_tokens = [buckets[d]["tokens"] for d in buckets if buckets[d]["_wday"] >= 5]
    wd_logins = [buckets[d]["logins"] for d in buckets if buckets[d]["_wday"] < 5]
    we_logins = [buckets[d]["logins"] for d in buckets if buckets[d]["_wday"] >= 5]

    def _avg(vals):
        return round(sum(vals) / len(vals)) if vals else 0

    growth_agents = _first_activity_cumulative(conn, "sessions", "agent_id", "started_at", env_id, data_mode, start_date, end_date)
    growth_users = _first_activity_cumulative(conn, "sessions", "user_id", "started_at", env_id, data_mode, start_date, end_date)

    total = {k: int(sum((g.get(k) or 0) for g in series)) for k in _SERIES_KEYS}
    return {
        "granularity": granularity,
        "start_date": start_date,
        "end_date": end_date,
        "series": series,
        "workday_avg": {
            "sessions": _avg(wd_sessions),
            "tokens": _avg(wd_tokens),
            "logins": _avg(wd_logins),
        },
        "weekend_avg": {
            "sessions": _avg(we_sessions),
            "tokens": _avg(we_tokens),
            "logins": _avg(we_logins),
        },
        "growth": {"agents": growth_agents, "users": growth_users},
        "summary": total,
    }