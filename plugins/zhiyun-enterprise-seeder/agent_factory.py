# -*- coding: utf-8 -*-
"""Agent Factory - 智能体自动配置（zhiyun-enterprise-seeder / Epic 2）。

把「智能体」从一条静态记录升级为完整可运行配置：Agent -> Model -> Skill ->
Tool -> App 权限 -> Data/Knowledge 范围，全部落成可追溯的关联记录。

模型 / 工具 / 应用访问均来自本地编目（MODEL_CATALOG / TOOL_CATALOG /
APP_ACCESS_BY_DEPT），保证 Agent 工厂产出的配置可校验、可被 Simulation Runtime
直接调用。本模块不反向依赖宿主插件，方便单测与复用。
"""

from __future__ import annotations

import json
import random
import uuid
from typing import Any

# ---------------------------------------------------------------------------
# 模型编目：Agent -> Model 的真实关联目标
# ---------------------------------------------------------------------------

MODEL_CATALOG: dict[str, dict[str, Any]] = {
    "local-qwen2.5-7b": {
        "name": "本地 Qwen2.5 7B",
        "provider": "qwen",
        "base_model": "Qwen2.5-7B-Instruct",
        "context_window": 32768,
        "max_tokens": 8192,
        "input_price_per_k": 0.0,
        "output_price_per_k": 0.0,
        "enabled": 1,
    },
    "local-qwen2.5-14b": {
        "name": "本地 Qwen2.5 14B",
        "provider": "qwen",
        "base_model": "Qwen2.5-14B-Instruct",
        "context_window": 65536,
        "max_tokens": 12288,
        "input_price_per_k": 0.0,
        "output_price_per_k": 0.0,
        "enabled": 1,
    },
    "local-qwen2.5-72b": {
        "name": "本地 Qwen2.5 72B",
        "provider": "qwen",
        "base_model": "Qwen2.5-72B-Instruct",
        "context_window": 131072,
        "max_tokens": 32768,
        "input_price_per_k": 0.0,
        "output_price_per_k": 0.0,
        "enabled": 1,
    },
    "cloud-qwen-max": {
        "name": "云端 Qwen-Max",
        "provider": "qwen-cloud",
        "base_model": "qwen-max",
        "context_window": 131072,
        "max_tokens": 32768,
        "input_price_per_k": 0.02,
        "output_price_per_k": 0.06,
        "enabled": 1,
    },
    "cloud-qwen-plus": {
        "name": "云端 Qwen-Plus",
        "provider": "qwen-cloud",
        "base_model": "qwen-plus",
        "context_window": 131072,
        "max_tokens": 32768,
        "input_price_per_k": 0.004,
        "output_price_per_k": 0.012,
        "enabled": 1,
    },
}


# ---------------------------------------------------------------------------
# 工具编目：Agent -> Tool 的真实关联目标
# ---------------------------------------------------------------------------

TOOL_CATALOG: dict[str, dict[str, str]] = {
    "query_enterprise_orders": {"name": "企业订单查询", "category": "data", "desc": "按客户/状态/日期查询企业订单执行情况"},
    "generate_simulated_orders": {"name": "演示订单生成", "category": "data", "desc": "按业务规则生成演示订单数据"},
    "customer_search": {"name": "企业联系人搜索", "category": "crm", "desc": "查询企业客户与联系人"},
    "quote_calc": {"name": "报价测算", "category": "sales", "desc": "按配置测算产品报价"},
    "contract_parse": {"name": "合同条款解析", "category": "sales", "desc": "解析合同关键条款"},
    "customer_followup": {"name": "客户回访跟进", "category": "crm", "desc": "生成并跟进客户回访计划"},
    "email_compose": {"name": "邮件内容生成", "category": "marketing", "desc": "生成营销邮件正文"},
    "email_track": {"name": "邮件状态追踪", "category": "marketing", "desc": "追踪邮件发送与反馈"},
    "lead_search": {"name": "线索检索", "category": "marketing", "desc": "检索潜在客户线索"},
    "invoice_ocr": {"name": "票据识别", "category": "finance", "desc": "OCR 识别票据票面信息"},
    "voucher_make": {"name": "凭证处理", "category": "finance", "desc": "生成记账凭证"},
    "cost_calc": {"name": "费用核算", "category": "finance", "desc": "核算成本与费用分摊"},
    "reconcile_check": {"name": "对账核验", "category": "supply", "desc": "核对采购与应付账款"},
    "vendor_score": {"name": "供应商评分", "category": "supply", "desc": "对供应商进行多维度评分"},
    "intent_route": {"name": "工单路由", "category": "service", "desc": "按意图路由客服工单"},
    "kb_qa": {"name": "知识问答", "category": "service", "desc": "基于知识库回答常见问题"},
    "report_gen": {"name": "报表生成", "category": "analytics", "desc": "生成经营分析报表"},
    "risk_alert": {"name": "风险预警", "category": "analytics", "desc": "识别经营风险并预警"},
    "schedule_plan": {"name": "排产排程", "category": "production", "desc": "生成生产排产计划"},
    "capacity_analysis": {"name": "产能分析", "category": "production", "desc": "分析产能与负荷"},
    "stock_inv": {"name": "库存盘点", "category": "inventory", "desc": "盘点库存数量与库龄"},
    "replenish_advice": {"name": "补货建议", "category": "inventory", "desc": "生成补货建议"},
}


