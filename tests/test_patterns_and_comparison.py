"""原文反例、分钟范围、中间时柱和结构化告警的回归。

辛寅甲丙兼透反例见《子平真诠·论用神变化》，来源见 references/patterns.md。
"""

import contextlib
import io
import json
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace

from bazi import BirthInput, astro, build_chart, compute_dayun, compute_liunian
from bazi.chart import _build_pillar
from bazi.cli import compare_output, main, to_json, to_markdown
from bazi.constants import ganzhi_index_from_pair, STEMS, BRANCHES
from bazi.patterns import analyze_patterns, branch_relations


def chart_of(*pillars):
    day_stem = STEMS.index(pillars[2][0])
    return SimpleNamespace(pillars={
        key: _build_pillar(key, ganzhi_index_from_pair(STEMS.index(gz[0]), BRANCHES.index(gz[1])), day_stem)
        for key, gz in zip(("year", "month", "day", "hour"), pillars)
    })


def run_cli(*args):
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        status = main(list(args))
    return status, stdout.getvalue(), stderr.getvalue()


class TestPatternEvidence(unittest.TestCase):
    def test_辛寅甲丙兼透不以一个候选排除另一个(self):
        result = analyze_patterns(chart_of("甲午", "丙寅", "辛酉", "壬辰"))
        candidates = {c["十神"]: c for c in result["格局候选"]}
        self.assertEqual(set(candidates), {"正财", "正官", "正印"})
        self.assertEqual(candidates["正财"]["不满足项"], [])
        self.assertEqual(candidates["正官"]["不满足项"], [])
        self.assertTrue(candidates["正印"]["不满足项"])
        self.assertTrue(all(c["状态"] == "候选，未判成格" for c in candidates.values()))

    def test_同五行不同干不算同一藏干透出(self):
        result = analyze_patterns(chart_of("乙未", "丙寅", "辛酉", "壬辰"))
        candidate = next(c for c in result["格局候选"] if c["十神"] == "正财")
        self.assertTrue(candidate["不满足项"])

    def test_月干伤官不误作午月月令伤官(self):
        chart = build_chart(BirthInput(1990, 6, 15, 14, 30))
        result = analyze_patterns(chart)
        self.assertEqual({c["十神"] for c in result["格局候选"]}, {"七杀", "偏印"})
        self.assertEqual(chart.pillars["month"].shi_shen, "伤官")

    def test_比劫月不得按普通八格直接定格(self):
        result = analyze_patterns(chart_of("丙午", "丙寅", "甲子", "戊辰"))
        self.assertTrue(any("月令本气为比劫" in s for s in result["未评估"]))

    def test_食杀同见仍输出未评估条件(self):
        result = analyze_patterns(chart_of("丙午", "庚寅", "甲子", "戊辰"))
        combo = next(c for c in result["十神组合线索"] if c["名称"] == "食神制杀同见线索")
        self.assertTrue(combo["未评估"])
        self.assertIn("不等于", combo["状态"])

    def test_合冲并存不自动解冲(self):
        relations = branch_relations(chart_of("甲子", "丙午", "己丑", "辛未"))
        self.assertTrue(any(r["地支"] == ["子", "午"] and r["关系"] == "六冲" for r in relations))
        self.assertTrue(any(r["地支"] == ["子", "丑"] and r["关系"] == "六合" for r in relations))

    def test_三合须三支齐全且外部关系保留来源(self):
        chart = chart_of("甲申", "丙子", "甲寅", "乙丑")
        self.assertFalse(any(r["关系"] == "三合支组" for r in branch_relations(chart)))
        hits = branch_relations(chart, (("2024流年甲辰", 4),))
        triples = [r for r in hits if r["关系"] == "三合支组"]
        self.assertEqual(len(triples), 1)
        self.assertIn("2024流年甲辰", triples[0]["位置"])
        self.assertTrue(all("2024流年甲辰" in r["位置"] for r in hits))


