# -*- coding: utf-8 -*-
"""企业级模拟数据生成器：向 enterprise.db 注入大量全局使用数据。

覆盖（跨应用，非单应用内）：sessions / tasks / token_usage / files /
file_downloads / login_activity / operation_logs / business_events。
所有行带 run_tag 标记，支持一键清理本次注入，不影响真实/种子数据。
生成逻辑保证通过 integrity 全部 14 项一致性检查（授权对、Token 日
聚合、下载计数回写、登录可回查、无孤儿事件引用）。

用法：
  python scripts/qa/generate_usage_data.py --days 90 --sessions-per-day 300 --tag sim-01
  python scripts/qa/generate_usage_data.py --days 7 --sessions-per-day 100 --dry-run
  python scripts/qa/generate_usage_data.py --cleanup sim-01
"""
from __future__ import annotations

import argparse
import random
import sqlite3
import sys
import time
import uuid
from datetime import date, timedelta
from pathlib import Path

DEFAULT_DB = Path("apps/qwenpaw-embedded/workspace/enterprise/enterprise.db")

APPS = ["zhiyun-data-core", "zhiyun-data-studio", "zhiyun-order-studio",
        "zhiyun-sales-studio", "zhiyun-finance-studio", "zhiyun-people-studio",
        "zhiyun-supply-studio", "zhiyun-service-studio", "zhiyun-chanjet-hub"]
DEVICES = ["Windows Chrome", "Windows Edge", "macOS Safari", "移动端 Safari",
           "移动端 Android", "平板 iPad"]
FILE_CATS = [("finance", "xlsx", "财务报表"), ("sales", "csv", "订单导出"),
             ("production", "pdf", "工艺单"), ("service", "docx", "维修方案"),
             ("people", "xlsx", "花名册")]
LOG_ACTIONS = [("应用访问", "info"), ("工件导出", "info"), ("数据导入", "info"),
               ("审阅接受", "info"), ("参数调整", "warn"), ("登录提醒", "warn")]
TOKEN_CHOICES = [120, 260, 480, 800, 1500, 2600, 4000, 6500, 9000, 15000]


def rand_dt(rng: random.Random, day: date) -> str:
    sec = rng.randint(8 * 3600, 21 * 3600)
    return f"{day.isoformat()} {sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def rand_ip(rng: random.Random) -> str:
    return f"10.{rng.randint(30, 40)}.{rng.randint(1, 250)}.{rng.randint(1, 250)}"


