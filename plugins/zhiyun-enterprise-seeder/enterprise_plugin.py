# -*- coding: utf-8 -*-
"""Enterprise Seeder - 企业环境初始化器（zhiyun-enterprise-seeder）。

一次性自动创建：企业 -> 部门 -> 员工 -> 角色 -> 权限 -> 智能体 -> 技能 ->
应用 -> 数据源 -> 会话 -> 任务执行 -> Token 统计 -> 操作日志，并把员工账号
同步到 zhiyun-auth 的用户文件，实现"不同用户绑定不同 Agent/数据/知识库"。

同一运行实例视为同一家企业；不同企业以实例边界隔离，本插件无需额外状态。

底层统一 data_mode：demo（演示环境） / production（生产环境）。
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import random
import secrets
import sqlite3
import threading
import time
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

try:
    from qwenpaw.constant import WORKING_DIR
    from qwenpaw.plugins.api import PluginApi
except ImportError:  # pragma: no cover - 单元测试时可能没有宿主
    WORKING_DIR = Path(os.environ.get("QWENPAW_WORKING_DIR", Path.cwd()))
    PluginApi = object  # type: ignore[assignment, misc]

try:
    from .agent_factory import (
        MODEL_CATALOG, TOOL_CATALOG, CATEGORY_DEFAULT_TOOLS, APP_ACCESS_BY_DEPT,
        build_agent_config, validate_agent_config, persist_bindings,
        reconcile_bindings, make_agent_row, new_agent_id,
    )
except ImportError:  # pragma: no cover - 兼容非包式加载
    from agent_factory import (
        MODEL_CATALOG, TOOL_CATALOG, CATEGORY_DEFAULT_TOOLS, APP_ACCESS_BY_DEPT,
        build_agent_config, validate_agent_config, persist_bindings,
        reconcile_bindings, make_agent_row, new_agent_id,
    )

try:
    from .simulation_runtime import (
        ensure_schema as ensure_sim_schema,
        build_day_events, execute_day_events, log_business_event,
        run_interval, preview_interval, list_events,
        status as runtime_status, list_envs,
    )
except ImportError:  # pragma: no cover - 兼容非包式加载
    from simulation_runtime import (
        ensure_schema as ensure_sim_schema,
        build_day_events, execute_day_events, log_business_event,
        run_interval, preview_interval, list_events,
        status as runtime_status, list_envs,
    )

try:
    from .analytics import build_trends as _build_trends
except ImportError:  # pragma: no cover - 兼容非包式加载
    from analytics import build_trends as _build_trends

PLUGIN_VERSION = "0.1.0"
ENTERPRISE_DIR = Path(os.environ.get("ZHIYUN_ENTERPRISE_DIR", WORKING_DIR / "enterprise"))
DB = ENTERPRISE_DIR / "enterprise.db"
AUTH_USERS_FILE = WORKING_DIR / "auth" / "users.json"
AUTH_SECRET_FILE = WORKING_DIR / "auth" / "token_secret.txt"

DEFAULT_PASSWORD = "ZhizaoYun@2026"
# rebrand 前企业员工默认口令；仅用于升级后向后兼容轮换，不用于新建账号。
LEGACY_DEFAULT_PASSWORD = "Zhiyun@2026"
DEFAULT_START = "2025-12-01"
DEFAULT_ACTIVITY = "medium"
DEFAULT_TEMPLATE = "manufacturing"
DEFAULT_DATA_MODE = "demo"

router = APIRouter()
_schema_lock = False

# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _today() -> str:
    return date.today().isoformat()


def _read_json(path: Path, default: Any) -> Any:
    try:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    return default


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _connect() -> sqlite3.Connection:
    ENTERPRISE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# ---------------------------------------------------------------------------
# 登录鉴权（与 zhiyun-auth 共用同一 token secret 与用户文件）
# ---------------------------------------------------------------------------


def _bearer_token(authorization: str) -> str:
    if authorization.startswith("Bearer "):
        return authorization[7:]
    return ""


def _find_user(username: str) -> dict[str, Any] | None:
    for user in _read_auth_users():
        if user.get("username") == username:
            return user
    return None


def _verify_token(token: str) -> str | None:
    try:
        b64, sig = token.split(".", 1)
        secret = _token_secret()
        if not secret:
            return None
        expected = hmac.new(secret.encode("utf-8"), b64.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(base64.urlsafe_b64decode(b64.encode("ascii")))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        username = str(payload.get("sub") or "")
        user = _find_user(username)
        if not user or not user.get("active", True):
            return None
        return username
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def _require_auth(authorization: str) -> dict[str, Any]:
    token = _bearer_token(authorization)
    username = _verify_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")
    user = _find_user(username)
    if not user:
        raise HTTPException(status_code=401, detail="账号不存在")
    return user


def _require_admin(authorization: str) -> dict[str, Any]:
    user = _require_auth(authorization)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


SCHEMA = """
CREATE TABLE IF NOT EXISTS enterprise_meta (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    env_id TEXT, tenant_id TEXT, data_mode TEXT, enterprise TEXT, template TEXT,
    start_date TEXT, end_date TEXT, scale INTEGER, departments INTEGER,
    agent_count INTEGER, activity TEXT, created_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS departments (
    id INTEGER PRIMARY KEY AUTOINCREMENT, env_id TEXT, tenant_id TEXT, data_mode TEXT,
    name TEXT, code TEXT, parent TEXT, head_user TEXT, weight INTEGER, created_at TEXT
);
CREATE TABLE IF NOT EXISTS org_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT, env_id TEXT, tenant_id TEXT, data_mode TEXT,
    username TEXT, display_name TEXT, email TEXT, phone TEXT, department TEXT,
    role TEXT, title TEXT, agent_id TEXT, data_scope TEXT, kb_scope TEXT,
    active INTEGER, dormant INTEGER, hired_on TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT, env_id TEXT, tenant_id TEXT, data_mode TEXT,
    name TEXT, code TEXT, permissions TEXT, description TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS agents (
    id INTEGER PRIMARY KEY AUTOINCREMENT, env_id TEXT, tenant_id TEXT, data_mode TEXT,
    agent_id TEXT, name TEXT, position TEXT, department TEXT, system_prompt TEXT,
    model TEXT, skills TEXT, tools TEXT, kb_scope TEXT, data_scope TEXT,
    max_tokens INTEGER, execution_freq INTEGER, work_start TEXT, work_end TEXT,
    auto_tasks INTEGER, manual_tasks INTEGER, success_rate REAL,
    avg_response_ms INTEGER, enabled INTEGER, created_at TEXT
);
CREATE TABLE IF NOT EXISTS skills (
    id INTEGER PRIMARY KEY AUTOINCREMENT, env_id TEXT, tenant_id TEXT, data_mode TEXT,
    skill_id TEXT, name TEXT, agent_id TEXT, category TEXT, description TEXT,
    enabled INTEGER, created_at TEXT
);
CREATE TABLE IF NOT EXISTS models (
    id INTEGER PRIMARY KEY AUTOINCREMENT, env_id TEXT, tenant_id TEXT, data_mode TEXT,
    model_id TEXT, name TEXT, provider TEXT, base_model TEXT, context_window INTEGER,
    max_tokens INTEGER, input_price_per_k REAL, output_price_per_k REAL,
    enabled INTEGER, created_at TEXT
);
CREATE TABLE IF NOT EXISTS agent_tools (
    id INTEGER PRIMARY KEY AUTOINCREMENT, env_id TEXT, tenant_id TEXT, data_mode TEXT,
    agent_id TEXT, tool_id TEXT, tool_name TEXT, tool_category TEXT,
    enabled INTEGER, created_at TEXT
);
CREATE TABLE IF NOT EXISTS agent_app_access (
    id INTEGER PRIMARY KEY AUTOINCREMENT, env_id TEXT, tenant_id TEXT, data_mode TEXT,
    agent_id TEXT, app_id TEXT, data_scope TEXT, kb_scope TEXT,
    enabled INTEGER, created_at TEXT
);
CREATE TABLE IF NOT EXISTS apps (
    id INTEGER PRIMARY KEY AUTOINCREMENT, env_id TEXT, tenant_id TEXT, data_mode TEXT,
    app_id TEXT, name TEXT, category TEXT, agent_id TEXT, icon TEXT,
    enabled INTEGER, created_at TEXT
);
CREATE TABLE IF NOT EXISTS data_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT, env_id TEXT, tenant_id TEXT, data_mode TEXT,
    source_id TEXT, name TEXT, source_type TEXT, app_id TEXT, records INTEGER,
    shared INTEGER, created_at TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, env_id TEXT, tenant_id TEXT, data_mode TEXT,
    session_id TEXT, user_id TEXT, agent_id TEXT, app_id TEXT, messages INTEGER,
    started_at TEXT, ended_at TEXT, status TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT, env_id TEXT, tenant_id TEXT, data_mode TEXT,
    task_id TEXT, session_id TEXT, agent_id TEXT, user_id TEXT, app_id TEXT,
    skill_id TEXT, label TEXT, status TEXT, success INTEGER, started_at TEXT,
    finished_at TEXT, latency_ms INTEGER, tokens INTEGER, result TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS token_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT, env_id TEXT, tenant_id TEXT, data_mode TEXT,
    day TEXT, agent_id TEXT, app_id TEXT, user_id TEXT, tokens INTEGER,
    calls INTEGER, success INTEGER, failed INTEGER, created_at TEXT
);
CREATE TABLE IF NOT EXISTS operation_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, env_id TEXT, tenant_id TEXT, data_mode TEXT,
    day TEXT, user_id TEXT, agent_id TEXT, app_id TEXT, action TEXT,
    detail TEXT, level TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT, env_id TEXT, tenant_id TEXT, data_mode TEXT,
    file_id TEXT, task_id TEXT, session_id TEXT, agent_id TEXT, user_id TEXT, app_id TEXT,
    name TEXT, category TEXT, format TEXT, size_kb INTEGER,
    download_count INTEGER, downloaded INTEGER, created_at TEXT
);
CREATE TABLE IF NOT EXISTS file_downloads (
    id INTEGER PRIMARY KEY AUTOINCREMENT, env_id TEXT, tenant_id TEXT, data_mode TEXT,
    download_id TEXT, file_id TEXT, task_id TEXT, user_id TEXT, agent_id TEXT, app_id TEXT,
    downloaded_at TEXT, ip TEXT, device TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS login_activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT, env_id TEXT, tenant_id TEXT, data_mode TEXT,
    day TEXT, user_id TEXT, agent_id TEXT, app_id TEXT,
    login_at TEXT, ip TEXT, device TEXT, success INTEGER, status TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS integrity_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT, env_id TEXT, tenant_id TEXT, data_mode TEXT,
    report_day TEXT, total INTEGER, passed INTEGER, failed INTEGER, healthy INTEGER,
    snapshot TEXT, created_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS integrity_repair_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, env_id TEXT, tenant_id TEXT, data_mode TEXT,
    day TEXT, check_id TEXT, action TEXT, affected INTEGER, detail TEXT,
    run_by TEXT, created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_integrity_reports_env ON integrity_reports(env_id, data_mode, report_day);
CREATE INDEX IF NOT EXISTS idx_repair_log_env ON integrity_repair_log(env_id, data_mode, day, created_at);
CREATE INDEX IF NOT EXISTS idx_files_env ON files(env_id, data_mode, created_at);
CREATE INDEX IF NOT EXISTS idx_files_task ON files(task_id);
CREATE INDEX IF NOT EXISTS idx_files_agent ON files(env_id, data_mode, agent_id);
CREATE INDEX IF NOT EXISTS idx_downloads_env ON file_downloads(env_id, data_mode, downloaded_at);
CREATE INDEX IF NOT EXISTS idx_downloads_file ON file_downloads(file_id);
CREATE INDEX IF NOT EXISTS idx_downloads_id ON file_downloads(env_id, data_mode, download_id);
CREATE INDEX IF NOT EXISTS idx_downloads_env_file ON file_downloads(env_id, data_mode, file_id);
CREATE INDEX IF NOT EXISTS idx_logins_env ON login_activity(env_id, data_mode, day);
CREATE INDEX IF NOT EXISTS idx_logins_user ON login_activity(user_id);
CREATE INDEX IF NOT EXISTS idx_users_env ON org_users(env_id, data_mode);
CREATE INDEX IF NOT EXISTS idx_agents_env ON agents(env_id, data_mode);
CREATE INDEX IF NOT EXISTS idx_sessions_env ON sessions(env_id, data_mode, started_at);
CREATE INDEX IF NOT EXISTS idx_tasks_env ON tasks(env_id, data_mode, started_at);
CREATE INDEX IF NOT EXISTS idx_token_env ON token_usage(env_id, data_mode, day);
CREATE INDEX IF NOT EXISTS idx_users_env_user ON org_users(env_id, data_mode, username);
CREATE INDEX IF NOT EXISTS idx_users_username ON org_users(username);
CREATE INDEX IF NOT EXISTS idx_agents_env_agent ON agents(env_id, data_mode, agent_id);
CREATE INDEX IF NOT EXISTS idx_models_env_model ON models(env_id, data_mode, model_id);
CREATE INDEX IF NOT EXISTS idx_agent_tools_env_agent ON agent_tools(env_id, data_mode, agent_id, tool_id);
CREATE INDEX IF NOT EXISTS idx_agent_app_access_env_agent ON agent_app_access(env_id, data_mode, agent_id, app_id);
CREATE INDEX IF NOT EXISTS idx_sessions_env_id ON sessions(env_id, data_mode, session_id);
CREATE INDEX IF NOT EXISTS idx_tasks_session ON tasks(session_id);
CREATE INDEX IF NOT EXISTS idx_tasks_task_id ON tasks(task_id);
CREATE INDEX IF NOT EXISTS idx_tasks_env_task ON tasks(env_id, data_mode, task_id);
CREATE INDEX IF NOT EXISTS idx_files_file_id ON files(file_id);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(env_id, data_mode, user_id);
CREATE INDEX IF NOT EXISTS idx_tasks_user_agent ON tasks(env_id, data_mode, user_id, agent_id);
"""

DEPT_TEMPLATES = {
    "manufacturing": [
        {"name": "销售部", "code": "sales", "weight": 5, "parent": "管理中心", "titles": ["销售专员", "大客户经理", "销售主管"]},
        {"name": "财务部", "code": "finance", "weight": 3, "parent": "管理中心", "titles": ["会计", "财务主管", "成本会计"]},
        {"name": "采购部", "code": "procurement", "weight": 3, "parent": "供应链中心", "titles": ["采购专员", "采购主管", "供应商经理"]},
        {"name": "客服部", "code": "service", "weight": 4, "parent": "客户中心", "titles": ["客服专员", "售后专员", "客服主管"]},
        {"name": "运营部", "code": "operations", "weight": 3, "parent": "管理中心", "titles": ["运营专员", "运营主管", "数据分析师"]},
        {"name": "管理层", "code": "exec", "weight": 2, "parent": "董事会", "titles": ["总经理", "总监", "副总"]},
        {"name": "生产部", "code": "production", "weight": 5, "parent": "制造中心", "titles": ["生产计划员", "车间主管", "工艺工程师"]},
        {"name": "研发部", "code": "rd", "weight": 3, "parent": "技术中心", "titles": ["研发工程师", "项目经理", "架构师"]},
    ],
    "finance": [
        {"name": "财务部", "code": "finance", "weight": 5, "parent": "管理中心", "titles": ["会计", "出纳", "财务主管"]},
        {"name": "风险合规部", "code": "risk", "weight": 3, "parent": "管理中心", "titles": ["风控专员", "合规主管"]},
        {"name": "投资部", "code": "investment", "weight": 2, "parent": "管理中心", "titles": ["投资分析师", "投资经理"]},
        {"name": "运营部", "code": "operations", "weight": 3, "parent": "管理中心", "titles": ["运营专员", "运营主管"]},
        {"name": "管理层", "code": "exec", "weight": 2, "parent": "董事会", "titles": ["总经理", "总监"]},
        {"name": "客户部", "code": "client", "weight": 4, "parent": "客户中心", "titles": ["客户经理", "客户专员"]},
    ],
}

AGENT_TEMPLATES = {
    "manufacturing": [
        {"id": "sales_quote", "name": "销售报价数字员工", "position": "销售报价", "department": "销售部", "category": "sales", "model": "本地 Qwen", "max_tokens": 8192, "execution_freq": 8, "auto_tasks": 2, "manual_tasks": 2, "success_rate": 0.94, "avg_response_ms": 1800, "skills": [("客户识别", "identify"), ("报价测算", "quote"), ("合同条款", "contract")], "tools": ["query_enterprise_orders", "generate_simulated_orders"]},
        {"id": "customer_followup", "name": "客户跟进数字员工", "position": "客户跟进", "department": "销售部", "category": "customer", "model": "本地 Qwen", "max_tokens": 6144, "execution_freq": 6, "auto_tasks": 1, "manual_tasks": 3, "success_rate": 0.91, "avg_response_ms": 2200, "skills": [("客情分析", "analyze"), ("回访跟进", "followup")], "tools": ["query_enterprise_orders"]},
        {"id": "email_marketing", "name": "邮件营销数字员工", "position": "邮件营销", "department": "运营部", "category": "marketing", "model": "本地 Qwen", "max_tokens": 8192, "execution_freq": 5, "auto_tasks": 2, "manual_tasks": 1, "success_rate": 0.89, "avg_response_ms": 2600, "skills": [("线索检索", "search"), ("邮件创作", "compose"), ("发送跟踪", "track")], "tools": []},
        {"id": "procurement_recon", "name": "采购对账数字员工", "position": "采购对账", "department": "采购部", "category": "supply", "model": "本地 Qwen", "max_tokens": 6144, "execution_freq": 7, "auto_tasks": 2, "manual_tasks": 2, "success_rate": 0.93, "avg_response_ms": 1600, "skills": [("单据处理", "invoice"), ("对账核验", "reconcile"), ("供应商评分", "vendor")], "tools": ["query_enterprise_orders"]},
        {"id": "finance_invoice", "name": "财务票据数字员工", "position": "财务票据", "department": "财务部", "category": "finance", "model": "本地 Qwen", "max_tokens": 6144, "execution_freq": 6, "auto_tasks": 3, "manual_tasks": 1, "success_rate": 0.96, "avg_response_ms": 1400, "skills": [("票据识别", "ocr"), ("凭证处理", "voucher"), ("费用核算", "cost")], "tools": []},
        {"id": "after_sales", "name": "售后客服数字员工", "position": "售后客服", "department": "客服部", "category": "service", "model": "本地 Qwen", "max_tokens": 6144, "execution_freq": 10, "auto_tasks": 1, "manual_tasks": 4, "success_rate": 0.88, "avg_response_ms": 2100, "skills": [("意图识别", "intent"), ("知识问答", "knowledge"), ("工单路由", "ticket")], "tools": []},
        {"id": "business_analyst", "name": "经营分析数字员工", "position": "经营分析", "department": "管理层", "category": "analytics", "model": "本地 Qwen", "max_tokens": 12288, "execution_freq": 4, "auto_tasks": 2, "manual_tasks": 1, "success_rate": 0.97, "avg_response_ms": 2400, "skills": [("指标归因", "attribution"), ("报表生成", "report"), ("风险预警", "risk")], "tools": ["query_enterprise_orders"]},
        {"id": "production_planner", "name": "生产计划数字员工", "position": "生产计划", "department": "生产部", "category": "production", "model": "本地 Qwen", "max_tokens": 8192, "execution_freq": 5, "auto_tasks": 3, "manual_tasks": 1, "success_rate": 0.92, "avg_response_ms": 1900, "skills": [("排产排程", "schedule"), ("产能分析", "capacity")], "tools": []},
        {"id": "inventory_manager", "name": "库存管理数字员工", "position": "库存管理", "department": "运营部", "category": "inventory", "model": "本地 Qwen", "max_tokens": 6144, "execution_freq": 6, "auto_tasks": 2, "manual_tasks": 2, "success_rate": 0.9, "avg_response_ms": 1700, "skills": [("库存盘点", "stock"), ("补货建议", "replenish")], "tools": []},
    ],
    "finance": [
        {"id": "expense_audit", "name": "报销审核数字员工", "position": "报销审核", "department": "财务部", "category": "finance", "model": "本地 Qwen", "max_tokens": 8192, "execution_freq": 8, "auto_tasks": 3, "manual_tasks": 2, "success_rate": 0.95, "avg_response_ms": 1500, "skills": [("票据识别", "ocr"), ("合规校验", "compliance"), ("费用分摊", "cost")], "tools": []},
        {"id": "financial_ratio", "name": "财务比率看板数字员工", "position": "财务分析", "department": "财务部", "category": "analytics", "model": "本地 Qwen", "max_tokens": 12288, "execution_freq": 3, "auto_tasks": 2, "manual_tasks": 1, "success_rate": 0.97, "avg_response_ms": 2300, "skills": [("比率测算", "ratio"), ("报表生成", "report")], "tools": []},
        {"id": "cost_forecast", "name": "成本预测数字员工", "position": "成本预测", "department": "财务部", "category": "analytics", "model": "本地 Qwen", "max_tokens": 8192, "execution_freq": 4, "auto_tasks": 2, "manual_tasks": 1, "success_rate": 0.91, "avg_response_ms": 2500, "skills": [("价格追踪", "price"), ("成本建模", "model")], "tools": []},
    ],
}

APP_TEMPLATES = [
    {"id": "zhiyun-data-core", "name": "统一数据中心", "category": "系统", "icon": "🗄️"},
    {"id": "zhiyun-order-studio", "name": "智能订单中心", "category": "业务", "icon": "📦"},
    {"id": "zhiyun-sales-studio", "name": "智能销售中心", "category": "业务", "icon": "📈"},
    {"id": "zhiyun-finance-studio", "name": "智能财务中心", "category": "业务", "icon": "💰"},
    {"id": "zhiyun-supply-studio", "name": "采购与供应链中心", "category": "业务", "icon": "🚚"},
    {"id": "zhiyun-service-studio", "name": "智能售后服务中心", "category": "业务", "icon": "🎧"},
    {"id": "zhiyun-people-studio", "name": "智能人力与协同中心", "category": "业务", "icon": "🧑‍🤝‍🧑"},
    {"id": "zhiyun-app-discovery", "name": "应用与项目中心", "category": "系统", "icon": "🧭"},
    {"id": "qwenpaw-knowledge-base", "name": "工作区知识库", "category": "知识", "icon": "📚"},
]

ROLE_TEMPLATES = [
    {"code": "admin", "name": "管理员", "permissions": ["*"], "description": "平台级管理员，可管理账号、Agent、数据与知识库"},
    {"code": "manager", "name": "部门主管", "permissions": ["agent:view", "agent:run", "data:view", "data:import", "kb:view", "kpo:manage"], "description": "部门主管，可绑定部门 Agent 并查看部门数据"},
    {"code": "member", "name": "普通员工", "permissions": ["agent:view", "agent:run", "data:view", "kb:view"], "description": "普通员工，只能访问被授权 Agent 与数据范围"},
]

SURNAMES = ["张", "李", "王", "刘", "陈", "杨", "赵", "黄", "周", "吴", "徐", "孙", "胡", "朱", "高", "林", "何", "郭", "马", "罗", "梁", "宋", "郑", "谢", "韩", "唐", "冯", "于", "董", "萧", "程", "曹", "袁", "邓", "许", "傅", "沈", "曾", "彭", "吕"]
GIVEN = ["伟", "芳", "娜", "敏", "静", "磊", "军", "洋", "勇", "艳", "杰", "涛", "明", "超", "秀英", "霞", "平", "刚", "桂英", "鑫", "雨", "晨", "嘉", "浩", "宇", "欣", "露", "子涵", "怡", "然", "博", "锐", "凌", "凡", "翔", "帆", "悦", "涵", "泽", "曦", "聪", "航", "帅", "倩", "颖", "慧", "璇", "琳", "桐", "雯"]

def _spawn_daily_integrity_report() -> None:
    """后台线程生成当日一致性快照，避免在大型企业库上阻塞启动钩子。"""

    def _run() -> None:
        try:
            _daily_integrity_report()
        except Exception:
            pass

    threading.Thread(target=_run, name="enterprise-daily-integrity", daemon=True).start()


def _ensure_schema() -> None:
    global _schema_lock
    if _schema_lock:
        return
    conn = _connect()
    try:
        conn.executescript(SCHEMA)
        ensure_sim_schema(conn)
        conn.commit()
        _schema_lock = True
    finally:
        conn.close()

def _startup_bootstrap() -> None:
    """启动入口：先确保 schema（同步、轻量），再后台生成当日一致性快照。

    _daily_integrity_report 在数十万行的企业库上需要较长时间，
    放到后台线程方不会阻塞单线程服务器启动。"""
    _ensure_schema()
    try:
        _rotate_legacy_employee_passwords()
    except Exception:
        # 员工口令轮换失败不应阻断启动，交由后续 seed 或人工修复兜底。
        pass
    _spawn_daily_integrity_report()


def _hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return digest, salt

def _verify_password(password: str, stored_hash: str, salt: str) -> bool:
    digest, _ = _hash_password(password, salt)
    return hmac.compare_digest(digest, stored_hash)


def _token_secret() -> str:
    try:
        if AUTH_SECRET_FILE.is_file():
            val = AUTH_SECRET_FILE.read_text(encoding="utf-8").strip()
            if val:
                return val
    except OSError:
        pass
    secret = secrets.token_hex(32)
    AUTH_SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    AUTH_SECRET_FILE.write_text(secret, encoding="utf-8")
    return secret


def _read_auth_users() -> list[dict[str, Any]]:
    data = _read_json(AUTH_USERS_FILE, [])
    if isinstance(data, list):
        return list(data)
    if isinstance(data, dict):
        return list(data.get("users") or [])
    return []


def _rotate_legacy_employee_passwords() -> int:
    """升级启动迁移：把仍使用 rebrand 前默认口令的非 admin 员工轮换为新默认口令。

    zhiyun-auth 在优先级 0 的启动钩子中已负责轮换 admin 账号；本插件负责
    其余员工账号。仅当账号仍能通过 LEGACY_DEFAULT_PASSWORD 校验时才更新，
    绝不覆盖用户自定义口令。返回实际轮换的账号数。
    """
    users = _read_auth_users()
    changed = 0
    for user in users:
        if (user.get("role") or "").lower() == "admin":
            # admin 由 zhiyun-auth 在优先级 0 的启动钩子中处理，避免共享文件双写竞争。
            continue
        stored = user.get("password_hash", "")
        salt = user.get("password_salt", "")
        if stored and salt and _verify_password(LEGACY_DEFAULT_PASSWORD, stored, salt):
            pw_hash, new_salt = _hash_password(DEFAULT_PASSWORD)
            user["password_hash"] = pw_hash
            user["password_salt"] = new_salt
            changed += 1
    if changed:
        _write_json(AUTH_USERS_FILE, users)
    return changed


def _sync_auth_users(
    rows: list[dict[str, Any]],
    enterprise: str,
    env_id: str = "",
    data_mode: str = "",
) -> dict[str, Any]:
    """把生成的员工账号合并进 zhiyun-auth 的 users.json。

    保留已有 admin / 历史账号；生成的员工按 username 去重；默认密码
    ZhizaoYun@2026；每个账号绑定 agent_id / data_scope / kb_scope，并记录其
    所属企业环境（env_id / data_mode），用于 RBAC 数据隔离。
    """
    users = _read_auth_users()
    by_username = {u.get("username"): u for u in users if u.get("username")}
    created = 0
    updated = 0
    for row in rows:
        username = row["username"]
        # 已存在的历史账号（admin 等）：跳过以避免覆盖自定义密码，但若仍使用
        # rebrand 前的默认口令，则向后兼容轮换为新默认口令。
        if username in by_username:
            existing = by_username[username]
            stored = existing.get("password_hash", "")
            salt = existing.get("password_salt", "")
            if stored and salt and _verify_password(LEGACY_DEFAULT_PASSWORD, stored, salt):
                pw_hash, new_salt = _hash_password(DEFAULT_PASSWORD)
                existing["password_hash"] = pw_hash
                existing["password_salt"] = new_salt
            updated += 1
            continue
        pw_hash, salt = _hash_password(DEFAULT_PASSWORD)
        auth = {
            "username": username,
            "display_name": row["display_name"],
            "role": row["role"],
            "password_hash": pw_hash,
            "password_salt": salt,
            "enterprise": enterprise,
            "agent_id": row["agent_id"],
            "data_scope": row["data_scope"],
            "kb_scope": row["kb_scope"],
            "active": bool(row["active"]),
            "created_at": row["created_at"],
        }
        if env_id:
            auth["env_id"] = env_id
        if data_mode:
            auth["data_mode"] = data_mode
        users.append(auth)
        created += 1
    _write_json(AUTH_USERS_FILE, users)
    return {"auth_users_file": str(AUTH_USERS_FILE), "created": created, "kept": len(users) - created, "updated": updated}



# ---------------------------------------------------------------------------
# 业务周期与生成规则
# ---------------------------------------------------------------------------


def _parse_date(value: str) -> date:
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail=f"日期格式应为 YYYY-MM-DD：{value}")


def _normalize_mode(data_mode: str) -> str:
    """把 live 归一化为 production，并校验 data_mode 合法值。"""
    if data_mode == "live":
        return "production"
    if data_mode == "":
        return ""
    if data_mode not in ("demo", "production"):
        raise HTTPException(status_code=422, detail="data_mode 只能是 demo 或 production")
    return data_mode


def _workday_factor(d: date) -> float:
    wd = d.weekday()
    if wd == 5:      # 周六
        return 0.22
    if wd == 6:      # 周日
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


def _make_name(rng: random.Random) -> str:
    return rng.choice(SURNAMES) + rng.choice(GIVEN)


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


def _build_users(depts, agents, scale, rng, enterprise, data_mode, env_id, tenant_id):
    """把 scale 位员工按部门权重摊分，并绑定 Agent/数据/知识库范围。"""
    total_weight = sum(d["weight"] for d in depts)
    rows = []
    idx = 0
    counts = [max(1, int(scale * d["weight"] / total_weight)) for d in depts]
    used = sum(counts)
    remaining = scale - used
    if remaining > 0:
        fracs = sorted(((d["weight"] * scale / total_weight) - counts[i], i) for i, d in enumerate(depts))
        for _, i in sorted(fracs, reverse=True)[:remaining]:
            counts[i] += 1
    elif remaining < 0:
        to_remove = -remaining
        for i in sorted(range(len(counts)), key=lambda i: counts[i], reverse=True):
            if to_remove <= 0:
                break
            if counts[i] > 1:
                counts[i] -= 1
                to_remove -= 1
    for dept, count in zip(depts, counts):
        dept_agents = [a for a in agents if a["department"] == dept["name"]]
        for i in range(count):
            idx += 1
            if dept_agents:
                agent = dept_agents[(i + idx) % len(dept_agents)]
            else:
                agent = agents[idx % len(agents)]
            surname = _make_name(rng)
            dept_code = dept["code"]
            username = f"{dept_code}_{idx:02d}"
            title = rng.choice(dept.get("titles", ["专员"]))
            role = "admin" if idx == 1 else ("manager" if rng.random() < 0.12 else "member")
            dormant = 1 if rng.random() < 0.08 else 0
            hired_on = f"{rng.randint(2019, 2026):04d}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"
            rows.append({
                "username": username,
                "display_name": surname if rng.random() < 0.4 else surname + rng.choice(GIVEN),
                "department": dept["name"],
                "role": role,
                "title": title,
                "agent_id": agent["agent_id"],
                "data_scope": "department" if role == "member" else ("enterprise" if role == "manager" else "enterprise"),
                "kb_scope": "department" if role == "member" else "enterprise",
                "active": 1 if dormant == 0 else 1,
                "dormant": dormant,
                "hired_on": hired_on,
                "created_at": f"{hired_on} 09:00:00",
            })
    return rows


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
_LOGIN_DEVICES = ["桌面端 Chrome", "桌面端 Edge", "桌面端 Firefox", "移动端 Chrome", "移动端 Safari"]
_LOGIN_STATUS = ["在线", "在线", "在线", "离开", "离线"]
_FORMATS = ["xlsx", "csv", "pdf", "docx", "md", "json"]

def _build_sessions_for_day(conn, day, active_users, enabled_agents, agents_by_id, dept_apps, apps_by_id, env_id, tenant_id, data_mode, activity_mult, rng):
    """生成某一天的会话、任务与 Token 聚合，返回当日统计。"""
    work = _workday_factor(day)
    month = _month_factor(day)
    if work < 0.2:
        return {"sessions": 0, "calls": 0, "success": 0, "failed": 0, "tokens": 0}

    sessions_per_user = 2.6 * activity_mult
    session_count = int(round(len(active_users) * sessions_per_user * work * month))
    session_count = max(0, min(session_count, 420))

    day_sessions = 0
    day_calls = 0
    day_success = 0
    day_failed = 0
    day_tokens = 0
    token_bucket: dict[tuple, dict[str, int]] = {}

    for _ in range(session_count):
        user = rng.choice(active_users)
        agent = agents_by_id.get(user["agent_id"])
        if not agent or agent["enabled"] == 0:
            continue
        app = rng.choice(dept_apps.get(user["department"], dept_apps.get("total", [
            {"app_id": "zhiyun-data-core", "name": "统一数据中心"}])))
        session_id = "s_" + uuid.uuid4().hex[:12]
        started = _pick_time(rng)
        messages = rng.randint(2, 12)
        latency = agent["avg_response_ms"] + rng.randint(-300, 500)
        success = rng.random() < agent["success_rate"]
        status = "completed" if success else "failed"
        # Token 估算：与消息数、Agent 上限、波动相关，避免整数/直线增长
        per_msg = rng.randint(70, 320)
        tokens = int(messages * per_msg + rng.randint(150, 1400) * (0.6 + 0.4 * work))
        ended_hms = _shift_time(started, latency)
        conn.execute(
            "INSERT INTO sessions (env_id, tenant_id, data_mode, session_id, user_id, agent_id, app_id, messages, started_at, ended_at, status, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (env_id, tenant_id, data_mode, session_id, user["username"], agent["agent_id"], app["app_id"], messages,
             f"{day.isoformat()} {started}:00", f"{day.isoformat()} {ended_hms}", status, _now()),
        )
        # 任务：每个会话 1-3 条 Agent 执行记录
        task_count = rng.randint(1, 3)
        for t in range(task_count):
            skill = agent["skills"][rng.randint(0, len(agent["skills"]) - 1)]
            task_id = "t_" + uuid.uuid4().hex[:12]
            task_ok = success
            task_tokens = int(tokens / task_count) + rng.randint(20, 120)
            conn.execute(
                "INSERT INTO tasks (env_id, tenant_id, data_mode, task_id, session_id, agent_id, user_id, app_id, skill_id, label, status, success, started_at, finished_at, latency_ms, tokens, result, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (env_id, tenant_id, data_mode, task_id, session_id, agent["agent_id"], user["username"], app["app_id"],
                 skill[1], skill[0], status, 1 if task_ok else 0,
                 f"{day.isoformat()} {started}:00", f"{day.isoformat()} {ended_hms}", latency, task_tokens,
                 "已生成" if task_ok else "执行异常", _now()),
            )
            # 文件工件：成功任务按概率产出可下载工件，并生成对应下载记录
            if task_ok and rng.random() < 0.62:
                kind = _FILE_KINDS.get(agent["position"], ("成果文件", "general", _FORMATS))
                base_name, category, formats = kind
                file_id = "f_" + uuid.uuid4().hex[:12]
                fmt = rng.choice(formats)
                size_kb = rng.randint(18, 1600)
                name = f"{base_name}_{day.strftime('%m%d')}_{rng.randint(100, 999)}.{fmt}"
                download_count = rng.choice([0, 1, 1, 2, 2, 3, 4])
                downloaded = 1 if download_count > 0 else 0
                conn.execute(
                    "INSERT INTO files (env_id, tenant_id, data_mode, file_id, task_id, session_id, agent_id, user_id, app_id, name, category, format, size_kb, download_count, downloaded, created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (env_id, tenant_id, data_mode, file_id, task_id, session_id, agent["agent_id"], user["username"], app["app_id"],
                     name, category, fmt, size_kb, download_count, downloaded, f"{day.isoformat()} {started}:00"),
                )
                for d in range(download_count):
                    dl_id = "dl_" + uuid.uuid4().hex[:12]
                    dl_time = _pick_time(rng)
                    ip = f"10.{rng.randint(10, 48)}.{rng.randint(1, 254)}.{rng.randint(1, 254)}"
                    conn.execute(
                        "INSERT INTO file_downloads (env_id, tenant_id, data_mode, download_id, file_id, task_id, user_id, agent_id, app_id, downloaded_at, ip, device, created_at) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (env_id, tenant_id, data_mode, dl_id, file_id, task_id, user["username"], agent["agent_id"], app["app_id"],
                         f"{day.isoformat()} {dl_time}:00", ip, rng.choice(_LOGIN_DEVICES), _now()),
                    )
            key = (agent["agent_id"], app["app_id"], user["username"])
            bucket = token_bucket.setdefault(key, {"tokens": 0, "calls": 0, "success": 0, "failed": 0})
            bucket["tokens"] += task_tokens
            bucket["calls"] += 1
            if task_ok:
                bucket["success"] += 1
            else:
                bucket["failed"] += 1
            day_calls += 1
            day_tokens += task_tokens
            if task_ok:
                day_success += 1
            else:
                day_failed += 1

        day_sessions += 1

    for (agent_id, app_id, username), bucket in token_bucket.items():
        conn.execute(
            "INSERT INTO token_usage (env_id, tenant_id, data_mode, day, agent_id, app_id, user_id, tokens, calls, success, failed, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (env_id, tenant_id, data_mode, day.isoformat(), agent_id, app_id, username,
             bucket["tokens"], bucket["calls"], bucket["success"], bucket["failed"], _now()),
        )
    return {"sessions": day_sessions, "calls": day_calls, "success": day_success, "failed": day_failed, "tokens": day_tokens}


def _shift_time(t: str, ms: int) -> str:
    try:
        base = datetime.strptime(t, "%H:%M")
        result = base + timedelta(milliseconds=ms)
        return result.strftime("%H:%M:%S")
    except (ValueError, TypeError):
        return "00:00:00"

# ---------------------------------------------------------------------------
# 主生成入口
# ---------------------------------------------------------------------------

DEPT_APP_MAP = {
    "销售部": ["zhiyun-sales-studio", "zhiyun-data-core", "zhiyun-app-discovery", "qwenpaw-knowledge-base"],
    "财务部": ["zhiyun-finance-studio", "zhiyun-data-core", "zhiyun-app-discovery", "qwenpaw-knowledge-base"],
    "采购部": ["zhiyun-supply-studio", "zhiyun-data-core", "zhiyun-app-discovery", "qwenpaw-knowledge-base"],
    "客服部": ["zhiyun-service-studio", "zhiyun-data-core", "zhiyun-app-discovery", "qwenpaw-knowledge-base"],
    "运营部": ["zhiyun-sales-studio", "zhiyun-supply-studio", "zhiyun-data-core", "zhiyun-app-discovery", "qwenpaw-knowledge-base"],
    "生产部": ["zhiyun-order-studio", "zhiyun-data-core", "zhiyun-app-discovery", "qwenpaw-knowledge-base"],
    "管理层": ["zhiyun-finance-studio", "zhiyun-sales-studio", "zhiyun-data-core", "zhiyun-app-discovery", "qwenpaw-knowledge-base"],
    "研发部": ["zhiyun-app-discovery", "zhiyun-data-core", "zhiyun-order-studio", "qwenpaw-knowledge-base"],
}

DATA_SOURCE_MAP = {
    "zhiyun-data-core": ("统一数据集市", "workspace"),
    "zhiyun-order-studio": ("销售订单执行数据", "excel"),
    "zhiyun-sales-studio": ("客户与商机数据", "excel"),
    "zhiyun-finance-studio": ("财务总账与票据", "excel"),
    "zhiyun-supply-studio": ("采购与库存数据", "excel"),
    "zhiyun-service-studio": ("售后服务工单", "excel"),
    "zhiyun-people-studio": ("组织与员工档案", "excel"),
    "zhiyun-app-discovery": ("应用与项目台账", "workspace"),
    "qwenpaw-knowledge-base": ("企业知识库文档", "workspace"),
}


# 知识库/工作区类应用在未导入真实文档前，data_sources.records 必须保持为空（0），
# 避免在全新初始化环境中伪造虚构记录数（见 AGENTS.md：不得用伪造数据证明实现）。
_EMPTY_RECORD_APPS = {"qwenpaw-knowledge-base"}


APP_DEFAULT_AGENT_MAP = {
    # 应用 -> 默认智能体（每个应用对应一个智能体，用于应用内「智能体对话」与问数）
    "zhiyun-data-core": "business_analyst",     # 统一数据中心 -> 经营分析
    "zhiyun-order-studio": "sales_quote",          # 智能订单中心 -> 销售报价
    "zhiyun-sales-studio": "customer_followup",    # 智能销售中心 -> 客户跟进
    "zhiyun-finance-studio": "finance_invoice",    # 智能财务中心 -> 财务票据
    "zhiyun-supply-studio": "procurement_recon",   # 采购与供应链中心 -> 采购对账
    "zhiyun-service-studio": "after_sales",        # 智能售后服务中心 -> 售后客服
    "zhiyun-people-studio": "expense_audit",       # 智能人力与协同中心 -> 报销审核
    "zhiyun-app-discovery": "business_analyst",   # 应用与项目中心 -> 经营分析
    "qwenpaw-knowledge-base": "business_analyst",  # 工作区知识库 -> 经营分析
}


def _resolve_default_agent(app_id: str, agents: list[dict[str, Any]]) -> str:
    """解析业务应用对应的默认智能体：优先精确映射，其次经营分析兜底，最后第一个智能体。"""
    target = APP_DEFAULT_AGENT_MAP.get(str(app_id))
    if target:
        for agt in agents:
            if agt.get("agent_id") == target or agt.get("id") == target:
                return target
    for agt in agents:
        if agt.get("agent_id") == "business_analyst":
            return "business_analyst"
    return (agents[0].get("agent_id") or agents[0].get("id") or "") if agents else ""


def _generate_enterprise(params: dict[str, Any]) -> dict[str, Any]:
    template = str(params.get("template") or DEFAULT_TEMPLATE)
    enterprise = str(params.get("enterprise") or "制造云科技").strip() or "制造云科技"
    start = _parse_date(params.get("start_date") or DEFAULT_START)
    end = _parse_date(params.get("end_date") or _today())
    if start > end:
        raise HTTPException(status_code=422, detail="起始日期不能晚于结束日期")
    scale = max(5, min(int(params.get("scale") or 50), 200))
    dept_count = max(3, min(int(params.get("departments") or 6), 12))
    agent_count = max(3, min(int(params.get("agents") or 9), 24))
    activity = str(params.get("activity") or DEFAULT_ACTIVITY)
    data_mode = _normalize_mode(str(params.get("data_mode") or DEFAULT_DATA_MODE))

    seed = params.get("seed")
    if seed is None:
        seed = (hash(enterprise + str(start) + str(end) + str(scale)) & 0x7FFFFFFF)
    rng = random.Random(int(seed))

    env_id = "env_" + uuid.uuid4().hex[:10]
    tenant_slug = "".join(c for c in enterprise.lower() if c.isalnum())[:16] or "ent"
    tenant_id = tenant_slug + "_" + env_id
    now = _now()
    activity_mult = _activity_multiplier(activity)

    conn = _connect()
    try:
        _ensure_schema()
        conn.execute(
            "INSERT INTO enterprise_meta (env_id, tenant_id, data_mode, enterprise, template, start_date, end_date, scale, departments, agent_count, activity, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (env_id, tenant_id, data_mode, enterprise, template, start.isoformat(), end.isoformat(),
             scale, dept_count, agent_count, activity, now, now),
        )

        # 部门
        dept_pool = DEPT_TEMPLATES.get(template, DEPT_TEMPLATES["manufacturing"])
        chosen = list(dept_pool) if dept_count >= len(dept_pool) else rng.sample(dept_pool, dept_count)
        if not any(d["code"] == "exec" for d in chosen):
            exec_dept = next((d for d in dept_pool if d["code"] == "exec"), dept_pool[0])
            chosen = chosen[:-1] + [exec_dept]
        depts = []
        for d in chosen:
            head = _make_name(rng) + "主管"
            depts.append({"name": d["name"], "code": d["code"], "parent": d["parent"], "head": head, "weight": d["weight"], "titles": d["titles"]})
            conn.execute(
                "INSERT INTO departments (env_id, tenant_id, data_mode, name, code, parent, head_user, weight, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (env_id, tenant_id, data_mode, d["name"], d["code"], d["parent"], head, d["weight"], now),
            )

        if len(depts) != dept_count:
            conn.execute("UPDATE enterprise_meta SET departments = ? WHERE env_id = ?", (len(depts), env_id))

        # 角色
        for role in ROLE_TEMPLATES:
            conn.execute(
                "INSERT INTO roles (env_id, tenant_id, data_mode, name, code, permissions, description, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (env_id, tenant_id, data_mode, role["name"], role["code"], json.dumps(role["permissions"], ensure_ascii=False), role["description"], now),
            )

        # 智能体
        agent_pool = AGENT_TEMPLATES.get(template, AGENT_TEMPLATES["manufacturing"])
        if agent_count >= len(agent_pool):
            agent_specs = list(agent_pool)
        else:
            base_pool = list(agent_pool)
            keep_analyst = next((a for a in base_pool if a["id"] == "business_analyst"), None)
            if keep_analyst:
                base_pool.remove(keep_analyst)
            agent_specs = rng.sample(base_pool, min(agent_count - 1, len(base_pool)))
            if keep_analyst:
                agent_specs.append(keep_analyst)
            agent_specs = agent_specs[:agent_count]
        agents = []
        for a in agent_specs:
            cfg = build_agent_config(a)
            dept_name = cfg["department"]
            conn.execute(
                "INSERT INTO agents (env_id, tenant_id, data_mode, agent_id, name, position, department, system_prompt, model, skills, tools, kb_scope, data_scope, max_tokens, execution_freq, work_start, work_end, auto_tasks, manual_tasks, success_rate, avg_response_ms, enabled, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (env_id, tenant_id, data_mode, cfg["agent_id"], cfg["name"], cfg["position"], dept_name,
                 cfg["system_prompt"], cfg["model"]["name"], json.dumps([s["name"] for s in cfg["skills"]], ensure_ascii=False),
                 json.dumps([t["tool_id"] for t in cfg["tools"]], ensure_ascii=False), cfg["kb_scope"], cfg["data_scope"],
                 cfg["max_tokens"], cfg["execution_freq"], cfg["work_start"], cfg["work_end"],
                 cfg["auto_tasks"], cfg["manual_tasks"], cfg["success_rate"], cfg["avg_response_ms"], 1, now),
            )
            for s in cfg["skills"]:
                conn.execute(
                    "INSERT INTO skills (env_id, tenant_id, data_mode, skill_id, name, agent_id, category, description, enabled, created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (env_id, tenant_id, data_mode, s["skill_id"], s["name"], a["id"], a["position"], f"{s['name']}能力，服务于{a['name']}。", 1, now),
                )
            persist_bindings(conn, env_id, tenant_id, data_mode, a, now)
            agents.append({**a, "agent_id": cfg["agent_id"], "department": dept_name, "enabled": 1})

        if len(agents) != agent_count:
            agent_count = len(agents)
            conn.execute("UPDATE enterprise_meta SET agent_count = ? WHERE env_id = ?", (agent_count, env_id))

        # 应用 + 数据源
        apps_by_id = {app["id"]: app for app in APP_TEMPLATES}
        for app in APP_TEMPLATES:
            conn.execute(
                "INSERT INTO apps (env_id, tenant_id, data_mode, app_id, name, category, agent_id, icon, enabled, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (env_id, tenant_id, data_mode, app["id"], app["name"], app["category"], _resolve_default_agent(app["id"], agents), app["icon"], 1, now),
            )
            source_name, source_type = DATA_SOURCE_MAP.get(app["id"], (app["name"], "workspace"))
            # 无真实导入数据的知识库类应用记录数保持为空（0），其余按业务体量生成。
            records = 0 if app["id"] in _EMPTY_RECORD_APPS else rng.randint(800, 5200)
            conn.execute(
                "INSERT INTO data_sources (env_id, tenant_id, data_mode, source_id, name, source_type, app_id, records, shared, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (env_id, tenant_id, data_mode, f"{app['id']}_ds", source_name, source_type, app["id"], records, 1 if app["category"] == "系统" else 0, now),
            )

        # 员工
        user_rows = _build_users(depts, agents, scale, rng, enterprise, data_mode, env_id, tenant_id)
        for row in user_rows:
            conn.execute(
                "INSERT INTO org_users (env_id, tenant_id, data_mode, username, display_name, department, role, title, agent_id, data_scope, kb_scope, active, dormant, hired_on, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (env_id, tenant_id, data_mode, row["username"], row["display_name"], row["department"], row["role"],
                 row["title"], row["agent_id"], row["data_scope"], row["kb_scope"], row["active"], row["dormant"],
                 row["hired_on"], row["created_at"]),
            )

        # 应用->岗位映射
        dept_apps = {}
        for dept in depts:
            app_ids = DEPT_APP_MAP.get(dept["name"], ["zhiyun-data-core", "zhiyun-app-discovery"])
            dept_apps[dept["name"]] = [{"app_id": apps_by_id[a]["id"], "name": apps_by_id[a]["name"], "category": apps_by_id[a]["category"]} for a in app_ids if a in apps_by_id]
        dept_apps["total"] = [{"app_id": a["id"], "name": a["name"], "category": a["category"]} for a in apps_by_id.values()]

        # 逐日生成业务活动
        agents_by_id = {a["agent_id"]: a for a in agents}
        active_pool = [r for r in user_rows if r["dormant"] == 0]
        total_days = max((end - start).days + 1, 1)
        totals = {"days": 0, "sessions": 0, "calls": 0, "success": 0, "failed": 0, "tokens": 0}
        for di in range(total_days):
            day = start + timedelta(days=di)
            growth = 0.4 + 0.6 * (di / max(total_days - 1, 1))
            enabled_count = max(1, round(len(agents) * (0.5 + 0.5 * growth)))
            enabled_agents = agents[:enabled_count]
            enabled_ids = {a["agent_id"] for a in enabled_agents}
            day_active_eligible = [r for r in active_pool if r["agent_id"] in enabled_ids]
            if not day_active_eligible:
                continue
            user_count = max(1, round(scale * growth))
            active_users = rng.sample(day_active_eligible, min(user_count, len(day_active_eligible)))
            plan = build_day_events(day, active_users, enabled_agents, agents_by_id, dept_apps, apps_by_id,
                                    env_id, tenant_id, data_mode, activity_mult, rng)
            st = execute_day_events(conn, plan)
            totals["days"] += 1
            totals["sessions"] += st["sessions"]
            totals["calls"] += st["calls"]
            totals["success"] += st["success"]
            totals["failed"] += st["failed"]
            totals["tokens"] += st["tokens"]
            # 操作日志：抽样记录用户进入应用/触发智能体
            if active_users and rng.random() < 0.5:
                u = rng.choice(active_users)
                app = rng.choice(dept_apps.get(u["department"], dept_apps["total"]))
                conn.execute(
                    "INSERT INTO operation_logs (env_id, tenant_id, data_mode, day, user_id, agent_id, app_id, action, detail, level, created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (env_id, tenant_id, data_mode, day.isoformat(), u["username"], u["agent_id"], app["app_id"],
                     "应用访问", f"{u['display_name']} 打开 {app['name']}", "info", now),
                )
            # 登录活动：非全员每日登录，按业务波动抽样，避免"所有用户每天登录"的生成痕迹
            lf = _workday_factor(day) * _month_factor(day)
            if lf > 0.1 and active_users:
                ratio = min(0.85, 0.30 + 0.40 * activity_mult * lf)
                login_count = max(1, int(round(len(active_users) * ratio)))
                login_pool = rng.sample(active_users, min(login_count, len(active_users)))
                for u in login_pool:
                    lapp = rng.choice(dept_apps.get(u["department"], dept_apps["total"]))
                    login_ok = rng.random() < 0.96
                    login_at = _pick_time(rng)
                    lip = f"10.{rng.randint(10, 48)}.{rng.randint(1,254)}.{rng.randint(1,254)}"
                    conn.execute(
                        "INSERT INTO login_activity (env_id, tenant_id, data_mode, day, user_id, agent_id, app_id, login_at, ip, device, success, status, created_at) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (env_id, tenant_id, data_mode, day.isoformat(), u["username"], u["agent_id"], lapp["app_id"],
                         f"{day.isoformat()} {login_at}:00", lip, rng.choice(_LOGIN_DEVICES),
                         1 if login_ok else 0, "在线" if login_ok else "登出", now),
                    )

        conn.commit()

        # 汇总计数
        summary = {
            "env_id": env_id, "tenant_id": tenant_id, "data_mode": data_mode,
            "enterprise": enterprise, "template": template, "start_date": start.isoformat(),
            "end_date": end.isoformat(), "scale": scale, "days": totals["days"],
            "departments": len(depts), "org_users": len(user_rows),
            "agents": len(agents), "apps": len(APP_TEMPLATES), "data_sources": len(APP_TEMPLATES),
            "sessions": totals["sessions"], "tasks": totals["calls"],
            "token_total": totals["tokens"], "success": totals["success"], "failed": totals["failed"],
        }
        sync = _sync_auth_users(user_rows, enterprise, env_id, data_mode)
        summary["auth"] = sync
        return summary
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# 请求模型与路由
# ---------------------------------------------------------------------------


class SeedRequest(BaseModel):
    template: str = Field(default=DEFAULT_TEMPLATE, max_length=80)
    enterprise: str = Field(default="制造云科技", max_length=80)
    start_date: str = Field(default=DEFAULT_START)
    end_date: str | None = None
    scale: int = Field(default=50, ge=5, le=200)
    departments: int = Field(default=6, ge=3, le=12)
    agents: int = Field(default=9, ge=3, le=24)
    activity: str = Field(default=DEFAULT_ACTIVITY, max_length=20)
    data_mode: str = Field(default=DEFAULT_DATA_MODE, max_length=20)
    seed: int | None = None


class AgentSpecRequest(BaseModel):
    """Agent Factory 校验用智能体规格请求体。"""
    id: str = Field(default="business_analyst", max_length=80)
    name: str = Field(default="数字员工", max_length=80)
    position: str = Field(default="业务岗位", max_length=40)
    department: str = Field(default="管理层", max_length=40)
    category: str = Field(default="analytics", max_length=40)
    model_id: str = Field(default="", max_length=60)
    max_tokens: int = Field(default=8192, ge=512, le=131072)
    execution_freq: int = Field(default=5, ge=1, le=60)
    work_start: str = Field(default="09:00", max_length=5)
    work_end: str = Field(default="18:00", max_length=5)
    auto_tasks: int = Field(default=0, ge=0, le=200)
    manual_tasks: int = Field(default=0, ge=0, le=200)
    success_rate: float = Field(default=0.9, ge=0, le=1)
    avg_response_ms: int = Field(default=1800, ge=100, le=60000)
    kb_scope: str = Field(default="enterprise", max_length=40)
    data_scope: str = Field(default="enterprise", max_length=40)
    skills: list[list[str]] = Field(default_factory=lambda: [["数据查询", "query"]])
    tools: list[str] = Field(default_factory=list)


class AgentReconcileRequest(BaseModel):
    """为旧环境的智能体回填 Model / Tool / App 绑定。"""
    env_id: str = Field(default="", max_length=64)
    data_mode: str = Field(default="", max_length=20)


class SimulationRunRequest(BaseModel):
    """Simulation Runtime 触发请求体。"""
    env_id: str = Field(default="", max_length=64)
    data_mode: str = Field(default="demo", max_length=20)
    start_date: str = Field(default="")
    end_date: str = Field(default="")
    seed: int = Field(default=0)
    force: bool = Field(default=False)


ENGINES = {"departments", "org_users", "roles", "agents", "skills", "apps",
           "agent_app_access", "data_sources", "sessions", "tasks", "token_usage", "operation_logs",
           "files", "file_downloads", "login_activity"}

_TIME_COLUMNS = {
    "sessions": "started_at",
    "tasks": "started_at",
    "token_usage": "day",
    "operation_logs": "day",
    "files": "created_at",
    "file_downloads": "downloaded_at",
    "login_activity": "day",
    "agent_app_access": "created_at",
}


_KB_ENTITIES = {"data_sources", "files", "file_downloads", "agent_app_access"}


def _range_sql(env_id: str, data_mode: str, table: str, date_col: str, start_date: str = "", end_date: str = "") -> tuple[str, list[Any]]:
    """构造某张表在指定时间范围内的 SQL 片段，返回 (where, args)。"""
    where = "WHERE env_id = ? AND data_mode = ?"
    args: list[Any] = [env_id, data_mode]
    if start_date:
        where += f" AND substr({date_col}, 1, 10) >= ?"
        args.append(start_date)
    if end_date:
        where += f" AND substr({date_col}, 1, 10) <= ?"
        args.append(end_date)
    return where, args



def _user_env(user: dict[str, Any]) -> tuple[str, str]:
    """返回 (env_id, data_mode) 给调用方用于 RBAC 数据隔离。

    优先取 auth 用户上持久化的 env_id / data_mode；若缺失则回退到
    enterprise_meta 按企业名匹配最新一条。无法解析时返回 ("", "")，调用方
    应拒绝访问。
    """
    env_id = str(user.get("env_id") or "")
    data_mode = str(user.get("data_mode") or "")
    if env_id and data_mode:
        return env_id, data_mode
    if not env_id or not data_mode:
        enterprise = str(user.get("enterprise") or "")
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT env_id, data_mode FROM enterprise_meta WHERE enterprise = ? ORDER BY id DESC LIMIT 1",
                (enterprise,),
            ).fetchone()
            if row:
                if not env_id:
                    env_id = row["env_id"]
                if not data_mode:
                    data_mode = row["data_mode"]
        finally:
            conn.close()
    return env_id, data_mode


def _enforce_user_env(user: dict[str, Any]) -> tuple[str, str]:
    """对非管理员解析并强制其所属企业环境；无法解析时返回 403。"""
    env_id, data_mode = _user_env(user)
    if not env_id or not data_mode:
        raise HTTPException(status_code=403, detail="无法确定当前账号所属企业环境")
    return env_id, data_mode


def _user_context(user: dict[str, Any], env_id: str = "") -> tuple[str, str, str]:
    """返回 (department, agent_id, user_id)，供按用户范围过滤使用。"""
    username = str(user.get("username") or "")
    agent = str(user.get("agent_id") or "")
    dept = ""
    conn = _connect()
    try:
        sql = "SELECT department, agent_id FROM org_users WHERE username = ?"
        args: list[Any] = [username]
        if env_id:
            sql += " AND env_id = ?"
            args.append(env_id)
        sql += " ORDER BY id DESC LIMIT 1"
        row = conn.execute(sql, args).fetchone()
        if row:
            dept = row["department"] or ""
            if not agent:
                agent = row["agent_id"] or ""
    finally:
        conn.close()
    return dept, agent, username


def _kb_department_clause(entity: str, dept: str, env_id: str = "") -> tuple[str, list[Any]]:
    """知识库类实体的部门范围限制：当用户 kb_scope=department 时使用。"""
    def _agents() -> tuple[str, list[Any]]:
        sql = "SELECT agent_id FROM agents WHERE department = ?"
        args: list[Any] = [dept]
        if env_id:
            sql += " AND env_id = ?"
            args.append(env_id)
        return sql, args

    def _users() -> tuple[str, list[Any]]:
        sql = "SELECT username FROM org_users WHERE department = ?"
        args: list[Any] = [dept]
        if env_id:
            sql += " AND env_id = ?"
            args.append(env_id)
        return sql, args

    if entity == "data_sources":
        a_sql, a_args = _agents()
        return (f"app_id IN (SELECT app_id FROM apps WHERE agent_id IN ({a_sql}))", a_args)
    if entity in ("files", "file_downloads"):
        a_sql, a_args = _agents()
        u_sql, u_args = _users()
        return (f"(agent_id IN ({a_sql}) OR user_id IN ({u_sql}))", a_args + u_args)
    if entity == "agent_app_access":
        a_sql, a_args = _agents()
        return (f"agent_id IN ({a_sql})", a_args)
    return ("1 = 1", [])


def _scope_clause(entity: str, user: dict[str, Any], env_id: str = "") -> tuple[str, list[Any]]:
    """构造非管理员用户的企业/部门/智能体/知识库数据范围 SQL 片段。

    - 数据域 data_scope 控制业务实体：enterprise=本环境全部；department=本部门。
    - 知识域 kb_scope 控制知识库类实体（files/data_sources/file_downloads/
      agent_app_access）：enterprise=本环境全部；department=本部门。
    env_id 用于在跨环境存在同名部门/智能体时仍隔离到正确环境。
    """
    dept, agent, uid = _user_context(user, env_id)
    kb_scope = str(user.get("kb_scope") or "enterprise")
    data_scope = str(user.get("data_scope") or "enterprise")

    # 知识域：kb_scope=department 时按部门限制知识类实体
    if entity in _KB_ENTITIES:
        if kb_scope != "department" or not dept:
            return ("1 = 1", [])
        return _kb_department_clause(entity, dept, env_id)

    # 非知识库实体按数据域控制
    if entity == "roles":
        return ("1 = 0", [])
    if data_scope == "enterprise":
        return ("1 = 1", [])
    if entity == "departments":
        return ("name = ?", [dept]) if dept else ("1 = 0", [])
    if entity == "org_users":
        return ("department = ?", [dept]) if dept else ("username = ?", [uid])
    if entity == "agents":
        if agent:
            return ("agent_id = ?", [agent])
        if dept:
            return ("department = ?", [dept])
        return ("1 = 0", [])
    if entity in ("skills", "apps", "sessions", "tasks", "token_usage", "agent_app_access"):
        return ("agent_id = ?", [agent]) if agent else ("1 = 0", [])
    if entity == "data_sources":
        return ("app_id IN (SELECT app_id FROM apps WHERE agent_id = ?)", [agent]) if agent else ("1 = 0", [])
    if entity in ("files", "file_downloads", "login_activity"):
        return ("agent_id = ?", [agent]) if agent else ("user_id = ?", [uid])
    if entity == "operation_logs":
        return ("user_id = ?", [uid])
    return ("1 = 1", [])


def _records(entity: str, limit: int, offset: int, env_id: str = "", data_mode: str = "", start_date: str = "", end_date: str = "", user: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    if entity not in ENGINES:
        raise HTTPException(status_code=404, detail=f"未知实体 {entity}")
    if start_date:
        _parse_date(start_date)
    if end_date:
        _parse_date(end_date)
    conn = _connect()
    try:
        if not env_id and not data_mode:
            row = conn.execute("SELECT env_id, data_mode FROM enterprise_meta ORDER BY id DESC LIMIT 1").fetchone()
            if row:
                env_id = row["env_id"]
                data_mode = row["data_mode"]
        clauses: list[str] = []
        args: list[Any] = []
        if env_id:
            clauses.append("env_id = ?")
            args.append(env_id)
        if data_mode:
            clauses.append("data_mode = ?")
            args.append(data_mode)
        if user is not None and user.get("role") != "admin":
            # 数据域与知识域独立判定：即使 data_scope=enterprise，
            # kb_scope=department 也必须对知识库类实体生效。
            clause, scope_args = _scope_clause(entity, user, env_id)
            if clause != "1 = 1":
                clauses.append(clause)
                args.extend(scope_args)
        # Epic 4 Time Machine：按实体时间列做时间范围过滤
        if (start_date or end_date) and entity in _TIME_COLUMNS:
            date_col = _TIME_COLUMNS[entity]
            if start_date:
                clauses.append(f"substr({date_col}, 1, 10) >= ?")
                args.append(start_date)
            if end_date:
                clauses.append(f"substr({date_col}, 1, 10) <= ?")
                args.append(end_date)
        sql = f"SELECT * FROM {entity}"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
        args.extend([limit, offset])
        cur = conn.execute(sql, args)
        rows = [dict(r) for r in cur.fetchall()]
        return rows
    finally:
        conn.close()


@router.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "version": PLUGIN_VERSION,
        "database": str(DB),
        "database_exists": DB.exists(),
    }


@router.get("/config")
async def config(authorization: str = Header(default="")) -> dict[str, Any]:
    _require_auth(authorization)
    return {
        "version": PLUGIN_VERSION,
        "database": str(DB),
        "defaults": {
            "template": DEFAULT_TEMPLATE,
            "enterprise": "制造云科技",
            "start_date": DEFAULT_START,
            "end_date": _today(),
            "scale": 50,
            "departments": 6,
            "agents": 9,
            "activity": DEFAULT_ACTIVITY,
            "data_mode": DEFAULT_DATA_MODE,
        },
        "templates": list(DEPT_TEMPLATES.keys()),
        "departments": {t: [d["name"] for d in v] for t, v in DEPT_TEMPLATES.items()},
        "agents": {t: [a["name"] for a in v] for t, v in AGENT_TEMPLATES.items()},
        "apps": [a["name"] for a in APP_TEMPLATES],
    }


@router.get("/summary")
async def summary(
    authorization: str = Header(default=""),
    data_mode: str = Query(default="", max_length=20),
    start_date: str = Query(default="", max_length=10),
    end_date: str = Query(default="", max_length=10),
    limit: int = Query(default=1, ge=1, le=20),
) -> dict[str, Any]:
    _require_auth(authorization)
    data_mode = _normalize_mode(data_mode)
    if start_date:
        _parse_date(start_date)
    if end_date:
        _parse_date(end_date)
    conn = _connect()
    try:
        mode_where = "WHERE data_mode = ?" if data_mode else ""
        mode_args = (data_mode,) if data_mode else ()
        cur = conn.execute(f"SELECT * FROM enterprise_meta {mode_where} ORDER BY id DESC LIMIT ?", mode_args + (limit,))
        metas = [dict(r) for r in cur.fetchall()]
        results = []
        for meta in metas:
            env_id, mode = meta["env_id"], meta["data_mode"]
            def count(table: str) -> int:
                return conn.execute(
                    f"SELECT COUNT(*) AS c FROM {table} WHERE env_id = ? AND data_mode = ?", (env_id, mode)
                ).fetchone()["c"]
            # Epic 4 Time Machine：默认全量；指定时间范围后按日聚合会话/任务/Token
            sessions = count("sessions")
            tasks = count("tasks")
            token_where, token_args = _range_sql(env_id, mode, "token_usage", "day", start_date, end_date)
            tokens = conn.execute(
                "SELECT COALESCE(SUM(tokens),0) AS t, COALESCE(SUM(calls),0) AS c, "
                "COALESCE(SUM(success),0) AS s, COALESCE(SUM(failed),0) AS f "
                "FROM token_usage " + token_where, token_args
            ).fetchone()
            if start_date or end_date:
                sw, sa = _range_sql(env_id, mode, "sessions", "started_at", start_date, end_date)
                sessions = conn.execute("SELECT COUNT(*) AS c FROM sessions " + sw, sa).fetchone()["c"]
                tw, ta = _range_sql(env_id, mode, "tasks", "started_at", start_date, end_date)
                tasks = conn.execute("SELECT COUNT(*) AS c FROM tasks " + tw, ta).fetchone()["c"]
            fw, fa = _range_sql(env_id, mode, "files", "created_at", start_date, end_date)
            files = conn.execute("SELECT COUNT(*) AS c FROM files " + fw, fa).fetchone()["c"]
            dw, da = _range_sql(env_id, mode, "file_downloads", "downloaded_at", start_date, end_date)
            downloads = conn.execute("SELECT COUNT(*) AS c FROM file_downloads " + dw, da).fetchone()["c"]
            lw, la = _range_sql(env_id, mode, "login_activity", "day", start_date, end_date)
            logins = conn.execute("SELECT COUNT(*) AS c FROM login_activity " + lw, la).fetchone()["c"]
            results.append({
                **meta,
                "departments": count("departments"),
                "org_users": count("org_users"),
                "agents": count("agents"),
                "apps": count("apps"),
                "data_sources": count("data_sources"),
                "sessions": sessions,
                "tasks": tasks,
                "token_total": tokens["t"],
                "calls": tokens["c"],
                "success": tokens["s"],
                "failed": tokens["f"],
                "files": files,
                "downloads": downloads,
                "logins": logins,
                "query_start": start_date or meta["start_date"],
                "query_end": end_date or meta["end_date"],
            })
        return {"total": len(metas), "summary": results, "range": {"start_date": start_date or "", "end_date": end_date or ""}}
    finally:
        conn.close()


@router.get("/analytics/trends")
async def analytics_trends(
    authorization: str = Header(default=""),
    env_id: str = Query(default="", max_length=64),
    data_mode: str = Query(default="", max_length=20),
    start_date: str = Query(default="", max_length=10),
    end_date: str = Query(default="", max_length=10),
    granularity: str = Query(default="day", max_length=10),
) -> dict[str, Any]:
    """Epic 4 Time Machine：按日/周/月返回活动趋势、工作日/周末均值与增长曲线。

    任意时间范围均来自企业环境元数据默认起止日期或调用方指定，口径与
    /summary、/records 完全一致：sessions/tasks/tokens/calls/files/downloads/
    logins/operations，并给出工作日与周末平均活跃、以及智能体/用户累计增长。
    """
    _require_auth(authorization)
    data_mode = _normalize_mode(data_mode)
    if granularity not in ("day", "week", "month"):
        raise HTTPException(status_code=422, detail="granularity 只能是 day / week / month")
    if start_date:
        _parse_date(start_date)
    if end_date:
        _parse_date(end_date)
    conn = _connect()
    try:
        meta = None
        if env_id:
            if data_mode:
                meta = conn.execute(
                    "SELECT * FROM enterprise_meta WHERE env_id = ? AND data_mode = ? ORDER BY id DESC LIMIT 1",
                    (env_id, data_mode),
                ).fetchone()
            if not meta:
                meta = conn.execute(
                    "SELECT * FROM enterprise_meta WHERE env_id = ? ORDER BY id DESC LIMIT 1",
                    (env_id,),
                ).fetchone()
        else:
            mode_where = "WHERE data_mode = ?" if data_mode else ""
            mode_args: list[Any] = (data_mode,) if data_mode else ()
            meta = conn.execute(
                f"SELECT * FROM enterprise_meta {mode_where} ORDER BY id DESC LIMIT 1", mode_args
            ).fetchone()
        if not meta:
            raise HTTPException(status_code=404, detail="尚未初始化企业环境")
        env_id = meta["env_id"]
        mode = meta["data_mode"]
        s = start_date or meta["start_date"] or DEFAULT_START
        e = end_date or meta["end_date"] or _today()
        return _build_trends(
            conn, env_id=env_id, data_mode=mode, start_date=s, end_date=e, granularity=granularity
        )
    finally:
        conn.close()
@router.post("/seed")
async def seed(request: SeedRequest, authorization: str = Header(default="")) -> dict[str, Any]:
    _require_admin(authorization)
    try:
        result = _generate_enterprise({
            "template": request.template, "enterprise": request.enterprise,
            "start_date": request.start_date, "end_date": request.end_date or _today(),
            "scale": request.scale, "departments": request.departments, "agents": request.agents,
            "activity": request.activity, "data_mode": request.data_mode, "seed": request.seed,
        })
        return {"ok": True, "summary": result}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - 统一转为 4xx 失败响应
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/records/{entity}")
async def records(
    entity: str,
    authorization: str = Header(default=""),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    data_mode: str = Query(default="", max_length=20),
    env_id: str = Query(default="", max_length=64),
    start_date: str = Query(default="", max_length=10),
    end_date: str = Query(default="", max_length=10),
) -> dict[str, Any]:
    user = _require_auth(authorization)
    if user.get("role") != "admin":
        env_id, data_mode = _enforce_user_env(user)
    rows = _records(entity, limit, offset, env_id, data_mode, start_date, end_date, user)
    return {"entity": entity, "count": len(rows), "rows": rows, "data_mode": data_mode, "env_id": env_id, "range": {"start_date": start_date, "end_date": end_date}}



def _integrity_report(env_id: str = "", data_mode: str = "") -> dict[str, Any]:
    """Epic 6 Data Integrity：跨模块一致性检查，返回 Data Integrity Report。"""
    conn = _connect()
    try:
        if not env_id or not data_mode:
            row = conn.execute("SELECT env_id, data_mode FROM enterprise_meta ORDER BY id DESC LIMIT 1").fetchone()
            if row:
                env_id = row["env_id"]
                data_mode = row["data_mode"]
        if not env_id:
            return {"status": "empty", "message": "尚未初始化企业环境", "report": []}

        def one(sql: str, args: tuple) -> int | float:
            return conn.execute(sql, args).fetchone()[0]

        base_args = (env_id, data_mode)

        def sum_col(table: str, col: str) -> int:
            return int(one(f"SELECT COALESCE(SUM({col}),0) FROM {table} WHERE env_id=? AND data_mode=?", base_args))

        org_users = int(one("SELECT COUNT(*) FROM org_users WHERE env_id=? AND data_mode=?", base_args))
        agent_count = int(one("SELECT COUNT(*) FROM agents WHERE env_id=? AND data_mode=?", base_args))
        sessions = int(one("SELECT COUNT(*) FROM sessions WHERE env_id=? AND data_mode=?", base_args))
        tasks = int(one("SELECT COUNT(*) FROM tasks WHERE env_id=? AND data_mode=?", base_args))

        task_token = sum_col("tasks", "tokens")
        token_total = sum_col("token_usage", "tokens")
        token_calls = sum_col("token_usage", "calls")
        token_success = sum_col("token_usage", "success")
        token_failed = sum_col("token_usage", "failed")

        orphan_sess_users = int(one(
            "SELECT COUNT(*) FROM sessions s WHERE s.env_id=? AND s.data_mode=? "
            "AND NOT EXISTS (SELECT 1 FROM org_users u WHERE u.username=s.user_id AND u.env_id=s.env_id AND u.data_mode=s.data_mode)",
            base_args))
        orphan_sess_agents = int(one(
            "SELECT COUNT(*) FROM sessions s WHERE s.env_id=? AND s.data_mode=? "
            "AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.agent_id=s.agent_id AND a.env_id=s.env_id AND a.data_mode=s.data_mode)",
            base_args))
        orphan_tasks = int(one(
            "SELECT COUNT(*) FROM tasks t WHERE t.env_id=? AND t.data_mode=? "
            "AND NOT EXISTS (SELECT 1 FROM sessions s WHERE s.session_id=t.session_id AND s.env_id=t.env_id AND s.data_mode=t.data_mode)",
            base_args))
        users_no_agent = int(one(
            "SELECT COUNT(*) FROM org_users u WHERE u.env_id=? AND u.data_mode=? AND (u.agent_id IS NULL OR u.agent_id='')",
            base_args))

        auth_users = _read_auth_users()
        missing_login = 0
        for u in auth_users:
            if not u.get("active", True):
                continue
            agent = u.get("agent_id") or "default"
            if agent == "default":
                continue
            exists = int(one(
                "SELECT COUNT(*) FROM org_users WHERE username=?",
                (u.get("username", ""),)))
            if exists == 0:
                missing_login += 1
        overall_failed = token_failed

        perm_violations = int(one(
            "SELECT COUNT(*) FROM sessions s "
            "WHERE s.env_id=? AND s.data_mode=? "
            "AND EXISTS (SELECT 1 FROM org_users u WHERE u.username=s.user_id AND u.env_id=s.env_id AND u.data_mode=s.data_mode) "
            "AND NOT EXISTS (SELECT 1 FROM org_users u WHERE u.username=s.user_id AND u.env_id=s.env_id AND u.data_mode=s.data_mode AND u.agent_id=s.agent_id)",
            base_args))

        file_count = int(one("SELECT COUNT(*) FROM files WHERE env_id=? AND data_mode=?", base_args))
        orphan_files = int(one(
            "SELECT COUNT(*) FROM files f WHERE f.env_id=? AND f.data_mode=? "
            "AND NOT EXISTS (SELECT 1 FROM tasks t WHERE t.task_id=f.task_id AND t.env_id=f.env_id AND t.data_mode=f.data_mode)",
            base_args))
        download_rows = int(one("SELECT COUNT(*) FROM file_downloads WHERE env_id=? AND data_mode=?", base_args))
        orphan_downloads = int(one(
            "SELECT COUNT(*) FROM file_downloads d WHERE d.env_id=? AND d.data_mode=? "
            "AND NOT EXISTS (SELECT 1 FROM files f WHERE f.file_id=d.file_id AND f.env_id=d.env_id AND f.data_mode=d.data_mode)",
            base_args))
        file_download_sum = int(one("SELECT COALESCE(SUM(download_count),0) FROM files WHERE env_id=? AND data_mode=?", base_args))
        login_count = int(one("SELECT COUNT(*) FROM login_activity WHERE env_id=? AND data_mode=?", base_args))
        # Epic 3：业务事件链完整性（business_events 引用的 session/task/file/download/user/agent 必须存在）。
        bus_events = int(one("SELECT COUNT(*) FROM business_events WHERE env_id=? AND data_mode=?", base_args))
        bus_orphan_total = 0
        for bcol, tbl, scol in (
            ("session_id", "sessions", "x.session_id"),
            ("task_id", "tasks", "x.task_id"),
            ("file_id", "files", "x.file_id"),
            ("download_id", "file_downloads", "x.download_id"),
            ("user_id", "org_users", "x.username"),
            ("agent_id", "agents", "x.agent_id"),
        ):
            bus_orphan_total += int(one(
                "SELECT COUNT(*) FROM business_events b WHERE b.env_id=? AND b.data_mode=? "
                f"AND b.{bcol} IS NOT NULL AND b.{bcol}<>'' "
                f"AND NOT EXISTS (SELECT 1 FROM {tbl} x WHERE {scol}=b.{bcol} "
                "AND x.env_id=b.env_id AND x.data_mode=b.data_mode)",
                base_args))
        agent_100 = int(one(
            "SELECT COUNT(*) FROM agents WHERE env_id=? AND data_mode=? AND success_rate >= 1.0",
            base_args))
        success_anomaly = agent_100 > 0 or (token_calls > 0 and overall_failed == 0)
        daily_tokens = [int(r[0]) for r in conn.execute(
            "SELECT COALESCE(SUM(tokens),0) FROM token_usage WHERE env_id=? AND data_mode=? GROUP BY day ORDER BY day",
            base_args).fetchall()]
        drops = 0
        flats = 0
        for i in range(1, len(daily_tokens)):
            if daily_tokens[i] < daily_tokens[i-1]:
                drops += 1
            elif daily_tokens[i] == daily_tokens[i-1]:
                flats += 1
        volatile_ok = len(daily_tokens) >= 2 and drops > 0
        checks: list[dict[str, Any]] = []

        def add_check(cid, name, passed, expected, actual, detail):
            checks.append({
                "id": cid, "name": name, "status": "pass" if passed else "fail",
                "passed": int(bool(passed)), "expected": expected, "actual": actual, "detail": detail,
            })

        add_check("execution_total", "执行总数（成功 + 失败 = 调用）",
                  token_success + token_failed == token_calls,
                  token_calls, token_success + token_failed,
                  f"Token 调用 {token_calls}，成功 {token_success}，失败 {token_failed}")
        add_check("token_consistency", "Token 一致性（任务 Token = Token 汇总）",
                  task_token == token_total,
                  token_total, task_token,
                  f"任务 Token {task_token}，Token 汇总 {token_total}")
        add_check("session_user_scope", "会话归属用户（无孤儿用户）",
                  orphan_sess_users == 0, 0, orphan_sess_users,
                  f"孤儿会话用户数 {orphan_sess_users}")
        add_check("session_agent_scope", "会话归属智能体（无孤儿智能体）",
                  orphan_sess_agents == 0, 0, orphan_sess_agents,
                  f"孤儿会话智能体数 {orphan_sess_agents}")
        add_check("task_session_scope", "任务归属会话（无孤儿任务）",
                  orphan_tasks == 0, 0, orphan_tasks,
                  f"孤儿任务数 {orphan_tasks}")
        add_check("user_agent_binding", "员工绑定智能体（无缺失绑定）",
                  users_no_agent == 0, 0, users_no_agent,
                  f"未绑定智能体员工数 {users_no_agent}")
        add_check("login_binding", "登录账号回查企业员工（无丢失账号）",
                  missing_login == 0, 0, missing_login,
                  f"无法回查的登录账号数 {missing_login}")

        add_check("file_task_scope", "文件归属任务（无孤儿文件）",
                  orphan_files == 0, 0, orphan_files,
                  f"孤儿文件数 {orphan_files}，总数 {file_count}")
        add_check("file_download_scope", "下载记录归属文件（无孤儿下载）",
                  orphan_downloads == 0, 0, orphan_downloads,
                  f"孤儿下载记录数 {orphan_downloads}，总数 {download_rows}")
        add_check("file_download_consistency", "文件下载计数一致（下载事件 = 文件累计下载）",
                  download_rows == file_download_sum, file_download_sum, download_rows,
                  f"下载事件 {download_rows}，文件累计下载 {file_download_sum}")
        add_check("permission_scope", "权限管控（用户不访问无权限智能体）",
                  perm_violations == 0, 0, perm_violations,
                  f"越权访问次数 {perm_violations}")
        add_check("success_rate_variance", "成功率真实（不存在 100% 成功率）",
                  not success_anomaly, 0, int(success_anomaly),
                  f"100% 成功率智能体数 {agent_100}；整体失败 {overall_failed}")
        add_check("daily_volatility", "日常波动（Token 非单调递增）",
                  volatile_ok, 1, drops,
                  f"采样日 {len(daily_tokens)}，下降日 {drops}，持平日 {flats}")
        add_check("business_event_scope", "业务事件链完整（无孤儿引用）",
                  bus_orphan_total == 0, 0, bus_orphan_total,
                  f"业务事件 {bus_events}，孤儿引用 {bus_orphan_total}")
        passed = sum(1 for c in checks if c["status"] == "pass")
        return {
            "status": "ready",
            "env_id": env_id,
            "data_mode": data_mode,
            "org_users": org_users,
            "agents": agent_count,
            "sessions": sessions,
            "tasks": tasks,
            "files": file_count,
            "downloads": download_rows,
            "logins": login_count,
            "business_events": bus_events,
            "total": len(checks),
            "passed": passed,
            "failed": len(checks) - passed,
            "healthy": passed == len(checks),
            "report": checks,
        }
    finally:
        conn.close()




def _integrity_target(conn: sqlite3.Connection, env_id: str, data_mode: str) -> tuple[str, str]:
    """解析一致性检查目标环境：缺省时取 enterprise_meta 最新一条记录。"""
    if not env_id or not data_mode:
        row = conn.execute("SELECT env_id, data_mode FROM enterprise_meta ORDER BY id DESC LIMIT 1").fetchone()
        if row:
            return row["env_id"], row["data_mode"]
    return env_id or "", _normalize_mode(data_mode) if data_mode else ""


def _repair_integrity(env_id: str = "", data_mode: str = "", run_by: str = "") -> dict[str, Any]:
    """Epic 6 Data Integrity：安全自动修复策略。

    只修复语义明确、可逆且不引入伪造数据的项：
      - 会话孤儿（用户/智能体不存在） -> 删除该会话
      - 任务孤儿（会话不存在）       -> 删除该任务
      - 文件孤儿（任务不存在）       -> 删除该文件
      - 下载孤儿（文件不存在）       -> 删除该下载记录
      - 下载计数不一致               -> 依据下载事件回写 files.download_count
      - 员工未绑定智能体             -> 回填同环境下首个可用智能体
      - 业务事件 Token 记账          -> 非任务事件 Token 归零（session/file/download 不重复计）
    需要人工决策的项（登录回查 / 权限管控 / 成功率方差 / 日常波动 / 业务事件链引用完整性）不改动。
    全部行为写入 integrity_repair_log，便于审计。
    """
    conn = _connect()
    try:
        env_id, data_mode = _integrity_target(conn, env_id, data_mode)
        if not env_id:
            return {"status": "empty", "message": "尚未初始化企业环境", "repairs": []}
        base_args = (env_id, data_mode)
        day = _today()
        repairs: list[dict[str, Any]] = []
        log_entries: list[tuple[Any, ...]] = []

        def run(cid: str, action: str, sql: str) -> int:
            cur = conn.execute(sql, base_args)
            n = max(int(cur.rowcount), 0)
            repairs.append({"check_id": cid, "action": action, "affected": n})
            log_entries.append((env_id, data_mode, day, cid, action, n, f"{action}影响 {n} 条", run_by, _now()))
            return n

        # 1) 会话孤儿（用户或智能体不存在）——删除会话，后续孤儿任务由第 2 步处理
        run("session_user_scope", "删除无归属用户会话",
            "DELETE FROM sessions WHERE env_id=? AND data_mode=? AND user_id<>'' "
            "AND NOT EXISTS (SELECT 1 FROM org_users u WHERE u.username=sessions.user_id "
            "AND u.env_id=sessions.env_id AND u.data_mode=sessions.data_mode)")
        run("session_agent_scope", "删除无归属智能体会话",
            "DELETE FROM sessions WHERE env_id=? AND data_mode=? AND agent_id<>'' "
            "AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.agent_id=sessions.agent_id "
            "AND a.env_id=sessions.env_id AND a.data_mode=sessions.data_mode)")
        # 2) 任务孤儿（会话不存在）
        run("task_session_scope", "删除无归属会话任务",
            "DELETE FROM tasks WHERE env_id=? AND data_mode=? AND session_id<>'' "
            "AND NOT EXISTS (SELECT 1 FROM sessions s WHERE s.session_id=tasks.session_id "
            "AND s.env_id=tasks.env_id AND s.data_mode=tasks.data_mode)")
        # 3) 文件孤儿（任务不存在）
        run("file_task_scope", "删除无归属任务文件",
            "DELETE FROM files WHERE env_id=? AND data_mode=? AND task_id<>'' "
            "AND NOT EXISTS (SELECT 1 FROM tasks t WHERE t.task_id=files.task_id "
            "AND t.env_id=files.env_id AND t.data_mode=files.data_mode)")
        # 4) 下载孤儿（文件不存在）
        run("file_download_scope", "删除无归属文件下载",
            "DELETE FROM file_downloads WHERE env_id=? AND data_mode=? AND file_id<>'' "
            "AND NOT EXISTS (SELECT 1 FROM files f WHERE f.file_id=file_downloads.file_id "
            "AND f.env_id=file_downloads.env_id AND f.data_mode=file_downloads.data_mode)")
        # 5) 下载计数不一致——依据下载事件真实回写
        mismatched = int(conn.execute(
            "SELECT COUNT(*) FROM files f WHERE f.env_id=? AND f.data_mode=? "
            "AND f.download_count <> COALESCE((SELECT COUNT(*) FROM file_downloads d "
            "WHERE d.file_id=f.file_id AND d.env_id=f.env_id AND d.data_mode=f.data_mode), 0)",
            base_args,
        ).fetchone()[0])
        conn.execute(
            "UPDATE files SET download_count = COALESCE((SELECT COUNT(*) FROM file_downloads d "
            "WHERE d.file_id=files.file_id AND d.env_id=files.env_id AND d.data_mode=files.data_mode), 0) "
            "WHERE env_id=? AND data_mode=?",
            base_args,
        )
        repairs.append({"check_id": "file_download_consistency", "action": "回写文件下载计数", "affected": mismatched})
        log_entries.append((env_id, data_mode, day, "file_download_consistency", "回写文件下载计数", mismatched,
                            f"校准 {mismatched} 个文件累计下载数", run_by, _now()))
        # 6) 员工未绑定智能体——回填同环境首个可用智能体（若存在），不新增智能体
        target_agent = conn.execute(
            "SELECT agent_id FROM agents WHERE env_id=? AND data_mode=? AND enabled=1 ORDER BY id LIMIT 1",
            base_args,
        ).fetchone()
        bound = 0
        if target_agent:
            cur = conn.execute(
                "UPDATE org_users SET agent_id=? WHERE env_id=? AND data_mode=? AND (agent_id IS NULL OR agent_id='')",
                (target_agent["agent_id"], env_id, data_mode),
            )
            bound = max(int(cur.rowcount), 0)
        repairs.append({"check_id": "user_agent_binding", "action": "回填员工智能体绑定", "affected": bound,
                        "target_agent": target_agent["agent_id"] if target_agent else ""})
        log_entries.append((env_id, data_mode, day, "user_agent_binding", "回填员工智能体绑定", bound,
                            f"绑定 {bound} 名员工至 {target_agent['agent_id'] if target_agent else '无可用智能体'}", run_by, _now()))

        # 7) 业务事件 Token 记账修正——非任务事件不重复记 Token，保证审计链 Token 与任务/用量一致。
        #    仅对 event_type<>'task' 归零，属幂等且可逆的记账校准，不删除任何行为记录。
        double_counted = int(conn.execute(
            "SELECT COUNT(*) FROM business_events WHERE env_id=? AND data_mode=? AND event_type<>'task' AND tokens<>0",
            base_args,
        ).fetchone()[0])
        conn.execute(
            "UPDATE business_events SET tokens=0 WHERE env_id=? AND data_mode=? AND event_type<>'task'",
            base_args,
        )
        repairs.append({"check_id": "business_event_token_accounting", "action": "校准非任务业务事件 Token", "affected": double_counted})
        log_entries.append((env_id, data_mode, day, "business_event_token_accounting", "校准非任务业务事件 Token", double_counted,
                            f"将 {double_counted} 条 session/file/download 事件 Token 归零，保证审计链 Token 单次计入", run_by, _now()))

        # 持久化修复日志
        for entry in log_entries:
            conn.execute(
                "INSERT INTO integrity_repair_log (env_id, tenant_id, data_mode, day, check_id, action, affected, detail, run_by, created_at) "
                "VALUES (?, (SELECT tenant_id FROM enterprise_meta WHERE env_id=? AND data_mode=? LIMIT 1), ?, ?, ?, ?, ?, ?, ?, ?)",
                (entry[0], entry[0], entry[1], entry[1], entry[2], entry[3], entry[4], entry[5], entry[6], entry[7], entry[8]),
            )
        conn.commit()

        after = _integrity_report(env_id, data_mode)
        attempted = [r["check_id"] for r in repairs]
        fixed_checks = [r["check_id"] for r in repairs if r["affected"] > 0]
        remaining = [c["id"] for c in after.get("report", []) if c.get("status") == "fail"]
        return {
            "ok": True,
            "status": "ready",
            "env_id": env_id,
            "data_mode": data_mode,
            "run_by": run_by or "admin",
            "run_at": _now(),
            "report_day": day,
            "repairs": repairs,
            "fixed_checks": fixed_checks,
            "remaining_checks": remaining,
            "report": after,
        }
    except Exception as exc:  # noqa: BLE001 - 修复失败需给路由可读错误
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"自动修复失败：{exc}") from exc
    finally:
        conn.close()


def _persist_daily_report(conn: sqlite3.Connection, report: dict[str, Any], day: str) -> str:
    """把当日一致性报告写入 integrity_reports（同一天重复写入为更新，保证幂等）。"""
    env_id = report.get("env_id", "")
    data_mode = report.get("data_mode", "")
    tenant = conn.execute(
        "SELECT tenant_id FROM enterprise_meta WHERE env_id=? AND data_mode=? LIMIT 1", (env_id, data_mode)
    ).fetchone()
    tenant_id = tenant["tenant_id"] if tenant else ""
    snapshot = json.dumps(report, ensure_ascii=False, default=str)
    existing = conn.execute(
        "SELECT id FROM integrity_reports WHERE env_id=? AND data_mode=? AND report_day=?",
        (env_id, data_mode, day),
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE integrity_reports SET total=?, passed=?, failed=?, healthy=?, snapshot=?, updated_at=? WHERE id=?",
            (int(report.get("total", 0)), int(report.get("passed", 0)), int(report.get("failed", 0)),
             1 if report.get("healthy") else 0, snapshot, _now(), existing["id"]),
        )
        return "updated"
    conn.execute(
        "INSERT INTO integrity_reports (env_id, tenant_id, data_mode, report_day, total, passed, failed, healthy, snapshot, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (env_id, tenant_id, data_mode, day, int(report.get("total", 0)), int(report.get("passed", 0)),
         int(report.get("failed", 0)), 1 if report.get("healthy") else 0, snapshot, _now(), _now()),
    )
    return "inserted"


def _daily_integrity_report(env_id: str = "", data_mode: str = "") -> dict[str, Any]:
    """生成并持久化当日一致性快照（懒生成：无环境时返回空）。"""
    conn = _connect()
    try:
        env_id, data_mode = _integrity_target(conn, env_id, data_mode)
        if not env_id:
            return {"status": "empty", "message": "尚未初始化企业环境", "report": []}
        report = _integrity_report(env_id, data_mode)
        day = _today()
        persist = _persist_daily_report(conn, report, day)
        conn.commit()
        return {**report, "report_day": day, "persist": persist, "generated_at": _now()}
    finally:
        conn.close()


def _integrity_history(env_id: str = "", data_mode: str = "", limit: int = 30) -> dict[str, Any]:
    """读取历史一致性快照，按日期倒序。"""
    conn = _connect()
    try:
        where: list[str] = []
        args: list[Any] = []
        if env_id:
            where.append("env_id = ?")
            args.append(env_id)
        if data_mode:
            where.append("data_mode = ?")
            args.append(data_mode)
        wsql = (" WHERE " + " AND ".join(where)) if where else ""
        rows = [dict(r) for r in conn.execute(
            "SELECT id, env_id, data_mode, report_day, total, passed, failed, healthy, created_at, updated_at "
            "FROM integrity_reports" + wsql + " ORDER BY report_day DESC, id DESC LIMIT ?",
            args + [limit],
        ).fetchall()]
        return {"count": len(rows), "rows": rows, "env_id": env_id, "data_mode": data_mode}
    finally:
        conn.close()


@router.get("/agent-factory/catalog")
async def agent_factory_catalog(authorization: str = Header(default="")) -> dict[str, Any]:
    """Agent Factory 编目：可用模型 / 工具 / 岗位默认工具 / 部门应用权限。"""
    _require_auth(authorization)
    return {
        "models": MODEL_CATALOG,
        "tools": TOOL_CATALOG,
        "category_default_tools": CATEGORY_DEFAULT_TOOLS,
        "app_access_by_dept": APP_ACCESS_BY_DEPT,
    }


@router.get("/agent-factory/templates")
async def agent_factory_templates(authorization: str = Header(default="")) -> dict[str, Any]:
    """按行业模板返回已构建的 Agent 配置（模型/技能/工具/应用权限/指标）。"""
    _require_auth(authorization)
    out: dict[str, list[dict[str, Any]]] = {}
    for tname, specs in AGENT_TEMPLATES.items():
        out[tname] = [build_agent_config(s) for s in specs]
    return {"templates": list(AGENT_TEMPLATES.keys()), "agents": out}


@router.get("/agent-factory/bindings")
async def agent_factory_bindings(
    authorization: str = Header(default=""),
    data_mode: str = Query(default="", max_length=20),
    env_id: str = Query(default="", max_length=64),
) -> dict[str, Any]:
    """查询已落库的 Model / Tool / App 关联记录。"""
    _require_auth(authorization)
    data_mode = _normalize_mode(data_mode)
    conn = _connect()
    try:
        where: list[str] = []
        args: list[Any] = []
        if env_id:
            where.append("env_id = ?")
            args.append(env_id)
        if data_mode:
            where.append("data_mode = ?")
            args.append(data_mode)
        wsql = (" WHERE " + " AND ".join(where)) if where else ""

        def rows(table: str) -> list[dict[str, Any]]:
            return [dict(r) for r in conn.execute(f"SELECT * FROM {table}{wsql} ORDER BY id DESC", args).fetchall()]

        return {
            "models": rows("models"),
            "agent_tools": rows("agent_tools"),
            "agent_app_access": rows("agent_app_access"),
            "env_id": env_id,
            "data_mode": data_mode,
        }
    finally:
        conn.close()


@router.post("/agent-factory/reconcile")
async def agent_factory_reconcile(
    request: AgentReconcileRequest,
    authorization: str = Header(default=""),
) -> dict[str, Any]:
    """为旧环境的智能体回填 Model / Tool / App 权限绑定（幂等）。"""
    _require_admin(authorization)
    conn = _connect()
    try:
        env_id = request.env_id
        data_mode = _normalize_mode(request.data_mode)
        where: list[str] = ["1=1"]
        args: list[Any] = []
        if env_id:
            where.append("env_id = ?")
            args.append(env_id)
        if data_mode:
            where.append("data_mode = ?")
            args.append(data_mode)
        agents = [dict(r) for r in conn.execute("SELECT * FROM agents WHERE " + " AND ".join(where), args).fetchall()]
        for ag in agents:
            aid, aeid, amode = ag["agent_id"], ag["env_id"], ag["data_mode"]
            conn.execute(
                "DELETE FROM agent_tools WHERE agent_id = ? AND env_id = ? AND data_mode = ?",
                (aid, aeid, amode),
            )
            conn.execute(
                "DELETE FROM agent_app_access WHERE agent_id = ? AND env_id = ? AND data_mode = ?",
                (aid, aeid, amode),
            )
            reconcile_bindings(conn, aeid, amode, ag)
        conn.commit()
        return {"ok": True, "reconciled": len(agents), "env_id": env_id, "data_mode": data_mode}
    finally:
        conn.close()


@router.post("/agent-factory/validate")
async def agent_factory_validate(
    request: AgentSpecRequest,
    authorization: str = Header(default=""),
) -> dict[str, Any]:
    """校验一份 Agent 规格，输出完整配置与错误清单。"""
    _require_admin(authorization)
    spec: dict[str, Any] = request.model_dump()
    config = build_agent_config(spec)
    errors = validate_agent_config(config)
    return {"ok": not errors, "config": config, "errors": errors}


@router.get("/integrity")
async def integrity(
    authorization: str = Header(default=""),
    data_mode: str = Query(default="", max_length=20),
    env_id: str = Query(default="", max_length=64),
) -> dict[str, Any]:
    _require_auth(authorization)
    data_mode = _normalize_mode(data_mode)
    return await asyncio.to_thread(_integrity_report, env_id, data_mode)




@router.get("/integrity/daily")
async def integrity_daily(
    authorization: str = Header(default=""),
    data_mode: str = Query(default="", max_length=20),
    env_id: str = Query(default="", max_length=64),
) -> dict[str, Any]:
    """当日一致性快照（懒生成并持久化，同一天重复调用为更新）。"""
    _require_auth(authorization)
    data_mode = _normalize_mode(data_mode)
    return await asyncio.to_thread(_daily_integrity_report, env_id, data_mode)


@router.get("/integrity/history")
async def integrity_history_route(
    authorization: str = Header(default=""),
    data_mode: str = Query(default="", max_length=20),
    env_id: str = Query(default="", max_length=64),
    limit: int = Query(default=30, ge=1, le=200),
) -> dict[str, Any]:
    """历史一致性快照列表，按日期倒序。"""
    _require_auth(authorization)
    data_mode = _normalize_mode(data_mode)
    return await asyncio.to_thread(_integrity_history, env_id, data_mode, limit)


@router.post("/integrity/repair")
async def integrity_repair(
    request: AgentReconcileRequest,
    authorization: str = Header(default=""),
) -> dict[str, Any]:
    """执行安全自动修复（管理员）。"""
    user = _require_admin(authorization)
    data_mode = _normalize_mode(request.data_mode)
    return await asyncio.to_thread(
        _repair_integrity, request.env_id, data_mode, user.get("username", "admin")
    )


@router.get("/simulation/status")
async def simulation_status(
    authorization: str = Header(default=""),
) -> dict[str, Any]:
    """获取 Simulation Runtime 运行时状态（环境列表 + 全局审计计数）。"""
    _require_auth(authorization)
    conn = _connect()
    try:
        return runtime_status(conn)
    finally:
        conn.close()


@router.get("/simulation/preview")
async def simulation_preview(
    authorization: str = Header(default=""),
    env_id: str = Query(default="", max_length=64),
    data_mode: str = Query(default="demo", max_length=20),
    start_date: str = Query(default="", max_length=20),
    end_date: str = Query(default="", max_length=20),
    activity: str = Query(default="medium", max_length=20),
    seed: int = Query(default=0),
) -> dict[str, Any]:
    """预览某环境在指定时间范围内的业务事件计划（只读不写库）。"""
    _require_auth(authorization)
    data_mode = _normalize_mode(data_mode)
    conn = _connect()
    try:
        return preview_interval(
            conn, env_id, data_mode,
            start_date or DEFAULT_START, end_date or _today(), activity, seed,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    finally:
        conn.close()


@router.post("/simulation/run")
async def simulation_run(
    request: SimulationRunRequest,
    authorization: str = Header(default=""),
) -> dict[str, Any]:
    """执行某环境指定时间范围内的业务事件生成，写入业务表与 business_events。"""
    _require_admin(authorization)
    data_mode = _normalize_mode(request.data_mode)
    conn = _connect()
    try:
        return run_interval(
            conn, request.env_id, data_mode,
            request.start_date or DEFAULT_START, request.end_date or _today(),
            seed=request.seed, force=request.force,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    finally:
        conn.close()


@router.get("/simulation/events")
async def simulation_events(
    authorization: str = Header(default=""),
    env_id: str = Query(default="", max_length=64),
    data_mode: str = Query(default="demo", max_length=20),
    start_date: str = Query(default="", max_length=20),
    end_date: str = Query(default="", max_length=20),
    limit: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    """查询某环境的业务事件审计明细。"""
    _require_auth(authorization)
    data_mode = _normalize_mode(data_mode)
    conn = _connect()
    try:
        rows = list_events(conn, env_id, data_mode, start_date, end_date, limit)
        return {"ok": True, "env_id": env_id, "data_mode": data_mode, "events": rows}
    finally:
        conn.close()


def _query_enterprise_status() -> dict[str, Any]:
    conn = _connect()
    try:
        cur = conn.execute("SELECT * FROM enterprise_meta ORDER BY id DESC LIMIT 1")
        meta = cur.fetchone()
        if not meta:
            return {"status": "empty", "message": "尚未初始化企业环境", "mode": "demo"}
        env_id, mode = meta["env_id"], meta["data_mode"]
        counts = {}
        for table in ("departments", "org_users", "agents", "apps", "data_sources", "sessions", "tasks"):
            counts[table] = conn.execute(
                f"SELECT COUNT(*) AS c FROM {table} WHERE env_id = ? AND data_mode = ?", (env_id, mode)
            ).fetchone()["c"]
        totals = conn.execute(
            "SELECT COALESCE(SUM(tokens),0) AS t, COALESCE(SUM(calls),0) AS c FROM token_usage WHERE env_id = ? AND data_mode = ?",
            (env_id, mode),
        ).fetchone()
        return {"status": "ready", "env_id": env_id, "tenant_id": meta["tenant_id"],
                "enterprise": meta["enterprise"], "data_mode": mode,
                "start_date": meta["start_date"], "end_date": meta["end_date"], **counts,
                "token_total": totals["t"], "calls": totals["c"]}
    finally:
        conn.close()


def _runtime_tool_status() -> dict[str, Any]:
    """Agent 工具入口：查询 Simulation Runtime 状态。"""
    conn = _connect()
    try:
        return runtime_status(conn)
    finally:
        conn.close()


def _run_simulation_tool(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Agent 工具入口：对指定范围执行业务事件生成。"""
    env_id = str(kwargs.get("env_id") or "")
    data_mode = _normalize_mode(str(kwargs.get("data_mode") or "demo"))
    start_date = str(kwargs.get("start_date") or "")
    end_date = str(kwargs.get("end_date") or "")
    force = bool(kwargs.get("force", False))
    seed = int(kwargs.get("seed") or 0)
    conn = _connect()
    try:
        return run_interval(
            conn, env_id, data_mode,
            start_date or DEFAULT_START, end_date or _today(),
            seed=seed, force=force,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    finally:
        conn.close()


class EnterpriseSeederPlugin:
    def register(self, api: PluginApi) -> None:
        api.register_http_router(router, prefix="/zhiyun-enterprise-seeder", tags=["zhiyun-enterprise-seeder"])
        api.register_startup_hook(hook_name="zhiyun-enterprise-seeder-init", callback=_startup_bootstrap, priority=91)
        api.register_tool(
            tool_name="seed_enterprise_data",
            tool_func=lambda **kwargs: _generate_enterprise(kwargs),
            description="一键初始化企业环境：企业/部门/员工/权限/Agent/应用/数据源/会话/任务/Token/日志，并向登录系统写入员工账号。",
            icon="🏢",
            tool_type="internal",
        )
        api.register_tool(
            tool_name="query_enterprise_status",
            tool_func=_query_enterprise_status,
            description="查询当前企业环境的初始化状态与各实体数量。",
            icon="📊",
            tool_type="internal",
        )
        api.register_tool(
            tool_name="query_enterprise_integrity",
            tool_func=lambda **kwargs: _integrity_report(kwargs.get("env_id", ""), kwargs.get("data_mode", "")),
            description="生成企业环境跨模块数据一致性检查报告（Data Integrity Report），校验执行总数、Token、会话归属、员工绑定与登录回查。",
            icon="✅",
            tool_type="internal",
        )
        api.register_tool(
            tool_name="run_integrity_repair",
            tool_func=lambda **kwargs: _repair_integrity(kwargs.get("env_id", ""), kwargs.get("data_mode", ""), run_by="agent"),
            description="执行企业环境数据安全自动修复：清理会话/任务/文件/下载孤儿，校准下载计数，回填员工智能体绑定，并写入修复日志。",
            icon="🧰",
            tool_type="internal",
        )
        api.register_tool(
            tool_name="query_daily_integrity_report",
            tool_func=lambda **kwargs: _daily_integrity_report(kwargs.get("env_id", ""), kwargs.get("data_mode", "")),
            description="生成并持久化当日数据一致性快照（同一天重复调用为更新）。",
            icon="📅",
            tool_type="internal",
        )
        api.register_tool(
            tool_name="query_integrity_history",
            tool_func=lambda **kwargs: _integrity_history(kwargs.get("env_id", ""), kwargs.get("data_mode", ""), int(kwargs.get("limit") or 30)),
            description="读取历史一致性快照列表，按日期倒序。",
            icon="🕘",
            tool_type="internal",
        )
        api.register_tool(
            tool_name="query_simulation_runtime",
            tool_func=lambda **kwargs: _runtime_tool_status(),
            description="查询 Simulation Runtime 运行时状态：环境列表、业务事件审计计数、会话/任务/文件/Token 总量。",
            icon="▶️",
            tool_type="internal",
        )
        api.register_tool(
            tool_name="run_simulation_events",
            tool_func=lambda **kwargs: _run_simulation_tool(kwargs),
            description="对指定环境的日期范围执行业务事件生成（写入 business_events 审计并回填会话/任务/文件/Token），默认跳过已有业务数据日期。",
            icon="⏯️",
            tool_type="internal",
        )


plugin = EnterpriseSeederPlugin()
