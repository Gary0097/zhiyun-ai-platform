"""Explicitly enable R1 PawApp tools for all configured QwenPaw agents."""

from qwenpaw.config.config import BuiltinToolConfig, load_agent_config, save_agent_config
from qwenpaw.config.utils import load_config

TOOLS = ("orders_query", "orders_delivery_risk")


def main() -> None:
    config = load_config()
    profiles = (config.agents.profiles if config.agents else {}) or {}
    if not profiles:
        raise RuntimeError("QwenPaw 尚未创建 Agent，请先执行 qwenpaw init")
    for agent_id in profiles:
        agent = load_agent_config(agent_id)
        for name in TOOLS:
            current = agent.tools.builtin_tools.get(name)
            agent.tools.builtin_tools[name] = (
                current.model_copy(update={"enabled": True})
                if current else BuiltinToolConfig(name=name, enabled=True, config={})
            )
        save_agent_config(agent_id, agent)
        print(f"已为 Agent {agent_id} 启用订单 Tool：{', '.join(TOOLS)}")


if __name__ == "__main__":
    main()
