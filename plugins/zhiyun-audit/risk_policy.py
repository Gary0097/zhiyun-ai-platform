"""Small deny policy for catastrophic Agent operations.

This is intentionally not an approval or capability system. It blocks only
irreversible, machine-wide operations that should never be executed by an
enterprise assistant and lets ordinary file/database work continue.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class RiskDecision:
    blocked: bool
    rule_id: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_SHELL_TOOL = re.compile(r"(shell|terminal|exec|command|powershell|bash|cmd)", re.I)
_SQL_TOOL = re.compile(r"(sql|database|query|execute)", re.I)
_DELETE_TOOL = re.compile(r"(delete|remove|unlink|rmdir)", re.I)
_COMMAND_KEYS = {"cmd", "command", "script", "shell", "powershell", "bash", "sql", "query"}

_RULES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "shell.catastrophic-delete",
        "禁止递归删除系统根目录、用户主目录或整块磁盘。",
        re.compile(
            r"(?:^|[;&|]\s*)(?:sudo\s+)?rm\s+(?=[^\n;&|]*(?:-[a-z]*r[a-z]*|--recursive))(?=[^\n;&|]*(?:-[a-z]*f[a-z]*|--force))[^\n;&|]*\s(?:/|/\*|~|\$HOME)(?:\s|$|[;&|])",
            re.I,
        ),
    ),
    (
        "windows.catastrophic-delete",
        "禁止递归强制删除 Windows 系统盘或用户主目录。",
        re.compile(
            r"(?:remove-item\b(?=[^\n;&|]*-recurse)(?=[^\n;&|]*-force)[^\n;&|]*(?:[a-z]:[\\/](?:\*)?|~|\$HOME|\$env:USERPROFILE)(?:\s|$)|(?:del|rmdir|rd)\b(?=[^\n;&|]*/s)(?=[^\n;&|]*/q)[^\n;&|]*[a-z]:[\\/](?:\*)?(?:\s|$))",
            re.I,
        ),
    ),
    (
        "disk.destructive-operation",
        "禁止格式化磁盘、重写分区表或直接覆盖块设备。",
        re.compile(r"(?:^|[;&|]\s*)(?:sudo\s+)?(?:mkfs(?:\.[a-z0-9]+)?|fdisk|parted|diskpart|format\s+[a-z]:|dd\b[^\n;&|]*\bof=/dev/(?:sd|nvme|vd))", re.I),
    ),
    (
        "git.destructive-rewrite",
        "禁止 Agent 强制重写或无差别清理 Git 工作区。",
        re.compile(r"\bgit\s+(?:reset\s+--hard|clean\s+-[a-z]*f[a-z]*d[a-z]*x|push\b[^\n;&|]*--force(?:-with-lease)?)", re.I),
    ),
    (
        "database.destructive-ddl",
        "禁止 Agent 直接删除数据库/数据表或清空整表。",
        re.compile(r"\b(?:drop\s+(?:database|schema|table)|truncate\s+(?:table\s+)?)\b", re.I),
    ),
)


def _command_text(tool_input: Any) -> str:
    if isinstance(tool_input, str):
        return tool_input
    if not isinstance(tool_input, dict):
        return ""
    values: list[str] = []
    for key, value in tool_input.items():
        if str(key).casefold() in _COMMAND_KEYS:
            values.append(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str))
    return "\n".join(values)


def _dangerous_path(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.strip().replace("/", "\\").rstrip("\\").casefold()
    return normalized in {"", "~", "$home", "$env:userprofile", "%userprofile%", "c:", "d:"}


def assess(tool_name: str, tool_input: Any) -> RiskDecision:
    """Return a deterministic block decision without mutating input."""
    name = str(tool_name or "")
    command = _command_text(tool_input)
    if command and (_SHELL_TOOL.search(name) or _SQL_TOOL.search(name) or isinstance(tool_input, dict)):
        for rule_id, reason, pattern in _RULES:
            if pattern.search(command):
                return RiskDecision(True, rule_id, reason)

    if _DELETE_TOOL.search(name) and isinstance(tool_input, dict):
        for key in ("path", "target", "directory", "file"):
            if key in tool_input and _dangerous_path(tool_input[key]):
                return RiskDecision(True, "file.root-delete", "禁止删除系统根目录、磁盘根目录或用户主目录。")
    return RiskDecision(False)
