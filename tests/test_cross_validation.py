"""
外部交叉校验 —— 冻结的期望值。

这 40 个用例不是本项目自己说对的，而是拿一个**完全独立的实现**对着拍出来的：

    工具：lunar-javascript（Node）的 `Lunar.fromSolar(...).getEightChar()`
    方法：随机生成 40 个日期（1940–2035，覆盖全部月份与多数时辰），两个引擎各自排盘，
          逐项比对；晚子时（23:00 后）由本文件下半部分的专项用例另行覆盖
    结果：完全一致 40 / 40

为什么值得固化：八字排盘的绝大部分风险来自「四柱排错了但看不出来」。
两套语言不同、算法不同（那边查表，这边算天文）的实现得出同一答案，
比任何内部断言都更有说服力。

★ 注意：这些用例**不能**保证所有边界都对 —— 随机采样几乎采不到
「出生在交节时刻前后十几分钟内」的人。那类情况由
`TestFourPillarsCrossValidated` 里的立春用例与边界告警机制负责。

新增/改动本文件的数据前，请先重新打印一遍对照值，并记录做到了什么：
    node 脚本产出：参考 CONTRIBUTING.md §三
"""

import unittest

from bazi import BirthInput, build_chart

# (年, 月, 日, 时, 分, "年/月/日/时")
CROSS_VALIDATED_CASES = tuple(
    (int(a), int(b_), int(c), int(d_), int(e), f)
    for a, b_, c, d_, e, f in [
    (1981, 3, 13, 20, 0, "辛酉/辛卯/庚寅/丙戌"),
    (1949, 9, 4, 11, 0, "己丑/壬申/丁酉/丙午"),
    (2004, 4, 2, 2, 45, "甲申/丁卯/辛亥/己丑"),
    (1993, 2, 8, 2, 45, "癸酉/甲寅/庚申/丁丑"),
    (1947, 10, 4, 7, 0, "丁亥/己酉/丙辰/壬辰"),
    (2013, 10, 13, 1, 15, "癸巳/壬戌/壬子/辛丑"),
    (1945, 9, 28, 4, 30, "乙酉/乙酉/庚子/戊寅"),
    (1993, 3, 18, 3, 30, "癸酉/乙卯/戊戌/甲寅"),
    (2011, 11, 6, 3, 15, "辛卯/戊戌/乙丑/戊寅"),
    (1987, 2, 18, 22, 0, "丁卯/壬寅/戊戌/癸亥"),
    (2012, 1, 20, 6, 45, "辛卯/辛丑/庚辰/己卯"),
    (2027, 9, 14, 10, 45, "丁未/己酉/丙申/癸巳"),
    (2014, 8, 12, 9, 15, "甲午/壬申/乙卯/辛巳"),
    (1963, 12, 25, 7, 0, "癸卯/甲子/壬寅/甲辰"),
    (2013, 5, 17, 15, 30, "癸巳/丁巳/癸未/庚申"),
    (2033, 8, 10, 19, 0, "癸丑/庚申/癸巳/壬戌"),
    (1955, 9, 14, 5, 30, "乙未/乙酉/戊寅/乙卯"),
    (1959, 8, 14, 1, 0, "己亥/壬申/戊辰/癸丑"),
    (2011, 10, 26, 10, 30, "辛卯/戊戌/甲寅/己巳"),
    (2028, 6, 20, 15, 45, "戊申/戊午/丙子/丙申"),
    (1948, 2, 9, 15, 0, "戊子/甲寅/甲子/壬申"),
    (1947, 12, 23, 9, 45, "丁亥/壬子/丙子/癸巳"),
    (1976, 12, 13, 21, 30, "丙辰/庚子/己亥/乙亥"),
    (1942, 8, 12, 5, 0, "壬午/戊申/丁酉/癸卯"),
    (2003, 1, 7, 9, 15, "壬午/癸丑/庚辰/辛巳"),
    (2034, 4, 13, 12, 45, "甲寅/戊辰/己亥/庚午"),
    (1950, 3, 15, 12, 30, "庚寅/己卯/己酉/庚午"),
    (1957, 7, 28, 17, 30, "丁酉/丁未/辛丑/丁酉"),
    (2030, 7, 12, 21, 45, "庚戌/癸未/戊申/癸亥"),
    (1969, 3, 3, 5, 15, "己酉/丙寅/丁丑/癸卯"),
    (1969, 11, 8, 0, 45, "己酉/乙亥/丁亥/庚子"),
    (2015, 3, 9, 9, 0, "乙未/己卯/甲申/己巳"),
    (1958, 7, 18, 11, 30, "戊戌/己未/丙申/甲午"),
    (1956, 12, 28, 16, 0, "丙申/庚子/己巳/壬申"),
    (1998, 11, 26, 17, 45, "戊寅/癸亥/丁丑/己酉"),
    (1990, 7, 13, 3, 45, "庚午/癸未/己卯/丙寅"),
    (2021, 7, 2, 6, 0, "辛丑/甲午/辛亥/辛卯"),
    (1966, 8, 6, 3, 30, "丙午/乙未/丁酉/壬寅"),
    (2016, 1, 4, 0, 15, "乙未/戊子/乙酉/丙子"),
    (2008, 2, 12, 19, 0, "戊子/甲寅/壬午/庚戌"),
    ]
)


