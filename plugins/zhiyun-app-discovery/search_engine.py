# -*- coding: utf-8 -*-
"""Deterministic local PawApp capability search."""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

CATALOG_FILE = Path(__file__).with_name("app_catalog.json")

SYNONYMS = {
    "订单风险": ["交付风险", "延期概率", "高风险订单"],
    "交付预警": ["交付风险", "红黄绿预警"],
    "销售业绩": ["销售人员业绩", "贡献归因", "业绩归属"],
    "票据审核": ["发票识别", "报销审核", "财务合规"],
    "找人": ["通讯录", "人员推荐", "找专家"],
    "知识工厂": ["知识库", "文档解析", "知识检索"],
    "接口": ["系统对接", "开放API", "ERP接口", "WMS接口"],
}


def load_catalog(path: Path = CATALOG_FILE) -> dict[str, Any]:
    """Load and minimally validate the packaged application catalog."""
    catalog = json.loads(path.read_text(encoding="utf-8"))
    if catalog.get("schema_version") != 1 or not isinstance(catalog.get("apps"), list):
        raise ValueError("unsupported app catalog")
    return catalog


def _normalize(value: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value.casefold())


def _terms(query: str) -> list[str]:
    normalized = _normalize(query)
    terms = {normalized}
    for source, targets in SYNONYMS.items():
        source_normalized = _normalize(source)
        if source_normalized and source_normalized in normalized:
            terms.update(_normalize(target) for target in targets)
    return sorted(term for term in terms if term)


def _text_values(app: dict[str, Any], capability: dict[str, Any]) -> Iterable[tuple[str, str]]:
    yield "应用名称", str(app.get("name", ""))
    for alias in app.get("aliases", []):
        yield "应用别名", str(alias)
    yield "功能名称", str(capability.get("name", ""))
    for keyword in capability.get("keywords", []):
        yield "功能关键词", str(keyword)
    for question in capability.get("questions", []):
        yield "典型问法", str(question)


def _match_score(query_terms: list[str], label: str, value: str) -> tuple[float, str]:
    candidate = _normalize(value)
    if not candidate:
        return 0.0, ""
    best = 0.0
    for term in query_terms:
        if term == candidate:
            best = max(best, 120.0)
        elif term in candidate or candidate in term:
            coverage = min(len(term), len(candidate)) / max(len(term), len(candidate))
            best = max(best, 82.0 + coverage * 28.0)
        else:
            ratio = SequenceMatcher(None, term, candidate).ratio()
            if ratio >= 0.62:
                best = max(best, ratio * 70.0)
    return best, f"{label}匹配“{value}”" if best else ""


def search_apps(
    query: str,
    *,
    limit: int = 5,
    catalog: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Search real catalog entries without requiring a model or network."""
    clean_query = query.strip()
    if not clean_query:
        return []
    query_terms = _terms(clean_query)
    results: list[dict[str, Any]] = []
    for app in (catalog or load_catalog())["apps"]:
        app_matches: list[dict[str, Any]] = []
        for capability in app.get("capabilities", []):
            matches = [_match_score(query_terms, label, value) for label, value in _text_values(app, capability)]
            score, reason = max(matches, key=lambda item: item[0], default=(0.0, ""))
            if score:
                app_matches.append({
                    "capability_id": capability.get("id"),
                    "capability_name": capability.get("name"),
                    "score": round(score, 2),
                    "reason": reason,
                })
        if not app_matches:
            continue
        app_matches.sort(key=lambda item: (-item["score"], item["capability_id"] or 0))
        top = app_matches[0]
        installed_bonus = 5.0 if app.get("install_status") == "installed" else 0.0
        results.append({
            "app_id": app["app_id"],
            "name": app["name"],
            "category": app.get("category"),
            "version": app.get("version"),
            "install_status": app.get("install_status", "available"),
            "health": app.get("health", "unknown"),
            "route": app.get("route"),
            "repository_url": app.get("repository_url"),
            "platforms": app.get("platforms", []),
            "score": round(top["score"] + installed_bonus, 2),
            "matched_capability": top,
            "related_capabilities": app_matches[1:3],
        })
    results.sort(key=lambda item: (-item["score"], item["name"]))
    return results[: max(1, min(limit, 20))]


def agent_response(query: str, limit: int = 3) -> dict[str, Any]:
    """Return an Agent-safe response sourced only from the real catalog."""
    results = search_apps(query, limit=limit)
    return {
        "query": query,
        "found": bool(results),
        "results": results,
        "message": (
            "已从真实应用能力索引找到可用应用。"
            if results
            else "真实应用目录中暂无匹配能力，不会虚构应用。"
        ),
    }
