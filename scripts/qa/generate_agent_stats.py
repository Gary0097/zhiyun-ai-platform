# -*- coding: utf-8 -*-
"""向 QwenPaw 工作区 sessions/ 注入模拟聊天会话，让 /agent-stats 页面有丰富数据。

数据源：workspace/workspaces/<agent>/sessions/console/<file>.json
读取逻辑（qwenpaw/agent_stats/service.py）：
  - 消息列表在 agent.state.context
  - 每条消息需有 role / created_at / content
  - assistant 消息可含 tool_calls（计入 tool_calls 统计）
  - 用户消息 → user_messages，助手消息 → assistant_messages
  - 同一天有消息的 session 计入 active_sessions
  - chats.json 中的 chat.created_at 计入 chats（每天聊天数）

用法：
  python scripts/qa/generate_agent_stats.py --days 60 --chats-per-day 30
  python scripts/qa/generate_agent_stats.py --cleanup
"""
from __future__ import annotations

import argparse
import json
import random
import shutil
import sys
import time
import uuid
from datetime import date, timedelta
from pathlib import Path

WORKSPACE = Path("apps/qwenpaw-embedded/workspace/workspaces/default")
SESSIONS_DIR = WORKSPACE / "sessions" / "console"
CHATS_FILE = WORKSPACE / "chats.json"
BACKUP_SUFFIX = ".pre-agent-stats-sim"

USER_PROMPTS = [
    "帮我分析本月销售趋势", "查询客户订单状态", "生成财务报表",
    "评估供应商风险", "创建售后工单", "分析人力数据",
    "预测成本变化", "检查订单合同一致性", "检索通讯录",
    "推荐审批路径", "监控供应链风险", "导入Excel数据",
    "生成知识库", "审阅报销单", "查看交付进度",
]
ASSISTANT_RESPONSES = [
    "已为您完成分析，结果如下：", "根据查询，共找到 3 条相关记录。",
    "建议采取以下措施：", "分析已完成，可查看详情工件。",
    "已生成待审阅工件，请确认。", "数据已导出，可直接下载。",
]
AGENT_NAMES = ["Default Agent", "Business Analyst", "Sales CRM Agent",
               "Finance Agent", "Support Agent"]


def rand_ts(rng: random.Random, day: date) -> str:
    sec = rng.randint(8 * 3600, 20 * 3600)
    return f"{day.isoformat()}T{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02}.{rng.randint(100000, 999999)}"


def generate_session_file(rng: random.Random, day: date, session_id: str) -> dict:
    """生成一个符合 QwenPaw 2.x session JSON 格式的模拟会话。"""
    messages = []
    n_turns = rng.randint(2, 8)

    system_prompt = (
        f"你是灵泽万川智造云 的智能体助手。当前会话：{session_id}。"
        "请基于真实数据回答业务问题，不要编造。"
    )
    messages.append({
        "name": "user", "role": "user",
        "content": [{"type": "text", "text": system_prompt}],
        "created_at": rand_ts(rng, day),
    })

    for i in range(n_turns):
        user_text = rng.choice(USER_PROMPTS)
        ts_user = rand_ts(rng, day)
        ts_asst = rand_ts(rng, day)
        if ts_asst < ts_user:
            ts_user, ts_asst = ts_asst, ts_user

        messages.append({
            "name": "user", "role": "user",
            "content": [{"type": "text", "text": user_text}],
            "created_at": ts_user,
        })

        asst_content = [
            {"type": "thinking", "thinking": f"User asks: {user_text}. I should query the data and respond concisely."},
            {"type": "text", "text": rng.choice(ASSISTANT_RESPONSES)},
        ]
        msg: dict = {
            "name": rng.choice(AGENT_NAMES), "role": "assistant",
            "content": asst_content,
            "created_at": ts_asst,
        }
        if rng.random() < 0.4:
            msg["tool_calls"] = [{
                "id": f"call_{uuid.uuid4().hex[:8]}",
                "type": "function",
                "function": {"name": "query_enterprise_orders", "arguments": "{}"},
            }]
        messages.append(msg)

    return {
        "agent": {
            "state": {
                "session_id": session_id,
                "summary": "",
                "context": messages,
                "reply_id": "",
                "cur_iter": 0,
            }
        }
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Agent Stats 模拟数据生成器")
    parser.add_argument("--days", type=int, default=60, help="生成天数")
    parser.add_argument("--chats-per-day", type=int, default=30, help="每天会话文件数")
    parser.add_argument("--seed", type=int, default=int(time.time()))
    parser.add_argument("--cleanup", action="store_true", help="删除所有模拟会话并恢复备份")
    args = parser.parse_args()

    rng = random.Random(args.seed)

    if args.cleanup:
        if SESSIONS_DIR.exists():
            count = 0
            for f in SESSIONS_DIR.glob("sim-*.json"):
                f.unlink()
                count += 1
            # 恢复 chats.json 备份
            backup = CHATS_FILE.parent / (CHATS_FILE.name + BACKUP_SUFFIX)
            if backup.exists():
                shutil.move(str(backup), str(CHATS_FILE))
            print(f"已删除 {count} 个模拟会话文件，chats.json 已恢复")
        else:
            print("sessions 目录不存在")
        return 0

    if not SESSIONS_DIR.exists():
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

    # 备份 chats.json
    if CHATS_FILE.exists():
        backup = CHATS_FILE.parent / (CHATS_FILE.name + BACKUP_SUFFIX)
        if not backup.exists():
            shutil.copy2(str(CHATS_FILE), str(backup))

    # 读取现有 chats
    chats: list = []
    if CHATS_FILE.exists():
        try:
            chats = json.loads(CHATS_FILE.read_text(encoding="utf-8"))
            if not isinstance(chats, list):
                chats = []
        except (json.JSONDecodeError, OSError):
            chats = []

    end = date.today()
    start = end - timedelta(days=args.days - 1)
    session_count = 0

    for offset in range(args.days):
        day = start + timedelta(days=offset)
        weekday = day.weekday()
        factor = 0.3 if weekday >= 5 else rng.uniform(0.7, 1.3)
        n_chats = max(2, int(args.chats_per_day * factor))

        for _ in range(n_chats):
            session_id = f"sim-{day.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"
            session_data = generate_session_file(rng, day, session_id)
            file_path = SESSIONS_DIR / f"{session_id}.json"
            file_path.write_text(json.dumps(session_data, ensure_ascii=False), encoding="utf-8")
            session_count += 1

            # chats.json 条目（计入每日 chats）
            chats.append({
                "id": session_id,
                "title": rng.choice(USER_PROMPTS),
                "created_at": rand_ts(rng, day),
                "updated_at": rand_ts(rng, day),
                "channel": "console",
            })

    CHATS_FILE.write_text(json.dumps(chats, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"已生成 {session_count} 个模拟会话（{start} ~ {end}，{args.days} 天）")
    print(f"chats.json 已更新（共 {len(chats)} 条）")
    print(f"清理：python scripts/qa/generate_agent_stats.py --cleanup")
    return 0


if __name__ == "__main__":
    sys.exit(main())
