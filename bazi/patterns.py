"""子平月令候选与结构关系。规则边界及原文对照见 references/patterns.md。

只记录可验证的条件，不给成格、合化、用神或吉凶结论。
"""

from itertools import combinations

from .constants import BRANCHES, STEMS, BRANCH_CHONG, BRANCH_HE, BRANCH_SAN_HE, element_of_stem, element_of_branch
from .classics import rule_reference, climate_reference

RULE_VERSION = "ziping-evidence-2"
SOURCES = {
    "月令": "https://donglishuzhai.net/chapter/3721.html",
    "成败": "https://donglishuzhai.net/chapter/3722.html",
    "变化": "https://donglishuzhai.net/chapter/3723.html",
    "冲合": "https://donglishuzhai.net/chapter/3720.html",
}
UNASSESSED = ["强弱与制化是否足够", "天干合化与位置先后", "格局变化、成败及救应", "调候、从格与化气格"]

# 这些是需要复核的同见线索，不是破格判断。出处：《论用神成败救应》。
CONFLICTS = {
    "正官": ("伤官", "七杀"), "七杀": ("正财", "偏财"),
    "正财": ("比肩", "劫财", "七杀"), "偏财": ("比肩", "劫财", "七杀"),
    "正印": ("正财", "偏财"), "偏印": ("正财", "偏财"),
    "食神": ("偏印",), "伤官": ("正官",),
}


def branch_relations(chart, extra=()):
    """全部位置的六冲、六合、完整三合支组；有外部支时只返回涉及外部的关系。

《论刑冲会合解法》所称申子辰“三会”按本仓库术语标“三合支组”。
关系同时列出，不擅自判合解冲；没有半合或合化判断。
"""
    natal = [(p.name, p.branch) for p in chart.pillars.values()]
    positions = natal + list(extra)
    hits = []
    for size in (2, 3):
        for indexes in combinations(range(len(positions)), size):
            if extra and all(i < len(natal) for i in indexes):
                continue
            branches = tuple(positions[i][1] for i in indexes)
            kind = None
            if size == 2:
                if BRANCH_CHONG[branches[0]] == branches[1]:
                    kind = "六冲"
                elif BRANCH_HE[branches[0]] == branches[1]:
                    kind = "六合"
            elif any(set(branches) == set(group) for group in BRANCH_SAN_HE):
                kind = "三合支组"
            if kind:
                hits.append({"关系": kind, "位置": [positions[i][0] for i in indexes],
                             "地支": [BRANCHES[b] for b in branches], "来源": SOURCES["冲合"]})
    return hits


def analyze_patterns(chart):
    month = chart.pillars["month"]
    visible = [p for k, p in chart.pillars.items() if k != "day"]
    candidates = []
    limits = list(UNASSESSED)
    if month.hidden_stems[0].shi_shen in ("比肩", "劫财"):
        limits.append("月令本气为比劫：涉及建禄月劫或阳刃取用，不能套用普通八格；须另查财官杀食及原文")
    if month.branch in (1, 4, 7, 10):
        limits.append("四墓月：杂气兼透、会支取用需复核，不按藏干顺序独断主格")
    for hidden in month.hidden_stems:
        if hidden.shi_shen in ("比肩", "劫财"):
            continue
        exposed = [p.name for p in visible if p.stem == hidden.stem]
        conflicts = [f"{p.name}{p.ganzhi}透{p.shi_shen}（仅同见，未判破格）"
                     for p in visible if p.shi_shen in CONFLICTS[hidden.shi_shen]]
        candidates.append({
            "名称": hidden.shi_shen + "格候选", "月令藏干": hidden.name,
            "层级": hidden.level, "十神": hidden.shi_shen,
            "命中条件": [f"月支{month.ganzhi[1]}藏{hidden.name}，相对日主为{hidden.shi_shen}"]
                         + [f"{pos}透出同一藏干{hidden.name}" for pos in exposed],
            "不满足项": [] if exposed else ["未透出同一藏干（仍保留月令候选，不据此否定成格）"],
            "反证线索": conflicts, "状态": "候选，未判成格",
            "来源": [SOURCES["月令"], SOURCES["变化"], SOURCES["成败"]],
            "规则编号": "ZP-MONTH-01",
            "条件检查": [{"条件": "月令藏干与日主配十神", "状态": "满足", "依据": [hidden.name, hidden.shi_shen],
                          "规则编号": "ZP-MONTH-01", "来源": rule_reference("ZP-MONTH-01")},
                         {"条件": "同一藏干透出", "状态": "满足" if exposed else "不满足", "依据": exposed,
                          "规则编号": "ZP-CHANGE-01", "来源": rule_reference("ZP-CHANGE-01")},
                         {"条件": "完整成败及救应", "状态": "未评估", "依据": [],
                          "规则编号": "ZP-MONTH-01", "来源": rule_reference("ZP-MONTH-01")}],
        })

    facts = structure_facts(chart)
    checks = combination_checks(chart)
    combinations_found = []
    for item in checks:
        if item["条件检查"][0]["状态"] == "满足":
            combinations_found.append({"名称": item["名称"] + "同见线索",
                "依据": item["条件检查"][0]["依据"],
                "状态": "十神组合线索，不等于成立的格局",
                "未评估": [c["条件"] for c in item["条件检查"] if c["状态"] == "未评估"],
                "来源": SOURCES["成败"], "规则编号": item["规则编号"],
                "条件检查": item["条件检查"]})
    return {"规则版本": RULE_VERSION, "格局候选": candidates, "十神组合线索": combinations_found,
            "原局冲合": branch_relations(chart), "未评估": limits,
            "结构事实": facts, "结构条件检查": checks,
            "调候参考": climate_reference(chart.pillars["day"].ganzhi[0], month.ganzhi[1]),
            "说明": "先看月令，透干与会支保留为证据；候选不是成格，合支不是合化。扶抑分数不用于自动取用神。"}


