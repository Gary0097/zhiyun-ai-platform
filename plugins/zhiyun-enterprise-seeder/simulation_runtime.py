from __future__ import annotations

import random
import zlib
import uuid
from datetime import date, datetime, timedelta
from typing import Any

"""Simulation Runtime / Business Activity Generator (Epic 3).

把「直接插数据」升级为可追溯的事件流：
    业务事件 -> Agent 执行 -> Skill 调用 -> Tool 调用 -> 结果工件
    -> 下载 -> Token -> 用户行为 -> 统计。

核心契约：`build_day_events` 只构建内存计划（不写库），
`execute_day_events` 将计划写进 sessions/tasks/files/file_downloads/
token_usage，并为每一步写一条 `business_events` 审计行，使任何统计都能
追溯到具体业务事件。

本模块刻意自包含（不反向 import enterprise_plugin），供 seeder 与独立
`/simulation` 接口共用。
"""

_FORMATS = ["xlsx", "csv", "pdf", "docx", "md", "json"]
_LOGIN_DEVICES = ["桌面端 Chrome", "桌面端 Edge", "桌面端 Firefox", "移动端 Chrome", "移动端 Safari"]
_DEFAULT_FILE_KIND = ("成果文件", "general", _FORMATS)
_FILE_KINDS = {
    "销售报价": ("报价单", "sales", ["xlsx", "pdf"]),
    "客户跟进": ("客户跟进记录", "customer", ["docx", "md"]),
    "邮件营销": ("营销邮件", "marketing", ["docx", "html", "pdf"]),
    "采购对账": ("对账单", "supply", ["xlsx", "pdf"]),
    "财务票据": ("票据凭证", "finance", ["pdf", "xlsx"]),
    "售后客服": ("工单记录", "service", ["pdf", "md"]),
    "经营分析": ("经营分析报告", "analytics", ["xlsx", "pdf"]),
    "生产计划": ("排产计划", "production", ["xlsx", "csv"]),
    "库存管理": ("库存盘点表", "inventory", ["xlsx", "csv"]),
    "报销审核": ("报销单", "finance", ["pdf", "xlsx"]),
    "财务分析": ("财务分析报告", "analytics", ["xlsx", "pdf"]),
    "成本预测": ("成本预测表", "analytics", ["xlsx", "csv"]),
}

DEPT_APP_MAP = {
    "销售部": ["sales_center", "data_center", "project_center", "qwenpaw-knowledge-base"],
    "财务部": ["finance_center", "data_center", "project_center", "qwenpaw-knowledge-base"],
    "采购部": ["supply_center", "data_center", "project_center", "qwenpaw-knowledge-base"],
    "客服部": ["service_center", "data_center", "project_center", "qwenpaw-knowledge-base"],
    "运营部": ["sales_center", "supply_center", "data_center", "project_center", "qwenpaw-knowledge-base"],
    "生产部": ["order_center", "data_center", "project_center", "qwenpaw-knowledge-base"],
    "管理层": ["finance_center", "sales_center", "data_center", "project_center", "qwenpaw-knowledge-base"],
    "研发部": ["project_center", "data_center", "order_center", "qwenpaw-knowledge-base"],
}

BUSINESS_EVENTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS business_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT, env_id TEXT, tenant_id TEXT, data_mode TEXT,
    day TEXT, user_id TEXT, agent_id TEXT, app_id TEXT,
    event_type TEXT, session_id TEXT, task_id TEXT, file_id TEXT,
    download_id TEXT, skill_id TEXT, tool_id TEXT,
    tokens INTEGER, success INTEGER, latency_ms INTEGER,
    started_at TEXT, created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_bus_events_env ON business_events(env_id, data_mode, day);
