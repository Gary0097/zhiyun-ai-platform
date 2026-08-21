"""Recoverably disable legacy Zhiyun UI/apps and remove stale 8390 tools."""

from __future__ import annotations

import shutil
from datetime import datetime

from qwenpaw.config.config import load_agent_config, save_agent_config
from qwenpaw.config.utils import get_plugins_dir, load_config
from qwenpaw.constant import WORKING_DIR

LEGACY_PLUGINS = ("zhiyun-brand", "zhiyun-orders")
LEGACY_TOOLS = (
    "enterprise_platform_status", "enterprise_query_orders", "enterprise_query_inventory",
    "enterprise_query_customers", "enterprise_search_knowledge", "orders_query", "orders_delivery_risk",
)


def main() -> None:
    plugins = get_plugins_dir()
    disabled = WORKING_DIR / "disabled_plugins"
    disabled.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    for plugin_id in LEGACY_PLUGINS:
        source = plugins / plugin_id
        if source.exists():
            target = disabled / f"{plugin_id}-{stamp}"
            shutil.move(str(source), str(target))
            print(f"已停用旧插件 {plugin_id}（可恢复备份：{target}）")
    config = load_config()
    profiles = (config.agents.profiles if config.agents else {}) or {}
    for agent_id in profiles:
        agent = load_agent_config(agent_id)
        removed = []
        for name in LEGACY_TOOLS:
            if name in agent.tools.builtin_tools:
                del agent.tools.builtin_tools[name]
                removed.append(name)
        if removed:
            save_agent_config(agent_id, agent)
            print(f"已清理 Agent {agent_id} 的遗留 Tool：{', '.join(removed)}")


if __name__ == "__main__":
    main()
