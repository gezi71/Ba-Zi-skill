"""
天文层回归测试。

命名 convention（沿用参考项目 ziwei-doushu 的做法）：**测试名就是它要守住的那个场景**，
而不是「test_something」。这样半年后有人改坏了代码，能从测试名直接读出「我破坏了什么」。
"""

import math
import unittest
from datetime import date, datetime, timedelta

from bazi import astro


class TestJulianDay(unittest.TestCase):
    """儒略日换算必须可逆 —— 后面的日柱公式完全建立在这上面。"""

    def test_j2000锚点(self):
        self.assertAlmostEqual(astro.gregorian_to_jd(2000, 1, 1, 0.5), 2451545.0, places=9)

    def test_格里高利历与儒略日往返一致(self):
        for y, m, d in ((1900, 1, 1), (1999, 12, 31), (2000, 2, 29), (2024, 6, 15), (2100, 3, 1)):
            for frac in (0.0, 0.5, 0.75):
                jd = astro.gregorian_to_jd(y, m, d, frac)
                back = astro.jd_to_datetime(jd)
                self.assertEqual((back.year, back.month, back.day), (y, m, d))
                got_frac = (back - datetime(y, m, d)).total_seconds() / 86400.0
                self.assertAlmostEqual(got_frac, frac, places=9)

    def test_非法日期被拦下(self):
        self.assertFalse(astro.is_valid_gregorian_date(2023, 2, 29))
        self.assertFalse(astro.is_valid_gregorian_date(2024, 13, 1))
        self.assertTrue(astro.is_valid_gregorian_date(2024, 2, 29))


class TestSolarLongitude(unittest.TestCase):
    def test_Meeus教材例题25a逐位一致(self):
        """《天文算法》例 25.a：1992-10-13 00:00 TD，视黄经标准答案 199.90894°

        这条测试是「防转录错误」的最后一道防线：只要什么改动破坏了公式，
        这条会第一个红。它不能证明算法足够准，只能证明实现忠实。
        """
        lam = astro.sun_apparent_longitude(2448908.5)
        self.assertAlmostEqual(lam, 199.90894, places=4)

    def test_太阳黄经全年单调且不回绕出错(self):
        prev = astro.sun_apparent_longitude(astro.gregorian_to_jd(2024, 1, 1))
        for i in range(1, 366):
            cur = astro.sun_apparent_longitude(astro.gregorian_to_jd(2024, 1, 1) + i)
            diff = astro._angle_diff(cur, prev)
            self.assertTrue(0 < diff < 1.2, f"第 {i} 天黄经增量异常：{diff}")
            prev = cur


class TestDeltaT(unittest.TestCase):
    def test_二十世纪各年代的已知取值(self):
        """各年代的 ΔT 是公开的标准值，用来锁住插值表不被人顺手改坏。"""
        for year, expect in ((1900, -2.72), (1960, 33.15), (2000, 63.83), (2020, 69.36)):
            self.assertAlmostEqual(astro.delta_t_seconds(year), expect, places=2,
                                   msg=f"{year} 年 ΔT 不符")

    def test_表外年份退化但不崩(self):
        for y in (1500.0, 2200.0):
            self.assertTrue(math.isfinite(astro.delta_t_seconds(y)))


class TestEquationOfTime(unittest.TestCase):
    def test_整年落在合理区间(self):
        """均时差全年应在 ±17 分钟以内 —— 超出这个范围说明均时差公式出问题了。"""
        for i in range(0, 366, 5):
            d = datetime(2024, 1, 1, 12) + timedelta(days=i)
            eot = astro.equation_of_time_minutes(d)
            self.assertTrue(-17 <= eot <= 17, f"{d.date()} 均时差 {eot} 超出物理范围")


