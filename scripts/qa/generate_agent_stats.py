# -*- coding: utf-8 -*-
"""向 QwenPaw 工作区 sessions/ 注入模拟聊天会话，让 /agent-stats 页面有丰富数据。

数据源：workspace/workspaces/<agent>/sessions/console/<file>.json
读取逻辑（qwenpaw/agent_stats/service.py）：
  - 消息列表在 agent.state.context
  - 每条消息需有 role / created_at / content
  - assistant 消息可含 tool_calls（计入 tool_calls 统计）
  - 用户消息 → user_messages，助手消息 → assistant_messages
  - 同一天有消息的 session 计入 active_sessions
  - chats.json（ChatsFile 格式 {"version":1,"chats":[ChatSpec]}）中的
    chat.created_at 计入每日 chats 数。写裸列表会被 JsonChatRepository
    拒绝，chats 统计始终为 0（2.1.0 启动日志会报 invalid chat registry）。

每次执行输出都不同：
  - 随机种子默认取当前时间；
  - 默认先清理上一次模拟（删除 sim-*.json 并以原始备份为底重建 chats.json）
    再生成全新数据，反复执行不会无限堆叠。

用法：
  python scripts/qa/generate_agent_stats.py
  python scripts/qa/generate_agent_stats.py --start-date 2025-12-01 --end-date 2026-09-01
  python scripts/qa/generate_agent_stats.py --days 60 --chats-per-day 30
  python scripts/qa/generate_agent_stats.py --seed 42
  python scripts/qa/generate_agent_stats.py --cleanup
"""
from __future__ import annotations

import argparse
import json
import random
import shutil
import time
import uuid
from datetime import date, datetime, timedelta
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
    "对比两期生产良率", "汇总服务工单超时原因", "测算下季度用工缺口",
]
ASSISTANT_RESPONSES = [
    "已为您完成分析，结果如下：", "根据查询，共找到 3 条相关记录。",
    "建议采取以下措施：", "分析已完成，可查看详情工件。",
    "已生成待审阅工件，请确认。", "数据已导出，可直接下载。",
    "检索到 5 条相关知识条目，已按相关度排序。",
]
TOOL_NAMES = ["search_records", "query_chanjet_orders", "export_excel",
              "list_departments", "search_knowledge", "get_order_detail"]


def rand_ts(rng: random.Random, day: date) -> str:
    sec = rng.randint(8 * 3600, 20 * 3600)
    return (f"{day.isoformat()}T{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"
            f".{rng.randint(100000, 999999)}Z")


def generate_session_file(rng: random.Random, day: date, session_id: str) -> dict:
    """生成一个符合 QwenPaw 2.x session JSON 格式的模拟会话。"""
    messages = []
    n_turns = rng.randint(2, 8)

    messages.append({
        "role": "system",
        "created_at": rand_ts(rng, day),
        "content": "你是智造云 AI-OS 的企业智能助手，基于授权数据回答业务问题。",
    })

    for _ in range(n_turns):
        messages.append({
            "role": "user",
            "created_at": rand_ts(rng, day),
            "content": rng.choice(USER_PROMPTS),
        })
        reply = rng.choice(ASSISTANT_RESPONSES)
        if rng.random() < 0.45:
            # 工具调用形态：content 为块列表，其中 type=tool_use 的块会被
            # agent_stats 计入 tool_calls（顶层 tool_calls 数组不被识别）。
            msg = {
                "role": "assistant",
                "created_at": rand_ts(rng, day),
                "content": [
                    {"type": "text", "text": reply},
                    {"type": "tool_use",
                     "id": f"call_{uuid.uuid4().hex[:8]}",
                     "name": rng.choice(TOOL_NAMES),
                     "input": {"limit": 10}},
                ],
            }
        else:
            msg = {
                "role": "assistant",
                "created_at": rand_ts(rng, day),
                "content": reply,
            }
        # 每轮 token 用量（qwenpaw_turn_usage 元数据 → agent token 统计）
        msg["metadata"] = {"qwenpaw_turn_usage": {"usage": {
            "prompt_tokens": rng.randint(1200, 26000),
            "completion_tokens": rng.randint(80, 1600),
        }}}
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


