"""模拟 Windows 管道的非 UTF-8 编码，验证实际 CLI 输出没有损坏或异常。"""

import json
import contextlib
from datetime import date
import io
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from bazi.cli import main


class AsciiFormatDate(date):
    """旧版 Windows strftime 在非中文区域设置下的格式串限制。"""
    def strftime(self, format):
        format.encode("ascii")
        return super().strftime(format)


class TestWindowsOutput(unittest.TestCase):
    def test_夏令时提示不依赖日期格式化支持中文(self):
        output, error = io.StringIO(), io.StringIO()
        dates = (AsciiFormatDate(1990, 4, 15), AsciiFormatDate(1990, 9, 16))
        with patch("bazi.cli.astro.china_dst_range", return_value=dates), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            status = main(["--date", "1990-06-15", "--time", "12:30", "--format", "json"])
        self.assertEqual(status, 0)
        self.assertIn("04月15日", error.getvalue())
        self.assertIn("09月16日", error.getvalue())
        self.assertEqual(json.loads(output.getvalue())["四柱"]["day"]["干支"], "辛亥")

    def run_windows_cli(self, output_format):
        code = """
import sys
from types import SimpleNamespace
from bazi import cli
# 只模拟 CLI 的平台检测，标准库仍使用实际宿主平台。
cli.sys = SimpleNamespace(platform='win32', stdout=sys.stdout, stderr=sys.stderr)
raise SystemExit(cli.main(sys.argv[1:]))
"""
        return subprocess.run(
            [sys.executable, "-B", "-c", code, "--date", "1990-06-15", "--time", "12:30",
             "--gender", "male", "--city", "北京", "--format", output_format],
            cwd=Path(__file__).resolve().parent.parent,
            env={**os.environ, "PYTHONIOENCODING": "cp1252"},
            capture_output=True,
        )

    def test_非UTF8管道可输出中文Markdown与告警(self):
        result = self.run_windows_cli("markdown")
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))
        output = result.stdout.decode("utf-8")
        self.assertIn("八字排盘原始数据", output)
        self.assertIn("⚠️", output)
        self.assertIn("夏令时", result.stderr.decode("utf-8"))

    def test_非UTF8管道可输出完整JSON(self):
        result = self.run_windows_cli("json")
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))
        data = json.loads(result.stdout.decode("utf-8"))
        self.assertEqual(data["四柱"]["day"]["干支"], "辛亥")
        self.assertTrue(data["告警"])


if __name__ == "__main__":
    unittest.main()
