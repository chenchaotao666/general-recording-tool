"""AI 生成工作流：自然语言需求 → {trigger, nodes, edges}。

流程：节点目录（注册表 schema）+ 用户自有表结构 → LLM → align 清洗 →
engine.validate_definition 兜底，失败把错误回喂重试一次（与 assist_task 同一套路）。
生成结果不落库，由前端画布加载后用户确认保存。
"""
import difflib
import json
import re

from sqlalchemy.orm import Session

from ...models import MetaField, MetaTable, User
from ..llm.base import LLMError
from ..llm.gateway import extract_json, get_default_provider
from .engine import WorkflowError, validate_definition
from .registry import REGISTRY

MAX_NODES = 12

SYSTEM = "你是工作流编排助手，把用户的办公自动化需求转成工作流定义 JSON。只输出 JSON，不要输出任何解释。"

TRIGGER_TYPES = {"manual", "interval", "cron", "record_created", "record_updated", "webhook", "form"}

# 记录的系统字段：不作为业务字段出现在 MetaField 里，但筛选/排序合法
SYS_FIELDS = {"id", "created_at", "updated_at"}
# 日期类操作符（相对日期）：字段被编造时，若表里有唯一日期字段可据此纠正
DATE_OPS = {"today", "past_days", "older_than_days", "within_days"}


def _tables_context(db: Session, user: User) -> tuple[str, set[int], dict[int, list]]:
    """用户自有表（工作流以归属人身份执行，只暴露自有表）。

    返回 (提示词文本, 表 id 集合, {table_id: [MetaField]})——字段映射供 align 校正字段引用用。
    """
    tables = (
        db.query(MetaTable)
        .filter(MetaTable.owner_id == user.id, MetaTable.status == "active")
        .order_by(MetaTable.id)
        .all()
    )
    if not tables:
        return "（用户还没有数据表）", set(), {}
    fields = (
        db.query(MetaField)
        .filter(MetaField.table_id.in_([t.id for t in tables]))
        .order_by(MetaField.table_id, MetaField.sort_order)
        .all()
    )
    by_table: dict[int, list] = {}
    for f in fields:
        by_table.setdefault(f.table_id, []).append(f)
    lines = []
    for t in tables:
        fs = "、".join(f"{f.label}({f.field_name},{f.data_type})" for f in by_table.get(t.id, []))
        lines.append(f"- table_id={t.id} 「{t.label}」字段：{fs}")
    return "\n".join(lines), {t.id for t in tables}, by_table


def _nodes_context() -> str:
    lines = []
    for nt in REGISTRY.values():
        schema = json.dumps(nt.config_schema, ensure_ascii=False)
        lines.append(f"- type={nt.type} 「{nt.name}」{nt.description}\n  config_schema: {schema}")
    return "\n".join(lines)


