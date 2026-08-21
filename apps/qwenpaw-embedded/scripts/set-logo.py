"""Set or reset the local AI-OS header logo without editing repository files."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from qwenpaw.constant import WORKING_DIR

MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".svg": "image/svg+xml", ".webp": "image/webp"}
MAX_BYTES = 2 * 1024 * 1024


def main() -> None:
    branding = WORKING_DIR / "branding"
    branding.mkdir(parents=True, exist_ok=True)
    config = branding / "logo.json"
    if len(sys.argv) == 2 and sys.argv[1] == "--reset":
        if config.exists():
            config.unlink()
        print("Logo 已恢复为项目默认值，重启 AI-OS 后生效。")
        return
    if len(sys.argv) != 2:
        raise SystemExit("用法：python set-logo.py <png|jpg|svg|webp>，或加 --reset 恢复默认")
    source = Path(sys.argv[1]).expanduser().resolve()
    mime = MIME.get(source.suffix.lower())
    if not source.is_file() or not mime:
        raise SystemExit("请选择有效的 PNG、JPG、SVG 或 WebP Logo 文件。")
    if source.stat().st_size > MAX_BYTES:
        raise SystemExit("Logo 文件不能超过 2 MB。")
    target = branding / f"ai-os-logo{source.suffix.lower()}"
    shutil.copy2(source, target)
    config.write_text(json.dumps({"path": str(target), "mime": mime}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Logo 已更新：{target}；重启 AI-OS 后生效。")


if __name__ == "__main__":
    main()
