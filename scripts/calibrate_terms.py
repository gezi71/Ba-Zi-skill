"""离线节气校准；权威公布值为分钟精度，不证明全年份误差上限。"""

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bazi.astro import terms_for_year


def calibrate():
    directory = ROOT / "assets" / "calibration"
    manifest = json.loads((directory / "sources.json").read_text(encoding="utf-8"))
    measurements = []
    for source in manifest["sources"]:
        raw = (directory / source["file"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != source["sha256"]:
            raise ValueError("校验值不符：" + source["file"])
        if "year" not in source:
            continue
        year = source["year"]
        terms = sorted((t for t in terms_for_year(year) if t.utc.year == year), key=lambda t: t.utc)
        rows = ET.fromstring(raw).findall("Data")
        if len(rows) != 24 or len(terms) != 24:
            raise ValueError("节气记录必须为 24 条")
        for term, row in zip(terms, rows):
            h, m = map(int, row.findtext("hm").split(":"))
            reference = datetime(year, int(row.findtext("M")), int(row.findtext("D")), h, m) - timedelta(hours=8)
            measurements.append({"year": year, "term": term.name, "major": term.is_major,
                                 "reference_utc": reference.isoformat(),
                                 "error_seconds": (term.utc - reference).total_seconds()})
    summaries = {}
    for label, subset in (("all_terms", measurements),
                          ("major_terms", [r for r in measurements if r["major"]])):
        errors = [r["error_seconds"] for r in subset]
        summaries[label] = {"count": len(errors), "min_seconds": min(errors),
                            "max_seconds": max(errors),
                            "max_absolute_seconds": max(map(abs, errors)),
                            "mean_absolute_seconds": sum(map(abs, errors)) / len(errors)}
    return {"sources": manifest["sources"], "reference_precision": "minute",
            "regression_threshold_seconds": 900,
            "note": "仅覆盖 2024、2026；阈值不是全年份误差上限，也不是预测准确率。",
            "summaries": summaries, "measurements": measurements}


if __name__ == "__main__":
    result = calibrate()
    print(json.dumps(result, ensure_ascii=True, indent=2))
    sys.exit(0 if result["summaries"]["all_terms"]["max_absolute_seconds"] <= 900 else 1)