def build_workflow_prompt(description: str, tables_ctx: str) -> str:
    return f"""用户需求：{description}

可用数据表：
{tables_ctx}

可用节点类型：
{_nodes_context()}

输出 JSON 格式：
{{
  "name": "工作流名称",
  "description": "一句话说明",
  "trigger": {{...}},
  "nodes": [{{"id": "q_1", "type": "query_records", "name": "查询记录", "config": {{...}}}}],
  "edges": [{{"from": "q_1", "to": "llm_1"}}, {{"from": "c_1", "to": "send_1", "branch": "true"}}],
  "notes": "需要用户自行补充的内容（如接收人邮箱、具体阈值），没有则留空字符串"
}}

规则：
1. trigger 取值：被动调用 {{"type":"manual"}}（不自动触发，子流程必须是这种）；定时 {{"type":"interval","minutes":分钟数}} 或 {{"type":"cron","expr":"分 时 日 月 周"}}；
   记录新增 {{"type":"record_created","table_id":表id}}；记录修改 {{"type":"record_updated","table_id":表id}}；Webhook {{"type":"webhook"}}；
   公开表单 {{"type":"form","table_id":表id}}（外部人员填表提交后写入该表并触发流程，变量同记录新增）
2. 节点 id 只用小写字母/数字/下划线，简短有意义（如 q_1、llm_1、c_1、send_1），总数不超过 {MAX_NODES} 个
3. 节点的 config 必须符合其 config_schema；数据表节点/触发器的 table_id 只能取自上面的可用数据表
4. 模板变量：{{trigger.record.字段名}}（记录触发）、{{trigger.params.xxx}}（手动/webhook）、
   {{nodes.节点id.records.0.字段名}}（查询结果第一条）、{{nodes.节点id.count}}、{{nodes.节点id.text}}（LLM 文本输出）、
   {{nodes.节点id.data.键}}（LLM JSON 输出）；
   内置时间变量：{{now.today}}（今天）、{{now.yesterday}}（昨天）、{{now.week_start}}（本周一）、
   {{now.last_week_start}}（上周一）、{{now.last_week_end}}（上周日）、{{now.month_start}}（本月 1 日）、
   {{now.last_month_start}}（上月 1 日）、{{now.last_month_end}}（上月最后一日）——筛选值/排序字段里都可以插
5. condition 节点：config.record 必须填整体引用（如 "{{trigger.record}}" 或 "{{nodes.q_1.records.0}}"）；
   它的出边必须分别带 "branch":"true" 和 "branch":"false"；
   switch（多路分支）节点：config.cases 是 [{{"label":"分支名","field","op","value"}}]，
   它的每条出边带 "branch":"分支名"，另需一条 "branch":"default" 的兜底出边；
   foreach（逐条处理）节点：config.items 填列表整体引用（如 "{{nodes.q_1.records}}"），
   出边两条——"branch":"loop" 连循环体、"branch":"done" 连循环结束后的节点，
   循环体最后一个节点再用一条普通边连回 foreach 节点形成循环；
   循环体内用 {{nodes.foreach节点id.item.字段名}} 引用当前条目
6. 流程图剔除 foreach 的回边后必须是 DAG，且只有一个没有入边的起始节点
7. 筛选条件（filters/rules）的操作符只能用：eq（等于）、ne（不等于）、gt、gte、lt、lte、contains（包含）、
   null（为空）、not_null（不为空）、today（当天）、past_days（过去 N 天）、older_than_days（早于 N 天前）、within_days（未来 N 天内）；
   "昨天"用 {{"field": "日期字段", "op": "past_days", "value": 1}} 这类相对日期操作符表达，
   模板变量只有第 4 条列出的单花括号形式，不要发明其他变量
8. filters/rules/order_by/watch_fields 里的 field 一律使用上面数据表列出的英文字段名（括号里的 field_name），
   不要填中文显示名，也不要编造表中不存在的字段名
9. condition 节点的 rules 涉及某张数据表的字段时，config.table_id 必须填那张表的 id（用于提供字段类型和字段清单）
10. 只输出 JSON"""


def _correct_field(raw, fields: list, notes: list[str], op: str | None = None) -> str | None:
    """把 LLM 给的字段引用对齐到真实 field_name。

    依次尝试：系统字段 → field_name 精确 → 中文显示名精确 →
    日期操作符 + 表里唯一日期字段 → 字段名/显示名模糊匹配。对不上返回 None。
    """
    name = str(raw or "").strip()
    if not name:
        return None
    if "{" in name:
        return name   # 模板变量（如 {trigger.params.sort_field}）：运行时渲染，不做字段对齐
    if name in SYS_FIELDS:
        return name
    by_name = {f.field_name: f for f in fields}
    if name in by_name:
        return name
    by_label = {f.label: f for f in fields}
    if name in by_label:
        f = by_label[name]
        notes.append(f"字段「{name}」已更正为字段名 {f.field_name}")
        return f.field_name
    if op in DATE_OPS:
        dates = [f for f in fields if f.data_type in ("date", "datetime")]
        if len(dates) == 1:
            notes.append(f"字段「{name}」不存在，已按日期条件更正为「{dates[0].label}」({dates[0].field_name})")
            return dates[0].field_name
    candidates = list(by_name) + list(by_label)
    close = difflib.get_close_matches(name, candidates, n=1, cutoff=0.6)
    if close:
        f = by_name.get(close[0]) or by_label[close[0]]
        notes.append(f"字段「{name}」不存在，已更正为「{f.label}」({f.field_name})")
        return f.field_name
    return None


