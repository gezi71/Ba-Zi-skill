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
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import astro, __version__
from .cities import lookup_city
from .chart import DEFAULT_LATE_ZISHI_RULE, LATE_ZISHI_RULES, BirthInput, build_chart
from .dayun import compute_dayun, compute_liunian
from .patterns import analyze_patterns, branch_relations

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
        if len(parts) not in (1, 2):
            raise ValueError
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError
        return h, m
    except (ValueError, IndexError):
        raise argparse.ArgumentTypeError(f"时间格式应为 HH:MM，收到：{value!r}")


def _parse_years(value: str) -> Tuple[int, ...]:
    out = []
    try:
        for chunk in value.replace("，", ",").split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            if "-" in chunk:
                a, b = [int(x) for x in chunk.split("-", 1)]
                if not 1 <= a <= b <= 9998:
                    raise ValueError
                out.extend(range(a, b + 1))
            else:
                year = int(chunk)
                if not 1 <= year <= 9998:
                    raise ValueError
                out.append(year)
    except ValueError:
        raise argparse.ArgumentTypeError("流年应为1–9998年，范围起年不得晚于止年")
    return tuple(out)


def _parse_time_range(value: str):
    try:
        start, end = value.split("-")
        return _parse_time(start), _parse_time(end)
    except (ValueError, argparse.ArgumentTypeError):
        raise argparse.ArgumentTypeError("时间范围应为 HH:MM-HH:MM；结束早于开始时表示跨午夜")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="bazi",
        description="八字排盘（零依赖 · 确定性 · 不做吉凶断言）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例：python scripts/bazi.py --date 1990-06-15 --time 12:30 --gender male --city 北京",
    )
    p.add_argument("--date", required=True, help="出生日期，YYYY-MM-DD")
    clock = p.add_mutually_exclusive_group(required=True)
    clock.add_argument("--time", type=_parse_time, help="出生时间，HH:MM（按下方 --tz 时区解读）")
    clock.add_argument("--time-range", type=_parse_time_range, help="不确定出生时间，HH:MM-HH:MM，含端点；早于开始则跨午夜")
    p.add_argument("--compare", action="store_true", help="比较适用的中国夏令时读数及交节精度情景；不是概率推断")
    p.add_argument("--gender", choices=("male", "female", "unknown"), default="unknown",
                   help="性别。未知则无法排大运")
    p.add_argument("--city", default="", help="出生地城市名，用于查经度；与 --longitude 二选一")
    p.add_argument("--longitude", type=float, default=None,
                   help="直接给出生地经度（东经为正）。给了就不再查城市表")
    p.add_argument("--tz", type=float, default=8.0,
                   help="出生时间的时区偏移，默认 +8（北京时间）")
    p.add_argument("--dst-adjust", action="store_true",
                   help="中国大陆表内日期、标准时区 +8：确认所报时间为夏令时读数时回拨 1 小时；海外用 --tz 实际偏移")
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
        "输出版本": __version__,
        "排盘条件": {
            "输入日期": f"{chart.birth.year:04d}-{chart.birth.month:02d}-{chart.birth.day:02d}",
            "输入时间": f"{chart.birth.hour:02d}:{chart.birth.minute:02d}",
            "时区偏移": chart.birth.tz_offset_hours,
            "出生地": place_label,
            "经度": chart.birth.longitude,
            "性别": chart.birth.gender,
            "晚子时规则": chart.birth.late_zishi_rule,
            "夏令时回拨": chart.birth.dst_adjust,
            "节气敏感性偏移分钟": chart.birth.term_offset_minutes,
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
        "传统结构": analyze_patterns(chart),
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
                    "与原局冲合": branch_relations(chart, ((f"第{d.index}步大运{d.ganzhi}", d.branch),)),
                }
                for d in dayun_list
            ],
        }
    if liunian:
        payload["流年"] = [
            {"年份": l.year, "干支": l.ganzhi, "十神": l.shi_shen, "年份差": l.age,
             "与原局冲合": branch_relations(chart, ((f"{l.year}流年{l.ganzhi}", l.branch),)),
             "大运叠加": [
                 {"大运": d.ganzhi, "起于": str(d.start_date), "止于": str(d.end_date),
                  "冲合": branch_relations(chart, ((f"第{d.index}步大运{d.ganzhi}", d.branch),
                                                  (f"{l.year}流年{l.ganzhi}", l.branch)))}
                 for d in dayun_list if d.start_date < date(l.year + 1, 1, 1)
                 and d.end_date > date(l.year, 1, 1)
             ]}
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
    if chart.warnings:
        lines.append("## ⚠️ 必须先告知的不确定性")
        lines.extend(f"- {w.message}" for w in chart.warnings)
        lines.append("")

    # ── 排盘条件 ──
    lines.append("## 一、排盘条件")
    lines.append("")
    lines.append("| 项目 | 值 |")
    lines.append("| --- | --- |")
    lines.append(f"| 输出版本 | {__version__} |")
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
        lines.append("| 年份 | 干支 | 十神 | 年份差 |")
        lines.append("| --- | --- | --- | --- |")
        for l in liunian:
            lines.append(f"| {l.year} | {l.ganzhi} | {l.shi_shen} | {l.age} |")
        lines.append("")

    structure = analyze_patterns(chart)
    lines.extend(["## 八、传统结构（候选，不是成格结论）", "", structure["说明"],
                  f"规则版本：{structure['规则版本']}", ""])
    for candidate in structure["格局候选"]:
        lines.append(f"### {candidate['名称']}")
        for field in ("命中条件", "不满足项", "反证线索"):
            lines.append(f"- {field}：{'；'.join(candidate[field]) or '无'}")
        lines.append("- 来源：" + " / ".join(candidate["来源"]))
        lines.append("")
    for combo in structure["十神组合线索"]:
        lines.append(f"- {combo['名称']}：{'；'.join(combo['依据'])}；{combo['状态']}。")
    lines.append("- 未评估：" + "；".join(structure["未评估"]))
    lines.extend(["", "### 原局、大运与流年冲合", "", "仅记录支组，不判合化、解冲或事件；流年按整年展示，大运起止日期为近似值。", ""])
    data = json.loads(to_json(chart, dayun_info, dayun_list, liunian, place_label))
    relation_groups = [("原局", structure["原局冲合"])]
    relation_groups += [(f"第{d['第几步']}步大运{d['干支']}", d["与原局冲合"])
                        for d in data.get("大运", {}).get("运程", [])]
    for item in data.get("流年", []):
        relation_groups.append((f"{item['年份']}流年", item["与原局冲合"]))
        for yun in item["大运叠加"]:
            relation_groups.append((f"{item['年份']}叠{yun['大运']}（{yun['起于']}至{yun['止于']}，止日不含）", yun["冲合"]))
    for label, relations in relation_groups:
        descriptions = [f"{'、'.join(r['位置'])}：{''.join(r['地支'])}{r['关系']}" for r in relations]
        lines.append(f"- {label}：{'；'.join(descriptions) or '未命中已支持的关系'}")
    lines.append("")

    return "\n".join(lines)


def _tzdelta(offset_hours: float) -> timedelta:
    return timedelta(hours=offset_hours)


def compare_output(birth, time_range, sensitivity, dayun_count, liunian_years, place_label):
    """分钟精度穷举出生范围，合并四柱相同的结果；保留每个输入情景的时间段。"""
    start = datetime(birth.year, birth.month, birth.day, birth.hour, birth.minute)
    end = start
    if time_range:
        end = start.replace(hour=time_range[1][0], minute=time_range[1][1])
        if end < start:
            end += timedelta(days=1)
    groups = {}
    sample_count = 0
    moment = start
    while moment <= end:
        base = replace(birth, year=moment.year, month=moment.month, day=moment.day,
                       hour=moment.hour, minute=moment.minute)
        dst_options = [birth.dst_adjust]
        if sensitivity and not birth.dst_adjust and birth.tz_offset_hours == 8 and astro.china_dst_range(moment.date()):
            dst_options.append(True)
        for dst in dst_options:
            current = replace(base, dst_adjust=dst)
            normal = build_chart(current)
            offsets = [0]
            if sensitivity and any(w.term_name != "夏令时" for w in normal.warnings):
                offsets = [-15, 0, 15]
            for offset in offsets:
                chart = normal if not offset else build_chart(replace(current, term_offset_minutes=offset))
                key = tuple(chart.pillars[k].ganzhi for k in ("year", "month", "day", "hour"))
                info, yun = compute_dayun(chart, dayun_count) if birth.gender != "unknown" else (None, ())
                if key not in groups:
                    years = compute_liunian(chart, liunian_years)
                    groups[key] = {"四柱": dict(zip(("年柱", "月柱", "日柱", "时柱"), key)),
                        "输入情景": [], "告警": [], "起运日期范围": [],
                        "代表排盘": json.loads(to_json(chart, info, yun, years, place_label))}
                group = groups[key]
                stamp = moment.strftime("%Y-%m-%d %H:%M")
                scenario = {"开始": stamp, "结束": stamp, "夏令时回拨": dst,
                            "节气敏感性偏移分钟": offset}
                # 不同情景交错采样，用同一情景的最后一个时间段判断连续性。
                previous = next((s for s in reversed(group["输入情景"])
                                 if s["夏令时回拨"] == dst and s["节气敏感性偏移分钟"] == offset), None)
                if previous and datetime.strptime(previous["结束"], "%Y-%m-%d %H:%M") + timedelta(minutes=1) == moment:
                    previous["结束"] = stamp
                else:
                    group["输入情景"].append(scenario)
                for warning in chart.warnings:
                    if warning.message not in group["告警"]:
                        group["告警"].append(warning.message)
                if info:
                    dates = group["起运日期范围"] + [str(info.qiyun_date)]
                    group["起运日期范围"] = [min(dates), max(dates)]
                sample_count += 1
        moment += timedelta(minutes=1)
    candidates = list(groups.values())
    shared = {pos: candidates[0]["四柱"][pos] for pos in ("年柱", "月柱", "日柱", "时柱")
              if all(c["四柱"][pos] == candidates[0]["四柱"][pos] for c in candidates)}
    return {"输出版本": __version__, "模式": "候选盘比较", "范围": [str(start), str(end)],
            "情景采样数": sample_count, "共同四柱": shared,
            "变化四柱": [p for p in ("年柱", "月柱", "日柱", "时柱") if p not in shared],
            "候选": candidates,
            "说明": "时间范围含端点，按分钟穷举；情景数量不是概率。节气±15分钟是敏感性测试，不是新天文精度或修改出生时间。代表排盘只代表该组一个输入；起运日期按范围比较。共同四柱不代表所有性格或事件结论成立。未比较晚子时流派。"}


def comparison_markdown(data):
    lines = ["# 八字候选盘比较", "", DISCLAIMER, "", "## ⚠️ 不确定性与适用范围", "", data["说明"], "",
             f"- 输入范围：{data['范围'][0]} 至 {data['范围'][1]}",
             "- 共同四柱：" + "、".join(f"{k}{v}" for k, v in data["共同四柱"].items()),
             "- 变化四柱：" + ("、".join(data["变化四柱"]) or "无（起运日期仍可能不同）"), ""]
    for index, candidate in enumerate(data["候选"], 1):
        lines.extend([f"## 候选 {index}：{' / '.join(candidate['四柱'].values())}", ""])
        for scenario in candidate["输入情景"]:
            lines.append(f"- {scenario['开始']} 至 {scenario['结束']}；夏令时回拨={scenario['夏令时回拨']}；节气偏移={scenario['节气敏感性偏移分钟']}分钟")
        lines.extend(f"- ⚠️ {w}" for w in candidate["告警"])
        if candidate["起运日期范围"]:
            lines.append("- 近似起运日期范围：" + " 至 ".join(candidate["起运日期范围"]))
        structure = candidate["代表排盘"]["传统结构"]
        lines.append("- 月令候选：" + ("、".join(c["名称"] for c in structure["格局候选"]) or "无普通八格候选"))
        lines.extend(["", "<details><summary>代表排盘与规则依据（JSON）</summary>", "", "```json",
                      json.dumps(candidate["代表排盘"], ensure_ascii=False, indent=2), "```", "", "</details>", ""])
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────────────────────

def main(argv: Optional[List[str]] = None) -> int:
    # Windows 在 CI/管道下可能使用 ANSI 编码，中文与告警符号需按 UTF-8 输出。
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8")
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
            hour=(args.time or args.time_range[0])[0], minute=(args.time or args.time_range[0])[1],
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

    if args.time_range or args.compare:
        try:
            data = compare_output(birth, args.time_range, args.compare, args.dayun_count,
                                  args.liunian, place_label)
        except ValueError as exc:
            print(f"输入有误：{exc}", file=sys.stderr)
            return 2
        out = json.dumps(data, ensure_ascii=False, indent=2) if args.format == "json" else comparison_markdown(data)
        if args.output:
            Path(args.output).write_text(out, encoding="utf-8")
            print(f"已写入 {args.output}", file=sys.stderr)
        else:
            print(out)
        return 0

    # 夏令时提示：命中就提醒，但绝不擅自改。
    dst_hit = astro.china_dst_range(date(y, m, d)) if birth.tz_offset_hours == 8 else None
    if dst_hit and not birth.dst_adjust:
        print(
            f"提示：{y} 年 {dst_hit[0].strftime('%m月%d日')} 至 {dst_hit[1].strftime('%m月%d日')} 中国大陆实行夏令时。"
            f"若您报的是夏令时读数，请加 --dst-adjust 由脚本回拨 1 小时；"
            f"若已是标准时则无需处理。（默认不自动回拨，理由见 README §5.3）",
            file=sys.stderr,
        )

    try:
        chart = build_chart(birth)
    except ValueError as exc:
        print(f"输入有误：{exc}", file=sys.stderr)
        return 2

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
