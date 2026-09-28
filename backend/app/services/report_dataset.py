"""数据集解析：把 source_json（多表左关联 + 计算字段）解析为统一的字段集与可查询对象。

- physical 基表：关联 + 计算字段下推为一个 SQL 子查询，报表引擎其余部分零改动（table.c[字段] 照常）；
- json 基表：记录加载后 Python 侧追加计算字段列（v1 json 基表不支持关联，校验阶段拦截）；
- 关联字段以 "{prefix}{field_name}" 进入数据集（如 "客户.等级"）。
"""
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import and_, select

from ..models import MetaField
from . import dyn_engine, json_store
from . import expr as expr_mod

MAX_JOINS = 3
COMPUTED_TYPES = {"int", "decimal", "bool", "varchar"}
SYSTEM_COLS = {"id", "created_at", "updated_at"}


# ---------- v3：模板级命名数据集 ----------

def dataset_source(d: dict) -> dict:
    """数据集定义 → source_json 形态（joins/computed_fields 复用既有解析）。"""
    return {"joins": d.get("joins") or [], "computed_fields": d.get("computed_fields") or []}


def template_datasets(tpl) -> list[dict]:
    """模板的数据集列表。v3 模板直接读 datasets_json；旧模板运行期合成 _default（行为不变）。"""
    datasets = getattr(tpl, "datasets_json", None)
    if datasets:
        return datasets
    src = getattr(tpl, "source_json", None) or {}
    table_id = getattr(tpl, "table_id", None)
    if not table_id:
        return []
    return [{
        "id": "_default", "name": "", "base_table_id": table_id,
        "joins": src.get("joins") or [], "computed_fields": src.get("computed_fields") or [],
    }]


def normalize_datasets(datasets: list | None, table_id: int | None, source: dict | None) -> list[dict]:
    """入参规范化（校验用）：v3 datasets 列表 或 旧格式（table_id+source）合成，统一为数据集定义列表。"""
    if datasets:
        ids: set = set()
        out = []
        for d in datasets:
            if not isinstance(d, dict):
                raise HTTPException(400, "数据集定义必须是对象")
            did = (d.get("id") or "").strip()
            if not did or did in ids:
                raise HTTPException(400, "数据集 id 缺失或重复")
            ids.add(did)
            if len(str(d.get("name") or "")) > 32:
                raise HTTPException(400, f"数据集名称不能超过 32 字：{did}")
            try:
                base_table_id = int(d.get("base_table_id"))
            except (TypeError, ValueError):
                raise HTTPException(400, f"数据集 {did} 的基表 id 无效")
            out.append({
                "id": did, "name": (d.get("name") or "").strip() or did,
                "base_table_id": base_table_id,
                "joins": d.get("joins") or [], "computed_fields": d.get("computed_fields") or [],
            })
        return out
    if table_id:
        src = source or {}
        return [{
            "id": "_default", "name": "", "base_table_id": table_id,
            "joins": src.get("joins") or [], "computed_fields": src.get("computed_fields") or [],
        }]
    return []


def _ns_field(field_name: str, label: str, data_type: str, widget=None, options=None):
    """关联/计算字段的轻量 MetaField 替身（引擎只读这些属性）。"""
    return SimpleNamespace(field_name=field_name, label=label, data_type=data_type,
                           widget=widget, options=options or {})


def has_source(source: dict | None) -> bool:
    return bool(source and ((source.get("joins") or []) or (source.get("computed_fields") or [])))


def validate_source(db, source: dict | None, base_table_id: int, base_mt, base_fields: list) -> None:
    """source_json 校验（建/改模板时调用）：关联 ≤3、物理表限定、前缀合法、on 字段存在、计算字段表达式合法。"""
    if not has_source(source):
        return
    if not isinstance(source, dict):
        raise HTTPException(400, "数据源配置必须是对象")
    if source.get("base_table_id") not in (None, base_table_id):
        raise HTTPException(400, "数据源的 base_table_id 必须与报表数据表一致")
    joins = source.get("joins") or []
    computed = source.get("computed_fields") or []
    if len(joins) > MAX_JOINS:
        raise HTTPException(400, f"最多关联 {MAX_JOINS} 张表")

    base_names = {f.field_name for f in base_fields}
    out_names = set(base_names) | SYSTEM_COLS
    prefixes = set()
    for j in joins:
        if base_mt.storage_mode != "physical":
            raise HTTPException(400, "多表关联仅支持物理存储的数据表（json 存储表请先转为物理表）")
        try:
            jid = int(j.get("table_id"))
        except (TypeError, ValueError):
            raise HTTPException(400, "关联表 id 无效")
        jmt, jfields = dyn_engine.load_meta(db, jid)
        if jmt is None:
            raise HTTPException(400, f"关联表不存在：{jid}")
        if jmt.storage_mode != "physical":
            raise HTTPException(400, f"关联表「{jmt.label}」不是物理存储，暂不支持关联")
        if jid == base_table_id:
            raise HTTPException(400, "暂不支持自关联")
        prefix = (j.get("prefix") or "").strip()
        if not prefix or len(prefix) > 16:
            raise HTTPException(400, "关联前缀必填且不超过 16 字")
        if prefix in prefixes:
            raise HTTPException(400, f"关联前缀重复：{prefix}")
        prefixes.add(prefix)
        jnames = {f.field_name for f in jfields}
        ons = j.get("on") or []
        if not ons:
            raise HTTPException(400, f"关联「{jmt.label}」缺少关联条件 on")
        for o in ons:
            if o.get("left") not in out_names:
                raise HTTPException(400, f"关联条件的左字段不在数据集中：{o.get('left')}")
            if o.get("right") not in jnames | SYSTEM_COLS:
                raise HTTPException(400, f"关联条件的右字段不在「{jmt.label}」中：{o.get('right')}")
        for f in jfields:
            out_name = prefix + f.field_name
            if out_name in out_names:
                raise HTTPException(400, f"关联字段与现有字段重名：{out_name}")
            out_names.add(out_name)

    cf_names = set()
    for cf in computed:
        name = (cf.get("name") or "").strip()
        if not name or len(name) > 32:
            raise HTTPException(400, "计算字段名必填且不超过 32 字")
        if name in out_names or name in cf_names:
            raise HTTPException(400, f"计算字段重名或与现有字段冲突：{name}")
        cf_names.add(name)
        ctype = cf.get("type")
        if ctype is not None and ctype not in COMPUTED_TYPES:
            raise HTTPException(400, f"计算字段类型无效：{ctype}")
        try:
            node = expr_mod.parse(cf.get("expr") or "", allow_fields=out_names)
        except expr_mod.ExprError as e:
            raise HTTPException(400, f"计算字段「{name}」：{e}")


