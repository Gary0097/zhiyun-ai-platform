"""Exercise runtime web tools and guest browser without model/provider credentials."""
import asyncio
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import time


async def main(output):
    output.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[1]
    os.environ["QWENPAW_WORKING_DIR"] = str(root / "apps/zhizaoyunAIOS/workspace")
    from qwenpaw.agents.tools.web_search import web_fetch, web_search
    from qwenpaw.browser.tool_entrypoint import run_browser_tool
    from qwenpaw.browser.execution.kernel import get_default_kernel_manager
    results = []

    async def check(name, operation, expected, external=False):
        start = time.perf_counter()
        try:
            chunk = await asyncio.wait_for(operation(), timeout=90)
            text = "\n".join(item.get("text", "") if isinstance(item, dict) else getattr(item, "text", "") for item in chunk.content)
            success = str(chunk.state).lower().endswith("success") and expected.lower() in text.lower()
            results.append(dict(name=name, status="pass" if success else ("blocked" if external else "fail"), seconds=round(time.perf_counter()-start, 3), detail=text[:2000]))
        except Exception as exc:
            results.append(dict(name=name, status="fail", detail=f"{type(exc).__name__}: {exc}"))
        print(json.dumps(results[-1], ensure_ascii=False), flush=True)

    await check("web-fetch", lambda: web_fetch("https://python-docx.readthedocs.io/en/latest/"), "python-docx")
    await check("web-search", lambda: web_search("python-docx official documentation"), "http")
    await check("image-license-unsplash", lambda: web_fetch("https://unsplash.com/license"), "license", external=True)
    await check("image-license-fallback", lambda: web_fetch("https://raw.githubusercontent.com/feathericons/feather/main/LICENSE"), "MIT", external=True)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b'''<html><head><title>Office synthetic test</title></head><body>
<label>Name <input aria-label="Name" id="name"></label>
<button onclick="document.getElementById('result').textContent='Saved '+document.getElementById('name').value">Save</button>
<p id="result">Waiting</p></body></html>'''
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    code = f'''browser = await Browser.connect(identity="guest")
page = await browser.open("http://127.0.0.1:{server.server_port}/")
obs = await page.snapshot()
assert "Name" in obs.text, obs.text
await page.get_by_role("textbox", name="Name").fill("Synthetic Office")
await page.get_by_role("button", name="Save").click()
obs = await page.snapshot()
assert "Saved Synthetic Office" in obs.text, obs.text
print("BROWSER_VERIFIED", obs.text[:1000])
await browser.close()
'''
    await check("browser-guest", lambda: run_browser_tool(code=code), "BROWSER_VERIFIED")
    await get_default_kernel_manager().close_workspace("default")
    await get_default_kernel_manager().discard_all_workers()
    server.shutdown()
    server.server_close()
    await asyncio.sleep(.2)
    (output / "connected-results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    # Worker shutdown API differs across runtime releases; process atexit cleans up.
    if any(r["status"] == "fail" for r in results): return 1
    return 2 if any(r["status"] == "blocked" for r in results) else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(Path(sys.argv[1]).resolve())))
