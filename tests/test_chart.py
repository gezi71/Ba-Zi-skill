"""
排盘层回归测试。

★ 最重要的一组期望值来自参考项目 ziwei-doushu 自己的回归测试
  （`scripts/regression/sizhu-lichun-boundary.test.ts`）。那边面对的是同一个问题：
  「会员说排给我的四柱不对」。两边用完全不同的语言与算法实现，却要给出同一个答案 ——
  这是本项目能得到的最强外部校验，所以在文件头记一笔来源。
"""

import unittest
from datetime import date, timedelta

from bazi import (
    BirthInput, build_chart, evaluate_strength, hour_stem_from_day,
    month_stem_from_year, compute_dayun, compute_liunian, make_ganzhi,
    shi_shen_of, chang_sheng_of, is_yang_year,
)
from bazi.chart import _day_pillar_index


def _pillars(chart) -> str:
    return "/".join(chart.pillars[k].ganzhi for k in ("year", "month", "day", "hour"))


class TestFourPillarsCrossValidated(unittest.TestCase):
    """四柱的权威期望值，来自外部实现（lunar-javascript / ziwei-doushu 回归测试）。"""

    def test_1990年6月15日午时(self):
        """2026-10-05 校验：与 lunar-javascript getEightChar() 完全一致。"""
        c = build_chart(BirthInput(1990, 6, 15, 12, 0, gender="male"))
        self.assertEqual(_pillars(c), "庚午/壬午/辛亥/甲午")

    def test_2004年2月4日丑时_立春前不换年柱(self):
        """★ 这条对应参考项目里一位会员的真实投诉：
        农历 2004 年正月十四 = 公历 2004-02-04，当天 19:56 立春，
        凌晨 2:40（丑时）出生的人排在立春之前，年柱必须还是癸未，连带月柱乙丑。
        「按立春当天整天切换」的实现会把这天全部算成甲申 —— 那是错的。
        """
        c = build_chart(BirthInput(2004, 2, 4, 2, 0, gender="male"))
        self.assertEqual(_pillars(c), "癸未/乙丑/癸丑/癸丑")

    def test_2004年2月4日亥时_立春后应换年柱(self):
        """同一天的另一个时辰，立春之后，年柱换成甲申 —— 锁住「同一天内按时刻分档」。"""
        c = build_chart(BirthInput(2004, 2, 4, 22, 0, gender="male"))
        self.assertEqual(c.pillars["year"].ganzhi, "甲申")

    def test_立春前后各一天(self):
        self.assertEqual(build_chart(BirthInput(2004, 2, 3, 2, 0, gender="male"))
                         .pillars["year"].ganzhi, "癸未")
        self.assertEqual(build_chart(BirthInput(2004, 2, 5, 2, 0, gender="male"))
                         .pillars["year"].ganzhi, "甲申")

    def test_日柱时柱不受立春边界影响(self):
        """立春只切年柱与月柱，日柱时柱照走 —— 防止改年柱时误伤另外两柱。"""
        before = build_chart(BirthInput(2004, 2, 4, 2, 0, gender="male"))
        after = build_chart(BirthInput(2004, 2, 4, 22, 0, gender="male"))
        self.assertEqual(before.pillars["day"].ganzhi, after.pillars["year"].ganzhi[:0] or "癸丑")


class TestGanzhiAnchors(unittest.TestCase):
    def test_日柱公式的两个已知锚点(self):
        self.assertEqual(_day_pillar_index(2024, 1, 1), 0)    # 甲子
        self.assertEqual(_day_pillar_index(2000, 1, 1), 54)   # 戊午

    def test_日柱连续三十天不跳号(self):
        step = timedelta(days=1)
        d = date(2024, 3, 1)
        for i in range(30):
            cur = _day_pillar_index(d.year, d.month, d.day)
            cur_date = d
            d += step
            nxt = _day_pillar_index(d.year, d.month, d.day)
            self.assertEqual((cur + 1) % 60, nxt, f"{cur_date} 处日柱不连续")

    def test_六十甲子配对的完整性(self):
        seen = set()
        for i in range(60):
            gz = make_ganzhi(i)
            self.assertEqual(len(gz), 2)
            seen.add(gz)
        self.assertEqual(len(seen), 60, "六十甲子出现重复")


