# 手绘画板 AI 评测 — 手绘画板 50 条测试会话

用例位于 `whiteboard_cases.py`，编号 `WB001`～`WB050`，合计 **50 条会话、58 轮用户请求**。
全部通过产品当前的 **auto 自动判断模式**调用 `generate_board_content`，不强制指定操作类型来绕过意图识别。

| 编号 | 覆盖内容 |
|---|---|
| 001～010 | 单图形、数量、双色、无填充、形状文字、独立文字、折线、箭头、人物、房屋、自然景物 |
| 011～020 | 填充色、边框色、文字色、不透明度、手绘程度、线宽、虚线、点线、取消填充、交叉线 |
| 021～030 | 流程图、条件分支、循环回边、独立节点、组织树、多行文字、零值和空表格单元格、复合内容 |
| 031～040 | 自动追加/替换、选区删除、按名删除、整体/选区汇总、多选修改、否定式指令、空输入/空画布 |
| 041～048 | 两轮连续会话：改色后取消、改名后再定位、恢复线型、切换选区、追加后修改、新建后修改、重画后汇总、零透明度恢复 |
| 049～050 | 附图识别：单图形颜色，以及流程图文字/连接方向；使用 `whiteboard_fixtures/` 中的合成图片 |

在 `backend` 目录运行：

```powershell
.venv/Scripts/python test/llm/whiteboard/eval_whiteboard.py --list
.venv/Scripts/python test/llm/whiteboard/eval_whiteboard.py --live
.venv/Scripts/python test/llm/whiteboard/eval_whiteboard.py --live WB011 WB041
.venv/Scripts/python test/llm/whiteboard/eval_whiteboard.py --live --group style
.venv/Scripts/python test/llm/whiteboard/eval_whiteboard.py --live --group conversation --repeat 3
.venv/Scripts/python -m unittest test.llm.whiteboard.test_whiteboard_eval
```

`--live` 使用当前启用的模型供应商，会产生模型调用费用；默认最多 2 个并发，可用 `--workers 1` 串行运行。
只读取模型配置，使用合成画布上下文，不创建、修改或删除真实业务画布。

结果写入同目录的 `whiteboard_results.json`；可用 `--output 路径` 保存不同轮次的报告。
每完成一条会话立即保存检查点，报告记录模型名称、每轮输入、上下文、期望、实际结果、失败原因和耗时。
前一轮失败时，不伪造上下文执行后续轮次，报告会记录未执行轮数。图片用例即使模型不支持视觉也会真实尝试并记录失败，不计作通过。

**验证边界**：自动断言核对类型、数量、精确色值、文字、选区、目标 ID、连线方向和多轮语义状态。
多轮状态由语义模拟器承接，不等同于真实 Excalidraw 渲染；位置、布局、美观以及界面“确认后才应用/取消不修改/撤销”仍需浏览器测试。
每条会话的 `visual_review` 指明人工检查重点。`PASS` 只代表该条自动断言通过，不代表图画美观或所有 UI 行为均通过。

修改提示词或更换模型后可以重跑同组用例；不要为了提高通过率放松“只改文字色不得改边框”等约束。
