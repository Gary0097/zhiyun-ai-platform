# -*- coding: utf-8 -*-
"""演示导入闭环探测：真实浏览器逐 Studio 上传样例 CSV -> 表格填充 -> 运行 -> 结果验证 + 截图。"""
import json
import pathlib
import urllib.request

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8088"


def api_login():
    request = urllib.request.Request(
        BASE + "/api/zhiyun-auth/login",
        data=json.dumps({"username": "admin", "password": "ZhizaoYun@2026"}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))["token"]

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DEMO = ROOT / "docs" / "qa" / "demo-data"
SHOT = ROOT / "docs" / "qa" / "screenshots" / "demo-import"
SHOT.mkdir(parents=True, exist_ok=True)

# (studio, module_label, module_key, run_button, csv_name or None)
CASES = [
    ("zhiyun-sales-studio", "销售BI分析", "bi", "生成销售BI", "bi-销售BI分析.csv"),
    ("zhiyun-sales-studio", "客户价值分层", "customers", "客户分层", "customers-客户价值分层.csv"),
    ("zhiyun-sales-studio", "销售业绩统计", "performance", "统计业绩", "performance-销售业绩统计.csv"),
    ("zhiyun-finance-studio", "报销审核", "expense", "审核报销", "expense-报销审核.csv"),
    ("zhiyun-finance-studio", "财务看板", "finance", "生成看板", "finance-财务看板.csv"),
    ("zhiyun-people-studio", "权限建议", "permission", "生成权限方案", "permission-权限建议.csv"),
    ("zhiyun-people-studio", "通讯录协作", "contact", "检索通讯录", "contact-通讯录协作.csv"),
    ("zhiyun-people-studio", "员工关怀", "anniversary", "生成关怀", "anniversary-员工关怀.csv"),
    ("zhiyun-people-studio", "人力分析", "hr", "分析人力", "hr-人力分析.csv"),
    ("zhiyun-supply-studio", "供应商评估", "supplier", "评估供应商", "supplier-供应商评估.csv"),
    ("zhiyun-supply-studio", "智能补货", "replenishment", "计算补货", "replenishment-智能补货.csv"),
    ("zhiyun-supply-studio", "风险监控", "risk", "监控风险", "risk-风险监控.csv"),
    ("zhiyun-service-studio", "知识库构建", "knowledge", "生成知识库", "knowledge-知识库构建.csv"),
]


def body(page):
    return page.evaluate("() => document.body.innerText.replace(/\\s+/g,' ').trim()")


def antd_msg(page):
    try:
        return page.evaluate(
            "() => Array.from(document.querySelectorAll('.ant-message-notice-content'))"
            ".map(e => e.innerText.trim()).filter(Boolean).slice(-2).join(' | ')"
        )
    except Exception:
        return ""


def dismiss_toast(page):
    # 宿主“桌面模式”引导浮层带全屏透明 SVG 热区，必须点掉否则拦截一切点击
    try:
        btn = page.locator("button:has-text('我知道了')")
        if btn.count() and btn.first.is_visible():
            btn.first.click(timeout=2000)
            page.wait_for_timeout(400)
            return True
    except Exception:
        pass
    return False


def remove_tour_mask(page):
    # QA 专用：宿主新手引导遮罩（qwenpaw-tour-mask）每次进入都出现并拦截点击，
    # 演示环境已知缺陷；探测中直接移除以保证可交互（真实用户可通过引导控件关闭）。
    try:
        page.evaluate(
            "() => document.querySelectorAll('.qwenpaw-tour-mask').forEach(e => e.remove())"
        )
    except Exception:
        pass


def click_by_text(page, texts):
    for t in texts:
        loc = page.locator(f".zy-app button:has-text('{t}')").locator("visible=true")
        for i in range(loc.count()):
            try:
                if loc.nth(i).is_visible():
                    loc.nth(i).click(timeout=3000)
                    return t
            except Exception:
                pass
    return None


