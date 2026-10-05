"""子平月令候选与结构关系。规则边界及原文对照见 references/patterns.md。

只记录可验证的条件，不给成格、合化、用神或吉凶结论。
"""

from itertools import combinations

from .constants import BRANCHES, BRANCH_CHONG, BRANCH_HE, BRANCH_SAN_HE

RULE_VERSION = "ziping-candidates-1"
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
        })

    # 只检查天干同见。暗藏而未透的组合不自动提升为已成立的结构。
    groups = (("官印相生", ("正官",), ("正印", "偏印")),
              ("食伤生财", ("食神", "伤官"), ("正财", "偏财")),
              ("食神制杀", ("食神",), ("七杀",)))
    combinations_found = []
    for name, left, right in groups:
        a = [p for p in visible if p.shi_shen in left]
        b = [p for p in visible if p.shi_shen in right]
        if a and b:
            combinations_found.append({"名称": name + "同见线索",
                "依据": [f"{p.name}{p.ganzhi}透{p.shi_shen}" for p in a + b],
                "状态": "十神组合线索，不等于成立的格局",
                "未评估": ["通根与实际力量", "制化、位置及干扰", "与月令主线的关系"],
                "来源": SOURCES["成败"]})
    return {"规则版本": RULE_VERSION, "格局候选": candidates, "十神组合线索": combinations_found,
            "原局冲合": branch_relations(chart), "未评估": limits,
            "说明": "先看月令，透干与会支保留为证据；候选不是成格，合支不是合化。扶抑分数不用于自动取用神。"}