def dataset_fields(db, base_fields: list, source: dict | None) -> list:
    """数据集输出字段：基表字段 + 关联字段（前缀）+ 计算字段。供校验/前端字段面板（需先过 validate_source）。"""
    fields_out = list(base_fields)
    for j in (source or {}).get("joins") or []:
        _, jfields = dyn_engine.load_meta(db, int(j["table_id"]))
        prefix = j["prefix"].strip()
        for f in jfields:
            fields_out.append(_ns_field(prefix + f.field_name, prefix + f.label, f.data_type, f.widget, f.options))
    for cf in (source or {}).get("computed_fields") or []:
        fbn = {f.field_name: f for f in fields_out}
        try:
            ctype = cf.get("type") or expr_mod.infer_type(expr_mod.parse(cf["expr"]), fbn)
        except expr_mod.ExprError:
            ctype = "decimal"
        fields_out.append(_ns_field(cf["name"].strip(), (cf.get("label") or cf["name"]).strip(), ctype))
    return fields_out


def build_sql_dataset(db, mt, source: dict | None):
    """physical 引擎：返回 (table_like, fields_out)。无 source 时与 dyn_engine.load_business 完全一致。"""
    _, base_fields, table = dyn_engine.load_business(db, mt.id)
    if not has_source(source):
        return table, base_fields

    dialect = db.bind.dialect.name if db.bind else "sqlite"
    cols: list = [table]
    froms = table
    fields_out = list(base_fields)
    resolver: dict = {}

    for i, j in enumerate(source.get("joins") or []):
        jmt, jfields, jtable = dyn_engine.load_business(db, int(j["table_id"]))
        alias = jtable.alias(f"j{i}")
        froms = froms.outerjoin(alias, and_(*[table.c[o["left"]] == alias.c[o["right"]] for o in j["on"]]))
        prefix = j["prefix"].strip()
        for f in jfields:
            out_name = prefix + f.field_name
            cols.append(alias.c[f.field_name].label(out_name))
            resolver[out_name] = alias.c[f.field_name]
            fields_out.append(_ns_field(out_name, prefix + f.label, f.data_type, f.widget, f.options))

    fbn = {f.field_name: f for f in fields_out}
    for cf in source.get("computed_fields") or []:
        name = cf["name"].strip()
        node = expr_mod.parse(cf["expr"], allow_fields=set(fbn) | SYSTEM_COLS)

        def resolve(n, _resolver=resolver, _table=table):
            col = _resolver.get(n)
            return col if col is not None else _table.c[n]

        cols.append(expr_mod.to_sql(node, resolve, dialect).label(name))
        ctype = cf.get("type") or expr_mod.infer_type(node, fbn)
        fields_out.append(_ns_field(name, (cf.get("label") or name).strip(), ctype))

    sub = select(*cols).select_from(froms).subquery("ds")
    return sub, fields_out


def load_json_dataset(db, mt, base_fields: list, source: dict | None):
    """json 引擎：返回 (fields_out, recs)。v1 仅计算字段（关联在 validate_source 已拦截）。"""
    recs = json_store.all_dicts(db, mt.id, base_fields, normalized=True)
    fields_out = list(base_fields)
    for cf in (source or {}).get("computed_fields") or []:
        name = cf["name"].strip()
        fbn = {f.field_name: f for f in fields_out}
        node = expr_mod.parse(cf["expr"], allow_fields=set(fbn) | SYSTEM_COLS)
        for r in recs:
            try:
                r[name] = expr_mod.evaluate(node, r)
            except Exception:  # noqa: BLE001 — 单行求值失败按 NULL 处理（对齐 SQL）
                r[name] = None
        ctype = cf.get("type") or expr_mod.infer_type(node, fbn)
        fields_out.append(_ns_field(name, (cf.get("label") or name).strip(), ctype))
    return fields_out, recs
