"""Run with a Python outside the install tree; a foreign listener must survive."""
from pathlib import Path
import shutil
import socket
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
assert not Path(sys.executable).resolve().is_relative_to(root), "Use system Python to model a foreign service"
with socket.socket() as listener:
    listener.bind(("127.0.0.1", 8088))
    listener.listen(8)
    result = subprocess.run([shutil.which("node"), str(root/"apps/zhizaoyunAIOS/scripts/start.mjs")],
                            cwd=root, capture_output=True, text=True, encoding="utf-8", timeout=45)
    assert result.returncode != 0, "Launcher must refuse an occupied foreign port"
    with socket.create_connection(("127.0.0.1", 8088), timeout=2):
        pass
    print("PASS foreign listener survives; launcher refuses to start on occupied port")
