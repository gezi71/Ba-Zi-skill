#!/usr/bin/env python3
"""命令行入口的薄壳 —— 真正的实现在 bazi/cli.py。

保留 scripts/bazi.py 是为了让 SKILL.md、README 里的示例命令始终可复制，
即使将来入口改名也不影响文档。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bazi.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
