# AI 助手功能设计

> 目标：在系统内提供对话式 AI 助手，简化使用 —— 聊天交互、智能填表、AI 建表、生成 Excel、数据问答。
> 交互形态：**全局侧边抽屉**（PC 各页面可唤起，感知当前页面上下文）；写操作一律**预览后确认**。
> 状态：**P0 + P1 + 联网搜索已实现**（聊天/智能填表/AI 建表/数据问答/生成 Excel/联网搜索，冒烟测试 10.10~10.11 节）；P2 未做。

## 1. 总体架构

```
┌─ 前端（App.vue 全局挂载）────────────────────────────┐
│ 悬浮按钮 → 聊天抽屉                                   │
│  消息流（文本 + 动作预览卡片 + 下载卡片）              │
│  上下文：当前路由（表 id/页面类型）自动随请求上报       │
└──────────────┬───────────────────────────────────────┘
               ▼
POST /api/assistant/chat          ← 无状态：客户端携带最近 K 条历史
  1. 组装上下文（用户表清单摘要 + 当前表字段四元组 + 历史）
  2. get_default_provider().complete(ASSISTANT_SYSTEM)
  3. extract_json → {reply, action?}（失败回喂重试 1 次，沿用现有模式）
  4. align_assistant_action() 清洗校验（非法字段/表丢弃、值按类型校验）
  5. 返回 {reply, action_card?}   ← 只生成"预览"，不落库
               ▼ 用户在预览卡片点「确认」
POST /api/assistant/execute       ← 动作落库的唯一入口
  按 action 类型分发：填表 → create_record×N / 建表 → create_business_table
  / 生成 Excel → 生成文件返回下载地址；执行前重新做权限 + 数据校验
```

核心设计决策：

1. **对话与执行分离**。`/chat` 只产出"回复 + 动作预览"，绝不写库；`/execute` 是唯一写入口，执行时**重新**鉴权和校验（不信任 chat 阶段的结果，防止预览被篡改后直传）。这延续系统现有 ai-assist"生成 → 预览 → 应用"的模式，只是确认从"填回表单"变成"调执行接口"。
2. **不用 function calling，用结构化 JSON 意图**。现有 provider 抽象只有 `complete(prompt, system) -> str`，让模型输出 `{reply, action}` 一段 JSON，服务端 align 清洗——与 assist_task/assist_report 完全同构，两套 provider（Claude/OpenAI 兼容）都零改动可用。
3. **数据问答走"受控聚合"而非 text-to-SQL**。让模型输出的是**已有报表引擎语义的查询规格**（agg/field/filters/group），服务端校验后复用 `dyn_engine`/`report_engine` 求值——字段白名单校验、双引擎对齐、权限检查全是现成的，杜绝 SQL 注入与越权。
4. **会话历史客户端持有**（localStorage，按用户隔离），每次请求携带最近 K 条（默认 10）。服务端无状态，不做会话表；执行留痕走已有 `log_audit`。后续要跨端同步再加会话表。

## 2. 消息与动作协议

### 请求

```json
POST /api/assistant/chat
{
  "message": "把这段话填进客户表：张三，电话138...，意向金额2万",
  "history": [{"role": "user|assistant", "content": "..."}],   // 最近 K 条
  "context": {"page": "table", "table_id": 12}                 // 前端自动带上
}
```

### 响应

```json
{
  "reply": "我整理出 1 条客户记录，请确认：",
  "action_card": {
    "type": "fill_records",
    "table_id": 12, "table_label": "客户跟进表",
    "summary": "新增 1 条记录",
    "payload": {"records": [{"customer_name": "张三", "phone": "138...", "amount": 20000}]},
    "warnings": ["phone 未匹配到字段，已忽略"]      // align 阶段产出的说明
  }
}
```

动作卡片五种类型：

