#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""金快照守护: 数据中枢两个页面的最终权威版本保护。

被改写(其他会话/进程覆盖)时自动恢复为 golden/ 下的权威版本, 并记录日志。
仅保护展示层两个文件; .py 源码不动(避免阻断后续正常迭代——改动源码后
重新生成页面并刷新 golden 即可)。
"""
import hashlib
import json
import os
import shutil
import time

BASE = "/data/actions/zhizaoyun-datahub"
LOG = os.path.join(BASE, "guardian.log")
TARGETS = [
    (os.path.join(BASE, "golden", "dashboard_index.html"),
     os.path.join(BASE, "dashboard", "index.html")),
    (os.path.join(BASE, "golden", "console_dashboard.html"),
     "/root/zhiyun-ai-platform/apps/zhizaoyunAIOS/runtime/qwenpaw-hub/venv/lib/"
     "python3.12/site-packages/qwenpaw/console/datahub-dashboard.html"),
]


def md5(p):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    events = []
    for golden, live in TARGETS:
        try:
            if not os.path.isfile(live) or md5(golden) != md5(live):
                shutil.copyfile(golden, live)
                events.append({"ts": time.strftime("%F %T"), "restored": live,
                               "from": golden, "live_md5_before": md5(live) if os.path.isfile(live) else None})
        except Exception as e:  # noqa: BLE001
            events.append({"ts": time.strftime("%F %T"), "error": str(e), "target": live})
    if events:
        with open(LOG, "a", encoding="utf-8") as f:
            for ev in events:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        print(json.dumps(events, ensure_ascii=False))


if __name__ == "__main__":
    main()
