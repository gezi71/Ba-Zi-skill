#!/usr/bin/env python3
"""
八字排盘命令行。

设计意图：**这个脚本只吐确定性事实，不吐结论。**
它的输出是给 LLM（或人）读的「原始素材」，解读由上层完成。
所以 Markdown 输出里不会出现「你今年运势不错」这类话 —— 那是编造，
而这里唯一该有的美德是：不编造。

用法
────
    python scripts/bazi.py --date 1990-06-15 --time 12:30 --gender male --city 北京
    python scripts/bazi.py --date 1990-06-15 --time 12:30 --gender male --longitude 116.4 --format json
    python scripts/bazi.py --date 1988-06-15 --time 14:00 --gender female --city 广州 --dst-adjust

退出码：0 成功；2 参数或输入无法处理（日期不存在、城市有歧义等）。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import astro
from .cities import lookup_city
from .chart import DEFAULT_LATE_ZISHI_RULE, LATE_ZISHI_RULES, BirthInput, build_chart
from .dayun import compute_dayun, compute_liunian

DISCLAIMER = (
    "> 本排盘由确定性算法生成，不涉及任何科学验证。"
    "命理属于传统文化研究范畴，请勿用于医疗、金融、法律等重大决策。"
)


# ─────────────────────────────────────────────────────────────
# 参数
# ─────────────────────────────────────────────────────────────

def _parse_time(value: str) -> Tuple[int, int]:
    try:
        parts = value.split(":")
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
        return h, m
    except (ValueError, IndexError):
        raise argparse.ArgumentTypeError(f"时间格式应为 HH:MM，收到：{value!r}")


def _parse_years(value: str) -> Tuple[int, ...]:
    out = []
    for chunk in value.replace("，", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            a, b = chunk.split("-", 1)
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(chunk))
    return tuple(out)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="bazi",
        description="八字排盘（零依赖 · 确定性 · 不做吉凶断言）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例：python scripts/bazi.py --date 1990-06-15 --time 12:30 --gender male --city 北京",
    )
    p.add_argument("--date", required=True, help="出生日期，YYYY-MM-DD")
    p.add_argument("--time", required=True, type=_parse_time, help="出生时间，HH:MM（按下方 --tz 时区解读）")
    p.add_argument("--gender", choices=("male", "female", "unknown"), default="unknown",
                   help="性别。未知则无法排大运")
    p.add_argument("--city", default="", help="出生地城市名，用于查经度；与 --longitude 二选一")
    p.add_argument("--longitude", type=float, default=None,
                   help="直接给出生地经度（东经为正）。给了就不再查城市表")
    p.add_argument("--tz", type=float, default=8.0,
                   help="出生时间的时区偏移，默认 +8（北京时间）")
    p.add_argument("--dst-adjust", action="store_true",
                   help="确认所报时间为夏令时读数时启用，自动回拨 1 小时")
    p.add_argument("--late-zishi", choices=LATE_ZISHI_RULES, default=DEFAULT_LATE_ZISHI_RULE,
                   help="晚子时（23:00 后）流派，默认 next-day")
    p.add_argument("--dayun-count", type=int, default=8, help="排几步大运，默认 8")
    p.add_argument("--liunian", type=_parse_years, default=(),
                   help="要排的流年，支持 2026-2030 或 2026,2027 写法")
    p.add_argument("--format", choices=("markdown", "json"), default="markdown")
    p.add_argument("-o", "--output", default=None, help="输出到文件；缺省打印到标准输出")
    return p


# ─────────────────────────────────────────────────────────────
# 城市 → 经度
# ─────────────────────────────────────────────────────────────

def resolve_longitude(city: str, explicit: Optional[float]) -> Tuple[Optional[float], str, List[str]]:
    """返回 (经度, 限定名, 提示列表)。有歧义时返回空经度并给出全部候选。"""
    if explicit is not None:
        if not -180 <= explicit <= 180:
            raise SystemExit(f"经度必须在 -180 ~ 180 之间，收到 {explicit}")
        return explicit, f"自定义经度 {explicit}°", []

    if not city:
        return None, "未提供出生地（不做真太阳时校正）", []

    hits = lookup_city(city)
    if not hits:
        raise SystemExit(f"城市表中查不到「{city}」。可以直接用 --longitude 给出经度。")
    if len(hits) > 1:
        listing = "\n".join(f"    {q}  经度 {lon}" for q, lon in hits[:12])
        raise SystemExit(
            f"「{city}」在表中命中 {len(hits)} 个地点，经度不同会影响时辰判定，请明确指定：\n{listing}\n"
            f"    例：--city 北京市/朝阳"
        )
    return hits[0][1], hits[0][0], []


# ─────────────────────────────────────────────────────────────
# 输出：JSON
# ─────────────────────────────────────────────────────────────

def to_json(chart, dayun_info, dayun_list, liunian, place_label: str) -> str:
    def pillar_json(p) -> Dict[str, Any]:
        return {
            "名称": p.name,
            "干支": p.ganzhi,
            "天干": p.ganzhi[0],
            "地支": p.ganzhi[1],
            "十神": p.shi_shen,
            "纳音": p.nayin,
            "纳音五行": p.nayin_element,
            "十二长生": p.chang_sheng,
            "空亡": list(p.xun_kong),
            "藏干": [
                {"天干": h.name, "层级": h.level, "权重": h.weight, "十神": h.shi_shen}
                for h in p.hidden_stems
            ],
        }

    payload: Dict[str, Any] = {
        "排盘条件": {
            "输入日期": f"{chart.birth.year:04d}-{chart.birth.month:02d}-{chart.birth.day:02d}",
            "输入时间": f"{chart.birth.hour:02d}:{chart.birth.minute:02d}",
            "时区偏移": chart.birth.tz_offset_hours,
            "出生地": place_label,
            "经度": chart.birth.longitude,
            "性别": chart.birth.gender,
            "晚子时规则": chart.birth.late_zishi_rule,
            "夏令时回拨": chart.birth.dst_adjust,
        },
        "真太阳时": {
            "钟表时间": chart.solar.clock_local.strftime("%Y-%m-%d %H:%M:%S"),
            "真太阳时": chart.solar.solar_local.strftime("%Y-%m-%d %H:%M:%S"),
            "经度修正分钟": round(chart.solar.longitude_minutes, 2),
            "均时差分钟": round(chart.solar.equation_minutes, 2),
            "绝对时刻(UTC)": chart.solar.moment_utc.strftime("%Y-%m-%d %H:%M:%S"),
        },
        "四柱": {k: pillar_json(chart.pillars[k]) for k in ("year", "month", "day", "hour")},
        "日主": {
            "天干": chart.pillars["day"].ganzhi[0],
            "五行": chart.day_master_element,
        },
        "强弱启发式": {
            "结论": chart.strength.verdict,
            "总分": round(chart.strength.total, 2),
            "月令": chart.strength.month_power,
            "明细": list(chart.strength.labels),
        },
        "神煞": [
            {"名称": h.name, "吉凶": h.nature, "落在": list(h.positions)}
            for h in chart.shen_sha
        ],
        "告警": [w.message for w in chart.warnings],
        "免责声明": DISCLAIMER.lstrip("> "),
    }

    if dayun_info is not None:
        payload["大运"] = {
            "方向": dayun_info.direction,
            "参节": dayun_info.reference_term,
            "参节时刻": dayun_info.reference_term_time.strftime("%Y-%m-%d %H:%M:%S"),
            "距节天数": round(dayun_info.gap_days, 4),
            "起运年龄": f"{dayun_info.years}岁{dayun_info.months}个月{dayun_info.days}天",
            "起运日期": str(dayun_info.qiyun_date) if dayun_info.qiyun_date else None,
            "运程": [
                {
                    "第几步": d.index, "干支": d.ganzhi, "十神": d.shi_shen,
                    "起": d.start_age, "止": d.end_age,
                    "起于": str(d.start_date), "止于": str(d.end_date),
                }
                for d in dayun_list
            ],
        }
    if liunian:
        payload["流年"] = [
            {"年份": l.year, "干支": l.ganzhi, "十神": l.shi_shen, "虚岁": l.age}
            for l in liunian
        ]
    return json.dumps(payload, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────────────────────
# 输出：Markdown
# ─────────────────────────────────────────────────────────────

def to_markdown(chart, dayun_info, dayun_list, liunian, place_label: str) -> str:
    b = chart.birth
    lines: List[str] = []

    lines.append("# 八字排盘原始数据")
    lines.append("")
    lines.append(DISCLAIMER)
    lines.append("")

    # ── 排盘条件 ──
    lines.append("## 一、排盘条件")
    lines.append("")
    lines.append("| 项目 | 值 |")
    lines.append("| --- | --- |")
    lines.append(f"| 出生日期（公历） | {b.year:04d}-{b.month:02d}-{b.day:02d} |")
    lines.append(f"| 出生时间（钟表） | {b.hour:02d}:{b.minute:02d} |")
    lines.append(f"| 出生地 | {place_label} |")
    lines.append(f"| 经度 | {b.longitude if b.longitude is not None else '未提供'} |")
    lines.append(f"| 时区偏移 | UTC{b.tz_offset_hours:+g} |")
    gender_label = {"male": "男", "female": "女", "unknown": "未知"}[b.gender]
    lines.append(f"| 性别 | {gender_label} |")
    lines.append(f"| 晚子时规则 | {b.late_zishi_rule} |")
    lines.append(f"| 夏令时回拨 | {'是' if b.dst_adjust else '否'} |")
    lines.append("")

    # ── 时间换算 ──
    lines.append("## 二、时间换算")
    lines.append("")
    lines.append("| 项目 | 值 |")
    lines.append("| --- | --- |")
    lines.append(f"| 钟表时间 | {chart.solar.clock_local.strftime('%Y-%m-%d %H:%M:%S')} |")
    lines.append(f"| 经度修正 | {chart.solar.longitude_minutes:+.2f} 分钟 |")
    lines.append(f"| 均时差 | {chart.solar.equation_minutes:+.2f} 分钟 |")
    lines.append(f"| 真太阳时 | {chart.solar.solar_local.strftime('%Y-%m-%d %H:%M:%S')} |")
    lines.append(f"| 绝对时刻（UTC） | {chart.solar.moment_utc.strftime('%Y-%m-%d %H:%M:%S')} |")
    if chart.prev_term:
        lines.append(f"| 上一个节 | {chart.prev_term.name}"
                     f"（{(chart.prev_term.utc + _tzdelta(b.tz_offset_hours)).strftime('%Y-%m-%d %H:%M')}） |")
    if chart.next_term:
        lines.append(f"| 下一个节 | {chart.next_term.name}"
                     f"（{(chart.next_term.utc + _tzdelta(b.tz_offset_hours)).strftime('%Y-%m-%d %H:%M')}） |")
    lines.append("")

    # ── 四柱 ──
    lines.append("## 三、四柱")
    lines.append("")
    lines.append("|  | 年柱 | 月柱 | 日柱 | 时柱 |")
    lines.append("| --- | --- | --- | --- | --- |")
    for label, attr in (
        ("天干", lambda p: p.ganzhi[0]),
        ("地支", lambda p: p.ganzhi[1]),
        ("十神", lambda p: p.shi_shen),
        ("纳音", lambda p: p.nayin),
        ("十二长生", lambda p: p.chang_sheng),
        ("空亡", lambda p: "".join(p.xun_kong)),
    ):
        row = [f"| {label} "] + [f"| {attr(chart.pillars[k])} " for k in ("year", "month", "day", "hour")] + ["|"]
        lines.append("".join(row))
    lines.append("")

    lines.append("### 藏干")
    lines.append("")
    lines.append("| 柱 | 藏干 |")
    lines.append("| --- | --- |")
    for k in ("year", "month", "day", "hour"):
        p = chart.pillars[k]
        body = "、".join(f"{h.name}（{h.level}·{h.shi_shen}）" for h in p.hidden_stems) or "—"
        lines.append(f"| {p.name} | {body} |")
    lines.append("")

    # ── 日主强弱 ──
    lines.append("## 四、日主强弱（启发式）")
    lines.append("")
    lines.append(f"日主 **{chart.pillars['day'].ganzhi[0]}**，五行属 **{chart.day_master_element}**。")
    lines.append("")
    lines.append(f"- 月令状态：{chart.strength.month_power}（{chart.strength.month_score:+.0f} 分）")
    lines.append(f"- 通根：{chart.strength.root_score:+.1f} 分")
    lines.append(f"- 天干帮扶：{chart.strength.stem_score:+.1f} 分")
    lines.append(f"- **合计 {chart.strength.total:+.1f} 分 → 判为「{chart.strength.verdict}」**")
    lines.append("")
    lines.append("评分明细：")
    for lb in chart.strength.labels:
        lines.append(f"- {lb}")
    lines.append("")
    lines.append("> 这是加权启发式，不是任何权威定式。命理界对身强弱至少有六七套互不支持的算法，"
                 "此分数的作用是给出一条可解释、可复核的线索。")
    lines.append("")

    # ── 神煞 ──
    lines.append("## 五、神煞")
    lines.append("")
    lines.append("| 神煞 | 吉凶 | 落在 |")
    lines.append("| --- | --- | --- |")
    for h in chart.shen_sha:
        lines.append(f"| {h.name} | {h.nature} | {'、'.join(h.positions)} |")
    lines.append("")

    # ── 大运 ──
    if dayun_info is not None:
        lines.append("## 六、大运")
        lines.append("")
        lines.append(dayun_info.summary)
        lines.append("")
        lines.append("| 步 | 干支 | 十神 | 起运 | 止运 | 起始日期 |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for d in dayun_list:
            lines.append(f"| {d.index} | {d.ganzhi} | {d.shi_shen} "
                         f"| {d.start_age} 岁 | {d.end_age} 岁 | {d.start_date} |")
        lines.append("")

    # ── 流年 ──
    if liunian:
        lines.append("## 七、流年")
        lines.append("")
        lines.append("| 年份 | 干支 | 十神 | 虚岁 |")
        lines.append("| --- | --- | --- | --- |")
        for l in liunian:
            lines.append(f"| {l.year} | {l.ganzhi} | {l.shi_shen} | {l.age} |")
        lines.append("")

    # ── 告警 ──
    if chart.warnings:
        lines.append("## 八、⚠️ 必须告知使用者的不确定性")
        lines.append("")
        for w in chart.warnings:
            lines.append(f"- {w.message}")
        lines.append("")

    return "\n".join(lines)


def _tzdelta(offset_hours: float) -> timedelta:
    return timedelta(hours=offset_hours)


# ─────────────────────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────────────────────

def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        y, m, d = [int(x) for x in args.date.split("-")]
    except ValueError:
        print("日期格式应为 YYYY-MM-DD", file=sys.stderr)
        return 2

    longitude, place_label, _ = resolve_longitude(args.city, args.longitude)

    try:
        birth = BirthInput(
            year=y, month=m, day=d,
            hour=args.time[0], minute=args.time[1],
            gender=args.gender,
            city_name=args.city,
            longitude=longitude,
            tz_offset_hours=args.tz,
            dst_adjust=args.dst_adjust,
            late_zishi_rule=args.late_zishi,
            liunian_years=args.liunian,
        )
    except ValueError as exc:
        print(f"输入有误：{exc}", file=sys.stderr)
        return 2

    # 夏令时提示：命中就提醒，但绝不擅自改。
    dst_hit = astro.china_dst_range(date(y, m, d))
    if dst_hit and not birth.dst_adjust:
        print(
            f"提示：{y} 年 {dst_hit[0].strftime('%m月%d日')} 至 {dst_hit[1].strftime('%m月%d日')} 中国大陆实行夏令时。"
            f"若您报的是夏令时读数，请加 --dst-adjust 由脚本回拨 1 小时；"
            f"若已是标准时则无需处理。（默认不自动回拨，理由见 README §5.3）",
            file=sys.stderr,
        )

    chart = build_chart(birth)

    dayun_info, dayun_list = None, ()
    if args.gender in ("male", "female"):
        dayun_info, dayun_list = compute_dayun(chart, args.dayun_count)

    liunian = compute_liunian(chart, args.liunian) if args.liunian else ()

    if args.format == "json":
        out = to_json(chart, dayun_info, dayun_list, liunian, place_label)
    else:
        out = to_markdown(chart, dayun_info, dayun_list, liunian, place_label)

    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
        print(f"已写入 {args.output}", file=sys.stderr)
    else:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