def load_valid_chats_file(path: Path) -> dict | None:
    """读取 ChatsFile 格式（{"version":1,"chats":[...]}）；无效则返回 None。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("chats"), list):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return None


def remove_previous_sim() -> int:
    count = 0
    if SESSIONS_DIR.exists():
        for f in SESSIONS_DIR.glob("sim-*.json"):
            f.unlink()
            count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description="Agent Stats 模拟数据生成器")
    parser.add_argument("--days", type=int, default=0,
                        help="生成天数（从 --end-date 往前推；忽略 --start-date）")
    parser.add_argument("--start-date", default="2025-12-01", help="开始日期（含）")
    parser.add_argument("--end-date", default="2026-09-01", help="结束日期（含）")
    parser.add_argument("--chats-per-day", type=int, default=30, help="每天会话文件数基准")
    parser.add_argument("--seed", type=int, default=int(time.time()),
                        help="随机种子（默认按当前时间，每次执行输出不同）")
    parser.add_argument("--keep-previous", action="store_true",
                        help="叠加到上一次模拟之上（默认先清理再生成）")
    parser.add_argument("--cleanup", action="store_true", help="删除所有模拟会话并恢复备份")
    args = parser.parse_args()

    rng = random.Random(args.seed)

    backup = CHATS_FILE.parent / (CHATS_FILE.name + BACKUP_SUFFIX)

    if args.cleanup:
        if SESSIONS_DIR.exists():
            count = remove_previous_sim()
            if backup.exists():
                shutil.move(str(backup), str(CHATS_FILE))
            print(f"已删除 {count} 个模拟会话文件，chats.json 已恢复")
        else:
            print("sessions 目录不存在")
        return 0

    end = date.fromisoformat(args.end_date)
    if args.days > 0:
        start = end - timedelta(days=args.days - 1)
    else:
        start = date.fromisoformat(args.start_date)
    if end < start:
        print("[错误] 结束日期早于开始日期")
        return 1
    total_days = (end - start).days + 1

    # 首次运行时备份原始 chats.json（含真实聊天）
    if CHATS_FILE.exists() and not backup.exists():
        shutil.copy2(str(CHATS_FILE), str(backup))

    if not args.keep_previous:
        removed = remove_previous_sim()
        if removed:
            print(f"已清理上一次模拟（{removed} 个会话文件），重新生成全新数据。")

    # 以真实数据为底追加（ChatsFile 格式）；--keep-previous 时保留当前文件里的模拟聊天
    chats_doc = None
    if args.keep_previous and CHATS_FILE.exists():
        chats_doc = load_valid_chats_file(CHATS_FILE)
    if chats_doc is None:
        chats_doc = load_valid_chats_file(backup) if backup.exists() else None
    if chats_doc is None:
        chats_doc = {"version": 1, "chats": []}

    session_count = 0
    for offset in range(total_days):
        day = start + timedelta(days=offset)
        weekday = day.weekday()
        factor = 0.3 if weekday >= 5 else rng.uniform(0.7, 1.3)
        progress = offset / max(1, total_days - 1)  # 12 月 → 9 月采用爬坡
        ramp = 0.5 + 0.8 * progress
        n_chats = max(2, int(args.chats_per_day * factor * ramp))

        for _ in range(n_chats):
            session_id = f"sim-{day.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"
            session_data = generate_session_file(rng, day, session_id)
            file_path = SESSIONS_DIR / f"{session_id}.json"
            file_path.write_text(json.dumps(session_data, ensure_ascii=False), encoding="utf-8")
            session_count += 1

            created = rand_ts(rng, day)
            updated_dt = datetime.fromisoformat(created.replace("Z", "+00:00")) \
                + timedelta(seconds=rng.randint(120, 5400))
            updated = updated_dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{rng.randint(100000, 999999)}Z"
            chats_doc["chats"].append({
                "id": str(uuid.uuid4()),
                "name": rng.choice(USER_PROMPTS)[:20],
                "session_id": session_id,
                "user_id": "sim-demo",
                "channel": "console",
                "created_at": created,
                "updated_at": updated,
                "meta": {},
                "status": "idle",
                "pinned": False,
                "archived_at": None,
                "source": "chat",
            })

    chats_doc["version"] = 1
    CHATS_FILE.write_text(json.dumps(chats_doc, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"已生成 {session_count} 个模拟会话（{start} ~ {end}，{total_days} 天）")
    print(f"chats.json 已更新（ChatsFile 格式，共 {len(chats_doc['chats'])} 条聊天）")
    print("清理：python scripts/qa/generate_agent_stats.py --cleanup")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
