"""权威分钟数据、PRC时刻边界、结构反例与解释证据。"""

import json
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from bazi import BirthInput, astro, build_chart
from bazi.cli import compare_output, to_json, to_markdown, comparison_markdown
from bazi.classics import catalog, climate_reference
from bazi.evidence import validate_reading
from bazi.patterns import analyze_patterns, structure_facts
from scripts.calibrate_terms import calibrate
from test_patterns_and_comparison import chart_of


class TestCalibration(unittest.TestCase):
    def test_离线来源完整且样本误差不超回归阈值(self):
        result = calibrate()
        self.assertEqual(result["summaries"]["all_terms"]["count"], 48)
        self.assertEqual(result["summaries"]["major_terms"]["count"], 24)
        self.assertLessEqual(result["summaries"]["all_terms"]["max_absolute_seconds"], 900)
        worst = max(result["measurements"], key=lambda r: abs(r["error_seconds"]))
        self.assertEqual((worst["year"], worst["term"]), (2026, "立夏"))
        self.assertLess(worst["error_seconds"], -800)
        self.assertAlmostEqual(astro.CALIBRATION_INFO["样本最大绝对差秒"], abs(worst["error_seconds"]))

    def test_损坏原始数据拒绝校准(self):
        with patch.object(Path, "read_bytes", return_value=b"corrupted"):
            with self.assertRaisesRegex(ValueError, "校验值不符"):
                calibrate()

    def test_权威交节前后候选覆盖并保留告警(self):
        for row in calibrate()["measurements"]:
            if not row["major"]:
                continue
            reference = datetime.fromisoformat(row["reference_utc"]) + timedelta(hours=8)
            for delta in (-15, -5, -1, 1, 5, 15):
                with self.subTest(year=row["year"], term=row["term"], delta=delta):
                    clock = reference + timedelta(minutes=delta)
                    data = compare_output(BirthInput(clock.year, clock.month, clock.day, clock.hour, clock.minute),
                                          None, True, 8, (), "未校正")
                    branch = dict(astro.MAJOR_TERM_MONTH_BRANCH)[row["term"]]
                    if delta < 0:
                        branch = (branch - 1) % 12
                    from bazi.constants import BRANCHES
                    self.assertIn(BRANCHES[branch], {c["四柱"]["月柱"][1] for c in data["候选"]})
                    if abs(delta) == 1:
                        self.assertTrue(any(c["告警"] for c in data["候选"]))


