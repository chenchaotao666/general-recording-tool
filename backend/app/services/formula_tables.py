"""公式整表引用（[#表] / [#表.字段]）：数据提供与依赖刷新。

- scope(db, tenant_id)：求值期间提供「表 id → 行列表」解析（同租户 json 表，按次缓存），
  行值与本行引用同样经 formula_context 规整（选项→文本、日期→日期）。
- refresh_dependents(db, table_id)：某表数据变化后，重算所有整表引用了它的公式表（含本表自引用），
  被重算的表若又被别的表引用则继续传递（visited 防环）。整表重算不触发自动化 / 不改最后编辑时间。

数据可见性：与查找引用一致——公式结果按所在表的权限展示，引用表的原始数据不直接返回给查看者。
"""
from __future__ import annotations

import logging
import re
from contextlib import contextmanager
from contextvars import ContextVar

from sqlalchemy.orm import Session

from ..models import MetaField, MetaTable
from . import expr

log = logging.getLogger(__name__)
_REF_RE = re.compile(r"\[#(\d+)(?:\.[^\]]+)?\]")
USER_NAME_RESOLVER = ContextVar("formula_user_name_resolver", default=None)


def _user_loader(db: Session, tenant_id: int | None):
    from ..models import User, TenantMember
    cache = {}

    def load(value):
        try:
            user_id = int(value)
        except (TypeError, ValueError):
            return str(value)
        if user_id not in cache:
            query = db.query(User.username).filter(User.id == user_id)
            if tenant_id is not None:
                query = query.join(TenantMember, TenantMember.user_id == User.id).filter(TenantMember.tenant_id == tenant_id)
            cache[user_id] = query.scalar() or '未知用户'
        return cache[user_id]
    return load


def table_refs_of(formula: str) -> set[int]:
    return {int(x) for x in _REF_RE.findall(formula or "")}


def _loader(db: Session, tenant_id: int | None):
    from . import json_store
    from .dyn_engine import _numify, formula_context
    from .meta_service import get_meta_fields
    cache: dict[int, list | None] = {}

    def load(table_id: int):
        if table_id in cache:
            return cache[table_id]
        mt = db.get(MetaTable, table_id)
        if not mt or mt.storage_mode != "json" or (tenant_id is not None and mt.tenant_id != tenant_id):
            cache[table_id] = None
            return None
        fields = get_meta_fields(db, table_id)
        cache[table_id] = [_numify(formula_context(fields, r)) for r in json_store.all_dicts(db, table_id, fields)]
        return cache[table_id]
    return load


@contextmanager
def scope(db: Session, tenant_id: int | None):
    token = expr.TABLE_RESOLVER.set(_loader(db, tenant_id))
    user_token = USER_NAME_RESOLVER.set(_user_loader(db, tenant_id))
    try:
        yield
    finally:
        USER_NAME_RESOLVER.reset(user_token)
        expr.TABLE_RESOLVER.reset(token)


def dependents(db: Session, table_id: int, tenant_id: int | None) -> list[int]:
    """整表引用了 table_id 的公式所在表（同租户 json 表）。"""
    q = (db.query(MetaField.table_id, MetaField.options).join(MetaTable, MetaTable.id == MetaField.table_id)
         .filter(MetaTable.storage_mode == "json", MetaField.field_type == "formula"))
    if tenant_id is not None:
        q = q.filter(MetaTable.tenant_id == tenant_id)
    out = []
    for tid, opts in q.all():
        if table_id in table_refs_of((opts or {}).get("formula") or "") and tid not in out:
            out.append(tid)
    return out


def refresh_dependents(db: Session, table_id: int, _visited: set | None = None) -> None:
    from . import json_store
    from .meta_service import get_meta_fields
    visited = _visited if _visited is not None else set()
    mt = db.get(MetaTable, table_id)
    if not mt:
        return
    for tid in dependents(db, table_id, mt.tenant_id):
        if tid in visited:
            continue
        visited.add(tid)
        dep = db.get(MetaTable, tid)
        try:
            changed = json_store.recompute_formulas(db, dep, get_meta_fields(db, tid))
        except Exception:  # noqa: BLE001 — 单表重算失败不影响其余依赖表
            log.exception("formula refresh failed for table %s", tid)
            db.rollback()
            continue
        if changed and tid != table_id:
            refresh_dependents(db, tid, visited)
