"""按需检索典籍索引；未经影印核查的调候条目只用于查阅。"""

import json
from functools import lru_cache
from pathlib import Path

from .constants import STEMS, BRANCHES


@lru_cache(maxsize=1)
def catalog():
    return json.loads((Path(__file__).parent / "data" / "classical_rules.json").read_text(encoding="utf-8"))


def rule_reference(rule_id):
    rule = next(r for r in catalog()["规则"] if r["规则编号"] == rule_id)
    return {key: rule[key] for key in ("规则编号", "书名", "版本", "章节", "影印页码", "链接", "校对状态")}


def climate_reference(day_stem, month_branch):
    if day_stem not in STEMS or month_branch not in BRANCHES:
        raise ValueError("日干或月支无效")
    month = (BRANCHES.index(month_branch) - 2) % 12 + 1
    season = ("春", "夏", "秋", "冬")[(month - 1) // 3]
    element = ("木", "木", "火", "火", "土", "土", "金", "金", "水", "水")[STEMS.index(day_stem)]
    return {"日干": day_stem, "月支": month_branch,
            "节月序号": month, "检索章节": f"论{day_stem}{element}／三{season}{day_stem}{element}",
            "链接": "https://zh.wikisource.org/wiki/穷通宝鉴",
            "匹配摘录": [r for r in catalog()["调候摘录"] if r["日干"] == day_stem and r["月支"] == month_branch],
            "状态": "调候查阅索引，未自动取用神",
            "限制": "月份按节月检索，不按农历日期；未校影的转录只供查阅，未摘录不代表无相关原文。"}