class TestTrueSolarTime(unittest.TestCase):
    def test_缺省不做半吊子校正(self):
        """★ 经度未给时必须**完全**不动时间。

        半吊子校正比不校正更危险：它给人「已经修正过了」的错觉。
        """
        solar = astro.to_true_solar_time(datetime(1990, 6, 15, 12, 30), None, 8.0)
        self.assertEqual(solar.longitude_minutes, 0.0)
        self.assertEqual(solar.equation_minutes, 0.0)
        self.assertEqual(solar.hour, 12)
        self.assertEqual(solar.minute, 30)

    def test_北京校正量与参考实现口径等价(self):
        """(116.4-120)×4 = -14.4 分钟经度修正，加均时差即为总修正量。"""
        solar = astro.to_true_solar_time(datetime(1990, 6, 15, 12, 30), 116.4, 8.0)
        self.assertAlmostEqual(solar.longitude_minutes, (116.4 - 120) * 4, places=6)

    def test_拉萨与北京时间差接近两小时(self):
        """西藏出生的极端例子：这是「必须做真太阳时校正」的最好论据。"""
        a = astro.to_true_solar_time(datetime(1990, 6, 15, 12, 0), 91.11, 8.0)   # 拉萨
        b = astro.to_true_solar_time(datetime(1990, 6, 15, 12, 0), 120.0, 8.0)   # 东经120
        gap = (b.solar_local - a.solar_local).total_seconds() / 60
        self.assertGreater(gap, 110, "拉萨与标准时的差距应接近两小时")

    def test_时辰判定边界(self):
        self.assertEqual(astro.branch_from_solar_minutes(0), 0)        # 00:00 子
        self.assertEqual(astro.branch_from_solar_minutes(59), 0)
        self.assertEqual(astro.branch_from_solar_minutes(60), 1)       # 01:00 丑
        self.assertEqual(astro.branch_from_solar_minutes(1379), 11)    # 22:59 亥
        self.assertEqual(astro.branch_from_solar_minutes(1380), 0)     # 23:00 子


class TestChinaDST(unittest.TestCase):
    def test_夏令时区间包含边界日(self):
        self.assertIsNotNone(astro.china_dst_range(date(1988, 4, 10)))   # 起始当天
        self.assertIsNotNone(astro.china_dst_range(date(1988, 9, 11)))   # 结束当天
        self.assertIsNotNone(astro.china_dst_range(date(1988, 7, 1)))

    def test_夏令时区间之外返回None(self):
        self.assertIsNone(astro.china_dst_range(date(1988, 4, 9)))
        self.assertIsNone(astro.china_dst_range(date(1988, 9, 12)))
        self.assertIsNone(astro.china_dst_range(date(2020, 7, 1)))


class TestSolarTerms(unittest.TestCase):
    def test_一年恰好二十四个节气且节中相间(self):
        terms = [t for t in astro.terms_for_year(2024) if t.utc.year == 2024]
        names = [t.name for t in terms]
        self.assertEqual(len(names), 24)
        self.assertEqual(names[0], "小寒")
        self.assertEqual(names[-1], "冬至")
        majors = [t for t in terms if t.is_major]
        self.assertEqual(len(majors), 12)

    def test_节书次序相邻间隔约十五天(self):
        terms = sorted(astro.terms_for_year(2024), key=lambda t: t.jd_tt)
        for a, b in zip(terms, terms[1:]):
            gap = (b.utc - a.utc).total_seconds() / 86400.0
            self.assertTrue(14.5 < gap < 15.8, f"{a.name}->{b.name} 间隔 {gap:.2f} 天异常")

    def test_节气窗口覆盖年初年尾(self):
        """出生在 1 月初或 12 月底的人仍能取到前后相邻的节。"""
        for y, m, d in ((2024, 1, 2), (2024, 12, 30)):
            terms = astro.terms_covering(y, m, d)
            prev_term, next_term = astro.find_surrounding_major_terms(datetime(y, m, d), terms)
            self.assertIsNotNone(prev_term, f"{y}-{m}-{d} 缺上一个节")
            self.assertIsNotNone(next_term, f"{y}-{m}-{d} 缺下一个节")


if __name__ == "__main__":
    unittest.main()
