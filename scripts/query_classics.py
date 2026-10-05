"""按日干/月支检索调候，或按简体关键词检索已经整理的规则。"""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bazi.classics import catalog, climate_reference


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--day-stem")
    parser.add_argument("--month-branch")
    parser.add_argument("--query")
    args = parser.parse_args()
    if args.day_stem or args.month_branch:
        if not args.day_stem or not args.month_branch:
            parser.error("日干与月支须同时提供")
        result = climate_reference(args.day_stem, args.month_branch)
    else:
        entries = catalog()["规则"] + catalog()["调候摘录"] + catalog()["补充摘录"]
        result = [r for r in entries if not args.query or args.query in r["检索词"] or args.query in r["项目解释"]]
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