CREATE INDEX IF NOT EXISTS idx_bus_events_session ON business_events(session_id);
CREATE INDEX IF NOT EXISTS idx_bus_events_task ON business_events(task_id);
CREATE INDEX IF NOT EXISTS idx_bus_events_file ON business_events(file_id);
CREATE INDEX IF NOT EXISTS idx_bus_events_user ON business_events(env_id, data_mode, user_id);
CREATE INDEX IF NOT EXISTS idx_bus_events_agent ON business_events(env_id, data_mode, agent_id);
"""


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _parse_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def _stable_day_seed(seed: int, di: int, env_id: str, day: date) -> int:
    """生成跨进程、跨调用稳定的每日随机种子（避免 PYTHONHASHSEED 漂移）。"""
    stable = zlib.crc32(f"{env_id}|{day.isoformat()}".encode("utf-8"))
    return (int(seed) + di * 7919 + stable) & 0x7FFFFFFF


def _workday_factor(d: date) -> float:
    wd = d.weekday()
    if wd == 5:
        return 0.22
    if wd == 6:
        return 0.14
    return 1.0


def _month_factor(d: date) -> float:
    if d.day <= 3:
        return 1.32
    if d.day >= 25:
        return 1.22
    return 1.0


def _activity_multiplier(activity: str) -> float:
    return {"low": 0.55, "medium": 1.0, "high": 1.55}.get(activity, 1.0)


def _pick_time(rng: random.Random, auto: bool = False) -> str:
    if auto or rng.random() < 0.02:
        hour = rng.choice([0, 1, 2, 3, 4, 5, 6, 22, 23])
        minute = rng.randint(0, 59)
        return f"{hour:02d}:{minute:02d}"
    slot = rng.random()
    if slot < 0.55:
        hour = rng.randint(9, 11)
    else:
        hour = rng.randint(14, 17)
    minute = rng.randint(0, 59)
    return f"{hour:02d}:{minute:02d}"


def _shift_time(t: str, ms: int) -> str:
    try:
        base = datetime.strptime(t, "%H:%M")
        return (base + timedelta(milliseconds=ms)).strftime("%H:%M:%S")
    except (ValueError, TypeError):
        return "00:00:00"


def ensure_schema(conn: Any) -> None:
    conn.executescript(BUSINESS_EVENTS_SCHEMA)


def _empty_plan(day: date) -> dict[str, Any]:
    return {
        "day": day.isoformat(),
        "env_id": "",
        "tenant_id": "",
        "data_mode": "",
        "events": [],
        "logins": [],
        "operations": [],
        "token_bucket": {},
        "stats": {"sessions": 0, "calls": 0, "success": 0, "failed": 0, "tokens": 0},
    }


def build_day_events(
    day: date,
    active_users: list[dict[str, Any]],
    enabled_agents: list[dict[str, Any]],
    agents_by_id: dict[str, dict[str, Any]],
    dept_apps: dict[str, list[dict[str, Any]]],
    apps_by_id: dict[str, dict[str, Any]],
    env_id: str,
    tenant_id: str,
    data_mode: str,
    activity_mult: float,
    rng: random.Random,
) -> dict[str, Any]:
    """构建某一天的完整业务事件计划（不写库）。与旧生成逻辑逐字节等价，仅改为计划对象。"""
    work = _workday_factor(day)
    month = _month_factor(day)
    if work < 0.2:
        plan = _empty_plan(day)
        plan["env_id"], plan["tenant_id"], plan["data_mode"] = env_id, tenant_id, data_mode
        return plan

    sessions_per_user = 2.6 * activity_mult
    session_count = int(round(len(active_users) * sessions_per_user * work * month))
    session_count = max(0, min(session_count, 420))

    plan: dict[str, Any] = {
        "day": day.isoformat(),
        "env_id": env_id,
        "tenant_id": tenant_id,
        "data_mode": data_mode,
        "events": [],
        "logins": [],
        "operations": [],
        "token_bucket": {},
        "stats": {"sessions": 0, "calls": 0, "success": 0, "failed": 0, "tokens": 0},
    }
    stats = plan["stats"]

    for _ in range(session_count):
        user = rng.choice(active_users)
        agent = agents_by_id.get(user["agent_id"])
        if not agent or agent.get("enabled", 1) == 0:
            continue
        app = rng.choice(dept_apps.get(user["department"], dept_apps.get("total", [
            {"app_id": "data_center", "name": "统一数据中心"}])))
        session_id = "s_" + uuid.uuid4().hex[:12]
        started = _pick_time(rng)
        messages = rng.randint(2, 12)
        latency = agent["avg_response_ms"] + rng.randint(-300, 500)
        success = rng.random() < agent["success_rate"]
        status = "completed" if success else "failed"
        per_msg = rng.randint(70, 320)
        tokens = int(messages * per_msg + rng.randint(150, 1400) * (0.6 + 0.4 * work))
        ended_hms = _shift_time(started, latency)

        plan["events"].append({
            "type": "session",
            "session_id": session_id,
            "user_id": user["username"],
            "agent_id": agent["agent_id"],
            "app_id": app["app_id"],
            "messages": messages,
            "started_at": f"{day.isoformat()} {started}:00",
            "ended_at": f"{day.isoformat()} {ended_hms}",
            "status": status,
            "tokens": tokens,
            "success": 1 if success else 0,
        })

        task_count = rng.randint(1, 3)
        for t in range(task_count):
            skills = agent.get("skills") or []
            skill = skills[rng.randint(0, len(skills) - 1)] if skills else ("通用任务", "generic")
            task_id = "t_" + uuid.uuid4().hex[:12]
            task_ok = success
            task_tokens = int(tokens / task_count) + rng.randint(20, 120)
            tools = list(agent.get("tools") or [])
            tool_id = tools[t % len(tools)] if tools else None
            plan["events"].append({
                "type": "task",
                "task_id": task_id,
                "session_id": session_id,
                "user_id": user["username"],
                "agent_id": agent["agent_id"],
                "app_id": app["app_id"],
                "skill_id": skill[1] if len(skill) > 1 else skill,
                "skill_name": skill[0] if len(skill) > 1 else skill,
                "tool_id": tool_id,
                "status": status,
                "success": 1 if task_ok else 0,
                "started_at": f"{day.isoformat()} {started}:00",
                "finished_at": f"{day.isoformat()} {ended_hms}",
                "latency_ms": latency,
                "tokens": task_tokens,
                "result": "已生成" if task_ok else "执行异常",
            })

            if task_ok and rng.random() < 0.62:
                kind = _FILE_KINDS.get(agent["position"], _DEFAULT_FILE_KIND)
                base_name, category, formats = kind
                file_id = "f_" + uuid.uuid4().hex[:12]
                fmt = rng.choice(formats)
                size_kb = rng.randint(18, 1600)
                name = f"{base_name}_{day.strftime('%m%d')}_{rng.randint(100, 999)}.{fmt}"
                download_count = rng.choice([0, 1, 1, 2, 2, 3, 4])
                downloaded = 1 if download_count > 0 else 0
                plan["events"].append({
                    "type": "file",
                    "file_id": file_id,
                    "task_id": task_id,
                    "session_id": session_id,
                    "user_id": user["username"],
                    "agent_id": agent["agent_id"],
                    "app_id": app["app_id"],
                    "name": name,
                    "category": category,
                    "format": fmt,
                    "size_kb": size_kb,
                    "download_count": download_count,
                    "downloaded": downloaded,
                    "created_at": f"{day.isoformat()} {started}:00",
                })
                for _d in range(download_count):
                    dl_id = "dl_" + uuid.uuid4().hex[:12]
                    dl_time = _pick_time(rng)
                    ip = f"10.{rng.randint(10, 48)}.{rng.randint(1, 254)}.{rng.randint(1, 254)}"
                    plan["events"].append({
                        "type": "download",
                        "download_id": dl_id,
                        "file_id": file_id,
                        "task_id": task_id,
                        "user_id": user["username"],
                        "agent_id": agent["agent_id"],
                        "app_id": app["app_id"],
                        "downloaded_at": f"{day.isoformat()} {dl_time}:00",
                        "ip": ip,
                        "device": rng.choice(_LOGIN_DEVICES),
                    })

            key = (agent["agent_id"], app["app_id"], user["username"])
            bucket = plan["token_bucket"].setdefault(key, {"tokens": 0, "calls": 0, "success": 0, "failed": 0})
            bucket["tokens"] += task_tokens
            bucket["calls"] += 1
            if task_ok:
                bucket["success"] += 1
            else:
                bucket["failed"] += 1
            stats["calls"] += 1
            stats["tokens"] += task_tokens
            if task_ok:
                stats["success"] += 1
            else:
                stats["failed"] += 1

        stats["sessions"] += 1

    # 登录活动：非全员每日登录，带业务波动并随机失败，避免"所有用户每天登录"的生成痕迹。
    logins: list[dict[str, Any]] = []
    lf = work * month
    if lf > 0.1 and active_users:
        ratio = min(0.85, 0.30 + 0.40 * activity_mult * lf)
        login_count = max(1, int(round(len(active_users) * ratio)))
        login_pool = rng.sample(active_users, min(login_count, len(active_users)))
        for u in login_pool:
            lapp = rng.choice(dept_apps.get(u["department"], dept_apps.get("total", [
                {"app_id": "data_center", "name": "统一数据中心"}])))
            login_ok = rng.random() < 0.96
            logins.append({
                "user_id": u["username"],
                "agent_id": u["agent_id"],
                "app_id": lapp["app_id"],
                "login_at": f"{day.isoformat()} {_pick_time(rng)}:00",
                "ip": f"10.{rng.randint(10, 48)}.{rng.randint(1, 254)}.{rng.randint(1, 254)}",
                "device": rng.choice(_LOGIN_DEVICES),
                "success": 1 if login_ok else 0,
                "status": "在线" if login_ok else "登出",
            })
    plan["logins"] = logins

    # 操作日志：抽样记录打开应用、触发智能体。
    operations: list[dict[str, Any]] = []
    if active_users and rng.random() < 0.5:
        u = rng.choice(active_users)
        app = rng.choice(dept_apps.get(u["department"], dept_apps.get("total", [
            {"app_id": "data_center", "name": "统一数据中心"}])))
        operations.append({
            "user_id": u["username"],
            "agent_id": u["agent_id"],
            "app_id": app["app_id"],
            "action": "应用访问",
            "detail": f"{u.get('display_name', u['username'])} 打开 {app['name']}",
            "level": "info",
        })
    plan["operations"] = operations

    return plan


def execute_day_events(conn: Any, plan: dict[str, Any]) -> dict[str, Any]:
    """执行某天的业务事件计划，写入业务表并生成 business_events 审计行。"""
    env_id = plan["env_id"]
    tenant_id = plan.get("tenant_id") or ""
    data_mode = plan["data_mode"]
    created = _now()

    for ev in plan["events"]:
        et = ev["type"]
        event_id = "be_" + uuid.uuid4().hex[:12]
        # 审计 Token 只以任务级为准；session/file/download/login 等事件不重复记 Token，
        # 保证 sum(business_events.tokens) == sum(token_usage.tokens) == sum(tasks.tokens)。
        audit_tokens = ev.get("tokens", 0) if et == "task" else 0
        conn.execute(
            "INSERT INTO business_events (event_id, env_id, tenant_id, data_mode, day, user_id, agent_id, app_id, "
            "event_type, session_id, task_id, file_id, download_id, skill_id, tool_id, tokens, success, latency_ms, "
            "started_at, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                event_id, env_id, tenant_id, data_mode, plan["day"],
                ev.get("user_id"), ev.get("agent_id"), ev.get("app_id"), et,
                ev.get("session_id"), ev.get("task_id"), ev.get("file_id"), ev.get("download_id"),
                ev.get("skill_id"), ev.get("tool_id"), audit_tokens, ev.get("success", 0),
                ev.get("latency_ms", 0), ev.get("started_at", ""), created,
            ),
        )
        if et == "session":
            conn.execute(
                "INSERT INTO sessions (env_id, tenant_id, data_mode, session_id, user_id, agent_id, app_id, messages, started_at, ended_at, status, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (env_id, tenant_id, data_mode, ev["session_id"], ev["user_id"], ev["agent_id"], ev["app_id"],
                 ev["messages"], ev["started_at"], ev["ended_at"], ev["status"], created),
            )
        elif et == "task":
            conn.execute(
                "INSERT INTO tasks (env_id, tenant_id, data_mode, task_id, session_id, agent_id, user_id, app_id, skill_id, label, status, success, started_at, finished_at, latency_ms, tokens, result, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (env_id, tenant_id, data_mode, ev["task_id"], ev["session_id"], ev["agent_id"], ev["user_id"],
                 ev["app_id"], ev["skill_id"], ev["skill_name"], ev["status"], ev["success"],
                 ev["started_at"], ev["finished_at"], ev["latency_ms"], ev["tokens"], ev["result"], created),
            )
        elif et == "file":
            conn.execute(
                "INSERT INTO files (env_id, tenant_id, data_mode, file_id, task_id, session_id, agent_id, user_id, app_id, name, category, format, size_kb, download_count, downloaded, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (env_id, tenant_id, data_mode, ev["file_id"], ev["task_id"], ev["session_id"], ev["agent_id"],
                 ev["user_id"], ev["app_id"], ev["name"], ev["category"], ev["format"], ev["size_kb"],
                 ev["download_count"], ev["downloaded"], ev["created_at"]),
            )
        elif et == "download":
            conn.execute(
                "INSERT INTO file_downloads (env_id, tenant_id, data_mode, download_id, file_id, task_id, user_id, agent_id, app_id, downloaded_at, ip, device, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (env_id, tenant_id, data_mode, ev["download_id"], ev["file_id"], ev["task_id"], ev["user_id"],
                 ev["agent_id"], ev["app_id"], ev["downloaded_at"], ev["ip"], ev["device"], created),
            )

    for (agent_id, app_id, username), bucket in plan["token_bucket"].items():
        conn.execute(
            "INSERT INTO token_usage (env_id, tenant_id, data_mode, day, agent_id, app_id, user_id, tokens, calls, success, failed, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (env_id, tenant_id, data_mode, plan["day"], agent_id, app_id, username,
             bucket["tokens"], bucket["calls"], bucket["success"], bucket["failed"], created),
        )

    # 登录活动：写 login_activity，并记一条业务事件（登录 -> 打开应用链路）。
    for lg in plan.get("logins", []):
        log_business_event(
            conn, env_id, tenant_id, data_mode, plan["day"], "login",
            user_id=lg["user_id"], agent_id=lg["agent_id"], app_id=lg["app_id"],
            success=lg["success"], latency_ms=0, started_at=lg["login_at"],
        )
        conn.execute(
            "INSERT INTO login_activity (env_id, tenant_id, data_mode, day, user_id, agent_id, app_id, login_at, ip, device, success, status, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (env_id, tenant_id, data_mode, plan["day"], lg["user_id"], lg["agent_id"], lg["app_id"],
             lg["login_at"], lg["ip"], lg["device"], lg["success"], lg["status"], created),
        )

    # 操作日志：抽样记录进入应用、触发智能体。
    for op in plan.get("operations", []):
        log_business_event(
            conn, env_id, tenant_id, data_mode, plan["day"], "operation",
            user_id=op["user_id"], agent_id=op["agent_id"], app_id=op["app_id"],
            success=1, latency_ms=0, started_at=f"{plan['day']} 09:00:00",
        )
        conn.execute(
            "INSERT INTO operation_logs (env_id, tenant_id, data_mode, day, user_id, agent_id, app_id, action, detail, level, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (env_id, tenant_id, data_mode, plan["day"], op["user_id"], op["agent_id"], op["app_id"],
             op["action"], op["detail"], op["level"], created),
        )

    return dict(plan["stats"])


def log_business_event(
    conn: Any,
    env_id: str,
    tenant_id: str,
    data_mode: str,
    day: str,
    event_type: str,
    *,
    user_id: str = "",
    agent_id: str = "",
    app_id: str = "",
    session_id: str = "",
    task_id: str = "",
    file_id: str = "",
    download_id: str = "",
    skill_id: str = "",
    tool_id: str = "",
    tokens: int = 0,
    success: int = 0,
    latency_ms: int = 0,
    started_at: str = "",
) -> str:
    event_id = "be_" + uuid.uuid4().hex[:12]
    conn.execute(
        "INSERT INTO business_events (event_id, env_id, tenant_id, data_mode, day, user_id, agent_id, app_id, "
        "event_type, session_id, task_id, file_id, download_id, skill_id, tool_id, tokens, success, latency_ms, "
        "started_at, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (event_id, env_id, tenant_id, data_mode, day, user_id, agent_id, app_id, event_type,
         session_id, task_id, file_id, download_id, skill_id, tool_id, tokens, success, latency_ms,
         started_at, _now()),
    )
    return event_id


def _day_has_data(conn: Any, env_id: str, data_mode: str, day: date) -> bool:
    """某天是否已有业务数据（会话/文件/业务事件任一），避免重复生成。"""
    iso = day.isoformat()
    for table, col in (
        ("business_events", "day"),
        ("sessions", "substr(started_at,1,10)"),
        ("files", "substr(created_at,1,10)"),
    ):
        if conn.execute(
            f"SELECT 1 FROM {table} WHERE env_id=? AND data_mode=? AND {col}=? LIMIT 1",
            (env_id, data_mode, iso),
        ).fetchone():
            return True
    return False


def _clear_day(conn: Any, env_id: str, data_mode: str, day: date) -> None:
    """强制重写某天时，先清除该环境该日的运行期业务表，避免重复插入。"""
    iso = day.isoformat()
    # 先删子表再删主表，保持引用自洽（SQLite 默认未启用外键约束，仍按从属顺序删除）。
    for table, col in (
        ("file_downloads", "substr(downloaded_at,1,10)"),
        ("files", "substr(created_at,1,10)"),
        ("tasks", "substr(started_at,1,10)"),
        ("sessions", "substr(started_at,1,10)"),
        ("token_usage", "day"),
        ("business_events", "day"),
        ("login_activity", "day"),
        ("operation_logs", "day"),
    ):
        conn.execute(
            f"DELETE FROM {table} WHERE env_id=? AND data_mode=? AND {col}=?",
            (env_id, data_mode, iso),
        )


def _load_day_context(
    conn: Any,
    env_id: str,
    data_mode: str,
    growth: float,
    scale: int,
    rng: random.Random,
) -> dict[str, Any]:
    users = [dict(r) for r in conn.execute(
        "SELECT * FROM org_users WHERE env_id=? AND data_mode=?", (env_id, data_mode))]
    agents = [dict(r) for r in conn.execute(
        "SELECT * FROM agents WHERE env_id=? AND data_mode=? ORDER BY id", (env_id, data_mode))]
    apps = [dict(r) for r in conn.execute(
        "SELECT * FROM apps WHERE env_id=? AND data_mode=?", (env_id, data_mode))]

    skills_by_agent: dict[str, list[tuple[str, str]]] = {}
    for r in conn.execute(
        "SELECT agent_id, skill_id, name FROM skills WHERE env_id=? AND data_mode=?", (env_id, data_mode)):
        skills_by_agent.setdefault(r["agent_id"], []).append((r["name"], r["skill_id"]))
    tools_by_agent: dict[str, list[str]] = {}
    for r in conn.execute(
        "SELECT agent_id, tool_id FROM agent_tools WHERE env_id=? AND data_mode=?", (env_id, data_mode)):
        tools_by_agent.setdefault(r["agent_id"], []).append(r["tool_id"])

    agents_by_id: dict[str, dict[str, Any]] = {}
    for a in agents:
        ad = dict(a)
        ad["skills"] = skills_by_agent.get(a["agent_id"], [])
        ad["tools"] = tools_by_agent.get(a["agent_id"], [])
        ad["enabled"] = a.get("enabled", 1)
        agents_by_id[a["agent_id"]] = ad

    apps_by_id = {a["app_id"]: a for a in apps}
    dept_apps: dict[str, list[dict[str, Any]]] = {}
    for dep in sorted({u["department"] for u in users}):
        app_ids = DEPT_APP_MAP.get(dep, ["data_center", "project_center"])
        dept_apps[dep] = [
            {"app_id": apps_by_id[ai]["app_id"], "name": apps_by_id[ai]["name"], "category": apps_by_id[ai]["category"]}
            for ai in app_ids if ai in apps_by_id
        ]
    dept_apps["total"] = [{"app_id": a["app_id"], "name": a["name"], "category": a["category"]} for a in apps]

    enabled_count = max(1, round(len(agents) * (0.5 + 0.5 * growth)))
    enabled_ids = {a["agent_id"] for a in agents[:enabled_count]}
    active_pool = [u for u in users if u["dormant"] == 0 and u["agent_id"] in enabled_ids]
    user_count = max(1, round(scale * growth))
    active_users = rng.sample(active_pool, min(user_count, len(active_pool))) if active_pool else []
    return {
        "active_users": active_users,
        "enabled_agents": [agents_by_id[a["agent_id"]] for a in agents[:enabled_count]],
        "agents_by_id": agents_by_id,
        "dept_apps": dept_apps,
        "apps_by_id": apps_by_id,
    }


def _aggregate(created: list[dict[str, Any]]) -> dict[str, Any]:
    total = {"days": len(created), "sessions": 0, "calls": 0, "success": 0, "failed": 0, "tokens": 0}
    for row in created:
        for k in ("sessions", "calls", "success", "failed", "tokens"):
            total[k] += row.get(k, 0)
    return total


def preview_interval(
    conn: Any,
    env_id: str,
    data_mode: str,
    start_date: str,
    end_date: str,
    activity: str = "medium",
    seed: int = 0,
) -> dict[str, Any]:
    meta = conn.execute(
        "SELECT activity, scale FROM enterprise_meta WHERE env_id=? AND data_mode=?", (env_id, data_mode)).fetchone()
    if not meta:
        raise ValueError("环境不存在")
    activity_mult = _activity_multiplier(meta["activity"] or activity)
    scale = int(meta["scale"] or 30)
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    total_days = max((end - start).days + 1, 1)
    created: list[dict[str, Any]] = []
    for di in range(total_days):
        day = start + timedelta(days=di)
        rng = random.Random(_stable_day_seed(seed, di, env_id, day))
        growth = 0.4 + 0.6 * (di / max(total_days - 1, 1))
        ctx = _load_day_context(conn, env_id, data_mode, growth, scale, rng)
        if not ctx["active_users"]:
            continue
        plan = build_day_events(
            day, ctx["active_users"], ctx["enabled_agents"], ctx["agents_by_id"],
            ctx["dept_apps"], ctx["apps_by_id"], env_id, "", data_mode, activity_mult, rng,
        )
        created.append({"day": day.isoformat(), **plan["stats"]})
    return {"ok": True, "env_id": env_id, "data_mode": data_mode, "preview": True,
            **{"summary": _aggregate(created)}, "days": [r["day"] for r in created]}


def run_interval(
    conn: Any,
    env_id: str,
    data_mode: str,
    start_date: str,
    end_date: str,
    *,
    seed: int = 0,
    force: bool = False,
) -> dict[str, Any]:
    meta = conn.execute(
        "SELECT activity, scale, tenant_id FROM enterprise_meta WHERE env_id=? AND data_mode=?",
        (env_id, data_mode)).fetchone()
    if not meta:
        raise ValueError("环境不存在")
    activity_mult = _activity_multiplier(meta["activity"] or "medium")
    scale = int(meta["scale"] or 30)
    tenant_id = meta["tenant_id"] or ""
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    total_days = max((end - start).days + 1, 1)
    created: list[dict[str, Any]] = []
    skipped = 0
    for di in range(total_days):
        day = start + timedelta(days=di)
        if not force and _day_has_data(conn, env_id, data_mode, day):
            skipped += 1
            continue
        if force:
            _clear_day(conn, env_id, data_mode, day)
        rng = random.Random(_stable_day_seed(seed, di, env_id, day))
        growth = 0.4 + 0.6 * (di / max(total_days - 1, 1))
        ctx = _load_day_context(conn, env_id, data_mode, growth, scale, rng)
        if not ctx["active_users"]:
            continue
        plan = build_day_events(
            day, ctx["active_users"], ctx["enabled_agents"], ctx["agents_by_id"],
            ctx["dept_apps"], ctx["apps_by_id"], env_id, tenant_id, data_mode, activity_mult, rng,
        )
        if not plan["events"]:
            continue
        created.append({"day": day.isoformat(), **execute_day_events(conn, plan)})
    conn.commit()
    return {"ok": True, "env_id": env_id, "data_mode": data_mode, "force": force,
            "start_date": start.isoformat(), "end_date": end.isoformat(),
            "days_written": len(created), "days_skipped": skipped, "summary": _aggregate(created)}


def list_events(
    conn: Any,
    env_id: str,
    data_mode: str,
    start_date: str = "",
    end_date: str = "",
    limit: int = 50,
) -> list[dict[str, Any]]:
    """查询某环境的业务事件审计记录，支持按日期范围与条数限制。"""
    where = "WHERE env_id = ? AND data_mode = ?"
    args: list[Any] = [env_id, data_mode]
    if start_date:
        where += " AND day >= ?"
        args.append(start_date)
    if end_date:
        where += " AND day <= ?"
        args.append(end_date)
    rows = conn.execute(
        "SELECT env_id, data_mode, tenant_id, event_id, day, user_id, agent_id, app_id, event_type, "
        "session_id, task_id, file_id, download_id, skill_id, tool_id, tokens, success, latency_ms, started_at "
        f"FROM business_events {where} ORDER BY id DESC LIMIT ?",
        (*args, int(limit)),
    ).fetchall()
    return [dict(r) for r in rows]


def list_envs(conn: Any) -> list[dict[str, Any]]:
    rows = [dict(r) for r in conn.execute(
        "SELECT env_id, tenant_id, data_mode, enterprise, template, scale, departments, agent_count, activity, start_date, end_date, updated_at "
        "FROM enterprise_meta ORDER BY id DESC")]
    for r in rows:
        r["business_events"] = conn.execute(
            "SELECT COUNT(*) AS c FROM business_events WHERE env_id=? AND data_mode=?",
            (r["env_id"], r["data_mode"])).fetchone()["c"]
    return rows


def status(conn: Any) -> dict[str, Any]:
    envs = list_envs(conn)
    total_events = conn.execute("SELECT COUNT(*) AS c FROM business_events").fetchone()["c"]
    total_sessions = conn.execute("SELECT COUNT(*) AS c FROM sessions").fetchone()["c"]
    total_tasks = conn.execute("SELECT COUNT(*) AS c FROM tasks").fetchone()["c"]
    total_files = conn.execute("SELECT COUNT(*) AS c FROM files").fetchone()["c"]
    total_token = conn.execute("SELECT COALESCE(SUM(tokens),0) AS s FROM token_usage").fetchone()["s"]
    return {
        "ok": True,
        "environments": envs,
        "totals": {
            "environments": len(envs),
            "business_events": total_events,
            "sessions": total_sessions,
            "tasks": total_tasks,
            "files": total_files,
            "tokens": total_token,
        },
        "note": "Simulation Runtime 事件闭环已启用：业务事件 -> Agent -> Skill -> Tool -> 结果 -> 下载 -> Token -> 统计。",
    }
