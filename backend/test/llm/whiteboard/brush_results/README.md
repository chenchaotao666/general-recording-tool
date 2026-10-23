# 曲线绘画实测

> 此实验方案已回退：当前生成优先采用基础图形，不再进行分阶段规划或视觉自检。以下内容仅保留为历史实验记录，文中自检测试文件已随方案移除。已有曲线内容的渲染兼容仍保留。

本目录保存真实模型生成的数据和通过 Excalidraw 转换器导出的 JPEG，便于后续用同一需求比较效果。

- `portrait.json` / `portrait.jpg`：头肩人像，64 个元素、59 个曲线笔触。仍有五官比例和颈部遮挡问题，不能视为达到写实目标。
- `portrait-review.jpg`：首次视觉检查返回的修正版。经比对，元素未改变。系统现已增加此类无效修正的检测，显示“发现问题但未能有效修正”。报告保留当次结果，不将模型声称的 revised 当成质量通过。
- `cat.json` / `cat.jpg`：精细猫插画。首次请求输出过长导致 JSON 不完整；加入精简重试策略后再次请求得到 43 个元素。耳形、五官定位仍有改善空间。

自动化回归：在 backend 下执行 `.venv/Scripts/python -m unittest test.test_board_ai test.test_board_review`；前端执行 `npx vitest run tests/BrushCurve.test.js tests/ExcalidrawAi.test.js tests/AiPromptConfirmation.test.js`。

实现采用可编辑曲线，不生成位图资产来替代画板元素。复杂绘画先请求构图与图层规划，再生成元素；前端在离屏画布渲染后发起一次视觉检查并展示预览，用户确认才应用。视觉调用失败时保留原草稿并提示未验证。检查通过仅表示模型未指出问题，不代表人工画质评测通过。
