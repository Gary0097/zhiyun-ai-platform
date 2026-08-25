# -*- coding: utf-8 -*-
"""App Discovery AgentChatRequest / _build_input 长度约束单元测试。

app_discovery_plugin 依赖 fastapi/httpx 与宿主 qwenpaw 运行时；当测试环境缺少
这些依赖（例如全局 Python 仅用于发布门禁 discovery 时）则自动跳过，避免
破坏 ``node scripts/verify-release.mjs`` 的 Python 套件。用 QwenPaw venv
Python 运行可完整执行本文件全部用例。
"""

import sys
import unittest

# 插件在缺少任意依赖（如全局 Python 缺 anyio）时会因 ImportError 失败，
# 这里捕获并标记为「无插件依赖」，测试整体跳过，保证发布门禁仍通过。
try:
    import app_discovery_plugin as adp

    _HAS_PLUGIN = True
except Exception:  # pragma: no cover - 依赖缺失环境
    adp = None
    _HAS_PLUGIN = False


@unittest.skipUnless(_HAS_PLUGIN, "app_discovery_plugin 依赖（fastapi/httpx/qwenpaw）不可用")
class AppDiscoveryChatBoundTests(unittest.TestCase):
    """校验 AgentChatRequest 对 context/history 的长度约束与截断逻辑。

    这是对「应用接入默认智能体 + 应用内智能体对话」参考实现的安全护栏测试：
    防止调用方通过超大 system context 或海量历史轮次造成模型上下文溢出/过度
    消耗 Token。与 UI 侧 12 轮上限保持兼容（服务端允许到 24）。
    """

    def test_context_too_long_rejected(self) -> None:
        from pydantic import ValidationError

        with self.assertRaises(ValidationError):
            adp.AgentChatRequest(text="hi", context="x" * 8001)

    def test_context_at_limit_accepted(self) -> None:
        req = adp.AgentChatRequest(text="hi", context="x" * 8000)
        self.assertEqual(len(req.context), 8000)

    def test_history_too_many_turns_rejected(self) -> None:
        from pydantic import ValidationError

        with self.assertRaises(ValidationError):
            adp.AgentChatRequest(text="hi", history=[{"role": "user", "text": "hi"}] * 25)

    def test_history_at_limit_accepted(self) -> None:
        req = adp.AgentChatRequest(text="hi", history=[{"role": "user", "text": "hi"}] * 24)
        self.assertEqual(len(req.history), 24)

    def test_normal_payload_validates(self) -> None:
        req = adp.AgentChatRequest(
            text="hi",
            context="系统上下文",
            history=[{"role": "user", "text": "上一轮问题"}, {"role": "assistant", "text": "上一轮回答"}],
        )
        self.assertEqual(req.app_id, "zhiyun-app-discovery")

    def test_build_input_truncates_history_text(self) -> None:
        """_build_input 必须防御性截断历史单轮文本（<=4000），避免绕过模型层校验。"""
        req = adp.AgentChatRequest(
            text="现在的问题",
            history=[{"role": "user", "text": "x" * 9000}],
        )
        messages = adp._build_input(req)
        # 包含 system 上下文、历史 user 轮（截断）、当前 user 轮
        self.assertEqual(len(messages), 3)
        user_payloads = [m for m in messages if m["role"] == "user"]
        history_msg = user_payloads[0]
        self.assertLessEqual(
            len(history_msg["content"][0]["text"]), 4000,
            "历史单轮文本必须被截断到 4000 以内",
        )
        # 当前用户消息不截断（本就在 max_length 内）
        self.assertEqual(user_payloads[1]["content"][0]["text"], "现在的问题")


if __name__ == "__main__":
    unittest.main()
