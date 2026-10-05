"""
大运与流年。

大运是八字里唯一「随时间流动」的部分，也是最容易排错的部分 ——
因为它的起点不是生日，而是「出生那一刻到最近一个节的距离」按
**三日为一岁、一日为四月、一个时辰为十天**折算出来的一个将来的日期。

★ 这条折算规则（而不是「生日当天起运」）是本模块最容易被人质疑、
也最经常被其他库实现错的地方。它意味着：
    · 距离下一个节差 3 天出生的人，1 岁起到 11 岁走的是第 1 步大运；
    · 距离差 15 天的人要到 5 岁才起运，前 5 年尚未进入第一步大运（本模块不计算小运/童限）；

方向规则也要说清楚：
    阳年男 / 阴年女 → 顺行（往时间后方的那个节数）
    阴年男 / 阳年女 → 逆行（往时间前方的那个节数）
「阳年」指年干为甲丙戊庚壬。性别未知时无法起运，返回空并说明原因。
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from typing import List, Optional, Sequence, Tuple

from . import astro
from .astro import TermMoment
from .chart import Chart
from .constants import STEMS, BRANCHES, make_ganzhi, shi_shen_of


@dataclass
class DaYun:
    index: int                 # 第几步（从 1 开始）
    ganzhi: str
    stem: int
    branch: int
    start_age: int
    end_age: int
    start_date: Optional[date]
    end_date: Optional[date]
    shi_shen: str              # 大运天干相对日主的十神
    nayin: str = ""


@dataclass
class QiYunInfo:
    direction: str                      # '顺行' | '逆行'
    reference_term: str                 # 参与折算的那个节
    reference_term_time: datetime       # 该节时刻（+8 时区展示）
    gap_days: float
    gap_hours: float
    years: int
    months: int
    days: int
    qiyun_date: Optional[date]
    summary: str


@dataclass
class LiuNian:
    year: int
    ganzhi: str
    stem: int
    branch: int
    shi_shen: str
    age: Optional[int]
    chang_sheng: str = ""


# 折算常量：三日起一岁、一日为四月、一个时辰（两小时）为十天。
HOURS_PER_YEAR_EQUIV = 72.0    # 3 天
HOURS_PER_MONTH_EQUIV = 6.0    # 1 天的 1/4 → 6 小时为一「月」
DAYS_PER_HALF_HOUR = 5.0       # 1 小时 = 5 天


def _add_years_months_days(d: date, years: int, months: int, days: int) -> date:
    """日期加「年/月/日」三段增量，负责处理月末溢出（1/31 加一个月要落到 2/28）。"""
    total_months = d.month - 1 + months
    y = d.year + years + total_months // 12
    m = total_months % 12 + 1
    dd = min(d.day, calendar.monthrange(y, m)[1])
    return date(y, m, dd) + timedelta(days=days)


def is_yang_year(year_stem: int) -> bool:
    """年干是否属阳（甲丙戊庚壬）。"""
    return year_stem % 2 == 0


def compute_dayun(chart: Chart, count: int = 8) -> Tuple[QiYunInfo, Tuple[DaYun, ...]]:
    """起大运。性别未知时第二步/后续全部无法计算，返回空结果并说明。"""
    birth = chart.birth
    gender = birth.gender
    year_stem = chart.pillars["year"].stem
    yang_year = is_yang_year(year_stem)

    if gender not in ("male", "female"):
        raise ValueError("排大运需要知道性别：阳男阴女顺行、阴男阳女逆行，性别未知无法定方向")

    forward = (yang_year and gender == "male") or ((not yang_year) and gender == "female")

    # 顺行看之后的节，逆行看之前的节
    term_used: Optional[TermMoment] = chart.next_term if forward else chart.prev_term
    if term_used is None:
        raise ValueError("找不到用于起运的「节」")

    delta = (term_used.utc - chart.solar.moment_utc).total_seconds() if forward \
        else (chart.solar.moment_utc - term_used.utc).total_seconds()
    if delta < 0:
        delta = abs(delta)

    total_hours = delta / 3600.0
    years = int(total_hours // HOURS_PER_YEAR_EQUIV)
    remainder = total_hours - years * HOURS_PER_YEAR_EQUIV
    months = int(remainder // HOURS_PER_MONTH_EQUIV)
    remainder -= months * HOURS_PER_MONTH_EQUIV
    days = int(remainder * DAYS_PER_HALF_HOUR)

    birth_date = date(birth.year, birth.month, birth.day)
    qiyun_date = _add_years_months_days(birth_date, years, months, days)

    direction = "顺行" if forward else "逆行"
    ymd_desc = f"{years} 年 {months} 个月 {days} 天"
    summary = (
        f"出生{direction}，距「{term_used.name}」{total_hours/24:.4f} 天，"
        f"按三日为一岁折算，{ymd_desc}后起运（约 {qiyun_date}）。"
    )
    info = QiYunInfo(
        direction=direction,
        reference_term=term_used.name,
        reference_term_time=term_used.utc + timedelta(hours=8),
        gap_days=total_hours / 24.0,
        gap_hours=total_hours,
        years=years, months=months, days=days,
        qiyun_date=qiyun_date,
        summary=summary,
    )

    day_stem = chart.day_master_stem
    start_index = chart.pillars["month"].index60
    results: List[DaYun] = []
    for step in range(1, count + 1):
        idx = (start_index + step) % 60 if forward else (start_index - step) % 60
        stem, branch = idx % 10, idx % 12
        s_age = years + (step - 1) * 10
        e_age = s_age + 10
        s_date = _add_years_months_days(qiyun_date, (step - 1) * 10, 0, 0)
        e_date = _add_years_months_days(qiyun_date, step * 10, 0, 0)
        results.append(DaYun(
            index=step,
            ganzhi=make_ganzhi(idx),
            stem=stem, branch=branch,
            start_age=s_age, end_age=e_age,
            start_date=s_date, end_date=e_date,
            shi_shen=shi_shen_of(day_stem, stem),
        ))
    return info, tuple(results)


def compute_liunian(chart: Chart, years: Sequence[int]) -> Tuple[LiuNian, ...]:
    """流年干支。取 `(公历年 - 4) % 60`，并提示切换点在立春。

    严格按节气切分流年的话，同一公历年的 1-2 月属于上一年干支；
    这里是「整年」口径，也是命理界排流年表的通行做法。
    """
    day_stem = chart.day_master_stem
    birth_year = chart.birth.year
    out: List[LiuNian] = []
    for y in years:
        idx = (y - 4) % 60
        stem, branch = idx % 10, idx % 12
        out.append(LiuNian(
            year=y,
            ganzhi=make_ganzhi(idx),
            stem=stem, branch=branch,
            shi_shen=shi_shen_of(day_stem, stem),
            age=y - birth_year,
        ))
    return tuple(out)
