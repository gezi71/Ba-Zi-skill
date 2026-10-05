# 八字 · 有据可查的排盘与解读

[中文](README.md) · [English](README.en.md)

![八字技能：四柱排盘、候选比较与规则证据](assets/images/overview.svg)

[![License: MIT](https://img.shields.io/badge/License-MIT-203b37)](LICENSE)
![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-203b37)
![Zero dependencies](https://img.shields.io/badge/运行依赖-零-607e72)
![Version 0.3.0](https://img.shields.io/badge/版本-0.3.0-607e72)

一个离线可用的八字排盘引擎，以及供 AI 助手使用的技能包。**先用脚本计算四柱，再依据传统文献和明确条件解释。** 出生时间有歧义时保留候选，重要判断可以回查到字段、规则和出处。

命理解读属于传统文化研究；本项目没有经过现实事件预测准确率验证。程序测试与天文校准用于检验计算和实现，不代表命运预测准确率。

## 这个 skill 能做什么

| 能力 | 输出与边界 |
| --- | --- |
| 四柱与基础信息 | 年月日时柱、十神、藏干、纳音、十二长生、神煞 |
| 真太阳时与时间口径 | 经度＋均时差校正；明确时区、夏令时和晚子时选择 |
| 候选盘比较 | 时间范围逐分钟比较；保留共同四柱、变化四柱和起运日期范围 |
| 大运与流年 | 起运及运程；原局与运年六冲、六合、完整三合支组 |
| 传统结构证据 | 月令候选、同干根与同五行根、透干生扶克泄耗、三态条件检查 |
| 典籍检索 | 五部典籍的参考目录与校对状态，规则摘录与调候章节索引 |
| 围绕问题解读 | 脚本字段 → 原文条件 → 文化性解释 → 不确定性 |

结构主线采用《子平真诠》的月令格局，扶抑与调候作为补充。当前输出**候选与线索**，尚未完整判断成格、破格、救应、合化、从格或唯一用神。强弱分数是项目启发式；有根不等于力量足够，同见不等于结构成立。

## 从输入到解释

![确认输入、脚本排盘、核查证据、围绕问题解释](assets/images/workflow.svg)

助手先核对公历日期、钟表读数、出生地点与当时的时区。需要大运时再确认性别；时间不明确时使用用户认可的范围。先传达告警，再读取结构条件和相关文献，默认围绕用户问题回答，完整报告按需生成。

## 快速开始

运行环境：**Python 3.9 或更高版本**，无需安装第三方运行依赖。

```bash
git clone https://github.com/gezi71/Ba-Zi-skill.git
cd Ba-Zi-skill

# Markdown 排盘
python scripts/bazi.py --date 2000-01-01 --time 14:30 --city 北京

# JSON 与大运（性别仅用于确定大运方向）
python scripts/bazi.py --date 2000-01-01 --time 14:30 \
  --gender male --longitude 116.4 --format json

# 夏令时读数未确认：保留输入假设
python scripts/bazi.py --date 1990-06-15 --time 14:30 \
  --gender male --city 北京 --compare --format json

# 只列用户关注的流年；年份示例不是默认值
python scripts/bazi.py --date 2000-01-01 --time 14:30 \
  --gender male --city 北京 --liunian 2026-2030 -o report.md
```

Python API：

```python
from bazi import BirthInput, build_chart, compute_dayun

chart = build_chart(BirthInput(2000, 1, 1, 14, 30,
                             gender="male", longitude=116.4))
print({key: pillar.ganzhi for key, pillar in chart.pillars.items()})
info, periods = compute_dayun(chart, 8)
print(info.summary)
```

## 时间不确定时，保留候选

![241 个分钟样本保留三种时柱，采样数不代表概率](assets/images/candidates.svg)

上图来自下面命令的实际输出：

```bash
python scripts/bazi.py --date 2000-01-01 \
  --time-range 13:00-17:00 --format json
```

此例未提供地点或经度，未做真太阳时校正。范围包含两端，241 次分钟采样得到三组四柱；共同年、月、日柱为己卯、丙子、戊午，变化时柱为己未、庚申、辛酉。**情景数量不代表概率。** 相同四柱的起运日期也可能不同，代表排盘不能代替整组输入范围。

`--time-range 23:30-00:30` 支持跨午夜；`--compare` 另检查适用的夏令时假设和交节时刻 ±15 分钟的敏感性情景。无效夏令时假设会列入 `排除情景`。详见 [不确定性处理](references/uncertainty.md)。

## 0.3.0 的新增内容

- **可复现校准**：保存香港天文台 2024、2026 年 48 条节气原始数据、时区与 SHA-256，提供离线校准脚本。
- **夏令时边界**：按 IANA 2026e PRC 规则处理 1986—1991 年具体转换时刻，修正 1988 年开始日为 4 月 17 日。缺失读数须核对，重复读数保留两种候选。
- **结构事实与条件**：保留原强弱分数，新增同干根、同五行根与三类组合的“满足／不满足／未评估”检查。
- **典籍与解释证据**：分开记录原文、后人注文和项目解释；核查核心判断的字段、规则编号及候选归属。

## 典籍与参考资料

| 典籍 | 项目中的用途 | 当前状态 |
| --- | --- | --- |
| 《子平真诠》 | 月令、变化、成败救应主线 | 相关章节有影印核对记录；非全书校勘 |
| 《渊海子平》 | 藏干与基础口诀异文 | 影印底本已定位，待逐条校对 |
| 《三命通会》 | 规则异说与版本背景 | 保存四库提要短摘录，未校影 |
| 《滴天髓》 | 旺衰、气势、寒暖参考 | 保存相关短摘录，正文与所录注文分层 |
| 《穷通宝鉴》 | 日干与节月的调候查阅 | 三段网页短摘录，待影印校对，不自动取用 |

每条资料标明版本、章节、链接、影印定位及校对状态。未核查内容不会被包装成已经验证的执行规则；古籍命例不作为现实预测准确率样本。详见 [典籍索引](references/classics.md) 与 [格局依据](references/patterns.md)。

```bash
python scripts/query_classics.py --query 成败
python scripts/query_classics.py --day-stem 甲 --month-branch 寅
python scripts/check_reading.py --chart /tmp/chart.json --reading /tmp/reading.json
```

解释检查器可核验字段存在、规则编号、类别与候选归属，不能证明自然语言全文忠实；仍需检查是否将候选说成成格、同见说成合化、评分说成用神。格式见 [解释证据约定](references/reading_contract.md)。

## 精度与验证

当前使用 Meeus《天文算法》第 25 章低精度太阳坐标。对香港天文台 2024、2026 年数据的离线校准结果：

| 样本 | 数量 | 最大绝对差 | 平均绝对差 |
| --- | --- | --- | --- |
| 两年全部节气 | 48 | 829.8 秒，约 13.8 分钟 | 313.5 秒，约 5.2 分钟 |
| 两年十二“节” | 24 | 829.8 秒，约 13.8 分钟 | 342.1 秒，约 5.7 分钟 |

参考时间精度到分钟；最大样本差为 2026 年立夏提前约 13.8 分钟。**15 分钟是样本回归阈值和敏感性窗口，不是全年份误差上限。** 旧 60 点测试未保存原始数据，其约 10.5 分钟记录不能再当作上限。[香港天文台资料说明](https://www.hko.gov.hk/tc/gts/astronomy/Solar_Term.htm)

```bash
python scripts/calibrate_terms.py
python -m unittest discover -s tests
```

0.3.0 本地验证包含 **93 项测试**。CI 配置覆盖 Windows、macOS、Linux 与 Python 3.9、3.11、3.13；远端运行状态以 [GitHub Actions](https://github.com/gezi71/Ba-Zi-skill/actions) 为准。

1940—2035 年另有 40 个冻结四柱回归样本。其他年份没有独立精度保证；ΔT 与均时差也未独立校准。起运日期受节气误差及折算口径影响。完整说明见 [校准与历史时间](references/calibration.md)。

## 排盘口径

| 项目 | 默认与选择 |
| --- | --- |
| 日期 | 公历；本脚本不转换农历输入 |
| 年柱／月柱 | 按立春时刻换年，按十二个“节”换月 |
| 时区 | 默认 UTC+8；海外须提供出生时实际 UTC 偏移，含当地夏令时 |
| 真太阳时 | 有经度时做经度＋均时差校正；缺经度时完全不校正 |
| 夏令时 | 不自动回拨；确认读数后才使用 `--dst-adjust`，海外使用 `--tz` |
| 晚子时 | 默认 `next-day`，另支持 `current-day`、`day-cur-time-next`、`all-current` |
| 流年 | 按公历年份整年列示，未按年内立春逐时切换 |
| 早期历史日期 | 仅有兼容性提示，不能推广为全国实际时间制度 |

不同软件结果不一致时，先核对上述输入与口径。参数清单见 [SKILL.md](SKILL.md)，取舍记录见 [decisions.md](references/decisions.md)。

## 作为 AI 技能使用

安装时保留整个仓库的相对目录结构，并以 `SKILL.md` 为入口。例如：

```bash
git clone https://github.com/gezi71/Ba-Zi-skill.git ~/.codex/skills/bazi-fortune
```

英文项目说明见 [README.en.md](README.en.md)，英文技能说明见 [SKILL.en.md](SKILL.en.md)。若需要以英文说明作为入口，可在安装副本中用 `SKILL.en.md` 替换 `SKILL.md` 的内容；脚本和参考资料共用，参考文档与程序输出目前主要为中文。

示例提问：

> 我 1990 年 6 月 15 日下午两点半出生在北京，想看看事业。出生时间可能有半小时误差。

助手会确认时间范围和夏令时读数，调用脚本保留候选，再解释与事业问题相关的证据。全面报告使用 [报告模板](assets/report_template.md)。

## 项目结构

```text
SKILL.md / SKILL.en.md       中英文技能说明
README.md / README.en.md     中英文项目介绍
bazi/                       标准库排盘引擎、结构证据与典籍数据
scripts/                    排盘、校准、典籍检索、解释证据检查
references/                 口径、规则、典籍与解读边界
assets/calibration/         离线原始基准和来源清单
assets/images/              介绍图片（SVG）
assets/report_template.md   全面报告模板
tests/                      计算、边界、结构和输出回归
```

## 来源与协议

- 参考项目：[ziwei-doushu](https://github.com/Renhuai123/ziwei-doushu)。城市经度资料及部分排盘口径见现有代码与 [口径记录](references/decisions.md)。
- 天文算法：Jean Meeus, *Astronomical Algorithms*, 2nd ed., 1998；均时差使用 NOAA 近似式，ΔT 保留既有近似表。
- 校准与时间资料：[香港天文台](https://www.hko.gov.hk/tc/gts/astronomy/Solar_Term.htm)、IANA 2026e，原始来源和校验值见 [sources.json](assets/calibration/sources.json)。
- 典籍版本与校对进度：[classics.md](references/classics.md)。

项目代码采用 [MIT License](LICENSE)。资料引用保留各自来源与状态；本项目不提供改运、择日或合婚算法，不以命理解读给出医疗、投资交易或生死判断。