# ── 晚子时专项 ───────────────────────────────────────────────
# 23:00 之后出生的人，日柱取当日还是次日，各家不一样。随机采样几乎采不到，
# 所以这里单独列一组，并且**按流派分别锁定**。
#
# ★ 这条代表了一次真实的发现（2026-10-05）：
#   lunar-javascript 在 23:00 之后走的是「日柱当日 + 时干按次日」，
#   也就是本项目的 `day-cur-time-next`；而参考项目 ziwei-doushu 的默认则是 `next-day`。
#   两家都是合理的流派，谁也不算错 —— 所以本项目保留自己的默认值，
#   但把这个分歧写进 `references/decisions.md`，并且两边的结果都锁下来。
LATE_ZISHI_EXPECTED_UNDER_DCTN = (   # day-cur-time-next，与 lunar-javascript 一致
    (1990, 6, 15, 23, 30, "庚午/壬午/辛亥/庚子"),
    (1988, 11, 3, 23, 5, "戊辰/壬戌/壬戌/壬子"),
    (2001, 1, 27, 23, 55, "庚辰/己丑/庚寅/戊子"),
    (1972, 9, 9, 23, 15, "壬子/己酉/癸卯/甲子"),
    (2020, 5, 5, 23, 45, "庚子/辛巳/戊申/甲子"),
)
# 同一批日期在 next-day 下的结果：日柱 +1，时柱天干同步变化。
LATE_ZISHI_EXPECTED_UNDER_NEXT_DAY = (
    (1990, 6, 15, 23, 30, "庚午/壬午/壬子/庚子"),
    (1988, 11, 3, 23, 5, "戊辰/壬戌/癸亥/壬子"),
    (2001, 1, 27, 23, 55, "庚辰/己丑/辛卯/戊子"),
    (1972, 9, 9, 23, 15, "壬子/己酉/甲辰/甲子"),
    (2020, 5, 5, 23, 45, "庚子/辛巳/己酉/甲子"),
)


class TestLateZishiDivergence(unittest.TestCase):
    """晚子时的流派分歧：两个流派都必须给得出来，且各自内部自洽。"""

    def test_day_cur_time_next与lunar_javascript一致(self):
        for y, m, d, hh, mm, expected in LATE_ZISHI_EXPECTED_UNDER_DCTN:
            chart = build_chart(BirthInput(y, m, d, hh, mm, gender="male",
                                           late_zishi_rule="day-cur-time-next"))
            got = "/".join(chart.pillars[k].ganzhi for k in ("year", "month", "day", "hour"))
            self.assertEqual(got, expected, f"{y}-{m:02d}-{d:02d} {hh:02d}:{mm:02d}")

    def test_next_day流派下日柱前进一步(self):
        for y, m, d, hh, mm, expected in LATE_ZISHI_EXPECTED_UNDER_NEXT_DAY:
            chart = build_chart(BirthInput(y, m, d, hh, mm, gender="male",
                                           late_zishi_rule="next-day"))
            got = "/".join(chart.pillars[k].ganzhi for k in ("year", "month", "day", "hour"))
            self.assertEqual(got, expected, f"{y}-{m:02d}-{d:02d} {hh:02d}:{mm:02d}")

    def test_两流派只在日柱上分歧_其余三柱相同(self):
        """年、月、时三柱不因晚子时流派而变 —— 变的只有日柱这一点。"""
        for y, m, d, hh, mm, _ in LATE_ZISHI_EXPECTED_UNDER_DCTN:
            a = build_chart(BirthInput(y, m, d, hh, mm, gender="male",
                                       late_zishi_rule="day-cur-time-next"))
            b = build_chart(BirthInput(y, m, d, hh, mm, gender="male",
                                       late_zishi_rule="next-day"))
            for key in ("year", "month", "hour"):
                self.assertEqual(a.pillars[key].ganzhi, b.pillars[key].ganzhi,
                                 f"{key} 柱不应因晚子时流派而变")


class TestAgainstExternalImplementation(unittest.TestCase):
    """对拍外部实现。任何一条失败都意味着排盘出现实质性回退，优先于其他所有 bug 排查。"""

    def test_全部冻结用例与对拍结果一致(self):
        failures = []
        for y, m, d, hh, mm, expected in CROSS_VALIDATED_CASES:
            chart = build_chart(BirthInput(y, m, d, hh, mm, gender="male"))
            got = "/".join(chart.pillars[k].ganzhi for k in ("year", "month", "day", "hour"))
            if got != expected:
                failures.append(f"{y:04d}-{m:02d}-{d:02d} {hh:02d}:{mm:02d} 得到 {got}，期望 {expected}")
        self.assertEqual(
            len(failures), 0,
            f"{len(failures)} / {len(CROSS_VALIDATED_CASES)} 个用例与外部实现对不上：\n"
            + "\n".join(failures),
        )

    def test_冻结用例数量不被悄悄删减(self):
        """防止将来有人「优化」测试用例表，把用例删掉假装通过。"""
        self.assertGreaterEqual(len(CROSS_VALIDATED_CASES), 40,
                                "随机采样的冻结样本不应少于 40 条")


if __name__ == "__main__":
    unittest.main()
