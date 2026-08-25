# -*- coding: utf-8 -*-
"""Anthropomorphic functional probe v2: full studio flows + system apps + Agent dock across all apps."""
import json, pathlib
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8088"
OUT = pathlib.Path(__file__).resolve().parents[2] / "docs" / "qa"
SHOT = OUT / "screenshots" / "functional"
SHOT.mkdir(parents=True, exist_ok=True)

def click_by_text(page, texts):
    for t in texts:
        loc = page.locator(f"button:has-text('{t}')")
        for i in range(loc.count()):
            try:
                if loc.nth(i).is_visible():
                    loc.nth(i).click(timeout=3000)
                    return t
            except Exception:
                pass
    return None

def dismiss_toast(page):
    try:
        b = page.locator("button:has-text('我知道了')")
        if b.count() and b.first.is_visible():
            b.first.click(timeout=2000); page.wait_for_timeout(400); return True
    except Exception:
        pass
    return False

def antd_msg(page):
    try:
        return page.evaluate("""() => {
          const els = Array.from(document.querySelectorAll('.ant-message-notice-content'));
          return els.map(e => e.innerText.trim()).filter(Boolean).slice(-2).join(' | ');
        }""")
    except Exception:
        return ""

def body(page):
    return page.evaluate("() => document.body.innerText.replace(/\\s+/g,' ').trim()")

def probe(page, cfg):
    rec = {"app_id": cfg["id"], "route": cfg["route"]}
    try:
        page.goto(BASE + cfg["route"], wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)
        dismiss_toast(page)
        pre = cfg.get("preload") or ["一键导入示例数据"]
        rec["preload_clicked"] = click_by_text(page, pre)
        page.wait_for_timeout(1200)
        dismiss_toast(page)
        rec["run_clicked"] = click_by_text(page, cfg["run"])
        for _ in range(40):
            t = body(page)
            if "智能引擎分析中" not in t and "正在结合模型计算" not in t:
                break
            page.wait_for_timeout(500)
        page.wait_for_timeout(1500)
        t = body(page)
        rec["msg"] = antd_msg(page)
        rec["empty_result"] = "暂无分析结果" in t
        rec["has_source_line"] = "数据来源" in t
        rec["has_error"] = any(k in t for k in ["执行失败","出错","Error","HTTP ","拉取失败","无法"])
        rec["result_len"] = len(t)
        rec["sample"] = t[:260]
        shot = SHOT / (cfg["id"] + ".png"); page.screenshot(path=str(shot), full_page=False); rec["screenshot"] = str(shot)
        # Agent dock for every app
        try:
            dock = page.locator("button:has-text('问 Agent')")
            rec["agent_buttons"] = dock.count()
            if dock.count():
                # pick the header one (last) if multiple
                dock.last.click(timeout=3000); page.wait_for_timeout(1200)
                atxt = body(page)
                rec["agent_opened"] = ("Agent" in atxt) or ("智能体" in atxt)
                rec["agent_input"] = bool(page.query_selector("textarea, .ant-input, input[type='text']"))
                a_shot = SHOT / (cfg["id"] + "-agent.png"); page.screenshot(path=str(a_shot), full_page=False); rec["agent_screenshot"] = str(a_shot)
                try:
                    page.keyboard.press("Escape"); page.wait_for_timeout(400)
                except Exception:
                    pass
        except Exception as e:
            rec["agent_error"] = str(e)
    except Exception as e:
        rec["error"] = str(e)
    return rec

APPS = [
    {"id":"zhiyun-sales-studio","route":"/apps/zhiyun-sales-studio","run":["生成销售BI"]},
    {"id":"zhiyun-finance-studio","route":"/apps/zhiyun-finance-studio","run":["审核报销"]},
    {"id":"zhiyun-supply-studio","route":"/apps/zhiyun-supply-studio","run":["评估供应商"]},
    {"id":"zhiyun-service-studio","route":"/apps/zhiyun-service-studio","preload":["载入示例文本"],"run":["生成应答"]},
    {"id":"zhiyun-people-studio","route":"/apps/zhiyun-people-studio","run":["生成权限方案"]},
    {"id":"zhiyun-order-studio","route":"/apps/zhiyun-order-studio","preload":["载入示例并运行"],"run":["提取并检查风险"]},
    {"id":"zhiyun-integration-hub","route":"/apps/zhiyun-integration-hub","preload":["载入示例"],"run":["读取数据并自动匹配字段"]},
    {"id":"zhiyun-data-studio","route":"/apps/zhiyun-data-studio","run":["刷新数据"]},
    {"id":"zhiyun-data-core","route":"/apps/zhiyun-data-core","run":["生成 20 条演示订单"]},
    {"id":"zhiyun-audit","route":"/apps/zhiyun-audit","run":["刷 新"]},
    {"id":"zhiyun-app-discovery","route":"/apps/zhiyun-app-discovery","run":["后台服务"]},
]

def main():
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe", headless=True, args=["--no-sandbox","--disable-gpu"])
        ctx = browser.new_context(viewport={"width":1440,"height":900})
        page = ctx.new_page()
        page.goto(BASE + "/", wait_until="domcontentloaded", timeout=60000); page.wait_for_timeout(2500)
        a = page.query_selector("input[placeholder='请输入员工账号']"); pwd = page.query_selector("input[placeholder='请输入登录密码']")
        if a and pwd:
            a.fill("admin"); pwd.fill("Zhiyun@2026"); page.click("button:has-text('登录')"); page.wait_for_timeout(3000)
        results.append({"login_token": bool(page.evaluate("() => window.localStorage.getItem('zhiyun_token')"))})
        for cfg in APPS:
            results.append(probe(page, cfg))
        browser.close()
    OUTF = OUT / "functional-interaction-probe.json"
    OUTF.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("WROTE", OUTF)
    for r in results:
        if "app_id" in r:
            print(f"{r['app_id']:26s} pre={str(r.get('preload_clicked')):12s} run={str(r.get('run_clicked')):13s} empty={str(r.get('empty_result')):5s} src={str(r.get('has_source_line')):5s} err={str(r.get('has_error')):5s} agent={str(r.get('agent_opened')):5s} aIn={str(r.get('agent_input')):5s} len={r.get('result_len')} msg={r.get('msg')}")

if __name__ == "__main__":
    main()
