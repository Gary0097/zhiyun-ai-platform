"""Enable Zhiyun's declared read-only tools for every local QwenPaw agent."""

from qwenpaw.config.config import BuiltinToolConfig, load_agent_config, save_agent_config
from qwenpaw.config.utils import load_config

TOOLS = (
    "enterprise_platform_status",
    "enterprise_query_orders",
    "enterprise_query_inventory",
    "enterprise_query_customers",
    "enterprise_search_knowledge",
)


def main() -> None:
    config = load_config()
    profiles = (config.agents.profiles if config.agents else {}) or {}
    if not profiles:
        raise RuntimeError("QwenPaw 尚未创建 Agent，请先执行 qwenpaw init")
    for agent_id in profiles:
        agent = load_agent_config(agent_id)
        for name in TOOLS:
            current = agent.tools.builtin_tools.get(name)
            if current is None:
                agent.tools.builtin_tools[name] = BuiltinToolConfig(name=name, enabled=True, config={})
            else:
                agent.tools.builtin_tools[name] = current.model_copy(update={"enabled": True})
        save_agent_config(agent_id, agent)
        print(f"已为 Agent {agent_id} 启用 {len(TOOLS)} 个智造云只读工具")


if __name__ == "__main__":
    main()