def _align_field_refs(config: dict, fields: list, notes: list[str], node_desc: str) -> None:
    """就地校正节点 config 里的字段引用（filters/match_filters/rules/order_by）。"""
    for key in ("filters", "match_filters"):
        fobj = config.get(key)
        if isinstance(fobj, dict) and isinstance(fobj.get("rules"), list):
            kept = []
            for r in fobj["rules"]:
                if not isinstance(r, dict):
                    continue
                fixed = _correct_field(r.get("field"), fields, notes, op=r.get("op"))
                if fixed is None:
                    notes.append(f"{node_desc}的筛选字段「{r.get('field')}」不存在，该条件已丢弃")
                    continue
                r["field"] = fixed
                kept.append(r)
            fobj["rules"] = kept
    if isinstance(config.get("rules"), list):
        kept = []
        for r in config["rules"]:
            if not isinstance(r, dict):
                continue
            fixed = _correct_field(r.get("field"), fields, notes, op=r.get("op"))
            if fixed is None:
                notes.append(f"{node_desc}的条件字段「{r.get('field')}」不存在，该规则已丢弃")
                continue
            r["field"] = fixed
            kept.append(r)
        config["rules"] = kept
    if config.get("order_by"):
        fixed = _correct_field(config["order_by"], fields, notes)
        if fixed is None:
            notes.append(f"{node_desc}的排序字段「{config['order_by']}」不存在，已改为默认排序")
            config.pop("order_by", None)
        else:
            config["order_by"] = fixed


def _sanitize_id(raw: str, used: set[str]) -> str:
    base = re.sub(r"[^a-z0-9_]", "_", str(raw or "").lower()).strip("_") or "node"
    base = base[:60]
    nid, i = base, 2
    while nid in used:
        nid = f"{base}_{i}"
        i += 1
    used.add(nid)
    return nid


