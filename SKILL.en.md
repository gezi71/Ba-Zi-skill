---
name: bazi-fortune
description: Calculate and interpret Bazi (Four Pillars) charts when users ask for a birth chart, Ten Gods, traditional pattern analysis, Dayun luck cycles, or annual readings. Run deterministic scripts before offering a source-based cultural interpretation; never calculate stems and branches from model memory.
metadata:
  agent_created: "true"
---

# Bazi chart calculation and interpretation

[Illustrated project overview](README.en.md) · [中文技能说明](SKILL.md)

Run this skill's scripts first, then explain the fields they provide. Never reconstruct pillars, Ten Gods, hidden stems, branch relations, or pattern candidates from model memory. Interpretation is a traditional cultural practice, without validated scientific predictive accuracy.

Supports birth-time ranges and candidate comparisons, month-command structural facts, classical-rule lookup, and reading-evidence checks. Preserve candidates for uncertain input; trace core statements to chart fields, rule IDs, and their conditions.

This file is the English alternative to `SKILL.md`, not an additional installed skill. To use it as the entry point, copy its contents into `SKILL.md` in the installed skill folder. Scripts, data, and references are shared. Program output and most references remain Chinese; explain their content in the user's language without renaming JSON fields.

## 1. Confirm the input and question

- Date: confirm Gregorian input. For lunar dates, ask for a verifiable Gregorian conversion; the script does not convert lunar dates.
- Time: record the clock reading and certainty. Use a user-approved range for vague times; do not choose a birth hour on the user's behalf.
- Place: resolve birthplace to longitude. Present choices for ambiguous city names. If longitude is missing, calculation can proceed without correction, with its hour-pillar limitation stated.
- UTC offset: mainland China defaults to +8. Overseas births require the actual offset at birth, including local DST; do not infer historical time from today's offset.
- Gender: optional for the natal chart, required for Dayun direction. If unknown, omit Dayun rather than guessing.
- Question: focus on the user's actual topic. A career question does not require asking whether they want a full report.

For supported mainland DST dates, confirm whether the reading is from the advanced clock or already converted to standard time. Use `--dst-adjust` only for a confirmed applicable reading; otherwise compare assumptions. Transitions in 1986–1991 use actual clock times. Earlier date entries are unverified regional hints, not a nationwide regime. For overseas births use the historical `--tz`, not `--dst-adjust`, to avoid subtracting twice.

## 2. Calculate the chart

Paths below are relative to the skill directory. Use absolute script paths when working elsewhere.

```bash
python scripts/bazi.py --date 1990-06-15 --time 14:30 --gender male --longitude 116.4 --format json
```

| Argument | Meaning |
| --- | --- |
| `--date YYYY-MM-DD` | Gregorian date |
| `--time HH:MM` | Known clock time; mutually exclusive with `--time-range` |
| `--time-range HH:MM-HH:MM` | Inclusive minute sampling; an earlier end time crosses midnight |
| `--gender male\|female\|unknown` | Default unknown; no Dayun |
| `--city NAME` / `--longitude DEGREES` | City lookup or direct longitude; east positive, west negative; direct longitude takes precedence |
| `--tz OFFSET` | UTC offset for the input reading; default +8 |
| `--dst-adjust` | Subtract one hour from a confirmed supported mainland DST reading |
| `--compare` | Compare applicable Chinese DST assumptions and solar-term sensitivity scenarios |
| `--late-zishi next-day\|current-day\|day-cur-time-next\|all-current` | Late Zi-hour convention; default next-day |
| `--dayun-count N` | Number of Dayun periods; default 8 |
| `--liunian 2026-2030` | User-requested annual range; “this year” uses the current conversation date |
| `--format markdown\|json` / `-o FILE` | Output format and optional file |

Check the exit code and read both stdout and stderr. Resolve input errors before interpretation. Read `告警` (warnings), each candidate group's warnings, and `排除情景` (excluded scenarios) before discussing the chart.

`传统结构` contains candidates, conditions, counterevidence clues, sources, and unassessed items. `年份差` is the year difference, not nominal age or exact chronological age.

## 3. Preserve uncertainty

Read [references/uncertainty.md](references/uncertainty.md) for details.

- Use `--time-range` for uncertain birth time; add `--compare` when DST or solar-term sensitivity also matters.
- Use known time plus `--compare` for an unconfirmed applicable Chinese DST reading.
- Within about ±15 minutes of a computed month-boundary term, use `--compare`. This shifts the solar-term reference, not the birth reading, and does not improve astronomical accuracy.
- Explain shared and varying pillars before interpreting structures. Scenario counts are not probabilities. Identical pillars can still have different Dayun start dates; use the group's date range.
- Do not mix candidates into one chart or select an hour because it “sounds more like” the user. Defer statements unsupported across the range.
- For software disagreements, compare date, UTC offset, correction, and late Zi-hour conventions first. See [references/decisions.md](references/decisions.md); do not change a chart to match an external answer.

## 4. Interpret the evidence

Read [references/reading_guide.md](references/reading_guide.md). For patterns, Ten Gods, or luck cycles, also read the relevant [pattern rules](references/patterns.md), [Ten Gods guide](references/shi_shen.md), or [Dayun guide](references/da_yun.md).

Use the Zi Ping month-command framework as the main line, with strength and seasonal considerations as supplements. The script outputs pattern candidates and co-occurrence clues, without a complete determination of established/failed patterns, transformations, seasonal useful elements, following patterns, or useful-element selection. State incomplete conditions explicitly. Do not derive useful elements from heuristic strength scores or missing elements.

For seasonal references, run:

```bash
python scripts/query_classics.py --day-stem 甲 --month-branch 寅
```

Check the review status in [references/classics.md](references/classics.md). Unreviewed scan material is for consultation only, not automatic useful-element selection. Search by the chart's day stem and month branch, not the birth lunar month number.

Trace each core statement through **chart fields → original rule conditions → cultural interpretation → uncertainty**. Distinguish the month stem, month branch, and hidden stems; co-occurrence is not an established structure. Report only branch relations supported by output, without assuming transformation or inevitable events.

Read `结构事实` and `结构条件检查`: statuses are `满足` (met), `不满足` (not met), and `未评估` (not assessed). Same-element roots include exact-stem roots. A root does not prove sufficient strength.

For structural interpretations, prepare core statements according to [references/reading_contract.md](references/reading_contract.md), then run `scripts/check_reading.py` to check field paths, rule IDs, and candidate ownership. A passing check does not prove natural-language fidelity; review each statement manually. For accuracy or historical-time questions, read [references/calibration.md](references/calibration.md).

Do not fabricate cases, probabilities, medical conclusions, investment-trading instructions, life-and-death predictions, or fear-based statements. Do not turn historical social assumptions into modern personal facts. Frame readings as conditional observations, not percentage-based predictions.

## 5. Answer the question

Default to a focused answer: relevant chart evidence, conditional interpretation, uncertainty, and practical observations. Use [assets/report_template.md](assets/report_template.md) only when a full reading is requested, translating the report into the user's language as appropriate.

Omit Dayun when gender is unknown. Preserve candidate comparisons when time is unconfirmed. Include only requested annual years. Full reports retain raw data, conventions, rule versions, and sources for verification.

Example: June 15, 1990, Beijing, 14:30, male, career question. Use `--compare --liunian 2026` (replace the year when required), preserving standard-time and DST-adjusted assumptions until the reading is confirmed.
