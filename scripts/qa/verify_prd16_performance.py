# -*- coding: utf-8 -*-
"""PRD §16 性能指标验收（可重复执行，输出 JSON 证据）。"""
import json
import statistics
import sys
import time

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8088"
APPS = ["zhiyun-sales-studio", "zhiyun-finance-studio", "zhiyun-people-studio",
        "zhiyun-supply-studio", "zhiyun-service-studio", "zhiyun-order-studio",
        "zhiyun-data-studio", "zhiyun-data-core", "zhiyun-audit",
        "zhiyun-app-discovery", "zhiyun-integration-hub"]
QUERIES = ["交付风险", "合同不一致", "报销审核", "供应商补货", "销售业绩", "工单",
           "成本预测", "人力分析", "订单进度", "客户分层", "知识库", "ERP对接"] * 3


def main() -> int:
    pages, searches = [], []
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                              headless=True, args=["--no-sandbox", "--disable-gpu"])
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.goto(BASE + "/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)
        page.fill("input[placeholder='请输入员工账号']", "admin")
        page.fill("input[placeholder='请输入登录密码']", "ZhizaoYun@2026")
        page.locator("#zhiyun-auth-root button:has-text('登录')").first.click(timeout=8000)
        page.wait_for_timeout(4000)

        for app in APPS:
            page.goto(BASE + "/apps/" + app, wait_until="domcontentloaded", timeout=60000)
            start = time.time()
            try:
                # 宽松可交互判定：正文充实且非空态提示
                page.wait_for_function(
                    "() => document.body.innerText.length > 400 && !document.body.innerText.includes('尚未加载')",
                    timeout=20000)
                pages.append({"app": app, "interactive_s": round(time.time() - start, 2), "ok": True})
            except Exception:
                pages.append({"app": app, "interactive_s": 20.0, "ok": False})

        page.goto(BASE + "/apps/zhiyun-app-discovery", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)
        page.evaluate("() => document.querySelectorAll('.qwenpaw-tour-mask,.qwenpaw-tour').forEach(e => e.remove())")
        for q in QUERIES:
            start = time.time()
            try:
                page.evaluate("""async (q) => {
                  const r = await fetch('/api/zhiyun-app-discovery/search?q=' + encodeURIComponent(q) + '&limit=12');
                  await r.json();
                }""", q)
                searches.append(round((time.time() - start) * 1000))
            except Exception:
                searches.append(5000)
        b.close()

    ss = sorted(searches)
    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "pages": pages,
        "page_interactive_max_s": max(p["interactive_s"] for p in pages),
        "page_all_under_2s": all(p["interactive_s"] < 2.0 for p in pages),
        "search_samples": len(ss),
        "search_p50_ms": ss[len(ss) // 2],
        "search_p95_ms": ss[int(len(ss) * 0.95)],
        "search_p95_under_500ms": ss[int(len(ss) * 0.95)] < 500,
    }
    report["prd16_pass"] = report["page_all_under_2s"] and report["search_p95_under_500ms"]
    out = "docs/qa/prd16-performance.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in report.items() if k != "pages"}, ensure_ascii=False))
    for pg in pages:
        print(f"  {pg['app']:28s} {pg['interactive_s']}s {'OK' if pg['ok'] else 'TIMEOUT'}")
    return 0 if report["prd16_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