| type | 预览卡片内容 | 确认后执行 |
|---|---|---|
| `fill_records` | 目标表 + 记录表格（可逐格编辑、可删行） | 逐条 `create_record`，报告成功/失败明细 |
| `create_table` | 表名 + 字段列表（类型/必填/枚举值，可编辑） | `create_business_table`（json 模式），跳转新表 |
| `create_report` | 报表名/口径/区块清单（复用 assist_report 管线生成） | 校验并创建 ReportTemplate（默认不启用推送），跳转查看 |
| `create_task` | 任务名/条件/周期/动作摘要（复用 assist_task 管线生成） | 复用任务路由校验创建 TaskRule（默认停用） |
| `gen_excel` | 说明 + 文件信息 | 生成 xlsx，返回带 token 的下载地址 |
| `query_answer` | 数值/表格/简单图表（只读结果，无需确认） | ——（chat 阶段已执行完，只读） |
| `search_answer` | 联网搜索的回答 + 参考来源链接（只读，无需确认） | ——（chat 阶段已搜索并二次调用组织回答） |
| `none` | 纯文本回复 | —— |

`query_answer` 与 `web_search`/`search_answer` 是仅有的"chat 阶段就执行"的动作——因为它们都是只读的，且答案必须当场给出；其余动作 chat 阶段只生成预览。

## 3. 四项能力详细设计

### 3.1 智能填表（fill_records）

- **输入**：聊天文本（名片、一段话、多条记录罗列）；当前在表页则默认目标表，否则模型从用户表清单中选并在卡片上可改。
- **流程**：字段四元组（`{field_name, label, data_type, options}`，与 gateway 现有三处一致，抽公共函数）+ 脱敏样例行 → 模型输出 records 数组 → **逐字段 `coerce_value` 校验**（同 `recognize_form` 的做法）：无法转换的值置空并记 warning，未知字段丢弃 → 预览卡片。
- **执行**：`/execute` 对每条记录走 `dyn_engine.create_record`（内部 `coerce_payload`，非空/类型校验兜底），权限 `require_table("create")`；返回 `{ok: n, fail: [{index, reason}]}`，卡片上展示部分成功的明细。
- 上限：单次 ≤ 50 条，超出提示分批。

### 3.2 AI 建表（create_table）

- **输入**："帮我建个客户跟进表，要记录姓名、电话、意向金额、下次跟进日期"。
- **流程**：模型输出 `{label, fields: [{field_name, label, data_type, widget, nullable, options}]}` → align：字段名合法性/重名/保留字（复用 `meta_service.validate_fields`）、非法类型降级 varchar、枚举 options 规整 → 预览卡片（字段可增删改）。
- **执行**：`create_business_table(payload, owner_id=user.id)`，`storage_mode` 默认 `json`（physical 需 `create_physical_table` 权限，无权限时提示并落 json）；遵守 `max_tables` 配额（tables.py:70-76 现成检查）；成功后卡片给"去使用"链接。

### 3.3 生成 Excel（gen_excel）

两种诉求都支持，模型在意图里区分：

- **空白模板**："给我一个客户登记表 Excel" → 字段结构 + 表头样式 + （可选）示例行，新写 `export_blank_xlsx(fields, sample_rows)`（openpyxl，几十行）。
- **数据导出**："把本月成交客户导成 Excel" → 模型输出 `{table_id, filters}`（filters 用现有 FILTER_OPS 语义！）→ 服务端校验后查询 → 新写 `export_records_xlsx(mt, fields, rows)`。
- 记录导出 xlsx 目前系统里不存在，正好是这次补齐的基础设施（未来记录页工具栏也能复用）。
- 交付方式：文件落临时存储或直接流式返回；抽屉里渲染下载卡片，URL 带 token query（沿用 `reportExportUrl` 模式）。

### 3.4 数据问答（query_answer）

- **输入**："本月成交总额多少"、"各分级客户数对比"。
- **输出规格**（复用报表引擎语义）：
  - 单值 → `{agg, field, filters}` 走 stat 语义；
  - 分组 → `{group: {kind, field}, agg, field, filters}` 走 chart 语义；
  - 清单 → `{columns, filters, limit ≤ 50}` 走 table 语义。
