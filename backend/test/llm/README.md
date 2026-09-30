# LLM 功能评测

离线评测 AI 功能的准确性。与冒烟测试（mock LLM、验证流程正确性）不同，这里的用例**真实调用模型**，
验证「AI 生成的配置是否正确」——改提示词、换模型后跑一遍，就能知道准确率有没有退化。

## eval_ai_block.py — AI 单区块配置（设计器「AI 帮我设置」）

覆盖每种区块类型的全部设置项（stat 聚合×7/对比/筛选/口径/日期字段、chart 类型×7/分组/多指标/
二级分组/堆叠/topN/环比同比/占比/层级钻取/联动/口径/自定义区间、pivot 行列维度/聚合/合计/前N、
table 列/排序/口径、filter 字段、text 改写），含一个「需求不完整时应追问或合理默认」的行为用例。

```bash
./.venv/Scripts/python test/llm/eval_ai_block.py              # 全部用例
./.venv/Scripts/python test/llm/eval_ai_block.py 3 7          # 指定编号
./.venv/Scripts/python test/llm/eval_ai_block.py --type chart # 只跑图表
```

## eval_ai_report.py — AI 生成报表

按报表设计器界面上的**每个可配置选项**逐条验证 AI 是否设置正确：

| 选项组 | 覆盖的界面选项 |
|---|---|
| stat | 计数 / 去重计数 / 求和 / 平均 / 占比(ratio) / 环比对比 / 同比对比 |
| chart_type | 柱状 / 折线 / 饼图 / 漏斗 / 面积 / 仪表盘（含满值 max） |
| chart_series | 多指标 / 二级分组 / 堆叠 / 柱线组合图 |
| chart_extra | 环比对比线 / 同比对比线 / 百分比显示 / 取前 N 项 / 点击联动过滤 / 层级钻取 |
| pivot | 字段×字段交叉 / 字段×时间交叉 / 行列合计开关 / 行取前 N 项 |
| table | 展示列 / 排序 / 条数上限 |
| filters_range | 块级筛选条件（含 OR 任一条件）/ 全局口径 / 口径日期字段 |
| block_range | 块级时间范围（固定上周 / 自定义区间）/ 块级日期字段 |
| misc | 文本小结（引用统计卡 {b1} 占位符）/ 筛选块 |

**人工专属项（AI 不生成，不在评测范围）**：跳转其他报表（on_click=jump，目标报表 id 只能人工选）、
筛选块指定作用区块（target=blocks，依赖人工画布上的块 id）。
提示词已明确禁止 AI 输出 jump。

### 运行

```bash
cd backend
./.venv/Scripts/python test/llm/eval_ai_report.py              # 全部用例
./.venv/Scripts/python test/llm/eval_ai_report.py 6 12         # 只跑第 6、12 号用例
./.venv/Scripts/python test/llm/eval_ai_report.py --group pivot  # 只跑透视表组
```

### 环境要求

- 已配置可用的模型供应商（设置页配好默认供应商）；每个用例真实调用一次 LLM，会产生少量 token 消耗
- 评测在独立数据库 `test/llm/eval_ai_report.db` 中进行（自动建临时表 + 试运行 + 用完即删），不影响业务数据
- 供应商配置存在主库 `grt.db`，脚本启动时会自动把 `llm_providers` 复制到评测库，无需手工配置

### 结果怎么看

- `PASS`：结构断言全过 + 落库保存 + 试运行成功
- `FAIL`：打印失败原因和 AI 实际生成的配置（截断 400 字）
- 末尾汇总 FAIL 集中的选项组 —— 某选项持续 FAIL，通常意味着生成提示词没有向模型说明该选项：
  对照 `app/services/llm/prompts.py` 的 `build_report_prompt` 补上说明，再复跑该组验证

### 加用例

在 `eval_ai_report.py` 的 `CASES` 里加一条：

```python
{"group": "chart_extra", "name": "chart·xx 某选项", "fields": PROD_FIELDS,
 "requirement": "一句用户会说的自然语言需求",
 "expect": [block("chart", chart_type="bar", top_n=5)]},
```

断言键与界面配置一一对应（`block()` 的 docstring 里有完整清单）；全局口径用 `range_eq("past_7d")` /
`range_field("production_date")`。新的表结构场景可以仿照 `PROD_FIELDS` 另建字段清单。

## 后续可加

- `eval_ai_workflow.py`：AI 生成工作流（assist_workflow）的同类评测
- `eval_ai_assistant.py`：AI 助手动作识别（填表/建表/查数据/建流程的意图分类准确率）

> 提示词踩坑备忘：否定式指令（「不要输出 JSON」「不要解释」）会让部分模型直接输出空白——
> 用简洁的正向指令（「直接输出撰写好的文本」）替代，见 gateway.py 文本块分支的注释。
