"""结构化解释的证据检查；不替代自然语言审阅或现实预测验证。"""

from .classics import catalog


def validate_reading(payload, judgments):
    if not isinstance(payload, dict):
        return ["排盘必须为JSON对象"]
    errors = []
    known = {r["规则编号"] for r in catalog()["规则"]}
    if not isinstance(judgments, list) or not judgments:
        return ["核心判断必须为非空列表"]
    for index, judgment in enumerate(judgments, 1):
        prefix = f"判断{index}："
        if not isinstance(judgment, dict):
            errors.append(prefix + "必须为对象")
            continue
        if judgment.get("类别") not in ("事实", "结构线索", "文化解释"):
            errors.append(prefix + "类别越界；本版未实现成格、合化或用神判定")
        if not isinstance(judgment.get("文本"), str) or not judgment["文本"].strip():
            errors.append(prefix + "缺少判断文本")
        chart = payload
        if payload.get("模式") == "候选盘比较":
            number = judgment.get("候选编号")
            if type(number) is not int or not 1 <= number <= len(payload["候选"]):
                errors.append(prefix + "须指明有效候选编号，不可混盘")
                continue
            chart = payload["候选"][number - 1]["代表排盘"]
        fields = judgment.get("字段")
        if not isinstance(fields, list) or not fields:
            errors.append(prefix + "缺少排盘字段证据")
            continue
        for pointer in fields:
            try:
                if not isinstance(pointer, str) or not pointer.startswith("/"):
                    raise ValueError()
                value = chart
                for segment in pointer[1:].split("/"):
                    segment = segment.replace("~1", "/").replace("~0", "~")
                    if isinstance(value, list):
                        if not segment.isdigit():
                            raise ValueError()
                        value = value[int(segment)]
                    else:
                        value = value[segment]
            except (KeyError, TypeError, IndexError, ValueError):
                errors.append(prefix + "字段不存在：" + str(pointer))
        if judgment.get("类别") != "事实":
            rules = judgment.get("规则编号")
            if not isinstance(rules, list) or not rules or any(not isinstance(r, str) or r not in known for r in rules):
                errors.append(prefix + "须引用已整理的有效规则编号")
            if all(isinstance(p, str) and p.startswith("/强弱启发式") for p in fields):
                errors.append(prefix + "不能只据启发式评分推导结构或文化结论")
    return errors
