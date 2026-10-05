"""
bazi —— 零依赖的八字排盘引擎。

对外只需要两件事：
    from bazi import BirthInput, build_chart
    chart = build_chart(BirthInput(1990, 6, 15, 12, 30, gender="male", longitude=116.4))

模块分工：
    astro     天文层 —— 节气时刻、真太阳时、ΔT、夏令时
    cities    出生地经度表（区县粒度）
    constants 全部口诀与规则表（藏干、纳音、神煞、长生…）
    chart     四柱排盘
    dayun     大运与流年

Python 标准库即可运行，无第三方依赖。
"""

from .chart import (
    BirthInput, BoundaryWarning, Chart, Pillar, ShenShaHit, StrengthBreakdown,
    HiddenStemInfo, LATE_ZISHI_RULES, DEFAULT_LATE_ZISHI_RULE,
    build_chart, hour_stem_from_day, month_stem_from_year, evaluate_strength,
    month_power_of,
)
from .dayun import DaYun, LiuNian, QiYunInfo, compute_dayun, compute_liunian, is_yang_year
from .constants import (
    STEMS, BRANCHES, make_ganzhi, shi_shen_of, chang_sheng_of, xun_kong_of,
    nayin_of, hidden_stems_of,
)

__version__ = "0.1.0"
__all__ = [
    "BirthInput", "Chart", "Pillar", "ShenShaHit", "StrengthBreakdown",
    "BoundaryWarning", "HiddenStemInfo", "build_chart", "compute_dayun", "compute_liunian",
    "DaYun", "LiuNian", "QiYunInfo", "is_yang_year", "evaluate_strength",
    "make_ganzhi", "shi_shen_of", "chang_sheng_of", "xun_kong_of", "nayin_of",
    "hidden_stems_of", "month_power_of", "month_stem_from_year", "hour_stem_from_day",
    "LATE_ZISHI_RULES", "DEFAULT_LATE_ZISHI_RULE", "STEMS", "BRANCHES", "__version__",
]
