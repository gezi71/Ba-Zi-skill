"""排盘引擎 —— 把出生时刻变成一整张八字盘。

设计取向：**这个模块只做确定性的计算与规则查表，不做任何吉凶判断。**
「命好命坏、该怎么断」交给上层拿着 `references/` 里的象义文档去组织语言。
这样分工的好处是：排盘结果可复现、可 diff、可被人拿着《渊海子平》逐条质疑。

一句话说清数据流：
    钟表时间 ──► 真太阳时 ──► 定 日/时 支 ──► 配四柱 ──► 查表出十神/神煞/长生
                        └──► 与节气时刻比较 ──► 定 年/月 柱

所有牵强的、派别之间有分歧的地方，都在 `references/decisions.md` 里列出来了。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Sequence, Tuple

from . import astro
from .astro import TrueSolarTime, TermMoment
from .constants import (
    BRANCH_ELEMENTS, BRANCHES, CHANG_SHENG_STAGES, HIDDEN_STEMS, HIDDEN_STEM_WEIGHT,
    NAYIN_ELEMENTS, PILLAR_KEYS, PILLAR_NAMES, SHEN_SHA_RULES, SHI_CHEN_NAMES,
    SHI_CHEN_RANGES, STEM_ELEMENTS, STEMS,
    chang_sheng_of, element_of_branch, element_of_stem, hidden_stems_of,
    make_ganzhi, nayin_element_of, nayin_of, shi_shen_of,
    xun_kong_of, FIXED_SHEN_SHA, ELEMENT_KE, ELEMENT_SHENG,
)

# ★ 晚子时（23:00-00:00 出生）到底算哪一天，自古就有分歧。
#   这不是 bug，是流派差异。四家教法都支持，由调用方选择，默认取最通行的 'next-day'。
#   逐条解释见 references/decisions.md §2
LATE_ZISHI_RULES: Tuple[str, ...] = (
    "next-day",          # 日柱与时柱天干都按次日 —— 最通行，也是多数排盘 App 的默认值
    "current-day",       # 都用当日
    "day-cur-time-next", # 日柱当日、时柱天干次日（俗称「夜子时」）
    "all-current",       # 完全不做真太阳时跨日，也 不换 日柱
)

DEFAULT_LATE_ZISHI_RULE = "next-day"


# ─────────────────────────────────────────────────────────────
# 输入输出的数据结构
# ─────────────────────────────────────────────────────────────

@dataclass
class BirthInput:
    """一次排盘所需的全部输入。缺字段→报错，不猜。"""
    year: int
    month: int
    day: int
    hour: int
    minute: int = 0
    gender: str = "unknown"              # 'male' | 'female' | 'unknown'
    city_name: str = ""
    longitude: Optional[float] = None    # 不给就不做真太阳时校正
    tz_offset_hours: float = 8.0
    dst_adjust: bool = False             # 夏令时是否由用户确认为「报的是夏令时读数」
    late_zishi_rule: str = DEFAULT_LATE_ZISHI_RULE
    liunian_years: Sequence[int] = ()
    term_offset_minutes: float = 0.0     # 仅用于节气误差敏感性比较，不是精度修正

    def __post_init__(self) -> None:
        if not astro.is_valid_gregorian_date(self.year, self.month, self.day):
            raise ValueError(f"不存在的公历日期：{self.year}-{self.month:02d}-{self.day:02d}")
        if not (0 <= self.hour <= 23 and 0 <= self.minute <= 59):
            raise ValueError(f"非法时间：{self.hour:02d}:{self.minute:02d}")
        if self.late_zishi_rule not in LATE_ZISHI_RULES:
            raise ValueError(f"未知的晚子时规则：{self.late_zishi_rule}")
        if self.gender not in ("male", "female", "unknown"):
            raise ValueError(f"未知性别：{self.gender}")
        if self.longitude is not None and not -180 <= self.longitude <= 180:
            raise ValueError("经度必须在 -180 ~ 180 之间")
        if not -14 <= self.tz_offset_hours <= 14:
            raise ValueError("时区偏移必须在 -14 ~ 14 之间")
        if not -15 <= self.term_offset_minutes <= 15:
            raise ValueError("节气敏感性偏移必须在 -15 ~ 15 分钟之间")


@dataclass
class HiddenStemInfo:
    stem: int
    name: str
    level: str
    weight: float
    shi_shen: str


@dataclass
class Pillar:
    """一柱。"""
    key: str
    name: str
    stem: int
    branch: int
    index60: int
    ganzhi: str
    nayin: str
    nayin_element: str
    chang_sheng: str
    xun_kong: Tuple[str, str]
    shi_shen: str = ""            # 相对日主的十神
    hidden_stems: Tuple[HiddenStemInfo, ...] = ()


@dataclass
class ShenShaHit:
    name: str
    nature: str
    positions: Tuple[str, ...]   # 出现在哪些柱，如 ('年柱','日柱')
    note: str = ""


@dataclass
class StrengthBreakdown:
    """日主强弱：把每一分都摊开写。

    市面上各种「强弱打分」互不相同，而且常常是个黑箱。这里唯一的优点是**可解释**——
    每一分来自哪一条都列出来，看不懂或不认同，直接改 `references/decisions.md` 里的权重。
    """
    total: float
    month_power: str            # 旺/相/休/囚/死
    month_score: float
    root_score: float
    stem_score: float
    labels: Tuple[str, ...]
    verdict: str                # '身强' | '身弱' | '中和'


@dataclass
class BoundaryWarning:
    """出生时刻贴近某个「节」的告警 —— 这类人可能被排错月柱/年柱。"""
    term_name: str
    term_time: datetime
    distance_seconds: float
    affected: str               # '月柱' | '年柱'
    message: str


@dataclass
class Chart:
    birth: BirthInput
    solar: TrueSolarTime
    pillars: Dict[str, Pillar]
    day_master_stem: int
    day_master_element: str
    strength: StrengthBreakdown
    shen_sha: Tuple[ShenShaHit, ...]
    warnings: Tuple[BoundaryWarning, ...]
    prev_term: Optional[TermMoment]
    next_term: Optional[TermMoment]
    license_note: str = ""


# ─────────────────────────────────────────────────────────────
# 四柱推算
# ─────────────────────────────────────────────────────────────

def _day_pillar_index(y: int, m: int, d: int) -> int:
    """公历日 → 六十甲子序号。

    公式：`(JDN + 49) % 60`，其中 JDN = floor(JD@当日12:00 UT + 0.5)。

    这不是从某本书里抄来的口诀，是手工验证过两遍才敢写进来的：
      · 2024-01-01 → JDN 2460311 → (2460311+49) % 60 = 0 → 甲子 ✓
      · 2000-01-01 → JDN 2451545 → (2451545+49) % 60 = 54 → 戊午 ✓
    偏移量 +49 就是由这两组已知锚点反解出来的，改之前必须重新验证。
    另有一致性校验：一年的日柱是连续的，任何改动都要保证「次日 = 本日+1」。
    """
    jdn = int(astro.gregorian_to_jd(y, m, d) + 0.5)
    return (jdn + 49) % 60


def _year_pillar_index(birth_moment: datetime, candidates: Sequence[TermMoment]) -> Tuple[int, int]:
    """由「上一个立春」定年柱，返回 (六十甲子序号, 那个立春所在的公历年)。"""
    best: Optional[TermMoment] = None
    for t in candidates:
        if t.name != "立春" or t.utc > birth_moment:
            continue
        if best is None or t.utc > best.utc:
            best = t
    if best is None:
        # 极端情况：出生年份在候选窗口之外。退回到「按公历年」的粗糙处理，
        # 宁可给个粗糙答案也不抛异常 —— 上层有 warnings 机制兜底。
        lichun_year = birth_moment.year
    else:
        lichun_year = best.utc.year
    return (lichun_year - 4) % 60, lichun_year


def month_stem_from_year(year_stem: int, month_branch: int) -> int:
    """五虎遁：由年干、月支推月干。

    寅月月干 = (年干 × 2 + 2) % 10 —— 这是「五虎遁元」的直接写法：
        甲己之年丙作首，乙庚之岁戊为头，丙辛之岁寻庚起，丁壬壬位顺行流，
        戊癸之年甲好求，正月建甲寅。
    之后每前进一个地支，天干也前进一位。

    验证：2024 甲辰年腊月（2024-01-01，子月）→ 年干癸(9)，
          (9*2+2)%10 = 0（甲），子月 offset=(0-2)%12=10 → (0+10)%10 = 0 → 甲子月。
          与该日的公认月柱一致。
    """
    base = (year_stem * 2 + 2) % 10
    offset = (month_branch - 2) % 12
    return (base + offset) % 10


def hour_stem_from_day(day_stem: int, hour_branch: int) -> int:
    """五鼠遁：由日干、时支推时干。

    子时时干 = (日干 × 2) % 10 —— 对应「甲己还加甲，乙庚丙作初，丙辛从戊起，
    丁壬庚子居，戊癸何方发，壬子是真途」。其余时辰顺推。
    """
    return ((day_stem * 2) % 10 + hour_branch) % 10


def _build_pillar(key: str, index60: int, day_stem: Optional[int]) -> Pillar:
    stem, branch = index60 % 10, index60 % 12
    hidden: List[HiddenStemInfo] = []
    for hs, level in HIDDEN_STEMS[branch]:
        weight = HIDDEN_STEM_WEIGHT[level]
        hidden.append(HiddenStemInfo(
            stem=hs,
            name=STEMS[hs],
            level=level,
            weight=weight,
            shi_shen=shi_shen_of(day_stem, hs) if day_stem is not None else "",
        ))
    kong_a, kong_b = xun_kong_of(index60)
    return Pillar(
        key=key,
        name=PILLAR_NAMES[PILLAR_KEYS.index(key)],
        stem=stem,
        branch=branch,
        index60=index60,
        ganzhi=make_ganzhi(index60),
        nayin=nayin_of(index60),
        nayin_element=nayin_element_of(index60),
        chang_sheng=chang_sheng_of(day_stem, branch) if day_stem is not None else "",
        xun_kong=(BRANCHES[kong_a], BRANCHES[kong_b]),
        shi_shen="日主" if key == "day" else (shi_shen_of(day_stem, stem) if day_stem is not None else ""),
        hidden_stems=tuple(hidden),
    )


# ─────────────────────────────────────────────────────────────
# 强弱（启发式，公开口径）
# ─────────────────────────────────────────────────────────────

_MONTH_POWER_SCORE = {"旺": 40.0, "相": 24.0, "休": 8.0, "囚": -16.0, "死": -28.0}
_STEM_SUPPORT = {
    "正印": 8.0, "偏印": 7.0, "比肩": 6.0, "劫财": 5.0,
    "食神": -5.0, "伤官": -6.0, "正财": -7.0, "偏财": -7.0, "正官": -8.0, "七杀": -9.0,
}


def month_power_of(day_element: str, season_element: str) -> str:
    """日主五行在某个月令下的旺相休囚死。

    口诀：当令者旺，我生者相，生我者休，克我者囚，我克者死（「我」指当令五行）。
    """
    if day_element == season_element:
        return "旺"
    if ELEMENT_SHENG[season_element] == day_element:
        return "相"
    if ELEMENT_SHENG[day_element] == season_element:
        return "休"
    if ELEMENT_KE[day_element] == season_element:
        return "囚"
    return "死"


def evaluate_strength(pillars: Dict[str, Pillar], day_stem: int) -> StrengthBreakdown:
    """日主强弱。

    ★ 必须说明白：这是**启发式**，不是任何权威版本的定式。
    八字的身强弱至少有六七种主流算法（调候扶抑、格局法、五行量化…），彼此结论可以相反。
    本实现给的是一个 OpenMetrics 风格的加权和，目的不是「取代老师傅」，
    而是让 LLM 有一条能引用、能解释、且明确标注为启发式的线索。
    权重全部常量化，改起来只要动 `_MONTH_POWER_SCORE` 和 `_STEM_SUPPORT`。
    """
    day_element = element_of_stem(day_stem)
    season = element_of_branch(pillars["month"].branch)
    power = month_power_of(day_element, season)
    month_score = _MONTH_POWER_SCORE[power]
    labels = [f"月令得「{power}」：{month_score:+.0f} 分（{season}月，日主属{day_element}）"]

    # 通根：四支藏干里有日主本气就算有根，按本气/中气/余气打折
    root_score = 0.0
    for key in PILLAR_KEYS:
        p = pillars[key]
        for hs, level in HIDDEN_STEMS[p.branch]:
            if hs == day_stem:
                w = HIDDEN_STEM_WEIGHT[level]
                pos_bonus = 1.2 if key == "month" else (1.1 if key == "day" else 1.0)
                got = 10.0 * w * pos_bonus
                root_score += got
                labels.append(f"{p.name}{p.ganzhi} 藏日主{level}：{got:+.1f} 分")
    # 上限保护：通根最多给到 30 分，避免某些盘「根满天下」把分数推到失真
    root_score = min(root_score, 30.0)

    # 天干帮扶/损耗：看月干、时干、年干
    stem_score = 0.0
    for key in ("year", "month", "hour"):
        p = pillars[key]
        ss = shi_shen_of(day_stem, p.stem)
        base = _STEM_SUPPORT.get(ss, 0.0)
        # 该天干在四支里有没有根，没根者力量减半
        has_root = any(p.stem in hidden_stems_of(pillars[k].branch) for k in PILLAR_KEYS)
        got = base if has_root else base * 0.5
        stem_score += got
        labels.append(f"{p.name}天干十神「{ss}」{'有根' if has_root else '无根'}：{got:+.1f} 分")

    total = month_score + root_score + stem_score
    verdict = "身强" if total >= 15 else ("身弱" if total <= -15 else "中和")
    return StrengthBreakdown(
        total=total, month_power=power, month_score=month_score,
        root_score=root_score, stem_score=stem_score,
        labels=tuple(labels), verdict=verdict,
    )


# ─────────────────────────────────────────────────────────────
# 神煞
# ─────────────────────────────────────────────────────────────

def collect_shen_sha(pillars: Dict[str, Pillar]) -> Tuple[ShenShaHit, ...]:
    """把全部神煞规则跑一遍，命中则记录出现在哪几柱。

    神煞是「辅助信息」而非断语本身 —— 现代命理基本认同：神煞只能加重/削弱某个十神倾向，
    不能单独断事。所以这里只负责「哪些神煞、落在哪柱」，不做好坏结论。
    """
    hits: List[ShenShaHit] = []
    seen: Dict[str, List[str]] = {}

    def record(name: str, nature: str, position: str) -> None:
        seen.setdefault(f"{name}|{nature}", []).append(position)

    for rule in SHEN_SHA_RULES:
        key_pillar = pillars[rule.key]
        if rule.kind == "stem->branch":
            targets = rule.table.get(key_pillar.stem, ())
            for key in PILLAR_KEYS:
                if pillars[key].branch in targets:
                    record(rule.name, rule.nature, pillars[key].name)
        elif rule.kind == "branch->branch":
            targets = rule.table.get(key_pillar.branch, ())
            for key in PILLAR_KEYS:
                if pillars[key].branch in targets:
                    record(rule.name, rule.nature, pillars[key].name)
        elif rule.kind == "month->stem":
            targets = rule.table.get(key_pillar.branch, ())
            for key in PILLAR_KEYS:
                if pillars[key].stem in targets:
                    record(rule.name, rule.nature, pillars[key].name)

    for name, scope, nature, combos in FIXED_SHEN_SHA:
        pillar = pillars["day"] if scope == "日" else pillars["year"]
        if pillar.ganzhi in combos:
            record(name, nature, pillar.name)

    for composite, positions in seen.items():
        name, nature = composite.split("|")
        hits.append(ShenShaHit(name=name, nature=nature, positions=tuple(positions)))
    hits.sort(key=lambda h: (h.nature != "吉", h.name))
    return tuple(hits)


# ─────────────────────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────────────────────

def build_chart(birth: BirthInput) -> Chart:
    """排一张八字盘。"""
    clock_local = datetime(birth.year, birth.month, birth.day, birth.hour, birth.minute)

    # 夏令时：只有当用户明确说「报的是夏令时读数」时才往前拨回 1 小时。
    # 默认不动 —— 理由见 astro.CHINA_DST_RANGES 顶部的注释：
    # 我们无法知道用户报的是夏令时读数还是已经换算过的标准时。
    dst_note = ""
    if birth.dst_adjust:
        dst_hit = astro.china_dst_range(clock_local.date())
        if not dst_hit or birth.tz_offset_hours != 8:
            raise ValueError("--dst-adjust 仅支持中国大陆表内日期及标准时区 +8；海外请用 --tz 指定出生当时实际 UTC 偏移（含夏令时）")
        clock_local = clock_local - timedelta(hours=1)
        dst_note = (f"已按夏令时读数回拨 1 小时（{dst_hit[0]} 至 {dst_hit[1]} 期间）")
    elif birth.tz_offset_hours == 8:
        dst_hit = astro.china_dst_range(clock_local.date())
        if dst_hit:
            dst_note = "日期命中中国大陆夏令时区间；若出生于中国大陆，请确认所报时间是夏令时读数还是已换算的标准时。当前未回拨。"

    solar = astro.to_true_solar_time(clock_local, birth.longitude, birth.tz_offset_hours)

    candidates = astro.terms_covering(birth.year, birth.month, birth.day)
    if birth.term_offset_minutes:
        candidates = [replace(t, utc=t.utc + timedelta(minutes=birth.term_offset_minutes),
                              jd_tt=t.jd_tt + birth.term_offset_minutes / 1440)
                      for t in candidates]

    # ── 日柱：先用真太阳时校正后的日期，再按晚子时规则决定是否 cross day ──
    chart_date = solar.solar_local.date()
    minutes_of_day = solar.hour * 60 + solar.minute + solar.second / 60.0
    hour_branch = astro.branch_from_solar_minutes(minutes_of_day)
    is_late_zi = (hour_branch == 0 and minutes_of_day >= 1380)

    day_delta = 0
    if birth.late_zishi_rule == "all-current":
        chart_date = date(birth.year, birth.month, birth.day)
    else:
        if is_late_zi:
            if birth.late_zishi_rule == "next-day":
                day_delta = 1
            elif birth.late_zishi_rule == "current-day":
                day_delta = 0
            elif birth.late_zishi_rule == "day-cur-time-next":
                day_delta = 0

    day_index = _day_pillar_index(chart_date.year, chart_date.month, chart_date.day)
    if day_delta:
        nxt = astro.shift_days(chart_date, day_delta)
        day_index = _day_pillar_index(nxt.year, nxt.month, nxt.day)
    day_stem, day_branch = day_index % 10, day_index % 12

    # ── 时柱 ──
    if birth.late_zishi_rule == "all-current":
        today = date(birth.year, birth.month, birth.day)
        today_index = _day_pillar_index(today.year, today.month, today.day)
        hour_stem_source = today_index % 10
    else:
        hour_stem_source = day_index % 10
        if birth.late_zishi_rule == "day-cur-time-next" and is_late_zi:
            nxt = astro.shift_days(chart_date, 1)
            hour_stem_source = _day_pillar_index(nxt.year, nxt.month, nxt.day) % 10
        elif birth.late_zishi_rule == "current-day" and is_late_zi:
            hour_stem_source = _day_pillar_index(chart_date.year, chart_date.month, chart_date.day) % 10
    hour_stem = hour_stem_from_day(hour_stem_source, hour_branch)
    hour_index = [i for i in range(60) if i % 10 == hour_stem and i % 12 == hour_branch][0]

    # ── 年柱 / 月柱：和节气时刻比大小 ──
    year_index, _ = _year_pillar_index(solar.moment_utc, candidates)
    year_stem = year_index % 10

    prev_term, next_term = astro.find_surrounding_major_terms(solar.moment_utc, candidates)
    if prev_term is None:
        raise ValueError("找不到出生时刻之前的「节」，可能是输入年份超出了引擎的可靠范围")
    month_branch = dict(astro.MAJOR_TERM_MONTH_BRANCH)[prev_term.name]
    month_stem = month_stem_from_year(year_stem, month_branch)
    month_index = [i for i in range(60) if i % 10 == month_stem and i % 12 == month_branch][0]

    raw = {
        "year": year_index, "month": month_index,
        "day": day_index, "hour": hour_index,
    }
    pillars = {k: _build_pillar(k, v, day_stem) for k, v in raw.items()}

    strength = evaluate_strength(pillars, day_stem)
    hits = collect_shen_sha(pillars)

    # ── 交节边界告警 ──
    warnings: List[BoundaryWarning] = []
    for term, affected in ((prev_term, "月柱"), (next_term, "月柱")):
        if term is None:
            continue
        d = abs((term.utc - solar.moment_utc).total_seconds())
        if d <= astro.BOUNDARY_WARNING_SECONDS:
            affected = "年柱、月柱" if term.name == "立春" else "月柱"
            warnings.append(BoundaryWarning(
                term_name=term.name,
                term_time=term.utc + timedelta(hours=8),
                distance_seconds=d,
                affected=affected,
                message=(
                    f"出生时刻距「{term.name}」仅 {d/60:.1f} 分钟。"
                    f"本引擎节气精度约 ±10 分钟（见 astro.py 文件头实测），"
                    f"{affected}可能排错，请核对出生时间后再用。"
                ),
            ))
    if dst_note:
        warnings.append(BoundaryWarning(
            term_name="夏令时", term_time=solar.moment_utc, distance_seconds=0.0,
            affected="输入口径", message=dst_note,
        ))

    return Chart(
        birth=birth,
        solar=solar,
        pillars=pillars,
        day_master_stem=day_stem,
        day_master_element=element_of_stem(day_stem),
        strength=strength,
        shen_sha=hits,
        warnings=tuple(warnings),
        prev_term=prev_term,
        next_term=next_term,
    )