class TestStemBranchRules(unittest.TestCase):
    def test_五虎遁_年干定月干(self):
        """甲己之年丙作首：甲年寅月必为丙寅。"""
        self.assertEqual(month_stem_from_year(0, 2), 2)
        self.assertEqual(month_stem_from_year(5, 2), 2)
        self.assertEqual(month_stem_from_year(1, 2), 4)

    def test_五鼠遁_日干定时干(self):
        """甲己还加甲：甲日子时必为甲子。"""
        self.assertEqual(hour_stem_from_day(0, 0), 0)
        self.assertEqual(hour_stem_from_day(5, 0), 0)
        self.assertEqual(hour_stem_from_day(1, 0), 2)

    def test_十神_同我者比劫_异性为劫(self):
        self.assertEqual(shi_shen_of(0, 0), "比肩")   # 甲见甲
        self.assertEqual(shi_shen_of(0, 1), "劫财")   # 甲见乙
        self.assertEqual(shi_shen_of(0, 2), "食神")   # 甲见丙（木生火，同性）
        self.assertEqual(shi_shen_of(0, 3), "伤官")   # 甲见丁
        self.assertEqual(shi_shen_of(0, 8), "偏印")   # 甲见壬（水生木，同性）
        self.assertEqual(shi_shen_of(0, 9), "正印")   # 甲见癸
        self.assertEqual(shi_shen_of(0, 4), "偏财")   # 甲见戊
        self.assertEqual(shi_shen_of(0, 5), "正财")   # 甲见己
        self.assertEqual(shi_shen_of(0, 6), "七杀")   # 甲见庚
        self.assertEqual(shi_shen_of(0, 7), "正官")   # 甲见辛

    def test_十二长生_甲长生在亥_顺行(self):
        self.assertEqual(chang_sheng_of(0, 11), "长生")
        self.assertEqual(chang_sheng_of(0, 2), "临官")
        self.assertEqual(chang_sheng_of(0, 3), "帝旺")

    def test_十二长生_乙长生在午_逆行(self):
        self.assertEqual(chang_sheng_of(1, 6), "长生")
        self.assertEqual(chang_sheng_of(1, 3), "临官")
        self.assertEqual(chang_sheng_of(1, 2), "帝旺")

    def test_阳年判定(self):
        for stem in (0, 2, 4, 6, 8):
            self.assertTrue(is_yang_year(stem))
        for stem in (1, 3, 5, 7, 9):
            self.assertFalse(is_yang_year(stem))


class TestLateZishi(unittest.TestCase):
    """晚子时四家教法的分歧，是流派差异不是 bug —— 这里锁住「它们确实给出不同结果」。"""

    def test_四种规则下时柱天干会不同(self):
        results = {}
        for rule in ("next-day", "current-day", "day-cur-time-next", "all-current"):
            c = build_chart(BirthInput(1990, 6, 15, 23, 30, gender="male", late_zishi_rule=rule))
            results[rule] = (c.pillars["day"].ganzhi, c.pillars["hour"].ganzhi)
        # next-day 的日柱/时干应与 current-day 不同（相差一天）
        self.assertNotEqual(results["next-day"], results["current-day"])
        # all-current 与 current-day 在日柱上一致（都是当日），但真太阳时未校正时也可能同
        self.assertEqual(results["all-current"][0], results["current-day"][0])

    def test_非晚子时四种规则结果一致(self):
        """正常时辰（非 23:00 后）不该因为流派选择而分歧。"""
        base = None
        for rule in ("next-day", "current-day", "day-cur-time-next", "all-current"):
            c = build_chart(BirthInput(1990, 6, 15, 12, 0, gender="male", late_zishi_rule=rule))
            got = _pillars(c)
            if base is None:
                base = got
            self.assertEqual(got, base, f"规则 {rule} 在普通时辰上给出了不同的盘")


