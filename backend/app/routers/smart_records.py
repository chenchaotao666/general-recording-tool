"""智能表网格查询（设计文档 §16.3）：视图配置服务端应用——合并个人覆盖 → DSL 适配 → 筛选排序 → 聚合分页。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import MetaView, MetaViewPref
from ..services import dyn_engine, json_store, view_config
from ..services.meta_service import get_meta_fields
from ..services.pyquery import match_filters, sort_records_multi
from ..utils.access import TableAccess, require_table
from ..utils.context import Context, get_current_context

router = APIRouter(prefix="/api/smart", tags=["smart-records"])


@router.get("/tables/{table_id}/grid")
def grid_query(table_id: int, view_id: int | None = None, page: int = 1, page_size: int = 200,
               db: Session = Depends(get_db),
               access: TableAccess = Depends(require_table("view"))):
    """一次请求给齐网格渲染所需：生效视图配置 + 字段 + 当前页记录 + 聚合 + 我的权限。"""
    mt = access.table
    if mt.storage_mode != "json":
        raise HTTPException(400, "智能表网格仅支持 JSON 存储模式的表")
    user = access.ctx.user

    # 视图：指定 / 默认 / 第一个
    vq = db.query(MetaView).filter_by(table_id=table_id)
    view = vq.filter_by(id=view_id).first() if view_id else None
    if view is None:
        view = vq.order_by(MetaView.is_default.desc(), MetaView.id).first()
    vcfg = (view.config or {}) if view else {}

    # 个人覆盖（仅你可见的筛选）
    pref = None
    if view:
        pref = db.query(MetaViewPref).filter_by(view_id=view.id, user_id=user.id).first()
    effective = view_config.merge_pref(vcfg, pref.config if pref else None)

    fields = get_meta_fields(db, table_id)
    fields_by_name = {f.field_name: f for f in fields}

    # 筛选 → 排序 → 聚合（json 模式全量内存求值，约定单表 ≤1 万行）
    rules = view_config.conditions_to_rules(effective.get("filters"))
    recs = json_store.all_dicts(db, table_id, fields, normalized=True)
    if rules:
        recs = [r for r in recs if match_filters(r, fields_by_name, {"logic": "AND", "rules": rules})]
    aggs = view_config.compute_aggregations(recs, effective.get("aggregations"), fields)
    total = len(recs)
    recs = sort_records_multi(recs, effective.get("sorts"), fields_by_name)

    page = max(page, 1)
    page_size = min(max(page_size, 1), dyn_engine.MAX_PAGE_SIZE)
    items = [
        {k: dyn_engine.serialize_value(v) for k, v in r.items()}
        for r in recs[(page - 1) * page_size: page * page_size]
    ]

    return {
        "items": items, "total": total, "aggregations": aggs,
        "view": {"id": view.id, "name": view.name, "type": view.type, "config": effective,
                 "is_default": bool(view.is_default)} if view else None,
        "fields": [
            {"id": f.id, "field_name": f.field_name, "label": f.label, "data_type": f.data_type,
             "field_type": f.field_type, "options": f.options or {}, "sort_order": f.sort_order}
            for f in fields
        ],
        "my_perms": access.my_perms(),
    }


@router.post("/tables/{table_id}/records:batch-delete")
def batch_delete(table_id: int, payload: dict, db: Session = Depends(get_db),
                 access: TableAccess = Depends(require_table("delete"))):
    """批量删除记录（撤销栈靠前端快照重建）。"""
    ids = payload.get("ids") or []
    if not isinstance(ids, list) or not ids or len(ids) > 500:
        raise HTTPException(400, "ids 必须是非空数组（最多 500 条）")
    mt = access.table
    fields = get_meta_fields(db, table_id)
    deleted = 0
    for rid in ids:
        try:
            json_store.delete_record(db, table_id, int(rid), fields, user=access.ctx.user.username)
            deleted += 1
        except HTTPException:
            continue
    db.commit()
    return {"deleted": deleted}
