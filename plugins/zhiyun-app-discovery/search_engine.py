# -*- coding: utf-8 -*-
"""Deterministic local PawApp capability search."""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

CATALOG_FILE = Path(__file__).with_name("app_catalog.json")
PROGRESS_FILE = Path(__file__).with_name("feature_progress.json")
DELIVERY_STATUSES = {"planned", "in_progress", "testing", "completed"}
LAUNCHABLE_STATUSES = {"completed", "testing"}

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


def load_progress(path: Path = PROGRESS_FILE) -> dict[str, Any]:
    """Load and validate the 31-item PRD delivery ledger."""
    ledger = json.loads(path.read_text(encoding="utf-8"))
    features = ledger.get("features")
    if ledger.get("schema_version") != 1 or not isinstance(features, list):
        raise ValueError("unsupported feature progress ledger")
    ids = [item.get("id") for item in features]
    if sorted(ids) != list(range(1, 32)) or len(ids) != len(set(ids)):
        raise ValueError("feature progress must contain unique IDs 1..31")
    for item in features:
        if item.get("status") not in DELIVERY_STATUSES:
            raise ValueError(f"unsupported delivery status for feature {item.get('id')}")
        progress = item.get("progress")
        if not isinstance(progress, int) or not 0 <= progress <= 100:
            raise ValueError(f"invalid progress for feature {item.get('id')}")
    return ledger


def progress_summary(ledger: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build an honest project summary from the feature ledger."""
    data = ledger or load_progress()
    features = data["features"]
    counts = {status: 0 for status in DELIVERY_STATUSES}
    for item in features:
        counts[item["status"]] += 1
    return {
        "total": len(features),
        "completed": counts["completed"],
        "testing": counts["testing"],
        "in_progress": counts["in_progress"],
        "planned": counts["planned"],
        "overall_progress": round(sum(item["progress"] for item in features) / len(features)),
        "updated_at": data.get("updated_at"),
    }


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
    ledger: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Search real catalog entries without requiring a model or network."""
    clean_query = query.strip()
    if not clean_query:
        return []
    query_terms = _terms(clean_query)
    progress_by_id = {item["id"]: item for item in (ledger or load_progress())["features"]}
    results: list[dict[str, Any]] = []
    for app in (catalog or load_catalog())["apps"]:
        app_matches: list[dict[str, Any]] = []
        for capability in app.get("capabilities", []):
            matches = [_match_score(query_terms, label, value) for label, value in _text_values(app, capability)]
            score, reason = max(matches, key=lambda item: item[0], default=(0.0, ""))
            if score:
                delivery = progress_by_id.get(capability.get("id"), {})
                delivery_status = capability.get("delivery_status", delivery.get("status", "planned"))
                app_matches.append({
                    "capability_id": capability.get("id"),
                    "capability_name": capability.get("name"),
                    "delivery_status": delivery_status,
                    "delivery_progress": delivery.get("progress", 0),
                    "delivery_note": delivery.get("note", "交付状态未登记。"),
                    "score": round(score, 2),
                    "reason": reason,
                })
        if not app_matches:
            continue
        app_matches.sort(key=lambda item: (-item["score"], item["capability_id"] or 0))
        top = app_matches[0]
        capability_available = (
            app.get("install_status") == "installed"
            and top["delivery_status"] in LAUNCHABLE_STATUSES
        )
        installed_bonus = 5.0 if capability_available else 0.0
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
            "available": capability_available,
            "score": round(top["score"] + installed_bonus, 2),
            "matched_capability": top,
            "related_capabilities": app_matches[1:3],
        })
    results.sort(key=lambda item: (-item["score"], item["name"]))
    return results[: max(1, min(limit, 20))]


def agent_response(query: str, limit: int = 3) -> dict[str, Any]:
    """Return an Agent-safe response sourced only from the real catalog."""
    results = search_apps(query, limit=limit)
    accepted = any(
        item["available"] and item["matched_capability"]["delivery_status"] == "completed"
        for item in results
    )
    testing = any(
        item["available"] and item["matched_capability"]["delivery_status"] == "testing"
        for item in results
    )
    available = accepted or testing
    if accepted:
        message = "已从真实应用能力索引找到已验收可用应用。"
    elif testing:
        message = "已找到可启动测试的应用，请前往对应应用页进行实机验收。"
    elif results:
        message = "找到对应应用或规划能力，但匹配功能尚未交付，当前不可用。"
    else:
        message = "真实应用目录中暂无匹配能力，不会虚构应用。"
    return {
        "query": query,
        "found": bool(results),
        "available": available,
        "results": results,
        "message": message,
    }