def align_workflow_definition(data: dict, table_ids: set[int],
                              fields_by_table: dict[int, list] | None = None) -> dict:
    """把 LLM 输出对齐到合法定义：清洗触发器/节点/边，非法项丢弃并记入 notes。"""
    notes_extra = []
    fields_by_table = fields_by_table or {}

    # 触发器
    t = data.get("trigger") or {}
    ttype = t.get("type") if t.get("type") in TRIGGER_TYPES else "manual"
    if ttype in ("record_created", "record_updated", "form"):
        tid = t.get("table_id")
        if tid not in table_ids:
            notes_extra.append("触发的数据表无效，已改为被动调用")
            trigger = {"type": "manual"}
        else:
            trigger = {"type": ttype, "table_id": tid}
            if ttype == "record_updated":
                tfields = fields_by_table.get(tid, [])
                watch = []
                for w in (t.get("watch_fields") or []):
                    if not isinstance(w, str):
                        continue
                    fixed = _correct_field(w, tfields, notes_extra)
                    if fixed and fixed not in SYS_FIELDS:
                        watch.append(fixed)
                dropped = len(t.get("watch_fields") or []) - len(watch)
                if dropped > 0:
                    notes_extra.append("部分监听字段不存在，已忽略")
                if watch:
                    trigger["watch_fields"] = watch
    elif ttype == "interval":
        try:
            trigger = {"type": "interval", "minutes": max(int(t.get("minutes") or 60), 1)}
        except (TypeError, ValueError):
            trigger = {"type": "interval", "minutes": 60}
    elif ttype == "cron":
        trigger = {"type": "cron", "expr": str(t.get("expr") or "0 9 * * *")}
    elif ttype == "webhook":
        trigger = {"type": "webhook"}
    else:
        trigger = {"type": "manual"}

    # 节点：类型过滤 + id 清洗重映射 + config 按 schema 过滤
    nodes = []
    used_ids: set[str] = set()
    id_map: dict[str, str] = {}
    for n in (data.get("nodes") or [])[:MAX_NODES]:
        if not isinstance(n, dict):
            continue
        ntype = n.get("type")
        cls = REGISTRY.get(ntype)
        if cls is None:
            notes_extra.append(f"未知节点类型 {ntype} 已丢弃")
            continue
        config = n.get("config") if isinstance(n.get("config"), dict) else {}
        props = (cls.config_schema or {}).get("properties") or {}
        if props:
            dropped = [k for k in config if k not in props]
            if dropped:
                notes_extra.append(f"节点 {ntype} 的无效配置项已丢弃：{'、'.join(dropped)}")
            config = {k: v for k, v in config.items() if k in props}
        tid = config.get("table_id")
        if "table_id" in props and isinstance(tid, int) and tid not in table_ids:
            notes_extra.append(f"节点 {ntype} 引用了无权限的数据表，节点已丢弃")
            continue
        # 字段引用校正：LLM 编造的英文字段名 → 真实 field_name，对不上就丢弃
        if isinstance(tid, int) and tid in fields_by_table:
            _align_field_refs(config, fields_by_table[tid], notes_extra, f"节点 {ntype}")
        nid = _sanitize_id(n.get("id") or ntype, used_ids)
        id_map[str(n.get("id") or "")] = nid
        nodes.append({
            "id": nid, "type": ntype,
            "name": str(n.get("name") or cls.name)[:64],
            "config": config,
        })
    if not nodes:
        raise LLMError("模型没有生成任何有效节点，请换一种描述再试")

    # 边：只保留存活节点之间；branch 只出现在 condition 节点的出边上
    node_types = {n["id"]: n["type"] for n in nodes}
    edges = []
    for e in data.get("edges") or []:
        if not isinstance(e, dict):
            continue
        src, dst = id_map.get(str(e.get("from") or "")), id_map.get(str(e.get("to") or ""))
        if not src or not dst or src not in node_types or dst not in node_types:
            continue
        edge = {"from": src, "to": dst}
        br = e.get("branch")
        if node_types[src] == "condition" and br in ("true", "false"):
            edge["branch"] = br
        elif node_types[src] == "switch" and isinstance(br, str) and br.strip():
            edge["branch"] = br.strip()   # switch 出边的 branch 是分支名或 default
        elif node_types[src] == "foreach" and br in ("loop", "done"):
            edge["branch"] = br
        edges.append(edge)

    notes = str(data.get("notes") or "")
    if notes_extra:
        notes = (notes + "；" if notes else "") + "；".join(notes_extra)
    return {
        "name": str(data.get("name") or "")[:128] or "AI 工作流",
        "description": str(data.get("description") or "")[:500],
        "trigger": trigger, "nodes": nodes, "edges": edges,
        "notes": notes,
    }


def assist_workflow(db: Session, user: User, description: str) -> dict:
    """LLM 生成工作流定义；JSON 解析失败或定义校验失败各回喂重试一次。"""
    provider = get_default_provider(db)
    tables_ctx, table_ids, fields_by_table = _tables_context(db, user)
    prompt = build_workflow_prompt(description, tables_ctx)

    last_err: Exception | None = None
    for attempt in range(2):
        current = prompt if attempt == 0 else (
            f"你上次的输出有问题：{last_err}。请修正后重新输出，只输出 JSON。\n\n原始任务：\n{prompt}"
        )
        try:
            raw = provider.complete(current, system=SYSTEM)
            data = extract_json(raw)
            if not isinstance(data.get("nodes"), list):
                raise ValueError("输出缺少 nodes 数组")
            definition = align_workflow_definition(data, table_ids, fields_by_table)
            validate_definition(
                db, definition["trigger"], definition["nodes"], definition["edges"], user,
            )
            return definition
        except (LLMError, WorkflowError) as e:
            last_err = e
        except Exception as e:
            last_err = e
    raise LLMError(f"模型生成的工作流不合法：{last_err}")