class TestCandidateComparison(unittest.TestCase):
    def test_范围不能只看两端而漏中间时柱(self):
        birth = BirthInput(2000, 1, 1, 13, 0)
        data = compare_output(birth, ((13, 0), (17, 0)), False, 8, (), "未校正")
        self.assertEqual(data["情景采样数"], 241)
        self.assertEqual({c["四柱"]["时柱"][1] for c in data["候选"]}, {"未", "申", "酉"})
        self.assertIn("时柱", data["变化四柱"])

    def test_跨午夜范围和未知性别(self):
        data = compare_output(BirthInput(2000, 1, 1, 23, 30), ((23, 30), (0, 30)), False, 8, (), "未校正")
        self.assertEqual(data["情景采样数"], 61)
        self.assertIn("2000-01-02", data["范围"][1])
        self.assertEqual(len(data["候选"]), 1)
        self.assertNotIn("大运", data["候选"][0]["代表排盘"])

    def test_相同四柱的夏令时情景仍保留起运日期变化(self):
        data = compare_output(BirthInput(1990, 6, 15, 14, 30, gender="male", longitude=116.4), None, True, 8, (), "北京")
        self.assertEqual(len(data["候选"]), 1)
        candidate = data["候选"][0]
        self.assertEqual({s["夏令时回拨"] for s in candidate["输入情景"]}, {False, True})
        self.assertNotEqual(*candidate["起运日期范围"])

    def test_交节情景改变参照而不改变出生读数(self):
        term = next(t for t in astro.terms_for_year(2024) if t.name == "立春")
        clock = term.utc + timedelta(hours=8)
        birth = BirthInput(clock.year, clock.month, clock.day, clock.hour, clock.minute)
        data = compare_output(birth, None, True, 8, (), "未校正")
        self.assertEqual(len(data["候选"]), 2)
        self.assertEqual(set(data["变化四柱"]), {"年柱", "月柱"})
        self.assertTrue(any(c["告警"] for c in data["候选"]))
        self.assertEqual({c["代表排盘"]["排盘条件"]["输入时间"] for c in data["候选"]}, {f"{clock.hour:02d}:{clock.minute:02d}"})


class TestOutputAndValidation(unittest.TestCase):
    def test_立春告警涵盖年柱月柱(self):
        t = next(t for t in astro.terms_for_year(2024) if t.name == "立春").utc + timedelta(hours=8)
        chart = build_chart(BirthInput(t.year, t.month, t.day, t.hour, t.minute))
        self.assertTrue(any(w.affected == "年柱、月柱" for w in chart.warnings))

    def test_JSON和Markdown都保留未回拨告警(self):
        chart = build_chart(BirthInput(1990, 6, 15, 14, 30))
        payload = json.loads(to_json(chart, None, (), (), "北京"))
        markdown = to_markdown(chart, None, (), (), "北京")
        self.assertTrue(payload["告警"])
        self.assertTrue(all(w in markdown for w in payload["告警"]))
        self.assertLess(markdown.index("⚠️"), markdown.index("## 一、排盘条件"))

    def test_流年年份差不冒充虚岁(self):
        chart = build_chart(BirthInput(2000, 1, 1, 12, 0))
        payload = json.loads(to_json(chart, None, (), compute_liunian(chart, (2000,)), "未校正"))
        self.assertEqual(payload["流年"][0]["年份差"], 0)
        self.assertNotIn("虚岁", payload["流年"][0])

    def test_海外回拨不再静默失效(self):
        status, _, error = run_cli("--date", "2024-06-15", "--time", "12:00", "--tz", "-5", "--dst-adjust")
        self.assertEqual(status, 2)
        self.assertIn("海外", error)

    def test_非法多段时间不再被截断(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exc:
            main(["--date", "2000-01-01", "--time", "12:30:garbage"])
        self.assertEqual(exc.exception.code, 2)

    def test_跨日太阳时偏移与日期一致(self):
        solar = astro.to_true_solar_time(datetime(2024, 1, 1, 0, 30), 90, 8)
        self.assertEqual(solar.solar_local.date().isoformat(), "2023-12-31")
        self.assertEqual(solar.day_offset, -1)

    def test_交运年保留两步运及日期(self):
        chart = build_chart(BirthInput(1990, 6, 15, 14, 30, gender="male", longitude=116.4))
        info, yun = compute_dayun(chart)
        data = json.loads(to_json(chart, info, yun, compute_liunian(chart, (2027,)), "北京"))
        self.assertEqual([d["大运"] for d in data["流年"][0]["大运叠加"]], ["乙酉", "丙戌"])
        self.assertEqual(data["流年"][0]["大运叠加"][0]["止于"], "2027-10-27")

    def test_时间范围CLI返回可解析比较结果(self):
        status, output, _ = run_cli("--date", "2000-01-01", "--time-range", "23:30-00:30", "--format", "json")
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(output)["情景采样数"], 61)


if __name__ == "__main__":
    unittest.main()
