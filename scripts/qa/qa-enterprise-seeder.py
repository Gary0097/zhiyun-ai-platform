# -*- coding: utf-8 -*-
"""企业环境初始化器 GUI 拟人交互测试（含登录）。"""
import json
import os
import sys
import time
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

BASE = "http://127.0.0.1:8088"
APP = BASE + "/apps/zhiyun-enterprise-seeder"
SS_DIR = r"C:\AI\zhiyun-ai-os-workspace\zhiyun-ai-platform\docs\qa\screenshots"
ADMIN = "admin"
PASS = "ZhizaoYun@2026"


def report(name, ok, detail=""):
    print(("PASS" if ok else "FAIL") + " | " + name + ((" | " + detail) if detail else ""))
    return (name, ok, detail)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    results = []
    logs = []
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe")
        page = browser.new_page(viewport={"width": 1440, "height": 980}, device_scale_factor=1)
        page.on("console", lambda m: logs.append(m.type + ":" + m.text))
        page.on("pageerror", lambda e: errors.append("pageerror: " + str(e)))
        try:
            page.goto(APP, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print("NAV_FAIL " + str(e))
            browser.close()
            return
        time.sleep(1)

        # ---- 登录墙处理 ----
        logged_in = False
        try:
            page.locator("input[placeholder='请输入员工账号']").first.wait_for(state="visible", timeout=12000)
            page.locator("input[placeholder='请输入员工账号']").first.fill(ADMIN)
            page.locator("input[type='password']").first.fill(PASS)
            page.get_by_role("button", name="登录").first.click(timeout=8000)
            page.wait_for_selector("text=系统管理员", timeout=15000)
            logged_in = True
        except (PWTimeout, Exception) as e:
            logged_in = False
            results.append(report("登录", False, str(e)))
        if logged_in:
            results.append(report("登录", True))
        time.sleep(1)

        # ---- 关闭宿主首启引导（试试桌面模式）----
        try:
            page.get_by_text("我知道了", exact=True).first.click(timeout=5000)
            time.sleep(0.5)
        except Exception:
            pass

        # ---- 应用主界面 ----
        try:
            page.wait_for_selector("text=企业环境初始化器", timeout=15000)
            results.append(report("页面渲染标题", True))
        except PWTimeout:
            results.append(report("页面渲染标题", False, "未找到「企业环境初始化器」"))

        for text in ["生成参数", "环境概览", "企业数据明细", "生成并运行", "智能体助手"]:
            results.append(report("页面文本[" + text + "]", page.get_by_text(text, exact=False).count() > 0))

        for stat in ["部门", "员工", "智能体", "应用", "会话", "任务", "Token"]:
            results.append(report("统计卡[" + stat + "]", page.get_by_text(stat, exact=False).count() > 0))

        chip_counts = page.locator("button:has-text('部门'), button:has-text('员工'), button:has-text('角色'), button:has-text('智能体'), button:has-text('应用'), button:has-text('数据源'), button:has-text('会话'), button:has-text('任务'), button:has-text('Token'), button:has-text('操作日志')").count()
        results.append(report("实体切换入口", chip_counts >= 10, "count=" + str(chip_counts)))

        ent = page.locator("input[placeholder='例如：制造云科技']").first
        ent_val = ent.input_value() if ent.count() > 0 else ""
        results.append(report("表单默认企业名", ent_val != "", "value=" + ent_val))

        page.screenshot(path=os.path.join(SS_DIR, "seeder-before.png"), full_page=True)

        # ---- 生成并运行 ----
        clicked = False
        try:
            page.get_by_role("button", name="生成并运行").last.click(timeout=12000)
            clicked = True
        except Exception as e:
            results.append(report("点击生成按钮", False, str(e)))
        if clicked:
            ok_gen = False
            try:
                page.wait_for_selector("text=企业环境已生成并运行", timeout=90000)
                ok_gen = True
            except PWTimeout:
                pass
            results.append(report("生成成功反馈", ok_gen))
            time.sleep(2)
            row_count = page.locator("table tbody tr").count()
            results.append(report("数据表有内容", row_count > 0, "rows=" + str(row_count)))
            try:
                stats_text = page.get_by_text("环境概览").locator("..").inner_text(timeout=5000)
            except Exception:
                stats_text = ""
            results.append(report("概览统计更新", ("制造云科技" in stats_text) or ("生成" in stats_text), stats_text[:80].replace("\n", " ")))
            page.screenshot(path=os.path.join(SS_DIR, "seeder-after-generate.png"), full_page=True)

        # ---- 切换实体 ----
        try:
            page.get_by_role("button", name="智能体", exact=True).click(timeout=8000)
            time.sleep(1.5)
            rows2 = page.locator("table tbody tr").count()
            results.append(report("切换实体-智能体表格", rows2 > 0, "rows=" + str(rows2)))
        except Exception as e:
            results.append(report("切换实体-智能体", False, str(e)))

        # ---- Agent 抽屉 ----
        try:
            page.get_by_role("button", name="智能体助手").first.click(timeout=8000)
            page.wait_for_selector("text=智能体助手", timeout=8000)
            results.append(report("Agent 抽屉打开", True))
            chips = page.get_by_text("初始化企业", exact=False).count() + page.get_by_text("查询状态", exact=False).count()
            results.append(report("Agent 快捷指令", chips >= 2, "chips=" + str(chips)))
            page.screenshot(path=os.path.join(SS_DIR, "seeder-agent-dock.png"), full_page=True)
        except Exception as e:
            results.append(report("Agent 抽屉", False, str(e)))

        browser.close()

    print("\n=== CONSOLE ERRORS ===")
    for l in errors:
        print(l)
    print("=== CONSOLE LOGS (first 20) ===")
    for l in logs[:20]:
        print(l)
    total = len(results)
    passed = sum(1 for _, ok, _ in results if ok)
    print("\nRESULT total=%d passed=%d failed=%d" % (total, passed, total - passed))
    for name, ok, detail in results:
        if not ok:
            print("  FAILED: " + name + ((" | " + detail) if detail else ""))


if __name__ == "__main__":
    main()