# 工具为空时按岗位类别给默认工具，保证每个 Agent 至少绑定一项真实工具。
CATEGORY_DEFAULT_TOOLS: dict[str, list[str]] = {
    "sales": ["quote_calc", "query_enterprise_orders"],
    "customer": ["customer_followup", "customer_search"],
    "marketing": ["lead_search", "email_compose", "email_track"],
    "supply": ["reconcile_check", "vendor_score", "query_enterprise_orders"],
    "finance": ["invoice_ocr", "voucher_make", "cost_calc"],
    "service": ["intent_route", "kb_qa"],
    "analytics": ["report_gen", "risk_alert", "query_enterprise_orders"],
    "production": ["schedule_plan", "capacity_analysis"],
    "inventory": ["stock_inv", "replenish_advice"],
}


# 部门 -> 可访问应用（与宿主 DEPT_APP_MAP 保持一致；不一致会被测试捕获）。
APP_ACCESS_BY_DEPT: dict[str, list[str]] = {
    "销售部": ["zhiyun-sales-studio", "zhiyun-data-core", "zhiyun-app-discovery", "qwenpaw-knowledge-base"],
    "财务部": ["zhiyun-finance-studio", "zhiyun-data-core", "zhiyun-app-discovery", "qwenpaw-knowledge-base"],
    "采购部": ["zhiyun-supply-studio", "zhiyun-data-core", "zhiyun-app-discovery", "qwenpaw-knowledge-base"],
    "客服部": ["zhiyun-service-studio", "zhiyun-data-core", "zhiyun-app-discovery", "qwenpaw-knowledge-base"],
    "运营部": ["zhiyun-sales-studio", "zhiyun-supply-studio", "zhiyun-data-core", "zhiyun-app-discovery", "qwenpaw-knowledge-base"],
    "生产部": ["zhiyun-order-studio", "zhiyun-data-core", "zhiyun-app-discovery", "qwenpaw-knowledge-base"],
    "管理层": ["zhiyun-finance-studio", "zhiyun-sales-studio", "zhiyun-data-core", "zhiyun-app-discovery", "qwenpaw-knowledge-base"],
    "研发部": ["zhiyun-app-discovery", "zhiyun-data-core", "zhiyun-order-studio", "qwenpaw-knowledge-base"],
}


# ---------------------------------------------------------------------------
# 纯配置构建：不改数据库，仅根据模板产出完整配置
# ---------------------------------------------------------------------------

def resolve_model_id(spec: dict[str, Any]) -> str:
    """根据模板解析真实模型 id：优先显式 model_id，其次按 max_tokens 选档。"""
    if spec.get("model_id") in MODEL_CATALOG:
        return str(spec["model_id"])
    if int(spec.get("max_tokens", 0) or 0) >= 12288:
        return "local-qwen2.5-72b"
    return "local-qwen2.5-7b"


def resolve_tools(spec: dict[str, Any]) -> list[str]:
    """解析工具绑定：模板显式工具优先，否则按岗位类别取默认工具。"""
    declared = [t for t in (spec.get("tools") or []) if t]
    if declared:
        return declared
    category = str(spec.get("category") or "general")
    return CATEGORY_DEFAULT_TOOLS.get(category, ["query_enterprise_orders"])


def resolve_apps(spec: dict[str, Any]) -> list[str]:
    """解析应用权限：按岗位部门取可访问应用列表。"""
    dept = str(spec.get("department") or "")
    return APP_ACCESS_BY_DEPT.get(dept, ["zhiyun-data-core", "zhiyun-app-discovery"])