class TestPreciseDST(unittest.TestCase):
    # 锁定 IANA 2026e PRC 规则的六年日期；尤其1988应为17日。
    DATES = ((1986, 5, 4, 9, 14), (1987, 4, 12, 9, 13), (1988, 4, 17, 9, 11),
             (1989, 4, 16, 9, 17), (1990, 4, 15, 9, 16), (1991, 4, 14, 9, 15))

    def test_六年开始结束时刻及缺失重复区间(self):
        for y, m1, d1, m2, d2 in self.DATES:
            spring, autumn = datetime(y, m1, d1, 2), datetime(y, m2, d2, 2)
            for clock, expected in ((spring - timedelta(minutes=1), "standard"),
                                    (spring, "gap"), (spring + timedelta(minutes=59), "gap"),
                                    (spring + timedelta(hours=1), "daylight"),
                                    (autumn - timedelta(minutes=61), "daylight"),
                                    (autumn - timedelta(hours=1), "overlap"),
                                    (autumn - timedelta(minutes=1), "overlap"), (autumn, "standard")):
                with self.subTest(clock=clock):
                    self.assertEqual(astro.china_dst_clock_status(clock), expected)

    def test_不存在的夏令时读数拒绝回拨(self):
        with self.assertRaisesRegex(ValueError, "不存在"):
            build_chart(BirthInput(1988, 4, 17, 2, 30, dst_adjust=True))
        chart = build_chart(BirthInput(1988, 4, 17, 2, 30))
        self.assertTrue(any("标准时" in w.message for w in chart.warnings))

    def test_缺失区间比较只保留标准时并说明排除原因(self):
        data = compare_output(BirthInput(1988, 4, 17, 2, 30), None, True, 8, (), "未知")
        self.assertEqual(data["情景采样数"], 1)
        self.assertTrue(data["排除情景"])
        self.assertIn("不存在", comparison_markdown(data))

    def test_重复区间两个实际UTC时刻均保留(self):
        normal = build_chart(BirthInput(1988, 9, 11, 1, 30))
        adjusted = build_chart(BirthInput(1988, 9, 11, 1, 30, dst_adjust=True))
        self.assertEqual(normal.solar.moment_utc - adjusted.solar.moment_utc, timedelta(hours=1))
        data = compare_output(normal.birth, None, True, 8, (), "未知")
        self.assertEqual({s["夏令时回拨"] for c in data["候选"] for s in c["输入情景"]}, {False, True})

    def test_区间外不能回拨(self):
        for values in ((1988, 4, 10, 12, 0), (1988, 4, 17, 1, 59), (1988, 9, 11, 2, 0)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                build_chart(BirthInput(*values, dst_adjust=True))

    def test_跨缺失区间范围只排除无效假设(self):
        data = compare_output(BirthInput(1988, 4, 17, 1, 59), ((1, 59), (3, 0)), True, 8, (), "未知")
        self.assertEqual(data["情景采样数"], 63)  # 62个标准时 + 03:00夏令时。
        self.assertEqual(len(data["排除情景"]), 60)
        with self.assertRaisesRegex(ValueError, "没有有效"):
            compare_output(BirthInput(1988, 4, 17, 2, 30, dst_adjust=True), None, True, 8, (), "未知")

    def test_早期历史提示不能当全国规则(self):
        chart = build_chart(BirthInput(1940, 6, 1, 12, 0))
        self.assertTrue(any("不能推广为全国" in w.message for w in chart.warnings))


class TestStructureEvidence(unittest.TestCase):
    def check_item(self, pillars, name):
        return next(c for c in analyze_patterns(chart_of(*pillars))["结构条件检查"] if c["名称"] == name)

    def test_三类正例只证明同见并保留必要条件(self):
        cases = (("官印相生", ("壬子", "辛酉", "甲寅", "乙卯")),
                 ("食伤生财", ("丙午", "戊戌", "甲寅", "乙卯")),
                 ("食神制杀", ("丙午", "庚申", "甲寅", "乙卯")))
        for name, pillars in cases:
            with self.subTest(name=name):
                item = self.check_item(pillars, name)
                self.assertEqual(item["条件检查"][0]["状态"], "满足")
                self.assertEqual(item["条件检查"][2]["状态"], "满足")
                self.assertTrue(item["必要条件未完成"])
                self.assertEqual(item["状态"], "候选线索，未判成格")

    def test_三类缺一侧反例(self):
        for name, pillars in (("官印相生", ("壬子", "癸亥", "甲寅", "乙卯")),
                              ("食伤生财", ("丙午", "丁巳", "甲寅", "乙卯")),
                              ("食神制杀", ("庚申", "辛酉", "甲寅", "乙卯"))):
            with self.subTest(name=name):
                self.assertEqual(self.check_item(pillars, name)["条件检查"][0]["状态"], "不满足")

    def test_三类同见无根不能升级成立(self):
        for name, pillars in (("官印相生", ("辛卯", "壬午", "甲寅", "乙卯")),
                              ("食伤生财", ("丙子", "戊申", "甲子", "乙卯")),
                              ("食神制杀", ("丙子", "庚子", "甲寅", "乙卯"))):
            with self.subTest(name=name):
                item = self.check_item(pillars, name)
                self.assertEqual(item["条件检查"][0]["状态"], "满足")
                self.assertEqual(item["条件检查"][2]["状态"], "不满足")
                self.assertTrue(any(c["状态"] == "未评估" for c in item["条件检查"]))

    def test_异性同五行根与同干根不同(self):
        facts = structure_facts(chart_of("乙卯", "丁卯", "甲子", "己卯"))
        self.assertEqual(facts["日主根"]["同干根"], [])
        self.assertEqual(len(facts["日主根"]["同五行根"]), 3)
        self.assertEqual({r["藏干"] for r in facts["日主根"]["同五行根"]}, {"乙"})

    def test_干扰线索不自动破格(self):
        item = self.check_item(("丙午", "庚申", "甲寅", "壬子"), "食神制杀")
        self.assertEqual(item["条件检查"][3]["状态"], "不满足")
        self.assertTrue(item["必要条件未完成"])

    def test_保留旧评分及新增事实JSONMarkdown(self):
        chart = build_chart(BirthInput(1990, 6, 15, 14, 30))
        payload = json.loads(to_json(chart, None, (), (), "未知"))
        self.assertEqual(payload["强弱启发式"]["总分"], round(chart.strength.total, 2))
        self.assertIn("结构事实", payload["传统结构"])
        self.assertIn("校准来源", payload)
        markdown = to_markdown(chart, None, (), (), "未知")
        self.assertIn("同五行根", markdown)
        self.assertIn("未评估", markdown)


class TestClassicsAndReading(unittest.TestCase):
    def setUp(self):
        self.chart = json.loads(to_json(build_chart(BirthInput(1990, 6, 15, 14, 30)), None, (), (), "未知"))
        self.claim = {"类别": "结构线索", "文本": "月令候选，必要条件尚未评估",
                      "字段": ["/传统结构/格局候选/0"], "规则编号": ["ZP-MONTH-01"]}

    def test_五本目录及原文解释分层(self):
        self.assertEqual(len(catalog()["典籍"]), 5)
        for rule in catalog()["规则"]:
            self.assertTrue(rule["原文摘录"])
            self.assertIn("后人注文", rule)
            self.assertTrue(rule["校对状态"])

    def test_调候全干支可查缺条目不补用神(self):
        from bazi.constants import STEMS, BRANCHES
        for stem in STEMS:
            for branch in BRANCHES:
                result = climate_reference(stem, branch)
                self.assertTrue(result["检索章节"])
                self.assertNotIn("用神", result)
        self.assertEqual(climate_reference("甲", "子")["节月序号"], 11)
        self.assertTrue(climate_reference("甲", "寅")["匹配摘录"])
        self.assertFalse(climate_reference("乙", "寅")["匹配摘录"])

    def test_有效字段和规则通过(self):
        self.assertEqual(validate_reading(self.chart, [self.claim]), [])

    def test_成格合化用神越界均拒绝(self):
        for kind in ("成格", "合化", "用神"):
            claim = dict(self.claim, 类别=kind)
            self.assertTrue(validate_reading(self.chart, [claim]))

    def test_伪造字段规则和仅评分解释被拒绝(self):
        for change in ({"字段": ["/未计算用神"]}, {"规则编号": ["fake"]},
                       {"字段": ["/强弱启发式/总分"]}):
            self.assertTrue(validate_reading(self.chart, [dict(self.claim, **change)]))

    def test_候选解释须有归属(self):
        payload = {"模式": "候选盘比较", "候选": [{"代表排盘": self.chart}]}
        self.assertTrue(validate_reading(payload, [self.claim]))
        self.assertFalse(validate_reading(payload, [dict(self.claim, 候选编号=1)]))
        self.assertTrue(validate_reading(payload, [dict(self.claim, 候选编号=2)]))


if __name__ == "__main__":
    unittest.main()
