"""Measure isolated Windows launcher startup to HTTP 200, preserving other services."""
import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import secrets
import subprocess
import time
import urllib.error
import urllib.request


def occupied():
    with socket.socket() as sock:
        sock.settimeout(.3)
        return sock.connect_ex(("127.0.0.1", 8088)) == 0


if __name__ == "__main__":
    if os.name != "nt":
        raise SystemExit("This benchmark owns Windows process trees; run it on Windows only")
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=2)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    for index in range(args.runs):
        if occupied():
            raise RuntimeError("8088 already occupied; refusing to stop an existing service")
        with (args.output / f"startup-{index+1}.log").open("w", encoding="utf-8") as log:
            start = time.perf_counter()
            env = dict(os.environ, QWENPAW_SECRET_DIR=str((args.output/f"auth-test-{index+1}").resolve()))
            child = subprocess.Popen([shutil.which("node"), str(root/"apps/zhizaoyunAIOS/scripts/start.mjs")], cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT)
            try:
                while time.perf_counter()-start < 120:
                    if child.poll() is not None:
                        raise RuntimeError(f"Launcher exited {child.returncode}; see log")
                    try:
                        with urllib.request.urlopen("http://127.0.0.1:8088/", timeout=.5) as response:
                            if response.status == 200:
                                html = response.read().decode("utf-8")
                                assert "智造云" in html or "AIOS" in html
                                break
                    except (OSError, urllib.error.URLError):
                        pass
                    time.sleep(.2)
                else:
                    raise TimeoutError("No HTTP 200 after 120 seconds")
                result = dict(run=index+1, http200_seconds=round(time.perf_counter()-start, 3))
                with urllib.request.urlopen("http://127.0.0.1:8088/api/auth/status", timeout=5) as response:
                    auth_status = json.load(response)
                assert auth_status["enabled"]
                if not auth_status["has_users"]:
                    request = urllib.request.Request("http://127.0.0.1:8088/api/auth/register",
                        data=json.dumps(dict(username="office-synthetic-test", password=secrets.token_urlsafe(24))).encode(),
                        headers={"Content-Type": "application/json"})
                    with urllib.request.urlopen(request, timeout=10) as response:
                        assert response.status == 200
                # Native token verification must reject an anonymous request.
                # Upstream intentionally permits loopback API access by default.
                try:
                    with urllib.request.urlopen("http://127.0.0.1:8088/api/auth/verify", timeout=5) as response:
                        result["anonymous_token_verify_status"] = response.status
                except urllib.error.HTTPError as exc:
                    result["anonymous_token_verify_status"] = exc.code
                assert result["anonymous_token_verify_status"] == 401, result
                results.append(result)
                print(json.dumps(result), flush=True)
            finally:
                # Only terminate the process tree created by this test.
                if child.poll() is None:
                    subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"], capture_output=True)
                child.wait(timeout=15)
        deadline = time.monotonic()+10
        while occupied() and time.monotonic() < deadline:
            time.sleep(.2)
    (args.output/"startup-results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