def build_agent_config(spec: dict[str, Any]) -> dict[str, Any]:
    """从模板规格构建完整智能体配置（含模型/技能/工具/应用/范围/指标）。"""
    model_id = resolve_model_id(spec)
    model = MODEL_CATALOG[model_id]
    tools = resolve_tools(spec)
    apps = resolve_apps(spec)
    skills = []
    for skill_name, skill_code in (spec.get("skills") or []):
        skills.append({"skill_id": f"{spec['id']}_{skill_code}", "name": skill_name, "code": skill_code})
    return {
        "agent_id": str(spec["id"]),
        "name": str(spec.get("name") or spec["id"]),
        "position": str(spec.get("position") or ""),
        "department": str(spec.get("department") or ""),
        "category": str(spec.get("category") or "general"),
        "system_prompt": str(spec.get("system_prompt") or _default_system_prompt(spec)),
        "model_id": model_id,
        "model": model,
        "max_tokens": int(spec.get("max_tokens") or model["max_tokens"]),
        "execution_freq": int(spec.get("execution_freq") or 5),
        "work_start": str(spec.get("work_start") or "09:00"),
        "work_end": str(spec.get("work_end") or "18:00"),
        "auto_tasks": int(spec.get("auto_tasks") or 0),
        "manual_tasks": int(spec.get("manual_tasks") or 0),
        "success_rate": float(spec.get("success_rate") or 0.9),
        "avg_response_ms": int(spec.get("avg_response_ms") or 1800),
        "kb_scope": str(spec.get("kb_scope") or "enterprise"),
        "data_scope": str(spec.get("data_scope") or "enterprise"),
        "skills": skills,
        "tools": [{"tool_id": t, **TOOL_CATALOG.get(t, {"name": t, "category": "unknown", "desc": ""})} for t in tools],
        "apps": apps,
    }


def _default_system_prompt(spec: dict[str, Any]) -> str:
    name = spec.get("name") or spec.get("id") or "智能体"
    position = spec.get("position") or "业务岗位"
    dept = spec.get("department") or "所属部门"
    return f"你是{dept}的{position}数字员工「{name}」。请基于企业统一数据中心与授权工具，高效、准确地完成{position}相关业务，输出可直接使用的结果并给出可追溯依据。"


def validate_agent_config(config: dict[str, Any]) -> list[dict[str, str]]:
    """校验配置完整性，返回错误列表（空列表表示通过）。"""
    errors: list[dict[str, str]] = []
    required = ["agent_id", "name", "position", "department", "model_id", "max_tokens", "success_rate", "avg_response_ms"]
    for field in required:
        if not config.get(field):
            errors.append({"field": field, "message": f"缺少必要字段：{field}"})
    if config.get("model_id") not in MODEL_CATALOG:
        errors.append({"field": "model_id", "message": f"未知模型：{config.get('model_id')}"})
    for tool in config.get("tools") or []:
        if tool.get("tool_id") not in TOOL_CATALOG:
            errors.append({"field": "tools", "message": f"工具未在编目注册：{tool.get('tool_id')}"})
    for app_id in config.get("apps") or []:
        if app_id not in _ALL_APP_IDS:
            errors.append({"field": "apps", "message": f"应用未在编目注册：{app_id}"})
    sr = config.get("success_rate")
    if sr is not None and not (0.0 <= float(sr) <= 1.0):
        errors.append({"field": "success_rate", "message": "成功率必须在 0~1 之间"})
    if not config.get("skills"):
        errors.append({"field": "skills", "message": "至少绑定一项技能"})
    return errors


_ALL_APP_IDS = sorted({app for apps in APP_ACCESS_BY_DEPT.values() for app in apps})


# ---------------------------------------------------------------------------
# 持久化：把配置写入数据库关联表
# ---------------------------------------------------------------------------