def run_case(page, studio, label, key, run_btn, csv_name):
    rec = {"studio": studio, "module": key, "label": label}
    try:
        page.goto(BASE + "/apps/" + studio, wait_until="domcontentloaded", timeout=60000)
        try:
            page.wait_for_selector(".zy-app", timeout=30000)
        except Exception as exc:  # noqa: BLE001
            rec["error"] = f"app did not mount: {exc}"
            return rec
        dismiss_toast(page)
        remove_tour_mask(page)
        # 左侧导航切到目标模块（重试 + 等待该模块输入表格就绪）
        switched = False
        for _ in range(3):
            try:
                # 用左侧导航结构定位（模块名可能同时出现在顶部副标题里，text= 会误中）
                page.locator(f".zy-rail .zy-nav-item:has-text('{label}')").locator("visible=true").first.click(timeout=4000)
                page.wait_for_selector(f".zy-app button:has-text('{run_btn}')", timeout=5000, state="attached")
                switched = True
                break
            except Exception:
                dismiss_toast(page)
                remove_tour_mask(page)
        if not switched:
            rec["error"] = "module input area did not appear"
            return rec
        dismiss_toast(page)
        remove_tour_mask(page)
        # 上传 CSV（antd.Upload 的隐藏 input[type=file]，取输入区可见面板的第一个）
        upload = page.locator(".zy-app input[type='file']").first
        upload.set_input_files(str(DEMO / studio / csv_name), timeout=20000)
        page.wait_for_timeout(1800)
        rec["import_msg"] = antd_msg(page)
        rec["import_tag"] = "已导入" in body(page)
        # 校验表格行数（输入区 antd 表格 tbody 行）
        try:
            rec["grid_rows"] = page.locator(".zy-cellgap tbody tr:not(.ant-table-measure-row)").count()
        except Exception:
            rec["grid_rows"] = -1
        # 运行（重试定位 chip 按钮）
        for _ in range(2):
            try:
                chip = page.locator(f".zy-app button:has-text('{run_btn}')").locator("visible=true").first
                chip.click(timeout=8000)
                rec["run_clicked"] = run_btn
                break
            except Exception:
                remove_tour_mask(page)
                dismiss_toast(page)
        for _ in range(40):
            t = body(page)
            if "智能引擎分析中" not in t and "正在结合模型计算" not in t:
                break
            page.wait_for_timeout(500)
        page.wait_for_timeout(1500)
        t = body(page)
        rec["empty_result"] = "暂无分析结果" in t
        rec["has_source"] = "数据来源" in t
        rec["has_error"] = any(k in t for k in ["执行失败", "执行「" + label + "」出现问题", "HTTP ", "无法"])
        rec["body_len"] = len(t)
        shot = SHOT / f"{studio}-{key}.png"
        page.screenshot(path=str(shot), full_page=False)
        rec["screenshot"] = str(shot)
    except Exception as exc:  # noqa: BLE001
        rec["error"] = str(exc)
        try:
            page.screenshot(path=str(SHOT / f"{studio}-{key}-error.png"), full_page=False)
        except Exception:
            pass
    return rec


def main():
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            headless=True, args=["--no-sandbox", "--disable-gpu"],
        )
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        loaded_rounds = []
        page.on("console", lambda m: loaded_rounds.append(1) if "plugin(s) loaded" in m.text else None)
        page.goto(BASE + "/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2500)
        # 真实 UI 登录（回归覆盖 zhiyun-auth 幂等挂载修复；用物理点击模拟真实用户）
        account = page.query_selector("input[placeholder='请输入员工账号']")
        password = page.query_selector("input[placeholder='请输入登录密码']")
        if account and password:
            account.fill("admin")
            password.fill("ZhizaoYun@2026")
            box = page.locator("#zhiyun-auth-root button:has-text('登录')").first.bounding_box()
            page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            page.wait_for_timeout(3500)
        # 宿主 PluginLoader 跑完（console 双重执行修复后仅一轮）后，应用直连路由才会挂载
        for _ in range(40):
            if len(loaded_rounds) >= 1:
                break
            page.wait_for_timeout(1000)
        page.wait_for_timeout(2000)
        results.append({"login_token": bool(page.evaluate("() => window.localStorage.getItem('zhiyun_token')")),
                        "auth_roots": page.evaluate("() => document.querySelectorAll('#zhiyun-auth-root').length"),
                        "plugin_loader_rounds": len(loaded_rounds)})
        for case in CASES:
            results.append(run_case(page, *case))
        browser.close()
    out = ROOT / "docs" / "qa" / "demo-import-probe.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("WROTE", out)
    ok = 0
    for r in results[1:]:
        good = (not r.get("error") and r.get("import_tag") and r.get("run_clicked")
                and not r.get("empty_result") and not r.get("has_error") and (r.get("grid_rows") or 0) > 0)
        ok += 1 if good else 0
        print(f"{'PASS' if good else 'FAIL'} {r['studio']}/{r['module']}: "
              f"tag={r.get('import_tag')} rows={r.get('grid_rows')} run={r.get('run_clicked')} "
              f"empty={r.get('empty_result')} err={r.get('has_error')} msg={r.get('import_msg')} {r.get('error') or ''}")
    print(f"\nSUMMARY: {ok}/{len(results) - 1} modules passed")


if __name__ == "__main__":
    main()