def roots_of(chart, stem):
    """不量化力量：分别记录同干根、同五行根（后者包含前者）。"""
    same, element = [], []
    for pillar in chart.pillars.values():
        for hidden in pillar.hidden_stems:
            fact = {"位置": pillar.name, "地支": pillar.ganzhi[1],
                    "藏干": hidden.name, "层级": hidden.level}
            if hidden.stem == stem:
                same.append(fact)
            if element_of_stem(hidden.stem) == element_of_stem(stem):
                element.append(fact)
    return {"同干根": same, "同五行根": element}


def structure_facts(chart):
    from .chart import month_power_of

    day = chart.pillars["day"].stem
    month = chart.pillars["month"]
    phases = {"正印": "生", "偏印": "生", "比肩": "扶", "劫财": "扶",
              "食神": "泄", "伤官": "泄", "正财": "耗", "偏财": "耗",
              "正官": "克", "七杀": "克"}
    visible = [{"位置": p.name, "干支": p.ganzhi, "十神": p.shi_shen,
                "相对日主作用": phases[p.shi_shen], **roots_of(chart, p.stem)}
               for key, p in chart.pillars.items() if key != "day"]
    return {"月令": {"月支": month.ganzhi[1],
                    "日主五行": element_of_stem(day), "月支五行": element_of_branch(month.branch),
                    "旺相休囚死参考": month_power_of(element_of_stem(day), element_of_branch(month.branch)),
                    "季节口径": "沿用月支五行参考；四墓按土，未判断藏干司令与实际力量",
                    "藏干": [{"天干": h.name, "十神": h.shi_shen, "层级": h.level} for h in month.hidden_stems],
                    "状态": "季节与月支事实；未判断司令深浅、实际旺衰或调候"},
            "日主根": roots_of(chart, day), "透干及作用": visible,
            "说明": "根是藏干事实，同五行根包含同干根；有根不等于力量足够，生扶克泄耗不等于吉凶。"}


def combination_checks(chart):
    groups = (("官印相生", ("正官",), ("正印", "偏印"), "ZP-GUANYIN-01", ("伤官", "七杀")),
              ("食伤生财", ("食神", "伤官"), ("正财", "偏财"), "ZP-FOODWEALTH-01", ("偏印", "七杀", "比肩", "劫财")),
              ("食神制杀", ("食神",), ("七杀",), "ZP-FOODKILL-01", ("正印", "偏印", "正财", "偏财")))
    visible = [p for key, p in chart.pillars.items() if key != "day"]
    results = []
    for name, left, right, rule_id, interfering in groups:
        a = [p for p in visible if p.shi_shen in left]
        b = [p for p in visible if p.shi_shen in right]
        source = rule_reference(rule_id)
        checks = []
        def record(condition, status, evidence):
            checks.append({"条件": condition, "状态": status, "依据": evidence,
                           "规则编号": rule_id, "来源": source})
        record("两类十神天干同见", "满足" if a and b else "不满足",
               [f"{p.name}{p.ganzhi}透{p.shi_shen}" for p in a + b])
        matching = [h for h in chart.pillars["month"].hidden_stems if h.shi_shen in left + right]
        record("月令含本组十神因素（非定格）", "满足" if matching else "不满足",
               [f"月令藏{h.name}为{h.shi_shen}" for h in matching])
        if a and b:
            roots = [{"位置": p.name, "天干": p.ganzhi[0], **roots_of(chart, p.stem)} for p in a + b]
            record("两侧透干均见同五行根（非力量判定）",
                   "满足" if all(roots_of(chart, p.stem)["同五行根"] for p in a + b) else "不满足", roots)
        else:
            record("两侧透干均见同五行根（非力量判定）", "未评估", [])
        record("未见所列天干干扰因素（不代表无干扰）",
               "不满足" if any(p.shi_shen in interfering for p in visible) else "满足",
               [f"{p.name}{p.ganzhi}透{p.shi_shen}，仅待核线索" for p in visible if p.shi_shen in interfering])
        record("实际旺衰及生制力量是否足够", "未评估", [])
        record("位置、生克先后、刑冲破害、合化及救应是否适宜", "未评估", [])
        record("与月令主线配合的完整成立条件", "未评估", [])
        results.append({"名称": name, "规则编号": rule_id, "条件检查": checks,
                        "状态": "候选线索，未判成格", "必要条件未完成": True})
    return results
