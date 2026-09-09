# -*- coding: utf-8 -*-
"""标准演示数据集一键注入（Token 消耗 + 智能体统计 + 聊天会话 + 企业使用量）。

串起三个生成器，统一日期区间（默认 2025-12-01 → 2026-09-01）：
  1. generate_usage_data.py    → enterprise.db（会话/任务/Token 日聚合/文件/
                                 下载/登录/操作日志/业务事件，run_tag=sim-demo）
  2. generate_agent_stats.py   → sessions/console/*.json + chats.json
                                 （/agent-stats 智能体统计 + 每日聊天数）
  3. generate_token_usage.py   → workspace/token_usage.json（设置→Token 消耗）

每次执行输出都不同（种子默认取当前时间）；默认先清理上一次标准注入再生成，
反复执行不会堆叠。企业库固定 run_tag=sim-demo，方便一键回滚。

用法：
  python scripts/qa/generate_demo_dataset.py
  python scripts/qa/generate_demo_dataset.py --start 2025-12-01 --end 2026-09-01
  python scripts/qa/generate_demo_dataset.py --seed 42      # 可复现
  python scripts/qa/generate_demo_dataset.py --cleanup-only # 一键清理全部模拟
  python scripts/qa/generate_demo_dataset.py --skip-enterprise --skip-agent --skip-token

注意：注入完成后需重启 AI-OS 服务（start-ai-os）才能在页面上看到新数据。
"""
from __future__ import annotations

import argparse
import random
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
QA_DIR = REPO_ROOT / "scripts" / "qa"
RUN_TAG = "sim-demo"


def days_between(start: str, end: str) -> int:
    return (date.fromisoformat(end) - date.fromisoformat(start)).days + 1


def run(label: str, script: str, extra: list[str]) -> bool:
    cmd = [sys.executable, str(QA_DIR / script)] + extra
    print(f"\n=== {label} ===\n$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=REPO_ROOT)
    if result.returncode != 0:
        print(f"[失败] {label} 退出码 {result.returncode}")
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="标准演示数据集一键注入")
    parser.add_argument("--start", default="2025-12-01", help="开始日期（含，默认 2025-12-01）")
    parser.add_argument("--end", default="2026-09-01", help="结束日期（含，默认 2026-09-01）")
    parser.add_argument("--seed", type=int, default=int(time.time()),
                        help="统一随机种子（默认按当前时间，每次执行输出不同）")
    parser.add_argument("--sessions-per-day", type=int, default=300,
                        help="企业库每日会话数基准")
    parser.add_argument("--chats-per-day", type=int, default=30,
                        help="智能体统计每日会话文件数基准")
    parser.add_argument("--data-mode", default="demo", choices=["demo", "production"])
    parser.add_argument("--cleanup-only", action="store_true", help="只清理全部模拟数据")
    parser.add_argument("--skip-enterprise", action="store_true")
    parser.add_argument("--skip-agent", action="store_true")
    parser.add_argument("--skip-token", action="store_true")
    args = parser.parse_args()

    if date.fromisoformat(args.end) < date.fromisoformat(args.start):
        print("[错误] --end 早于 --start")
        return 1

    print(f"智造云 AI-OS 标准演示数据集")
    print(f"区间：{args.start} ~ {args.end}（{days_between(args.start, args.end)} 天）"
          f" | 种子：{args.seed} | run_tag：{RUN_TAG}")

    if args.cleanup_only:
        ok = True
        ok = run("清理企业使用量（enterprise.db）", "generate_usage_data.py",
                 ["--cleanup", RUN_TAG]) and ok
        ok = run("清理智能体统计 + 聊天会话", "generate_agent_stats.py", ["--cleanup"]) and ok
        ok = run("清理 Token 消耗", "generate_token_usage.py", ["--cleanup"]) and ok
        print("\n清理完成。" if ok else "\n清理过程有失败项，请检查上方日志。")
        return 0 if ok else 1

    # 为三个生成器派生独立子种子（避免同种子导致的相关模式）
    rng = random.Random(args.seed)
    seed_ent = rng.randrange(2**31)
    seed_agent = rng.randrange(2**31)
    seed_token = rng.randrange(2**31)

    ok = True
    if not args.skip_enterprise:
        # 固定 run_tag：先清理上次标准注入，再写入（否则重复执行会翻倍）
        ok = run("清理上次企业使用量（run_tag=sim-demo）", "generate_usage_data.py",
                 ["--cleanup", RUN_TAG]) and ok
        ok = run("企业使用量（enterprise.db）", "generate_usage_data.py", [
            "--start-date", args.end,
            "--days", str(days_between(args.start, args.end)),
            "--sessions-per-day", str(args.sessions_per_day),
            "--data-mode", args.data_mode,
            "--tag", RUN_TAG,
            "--seed", str(seed_ent),
        ]) and ok
    if not args.skip_agent:
        ok = run("智能体统计 + 聊天会话（sessions/ + chats.json）",
                 "generate_agent_stats.py", [
                     "--start-date", args.start, "--end-date", args.end,
                     "--chats-per-day", str(args.chats_per_day),
                     "--seed", str(seed_agent),
                 ]) and ok
    if not args.skip_token:
        ok = run("Token 消耗（token_usage.json）", "generate_token_usage.py", [
            "--start-date", args.start, "--end-date", args.end,
            "--seed", str(seed_token),
        ]) and ok

    if not ok:
        print("\n[警告] 部分生成器失败，请检查上方日志。")
        return 1

    print(f"""
============================================================
 标准演示数据集注入完成（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）
 覆盖：Token 消耗 / 智能体统计 / 聊天会话 / 企业使用量
 再执行一次本脚本 → 全部换成新的随机数据
 回滚：python scripts/qa/generate_demo_dataset.py --cleanup-only
 注意：请重启 AI-OS 服务（start-ai-os）后查看页面
============================================================""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