def rid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class Generator:
    def __init__(self, db_path: Path, run_tag: str, days: int, sessions_per_day: int,
                 env_id: str, data_mode: str, start_date: str, seed: int):
        self.db_path = db_path
        self.run_tag = run_tag
        self.env_id = env_id
        self.data_mode = data_mode
        self.tenant_id = f"sim-{run_tag}"
        self.days = days
        self.sessions_per_day = sessions_per_day
        self.end = date.fromisoformat(start_date)
        self.start = self.end - timedelta(days=days - 1)
        self.rng = random.Random(seed)

    def load_context(self, conn: sqlite3.Connection) -> tuple[list[dict], dict[str, list[str]]]:
        """返回 (可用用户列表, 授权映射 agent -> [apps])。"""
        users = [dict(r) for r in conn.execute(
            "SELECT username, department, agent_id FROM org_users "
            "WHERE env_id = ? AND COALESCE(active, 1) = 1 LIMIT 500",
            (self.env_id,)).fetchall()]
        allowed: dict[str, list[str]] = {}
        for r in conn.execute(
                "SELECT agent_id, app_id FROM agent_app_access "
                "WHERE env_id = ? AND enabled = 1", (self.env_id,)):
            allowed.setdefault(r["agent_id"], []).append(r["app_id"])
        return users, allowed

    def generate(self, conn: sqlite3.Connection) -> dict[str, int]:
        rng = self.rng
        users, allowed = self.load_context(conn)
        usable = [u for u in users if u.get("agent_id") in allowed]
        if not usable:
            raise SystemExit("该环境没有可用的（用户, 授权应用）组合，请先运行企业初始化")

        counts = dict.fromkeys(
            ["sessions", "tasks", "token_usage", "files", "file_downloads",
             "login_activity", "operation_logs", "business_events"], 0)

        session_sql = ("INSERT INTO sessions(session_id, env_id, tenant_id, data_mode, run_tag,"
                       " user_id, agent_id, app_id, messages, started_at, ended_at, status, created_at)"
                       " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)")
        task_sql = ("INSERT INTO tasks(task_id, env_id, tenant_id, data_mode, run_tag,"
                    " session_id, agent_id, user_id, app_id, skill_id, label, status, success,"
                    " started_at, finished_at, latency_ms, tokens, created_at)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)")
        token_sql = ("INSERT INTO token_usage(env_id, tenant_id, data_mode, run_tag, day,"
                     " agent_id, app_id, user_id, tokens, calls, success, failed, created_at)"
                     " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)")
        file_sql = ("INSERT INTO files(file_id, env_id, tenant_id, data_mode, run_tag, task_id,"
                    " session_id, agent_id, user_id, app_id, name, category, format, size_kb,"
                    " download_count, created_at)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)")
        dl_sql = ("INSERT INTO file_downloads(download_id, env_id, tenant_id, data_mode, run_tag,"
                  " file_id, task_id, user_id, agent_id, app_id, downloaded_at, ip, device, created_at)"
                  " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)")
        login_sql = ("INSERT INTO login_activity(env_id, tenant_id, data_mode, run_tag, day,"
                     " user_id, agent_id, app_id, login_at, ip, device, success, status, created_at)"
                     " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)")
        log_sql = ("INSERT INTO operation_logs(env_id, tenant_id, data_mode, run_tag, day,"
                   " user_id, agent_id, app_id, action, detail, level, created_at)"
                   " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)")
        event_sql = ("INSERT INTO business_events(event_id, env_id, tenant_id, data_mode, run_tag,"
                     " day, user_id, agent_id, app_id, event_type, session_id, task_id, file_id,"
                     " download_id, tokens, created_at)"
                     " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)")

        cursor = conn.cursor()
        for offset in range(self.days):
            day = self.start + timedelta(days=offset)
            weekday = day.weekday()
            factor = 0.35 if weekday >= 5 else rng.uniform(0.75, 1.25)
            n_sessions = max(5, int(self.sessions_per_day * factor))

            token_day_rows: list[dict] = []

            for _ in range(n_sessions):
                user = rng.choice(usable)
                agent = user["agent_id"]
                app = rng.choice(allowed[agent])
                started = rand_dt(rng, day)
                n_messages = rng.randint(2, 9)
                ended = started[:-2] + f"{int(started[-2:]) + rng.randint(1, 5):02d}"
                session_id = rid("s")
                cursor.execute(session_sql, (
                    session_id, self.env_id, self.tenant_id, self.data_mode, self.run_tag,
                    user["username"], agent, app, n_messages, started, ended,
                    "completed" if rng.random() < 0.93 else "failed", started))
                counts["sessions"] += 1

                for _ in range(rng.randint(1, 3)):
                    task_id = rid("t")
                    success = rng.random() < 0.94
                    skill, _, _ = rng.choice(FILE_CATS)
                    tokens_used = rng.choice(TOKEN_CHOICES)
                    latency = rng.randint(300, 9000)
                    finished = started[:-2] + f"{int(started[-2:]) + rng.randint(1, 5):02d}"
                    cursor.execute(task_sql, (
                        task_id, self.env_id, self.tenant_id, self.data_mode, self.run_tag,
                        session_id, agent, user["username"], app, skill,
                        f"{skill}任务", "completed" if success else "failed", int(success),
                        started, finished, latency, tokens_used if success else 0, started))
                    counts["tasks"] += 1

                    if success:
                        # 只有成功任务才计入 token 汇总（tasks.tokens 在失败时为 0）
                        token_day_rows.append({
                            "day": day.isoformat(), "agent": agent, "app": app,
                            "user": user["username"], "tokens": tokens_used,
                            "calls": 1})
                    cursor.execute(event_sql, (
                        rid("e"), self.env_id, self.tenant_id, self.data_mode, self.run_tag,
                        day.isoformat(), user["username"], agent, app, "task",
                        session_id, task_id, None, None,
                        tokens_used if success else 0, started))
                    counts["business_events"] += 1

                    if success and rng.random() < 0.5:
                        file_id = rid("f")
                        cat, fmt, prefix = rng.choice(FILE_CATS)
                        file_name = f"{prefix}_{rng.randint(100, 999)}.{fmt}"
                        n_dl = rng.randint(0, 3)
                        file_size = rng.randint(12, 4200)
                        cursor.execute(file_sql, (
                            file_id, self.env_id, self.tenant_id, self.data_mode, self.run_tag,
                            task_id, session_id, agent, user["username"], app,
                            file_name, cat, fmt, file_size, n_dl, started))
                        counts["files"] += 1
                        for _ in range(n_dl):
                            dl_id = rid("dl")
                            dl_at = rand_dt(rng, day)
                            cursor.execute(dl_sql, (
                                dl_id, self.env_id, self.tenant_id, self.data_mode, self.run_tag,
                                file_id, task_id, user["username"], agent, app,
                                dl_at, rand_ip(rng), rng.choice(DEVICES), started))
                            counts["file_downloads"] += 1
                            cursor.execute(event_sql, (
                                rid("e"), self.env_id, self.tenant_id, self.data_mode, self.run_tag,
                                day.isoformat(), user["username"], agent, app, "download",
                                session_id, task_id, file_id, dl_id, 0, dl_at))
                            counts["business_events"] += 1

            # Token 日聚合：任务 tokens 累加，保证 token_consistency 恒等
            agg: dict[tuple, dict] = {}
            for tr in token_day_rows:
                key = (tr["day"], tr["agent"], tr["app"], tr["user"])
                a = agg.setdefault(key, {"tokens": 0, "calls": 0})
                a["tokens"] += tr["tokens"]
                a["calls"] += 1
            for (day_s, agent, app, user_id), a in agg.items():
                cursor.execute(token_sql, (
                    self.env_id, self.tenant_id, self.data_mode, self.run_tag, day_s,
                    agent, app, user_id, a["tokens"], a["calls"], a["calls"], 0,
                    f"{day_s} 23:00:00"))
                counts["token_usage"] += 1

            # 登录（用户来自 org_users，保证可回查）
            for _ in range(max(3, int(n_sessions * 0.6))):
                user = rng.choice(usable)
                cursor.execute(login_sql, (
                    self.env_id, self.tenant_id, self.data_mode, self.run_tag, day.isoformat(),
                    user["username"], user["agent_id"], rng.choice(allowed[user["agent_id"]]),
                    rand_dt(rng, day), rand_ip(rng), rng.choice(DEVICES),
                    1, "在线", day.isoformat()))
                counts["login_activity"] += 1

            # 操作日志（运营观测用）
            for _ in range(rng.randint(4, 12)):
                user = rng.choice(usable)
                action, level = rng.choice(LOG_ACTIONS)
                cursor.execute(log_sql, (
                    self.env_id, self.tenant_id, self.data_mode, self.run_tag, day.isoformat(),
                    user["username"], user["agent_id"], rng.choice(allowed[user["agent_id"]]),
                    action, f"{user['username']} {action}", level, day.isoformat()))
                counts["operation_logs"] += 1

        return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="企业级模拟使用数据生成器")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="enterprise.db 路径")
    parser.add_argument("--days", type=int, default=120, help="生成天数（往前推）")
    parser.add_argument("--sessions-per-day", type=int, default=400, help="每天会话数基准")
    parser.add_argument("--env-id", default="", help="目标 env_id（默认取库中最新环境）")
    parser.add_argument("--data-mode", default="demo", choices=["demo", "production"])
    parser.add_argument("--start-date", default=date.today().isoformat(), help="结束日期（含）")
    parser.add_argument("--seed", type=int, default=int(time.time()), help="随机种子（同种子结果一致）")
    parser.add_argument("--tag", default=f"sim-{int(time.time())}", help="运行标记（清理凭据）")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划，不写入")
    parser.add_argument("--cleanup", default="", metavar="RUN_TAG", help="清理指定 run_tag 注入的数据")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"[错误] 数据库不存在：{db_path}")
        return 1

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    if args.cleanup:
        total = 0
        with conn:
            for table in ["business_events", "file_downloads", "files", "token_usage",
                          "operation_logs", "login_activity", "tasks", "sessions"]:
                cur = conn.execute(f"DELETE FROM {table} WHERE run_tag = ?", (args.cleanup,))
                total += cur.rowcount
                print(f"  {table}: -{cur.rowcount}")
        print(f"清理完成，共删除 {total} 行（run_tag={args.cleanup}）")
        conn.close()
        return 0

    env_id = args.env_id
    if not env_id:
        row = conn.execute("SELECT env_id FROM enterprise_meta ORDER BY id DESC LIMIT 1").fetchone()
        env_id = row["env_id"] if row else "env_default"
    print(f"目标库：{db_path}")
    print(f"环境：{env_id} | 数据态：{args.data_mode} | 天数：{args.days} | 每日会话：{args.sessions_per_day}")
    print(f"日期范围：{args.start_date} 往前 {args.days} 天 | run_tag：{args.tag}")

    if args.dry_run:
        est = args.days * args.sessions_per_day
        print(f"dry-run 模式，未写入。预计行数量级：会话 ~{est}，任务 ~{est * 2}，Token 日聚合 ~{est // 40}")
        conn.close()
        return 0

    gen = Generator(db_path, args.tag, args.days, args.sessions_per_day,
                    env_id, args.data_mode, args.start_date, args.seed)
    t0 = time.time()
    try:
        with conn:
            counts = gen.generate(conn)
    except SystemExit as exc:
        print(f"[中止] {exc}")
        conn.close()
        return 1
    elapsed = round(time.time() - t0, 1)
    print(f"\n写入完成（{elapsed}s）：")
    for k, v in counts.items():
        print(f"  {k}: {v}")
    print(f"\nrun_tag = {args.tag}（清理：--cleanup {args.tag}）")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