- **执行**：服务端 align（字段白名单 + 聚合类型校验，同 `align_report_config` 思路）→ 调 `dyn_engine`/`report_engine` 求值（时间口径默认"全部时间"，模型可指定 range）→ 结果随 reply 返回，卡片渲染数值/小表格。
- 回答不了（无此数据/权限不足）时模型应直接说，不硬编；权限不足在服务端表现为 404（不泄露表存在性）。

## 4. 后端实现要点

**新增文件**

```
backend/app/routers/assistant.py        # /chat /execute /download
backend/app/services/assistant_engine.py # 意图执行（填表/建表/Excel/问答求值）
backend/app/services/llm/prompts.py     # ASSISTANT_SYSTEM + build_assistant_prompt
backend/app/services/llm/gateway.py     # assist_chat(db, user, message, history, context) + align_assistant_action
backend/app/services/records_export.py  # export_blank_xlsx / export_records_xlsx
```

**提示词骨架（ASSISTANT_SYSTEM）**：角色（记录工具助手）→ 可用动作五种及各自的 JSON schema → 上下文（用户可见表清单 `[{id, label}]`、当前表字段四元组、当前日期）→ 硬规则（只输出 JSON；只用清单内的表和字段；枚举值必须从 options 选；日期值用 YYYY-MM-DD；筛选 op 白名单；无法确定目标表时在 reply 里追问而不是猜）。

**权限与安全**：

- `/chat`：context.table_id 需 `get_table_access`；模型可见的表清单只含当前用户可访问的表（json 模式 + 分享给我的）。
- `/execute`：每个动作重新校验——填表 `require_table("create")`、建表 RBAC `max_tables`、导出走 `require_table("view")`；payload 全部重新过 `coerce_payload`/`validate_fields`，不信任 chat 输出。
- 发给模型的样例数据经 `mask_sensitive` 脱敏；建表/填表落库写 `log_audit`。
- 频率保护：复用 axios 180s 超时；服务端对 /chat 做简单的用户级冷却（如 3s），防连点刷 token。

## 5. 前端实现要点

- **挂载**：`App.vue` 受保护布局内（el-container 尾部）加悬浮按钮 + `el-drawer`（size 420px）；登录/分享页不显示。当前路由变化时更新 `context`（`/t/:id` → table_id）。
- **抽屉组件 `AssistantPanel.vue`**：消息流（user 右/assistant 左气泡）、输入框（Enter 发送，支持粘贴多行文本）、加载态"AI 思考中…"；动作卡片子组件按 type 渲染：记录表格（el-table 可编辑）、字段清单（可编辑）、下载卡片、问答结果卡。
- **历史**：`localStorage` 按用户 id 存最近 50 条，抽屉顶部"清空对话"。
- **api/index.js** 末尾加 `assistantChat / assistantExecute / assistantDownloadUrl`。
- 小程序端：首期不做（四项能力中拍照识别填表、AI 建表在小程序已有独立入口）；后续用独立页面承接。

## 6. 分期

| 期 | 内容 | 理由 |
|---|---|---|
| P0 | 抽屉 + 聊天 + 智能填表 + AI 建表 | 写路径模式与现有 ai-assist 最同构，风险最低 |
| P1 | 数据问答 + 生成 Excel（含 records 导出基建） | 问答依赖受控聚合规格打磨；导出是新基建 |
| P2 | 图片输入（复用 recognize 多模态）、流式输出（SSE）、小程序端、会话持久化跨端同步 | 体验增强 |

## 7. 验证

- 冒烟测试（`smoke_test.py` 新增节）：monkeypatch provider.complete 返回固定 JSON（现有 webhook 测试同款手法）→ 断言 chat 输出结构、align 清洗（非法字段丢弃、坏值置空 + warning）、execute 的权限拒绝（无 create 权限 404/403）、填表成功且经 coerce 校验、建表落库、问答聚合值与报表引擎一致、Excel 下载 200。
- 手工：Drawer 各页面唤起、上下文感知（表页默认当前表）、预览编辑后确认、部分失败展示、清空对话。