def persist_bindings(conn, env_id: str, tenant_id: str, data_mode: str, spec: dict[str, Any], now: str) -> dict[str, Any]:
    """为一个智能体落地 Model / Skill / Tool / App 权限关联记录，返回配置摘要。"""
    config = build_agent_config(spec)
    model_id = config["model_id"]
    model = MODEL_CATALOG[model_id]
    # 模型（同环境同模型幂等）
    cursor = conn.execute(
        "SELECT id FROM models WHERE env_id=? AND data_mode=? AND model_id=?",
        (env_id, data_mode, model_id),
    )
    if not cursor.fetchone():
        conn.execute(
            "INSERT INTO models (env_id, tenant_id, data_mode, model_id, name, provider, base_model, context_window, max_tokens, input_price_per_k, output_price_per_k, enabled, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (env_id, tenant_id, data_mode, model_id, model["name"], model["provider"], model["base_model"],
             model["context_window"], model["max_tokens"], model["input_price_per_k"], model["output_price_per_k"],
             model["enabled"], now),
        )
    # 工具绑定（仅写编目内已注册工具，避免脏数据）
    for tool in config["tools"]:
        if tool["tool_id"] not in TOOL_CATALOG:
            continue
        conn.execute(
            "INSERT INTO agent_tools (env_id, tenant_id, data_mode, agent_id, tool_id, tool_name, tool_category, enabled, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (env_id, tenant_id, data_mode, config["agent_id"], tool["tool_id"], tool["name"], tool["category"], 1, now),
        )
    # 应用权限矩阵
    for app_id in config["apps"]:
        conn.execute(
            "INSERT INTO agent_app_access (env_id, tenant_id, data_mode, agent_id, app_id, data_scope, kb_scope, enabled, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (env_id, tenant_id, data_mode, config["agent_id"], app_id, config["data_scope"], config["kb_scope"], 1, now),
        )
    return {"agent_id": config["agent_id"], "model_id": model_id, "skills": len(config["skills"]),
            "tools": len(config["tools"]), "apps": len(config["apps"])}


def reconcile_bindings(conn, env_id: str, data_mode: str, agent_row: Any, dept_apps: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """为已存在的一行 agent 生成完整绑定配置（模型/工具/应用权限），用于回填旧环境。"""
    spec = {
        "id": agent_row["agent_id"],
        "name": agent_row["name"],
        "position": agent_row["position"],
        "department": agent_row["department"],
        "category": _category_from_position(agent_row["position"]),
        "model": agent_row["model"],
        "max_tokens": agent_row["max_tokens"],
        "execution_freq": agent_row["execution_freq"],
        "work_start": agent_row["work_start"],
        "work_end": agent_row["work_end"],
        "auto_tasks": agent_row["auto_tasks"],
        "manual_tasks": agent_row["manual_tasks"],
        "success_rate": agent_row["success_rate"],
        "avg_response_ms": agent_row["avg_response_ms"],
        "kb_scope": agent_row["kb_scope"],
        "data_scope": agent_row["data_scope"],
        "skills": _skills_from_json(agent_row["skills"]),
        "tools": json.loads(agent_row["tools"] or "[]"),
    }
    now = _now()
    return persist_bindings(conn, env_id, agent_row["tenant_id"], data_mode, spec, now)


def _skills_from_json(raw: str) -> list[tuple[str, str]]:
    try:
        skills = json.loads(raw or "[]")
        return [(s, s) for s in skills] if isinstance(skills, list) else []
    except (ValueError, TypeError):
        return []


def _category_from_position(position: str) -> str:
    mapping = {
        "销售报价": "sales", "客户跟进": "customer", "邮件营销": "marketing", "采购对账": "supply",
        "财务票据": "finance", "售后客服": "service", "经营分析": "analytics", "生产计划": "production",
        "库存管理": "inventory", "报销审核": "finance", "财务分析": "analytics", "成本预测": "analytics",
    }
    return mapping.get(position, "general")


def make_agent_row(env_id: str, tenant_id: str, data_mode: str, spec: dict[str, Any], now: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """构建插入 agents 表的行与 skills 行（不写库，供宿主使用）。"""
    config = build_agent_config(spec)
    agent_row = {
        "agent_id": config["agent_id"],
        "name": config["name"],
        "position": config["position"],
        "department": config["department"],
        "system_prompt": config["system_prompt"],
        "model": MODEL_CATALOG[config["model_id"]]["name"],
        "skills": json.dumps([s["name"] for s in config["skills"]], ensure_ascii=False),
        "tools": json.dumps([t["tool_id"] for t in config["tools"]], ensure_ascii=False),
        "kb_scope": config["kb_scope"],
        "data_scope": config["data_scope"],
        "max_tokens": config["max_tokens"],
        "execution_freq": config["execution_freq"],
        "work_start": config["work_start"],
        "work_end": config["work_end"],
        "auto_tasks": config["auto_tasks"],
        "manual_tasks": config["manual_tasks"],
        "success_rate": config["success_rate"],
        "avg_response_ms": config["avg_response_ms"],
        "enabled": 1,
    }
    skill_rows = [{"skill_id": s["skill_id"], "name": s["name"], "code": s["code"]} for s in config["skills"]]
    return agent_row, skill_rows


def _now() -> str:
    import time
    return time.strftime("%Y-%m-%d %H:%M:%S")


def new_agent_id(template_id: str) -> str:
    """为新生成的独立智能体生成不冲突的 agent_id。"""
    return f"{template_id}_{uuid.uuid4().hex[:6]}"
