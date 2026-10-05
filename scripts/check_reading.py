"""检查核心判断的字段、规则编号和候选归属；不证明自然语言全文忠实。"""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bazi.evidence import validate_reading


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chart", required=True, type=Path)
    parser.add_argument("--reading", required=True, type=Path)
    args = parser.parse_args()
    try:
        errors = validate_reading(json.loads(args.chart.read_text(encoding="utf-8")),
                                  json.loads(args.reading.read_text(encoding="utf-8")))
    except (ValueError, OSError, TypeError, KeyError) as error:
        errors = [str(error)]
    print(json.dumps({"通过": not errors, "错误": errors}, ensure_ascii=True, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
