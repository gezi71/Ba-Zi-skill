# 贡献指南

先说一句：这个项目做的是命理日历工具，不是「算命 productive 服务」。
任何让输出看起来更像 predictions 的贡献都会被退回 —— 见最后一节。

## 一、先跑起来

零依赖是硬约束，不需要也不能装包：

```bash
python --version                       # >= 3.9
python -m unittest discover -s tests   # 49 项断言（含 45 条对拍外部实现的冻结用例）
python scripts/bazi.py --date 1990-06-15 --time 12:30 --gender male --city 北京
```

## 二、改代码前先读这三处注释

它们解释了为什么写成现在这样，改错了就会退化：

1. `bazi/astro.py` 文件头 —— 节气精度的实测边界，以及交节告警的设计
2. `bazi/chart.py` `_day_pillar_index` —— 日柱公式的两个锚点怎么来的
3. `bazi/dayun.py` 文件头 —— 大运「三日为一岁」的折算规则

## 三、改任何一个口诀或数值表，必须同时提交证据

口诀类改动（`bazi/constants.py`）不接受「我记得是这样」。请附上：

- 出处（书名版本章回，或古籍影印截图）
- 至少两条不同来源的交叉引用
- 一条新的回归测试，锁住这条口诀的期望值

参考做法：本项目的纳音表在初版时漏抄了第 6–10 组，是单元测试撞出来的，
随后在 `constants._assert_tables_length` 里加了一道启动自检。**不要让同样的错误重演。**

## 四、改动之后

- `python -m unittest discover -s tests` 必须全绿
- 新增 `--liunian` 之类参数时，同步更新 `SKILL.md` 的参数表
- 若影响到 `references/` 里的知识文档，两处一起改

## 五、我们不接受的 PR

- 加入第三方依赖（calendar 类库、pandas、requests 等）
- 让引擎输出吉凶断语、运势打分、宜忌、改运建议
- 「凭经验调一下权重」而没有给出评估方法与对比数据
- 删除或弱化免责声明

## 六、我们特别欢迎的 PR

- 提高节气精度：替换 `sun_apparent_longitude` 为更高阶星历，
  并用 README §4 记录的方法复测新误差边界
- 补充 `references/` 里引用的古籍原文
- 勘误：任何一处口诀、纳音、神煞起法写错的修正（附出处）
- 非中文界面的 i18n（英文版本的十神名、神煞名等）

## 七、行为准则

见 `CODE_OF_CONDUCT.md`（沿用 Contributor Covenant 中文版）。
