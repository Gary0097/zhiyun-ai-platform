# -*- coding: utf-8 -*-
"""Token 消耗页面（设置 → Token 消耗）模拟数据生成器。

数据源文件：apps/qwenpaw-embedded/workspace/token_usage.json
格式（见 qwenpaw/token_usage/buffer.py::_apply_event）：
  { "YYYY-MM-DD": { "provider:model": {
        "provider_id": str, "model_name": str,
        "prompt_tokens": int, "completion_tokens": int, "call_count": int } } }

特性：
  - 默认区间 2025-12-01 → 2026-09-01；
  - 保留已存在的真实日数据（含页面上已有的实际调用记录），只补模拟日期；
  - 模拟日期记录在 sidecar（token_usage.sim-days.json），--cleanup 一键还原；
  - 默认先清理上一次模拟再生成——同一命令反复执行，每次输出都不一样
    （随机种子默认取当前时间，--seed 可复现）；
  - 企业采用曲线：12 月起爬坡、工作日高 / 周末低、每日随机扰动。

用法：
  python scripts/qa/generate_token_usage.py
  python scripts/qa/generate_token_usage.py --start-date 2025-12-01 --end-date 2026-09-01
  python scripts/qa/generate_token_usage.py --seed 42
  python scripts/qa/generate_token_usage.py --cleanup
"""
from __future__ import annotations

import argparse
import json
import random
import shutil
import time
from datetime import date, timedelta
from pathlib import Path

USAGE_FILE = Path("apps/qwenpaw-embedded/workspace/token_usage.json")
SIDECAR = USAGE_FILE.with_suffix(".sim-days.json")
BACKUP = USAGE_FILE.with_name(USAGE_FILE.name + ".pre-sim")

# (provider_id, model_name, 权重, 单次调用 prompt 均值, 单次 completion 均值)
# 权重决定该模型被使用的概率；均值仅作量级参考（真实样本：unsloth 27B
# 单日 prompt ~1.9M、kilo flash ~20k）。
MODELS = [
    ("unsloth", "DavidAU/Qwen3.8-27B-Cold-Fusion-GAIN-V1.1-NM-DAU-NEO-MAX-MTP-GGUF",
     0.46, 38_000, 900),
    ("kilo", "stepfun/step-3.7-flash:free", 0.22, 640, 120),
    ("lmstudio", "DavidAU/Qwen3.8-27B-Cold-Fusion-GAIN-V1.1-NM-DAU-NEO-MAX-MTP-GGUF",
     0.18, 31_000, 700),
    ("kilo", "kilo-auto/free", 0.14, 900, 160),
]


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def save_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def cleanup(data: dict, sidecar_days: list[str]) -> tuple[dict, int]:
    removed = 0
    for day in sidecar_days:
        if day in data:
            del data[day]
            removed += 1
    return data, removed


def generate_day(rng: random.Random, day: date, progress: float) -> dict:
    """progress: 0→1（区间起点→终点），驱动企业采用量爬坡。"""
    weekday_factor = rng.uniform(0.18, 0.35) if day.weekday() >= 5 else rng.uniform(0.75, 1.3)
    ramp = 0.4 + 0.9 * progress
    day_entry: dict = {}
    for provider, model, weight, p_mean, c_mean in MODELS:
        # 每个模型每天独立出现概率：主力模型几乎每天在用，边缘模型偶发。
        presence = min(1.0, weight * 2.6)
        if rng.random() > presence:
            continue
        calls = max(1, int(rng.triangular(3, 140, int(60 * weight * 4))))
        prompt = int(calls * p_mean * ramp * weekday_factor * rng.uniform(0.55, 1.5))
        completion = int(calls * c_mean * ramp * weekday_factor * rng.uniform(0.5, 1.6))
        day_entry[f"{provider}:{model}"] = {
            "provider_id": provider,
            "model_name": model,
            "prompt_tokens": max(calls * 120, prompt),
            "completion_tokens": max(calls * 8, completion),
            "call_count": calls,
        }
    return day_entry


def main() -> int:
    parser = argparse.ArgumentParser(description="Token 消耗 模拟数据生成器")
    parser.add_argument("--start-date", default="2025-12-01", help="开始日期（含）")
    parser.add_argument("--end-date", default="2026-09-01", help="结束日期（含）")
    parser.add_argument("--seed", type=int, default=int(time.time()),
                        help="随机种子（默认按当前时间，每次执行输出不同）")
    parser.add_argument("--keep-previous", action="store_true",
                        help="叠加到上一次模拟之上（默认先清理上一次再生成）")
    parser.add_argument("--cleanup", action="store_true", help="删除全部模拟日期并还原")
    args = parser.parse_args()

    if not USAGE_FILE.exists():
        print(f"[错误] 未找到 {USAGE_FILE}")
        return 1

    rng = random.Random(args.seed)
    data = load_json(USAGE_FILE, {})
    sidecar_days = load_json(SIDECAR, [])

    if args.cleanup:
        if not sidecar_days:
            print("没有可清理的模拟数据。")
            return 0
        data, removed = cleanup(data, sidecar_days)
        save_json(USAGE_FILE, data)
        SIDECAR.unlink(missing_ok=True)
        print(f"已清理 {removed} 个模拟日期，真实调用数据保持不变。")
        return 0

    if not args.keep_previous and sidecar_days:
        data, removed = cleanup(data, sidecar_days)
        print(f"已清理上一次模拟（{removed} 天），重新生成全新数据。")

    # 备份真实原始文件（只备份一次，且备份里不含模拟数据）
    if not BACKUP.exists():
        pristine = load_json(BACKUP, None)
        if pristine is None:
            shutil.copy2(USAGE_FILE, BACKUP)

    start = date.fromisoformat(args.start_date)
    end = date.fromisoformat(args.end_date)
    if end < start:
        print("[错误] --end-date 早于 --start-date")
        return 1
    total_days = (end - start).days + 1

    real_days = set(data.keys())
    written = 0
    for offset in range(total_days):
        day = start + timedelta(days=offset)
        key = day.isoformat()
        if key in real_days:
            continue  # 保留真实日数据
        progress = offset / max(1, total_days - 1)
        entry = generate_day(rng, day, progress)
        if entry:
            data[key] = entry
            sidecar_days.append(key)
            written += 1

    save_json(USAGE_FILE, data)
    save_json(SIDECAR, sorted(set(sidecar_days)))

    total_p = sum(e["prompt_tokens"] for day in data.values() for e in day.values())
    total_c = sum(e["completion_tokens"] for day in data.values() for e in day.values())
    total_calls = sum(e["call_count"] for day in data.values() for e in day.values())
    print(f"Token 消耗：新增模拟 {written} 天（{start} ~ {end}，跳过 {total_days - written} 个已有真实日）")
    print(f"当前全量：{len(data)} 天 | prompt {total_p:,} | completion {total_c:,} | 调用 {total_calls:,} 次")
    print(f"清理：python scripts/qa/generate_token_usage.py --cleanup")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