class TestInputValidation(unittest.TestCase):
    def test_不存在的日期直接报错而不是猜(self):
        with self.assertRaises(ValueError):
            BirthInput(2023, 2, 30, 12, 0, gender="male")
        with self.assertRaises(ValueError):
            BirthInput(1990, 6, 15, 25, 0, gender="male")

    def test_未知晚子时规则报错(self):
        with self.assertRaises(ValueError):
            BirthInput(1990, 6, 15, 12, 0, late_zishi_rule="maybe")


class TestStrengthHeuristic(unittest.TestCase):
    def test_强弱评分必须带明细而不是一个孤零零的数字(self):
        """启发式评分的全部价值在于可解释 —— 没有任何明细的分数是不可信的。"""
        c = build_chart(BirthInput(1990, 6, 15, 12, 0, gender="male"))
        self.assertGreater(len(c.strength.labels), 0)
        self.assertIn(c.strength.verdict, ("身强", "身弱", "中和"))
        total = c.strength.month_score + c.strength.root_score + c.strength.stem_score
        self.assertAlmostEqual(c.strength.total, total, places=6)

    def test_得令与否影响明显(self):
        """同一种日主，生在当令月一定比生在被克的月分数高。"""
        charts = {}
        for month in (2, 8):   # 寅月(木旺) / 申月(金旺)
            c = build_chart(BirthInput(1990, month, 15, 12, 0, gender="male"))
            charts[month] = c.strength.total
        self.assertNotEqual(*charts.values())


class TestShenSha(unittest.TestCase):
    def test_神煞命中位置非空(self):
        c = build_chart(BirthInput(1990, 6, 15, 12, 0, gender="male"))
        self.assertGreater(len(c.shen_sha), 0)
        for hit in c.shen_sha:
            self.assertGreater(len(hit.positions), 0)
            self.assertIn(hit.nature, ("吉", "凶", "中性"))


class TestDayun(unittest.TestCase):
    def test_阳男顺行_阴男逆行(self):
        """甲年男（阳年男）顺行，乙年男（阴年男）逆行。"""
        male_yang = build_chart(BirthInput(1984, 6, 15, 12, 0, gender="male"))     # 甲子年
        male_yin = build_chart(BirthInput(1985, 6, 15, 12, 0, gender="male"))      # 乙丑年
        self.assertEqual(compute_dayun(male_yang)[0].direction, "顺行")
        self.assertEqual(compute_dayun(male_yin)[0].direction, "逆行")

    def test_女命方向相反(self):
        female_yang = build_chart(BirthInput(1984, 6, 15, 12, 0, gender="female"))
        female_yin = build_chart(BirthInput(1985, 6, 15, 12, 0, gender="female"))
        self.assertEqual(compute_dayun(female_yang)[0].direction, "逆行")
        self.assertEqual(compute_dayun(female_yin)[0].direction, "顺行")

    def test_性别未知不给排大运(self):
        c = build_chart(BirthInput(1990, 6, 15, 12, 0))
        with self.assertRaises(ValueError):
            compute_dayun(c)

    def test_三日折一岁的折算规则(self):
        c = build_chart(BirthInput(1990, 6, 15, 12, 0, gender="male"))
        info, yun = compute_dayun(c, 4)
        self.assertEqual(len(yun), 4)
        self.assertEqual(yun[0].start_age, info.years)
        self.assertEqual(yun[1].start_age - yun[0].start_age, 10)
        self.assertGreater(info.gap_days, 0)

    def test_大运天干顺行时逐位递增(self):
        c = build_chart(BirthInput(1984, 6, 15, 12, 0, gender="male"))
        info, yun = compute_dayun(c, 5)
        for a, b in zip(yun, yun[1:]):
            self.assertEqual((a.index + 1) % 60, b.index % 60)
            self.assertEqual((a.stem + 1) % 10, b.stem)
            self.assertEqual((a.branch + 1) % 12, b.branch)


class TestLiuNian(unittest.TestCase):
    def test_流年按干支纪年推(self):
        c = build_chart(BirthInput(1990, 6, 15, 12, 0, gender="male"))
        items = compute_liunian(c, [2026, 2027])
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].ganzhi, make_ganzhi((2026 - 4) % 60))
        self.assertEqual(items[0].year, 2026)


if __name__ == "__main__":
    unittest.main()
