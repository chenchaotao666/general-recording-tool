"""数据表管理：确认建表 + 导入、表/字段元数据查询与调整、删表、分享授权。"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Group, GroupMember, ImportBatch, MetaField, MetaTable, TableShare, User
from ..schemas import TableCreate, TableShareIn, TableUpdate
from ..services import entitlement, meta_service
from ..services.dyn_engine import log_audit
from ..services.excel_parser import ExcelParseError, build_headers, read_sheet
from ..services.meta_service import MetaError
from ..services.notify import notify_user
from ..services.typemap import coerce_value
from ..services.uploads import UploadNotFound, get_upload_filename, get_upload_path
from ..utils.access import TableAccess, get_table_access, require_table
from ..utils.context import Context, get_current_context
from ..utils.rbac import has_perm, tenant_role
from .friends import is_friend, same_group

router = APIRouter(prefix="/api/tables", tags=["tables"])

IMPORT_BATCH_SIZE = 500
FAIL_DETAIL_CAP = 200


def _share_perms(db: Session, mt: MetaTable, user: User, ctx: Context | None = None) -> dict:
    """table_out 附加字段：我的权限 + 主人用户名。"""
    access = get_table_access(db, mt.id, user, ctx)
    owner = db.get(User, mt.owner_id) if mt.owner_id else None
    return {
        "is_owner": access.is_owner,
        "my_perms": {
            "can_view": access.can_view, "can_create": access.can_create,
            "can_edit": access.can_edit, "can_delete": access.can_delete,
        },
        "owner_label": owner.username if owner else "",
    }


@router.get("")
def list_tables(db: Session = Depends(get_db), ctx: Context = Depends(get_current_context),
                all: bool = False):
    """我的表 + 分享给我的表（含用户组分享，可跨租户——好友分享能力不变）。
    all=true（仅当前租户 admin 生效）：返回本租户全部表，供关联配置等跨属主选表场景。"""
    user = ctx.user
    if all:
        if not ctx.is_tenant_admin:
            raise HTTPException(403, "需要工作空间管理员权限")
        rows = (db.query(MetaTable).filter(MetaTable.tenant_id == ctx.tenant.id)
                .order_by(MetaTable.id.desc()).all())
        return [meta_service.table_out(db, t, with_fields=False, access=_share_perms(db, t, user, ctx)) for t in rows]
    shared_ids = [
        s.table_id for s in db.query(TableShare)
        .outerjoin(GroupMember, TableShare.group_id == GroupMember.group_id)
        .filter(
            or_(TableShare.user_id == user.id, GroupMember.user_id == user.id),
            TableShare.can_view == True,  # noqa: E712
            TableShare.status == "accepted",
        )
    ]
    q = db.query(MetaTable).filter(or_(MetaTable.owner_id == user.id, MetaTable.id.in_(shared_ids or [-1])))
    rows = q.order_by(MetaTable.id.desc()).all()
    return [meta_service.table_out(db, t, with_fields=False, access=_share_perms(db, t, user, ctx)) for t in rows]


@router.get("/{table_id}")
def get_table(table_id: int, db: Session = Depends(get_db),
              access: TableAccess = Depends(require_table("view"))):
    return meta_service.table_out(db, access.table,
                                  access=_share_perms(db, access.table, access.ctx.user, access.ctx))


@router.post("")
def create_table(payload: TableCreate, db: Session = Depends(get_db),
                 ctx: Context = Depends(get_current_context)):
    user = ctx.user
    role = ctx.membership.role if ctx.membership else ("admin" if ctx.is_platform_admin else None)
    # 权限门槛：独立物理表需「创建独立表」权限；数据表数量受套餐配额约束（宽限期模型）
    if payload.storage_mode == "physical" and not has_perm(db, role, "create_physical_table"):
        raise HTTPException(403, "独立物理表需要「创建独立表」权限")
    entitlement.assert_tenant_writable(db, ctx.tenant.id)
    entitlement.check_quota(db, ctx.tenant.id, "max_tables")
    try:
        mt = meta_service.create_business_table(db, payload, owner_id=user.id, tenant_id=ctx.tenant.id)
    except MetaError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(400, f"建表失败：{e}")

    entitlement.bump_usage(db, ctx.tenant.id, "table_count", 1)
    log_audit(db, "create_table", mt.id, after={"name": mt.name, "label": mt.label},
              user=user.username, tenant_id=ctx.tenant.id)
    db.commit()

    report = None
    if payload.source:
        report = _run_import(db, mt, payload.source)
    return {"table": meta_service.table_out(db, mt), "import_report": report}


@router.put("/{table_id}")
def update_table(table_id: int, payload: TableUpdate, db: Session = Depends(get_db),
                 access: TableAccess = Depends(require_table("view"))):
    # 改表结构仅主人/租户 admin（分享者的编辑权限只到记录级）
    if not access.is_owner and not access.is_admin:
        raise HTTPException(404, "数据表不存在")
    entitlement.assert_tenant_writable(db, access.table.tenant_id)
    mt = access.table
    if payload.label is not None:
        mt.label = payload.label
    for fu in (payload.fields or []):
        f = db.get(MetaField, fu.id)
        if not f or f.table_id != table_id:
            continue
        for attr in ("label", "nullable", "widget", "options", "sort_order"):
            v = getattr(fu, attr)
            if v is not None:
                setattr(f, attr, v)
    db.commit()
    return meta_service.table_out(db, mt)


@router.delete("/{table_id}")
def delete_table(table_id: int, db: Session = Depends(get_db),
                 access: TableAccess = Depends(require_table("view"))):
    # 删表仅主人/租户 admin（删除授权不含删表结构）
    if not access.is_owner and not access.is_admin:
        raise HTTPException(404, "数据表不存在")
    entitlement.assert_tenant_writable(db, access.table.tenant_id)
    mt = access.table
    # 用量回收：表数 -1、记录数 -n（该行表全部记录）
    row_count = meta_service.record_count(db, mt)
    log_audit(db, "drop_table", mt.id, before={"name": mt.name, "label": mt.label},
              user=access.ctx.user.username, tenant_id=mt.tenant_id)
    meta_service.drop_business_table(db, mt)
    entitlement.bump_usage(db, mt.tenant_id, "table_count", -1)
    if row_count:
        entitlement.bump_usage(db, mt.tenant_id, "row_count", -row_count)
    db.commit()
    return {"ok": True}


class AlterIn(BaseModel):
    ops: list[dict]   # [{op: add_field|update_field|delete_field|rename_field, ...}]


@router.post("/{table_id}/alter")
def alter_table(table_id: int, payload: AlterIn, db: Session = Depends(get_db),
                access: TableAccess = Depends(require_table("view"))):
    """表结构变更（加/删/改/重命名字段）：仅主人/租户 admin。任何一步非法整体回滚。"""
    if not access.is_owner and not access.is_admin:
        raise HTTPException(404, "数据表不存在")
    if not payload.ops:
        raise HTTPException(400, "没有要执行的结构变更")
    entitlement.assert_tenant_writable(db, access.table.tenant_id)
    try:
        result = meta_service.alter_business_table(db, access.table, payload.ops)
    except MetaError as e:
        db.rollback()
        raise HTTPException(400, str(e))
    log_audit(db, "alter_table", table_id, after={"ops": payload.ops},
              user=access.ctx.user.username, tenant_id=access.table.tenant_id)
    db.commit()
    return {**result, "table": meta_service.table_out(db, access.table)}


# ---------- 分享授权（主人且有「分享」权限，或租户 admin；好友分享可跨租户） ----------

def _require_sharer(db: Session, mt: MetaTable, user: User) -> None:
    role = tenant_role(db, user, mt.tenant_id)
    if role == "admin":
        return
    if mt.owner_id != user.id:
        raise HTTPException(404, "数据表不存在")
    if not has_perm(db, role, "share"):
        raise HTTPException(403, "分享需要「分享」权限")


def _share_out(db: Session, s: TableShare) -> dict:
    if s.group_id:
        g = db.get(Group, s.group_id)
        target, target_type = (g.name if g else s.group_id), "group"
    else:
        u = db.get(User, s.user_id)
        target, target_type = (u.username if u else s.user_id), "user"
    return {
        "id": s.id, "target": target, "target_type": target_type,
        "can_view": s.can_view, "can_create": s.can_create,
        "can_edit": s.can_edit, "can_delete": s.can_delete,
        "status": s.status,
    }


@router.get("/{table_id}/shares")
def list_shares(table_id: int, db: Session = Depends(get_db),
                access: TableAccess = Depends(require_table("view"))):
    _require_sharer(db, access.table, access.ctx.user)
    shares = db.query(TableShare).filter_by(table_id=table_id).all()
    return [_share_out(db, s) for s in shares]


@router.post("/{table_id}/shares")
def put_share(table_id: int, payload: TableShareIn, db: Session = Depends(get_db),
              access: TableAccess = Depends(require_table("view"))):
    mt = access.table
    user = access.ctx.user
    _require_sharer(db, mt, user)
    is_admin = tenant_role(db, user, mt.tenant_id) == "admin"
    notify_target = None
    notify_members: list[int] = []
    if payload.group_id is not None:
        group = db.get(Group, payload.group_id)
        if not group:
            raise HTTPException(404, "用户组不存在")
        # 组分享只能发到自己所在的组（admin 豁免）；组成员资格即同意，即时生效
        if not is_admin and not db.query(GroupMember).filter_by(
            group_id=payload.group_id, user_id=user.id
        ).first():
            raise HTTPException(403, "只能分享到自己所在的组")
        share = db.query(TableShare).filter_by(table_id=table_id, group_id=payload.group_id).first()
        if not share:
            share = TableShare(table_id=table_id, group_id=payload.group_id, shared_by=user.id)
            db.add(share)
            # 即时生效，但告知每个成员（更新权限不重复通知）
            notify_members = [
                m.user_id for m in db.query(GroupMember).filter_by(group_id=payload.group_id).all()
                if m.user_id != user.id
            ]
        share.status = "accepted"
    else:
        target = None
        if payload.user_id is not None:
            target = db.get(User, payload.user_id)
        elif payload.username:
            target = db.query(User).filter(User.username == payload.username.strip()).first()
        if not target:
            raise HTTPException(404, "用户不存在" if (payload.user_id is not None or payload.username) else "请指定分享的用户或用户组")
        if target.id == mt.owner_id:
            raise HTTPException(400, "不能分享给表主人")
        # 直发对象约束（admin 豁免）：只能分享给好友或同组用户
        if not is_admin and not (is_friend(db, user.id, target.id) or same_group(db, user.id, target.id)):
            raise HTTPException(403, "只能分享给好友或同组用户")
        share = db.query(TableShare).filter_by(table_id=table_id, user_id=target.id).first()
        if not share:
            share = TableShare(table_id=table_id, user_id=target.id, shared_by=user.id, status="pending")
            db.add(share)
            notify_target = target
        elif share.status == "rejected":
            share.status = "pending"   # 被拒绝后重新发起
            notify_target = target
        # accepted 仅更新权限不打扰对方；pending 更新权限不重复通知
    share.can_view = payload.can_view
    share.can_create = payload.can_create
    share.can_edit = payload.can_edit
    share.can_delete = payload.can_delete
    if notify_target:
        notify_user(db, notify_target.id, "收到表分享",
                    f"{user.username} 把数据表「{mt.label}」分享给你，请确认", link="/tables")
    for mid in notify_members:
        notify_user(db, mid, "收到表分享",
                    f"{user.username} 把数据表「{mt.label}」分享给你所在的组「{group.name}」，现在可以查看",
                    link="/tables")
    db.commit()
    return _share_out(db, share)


@router.delete("/{table_id}/shares/{share_id}")
def delete_share(table_id: int, share_id: int, db: Session = Depends(get_db),
                 access: TableAccess = Depends(require_table("view"))):
    _require_sharer(db, access.table, access.ctx.user)
    share = db.get(TableShare, share_id)
    if not share or share.table_id != table_id:
        raise HTTPException(404, "分享不存在")
    db.delete(share)
    db.commit()
    return {"ok": True}


def _run_import(db: Session, mt, source) -> dict:
    """把 Excel 数据按字段映射批量写入业务表，返回导入报告。
    配额闸：json 模式在 json_store.bulk_insert 内按批校验；physical 模式在此处按批校验。"""
    entitlement.assert_tenant_writable(db, mt.tenant_id)
    fields = meta_service.get_meta_fields(db, mt.id)
    try:
        path = get_upload_path(source.file_id)
        rows = read_sheet(path, source.sheet_name)
    except (UploadNotFound, ExcelParseError) as e:
        raise HTTPException(400, str(e))

    h_idx = source.header_row - 1
    if h_idx < 0 or h_idx >= len(rows):
        raise HTTPException(400, "表头行号超出范围")
    headers = build_headers(rows[h_idx])
    data_rows = rows[h_idx + 1:]

    # 源表头 -> 字段 映射（以字段上记录的 source_header 为准）
    header_to_field: dict[str, MetaField] = {}
    for f in fields:
        src = (f.options or {}).get("source_header")
        if src and src not in header_to_field:
            header_to_field[src] = f

    is_json = mt.storage_mode == "json"
    table = None if is_json else meta_service.reflect_table(mt.name)
    total = len(data_rows)
    success, failures = 0, []

    def flush_batch(batch: list[tuple[int, dict]]):
        nonlocal success
        if not batch:
            return
        try:
            if is_json:
                from ..services import json_store
                json_store.bulk_insert(db, mt.id, [item for _, item in batch])
            else:
                entitlement.check_quota(db, mt.tenant_id, "max_rows", delta=len(batch))
                db.execute(table.insert(), [item for _, item in batch])
                entitlement.bump_usage(db, mt.tenant_id, "row_count", len(batch))
                db.commit()
            success += len(batch)
        except HTTPException:
            db.rollback()
            raise   # 配额 403 直接透传，不降级为逐行
        except Exception:
            db.rollback()
            # 批量失败则逐行隔离坏数据
            for row_no, item in batch:
                try:
                    if is_json:
                        from ..services import json_store
                        json_store.bulk_insert(db, mt.id, [item])
                    else:
                        entitlement.check_quota(db, mt.tenant_id, "max_rows", delta=1)
                        db.execute(table.insert().values(**item))
                        entitlement.bump_usage(db, mt.tenant_id, "row_count", 1)
                        db.commit()
                    success += 1
                except Exception as e:
                    db.rollback()
                    failures.append({"row_no": row_no, "error": str(e)[:200],
                                     "values": {k: str(v)[:50] for k, v in item.items()}})

    batch: list[tuple[int, dict]] = []
    for idx, row in enumerate(data_rows):
        row_no = h_idx + 2 + idx  # Excel 中的 1-based 行号
        item, row_errors = {}, {}
        for i, h in enumerate(headers):
            f = header_to_field.get(h)
            if f is None:
                continue
            raw = row[i] if i < len(row) else None
            ok, cv, err = coerce_value(raw, f.data_type, f.nullable)
            if ok:
                item[f.field_name] = cv
            else:
                row_errors[f.field_name] = f"{f.label}：{err}"
        if row_errors:
            failures.append({"row_no": row_no, "error": "; ".join(row_errors.values()),
                             "values": {h: str(row[i])[:50] for i, h in enumerate(headers) if i < len(row)}})
            continue
        now = datetime.now()
        item["created_at"] = now
        item["updated_at"] = now
        if not is_json:
            item["tenant_id"] = mt.tenant_id   # 物理表冗余列（json 模式由 bulk_insert 落 Record 列）
            item["owner_id"] = mt.owner_id
        batch.append((row_no, item))
        if len(batch) >= IMPORT_BATCH_SIZE:
            flush_batch(batch)
            batch = []
    flush_batch(batch)

    batch_row = ImportBatch(
        table_id=mt.id, file_name=get_upload_filename(source.file_id),
        total=total, success=success, failed=len(failures),
        fail_detail=failures[:FAIL_DETAIL_CAP],
    )
    db.add(batch_row)
    log_audit(db, "import", mt.id, after={"total": total, "success": success, "failed": len(failures)},
              tenant_id=mt.tenant_id)
    db.commit()
    return {"total": total, "success": success, "failed": len(failures), "failures": failures[:FAIL_DETAIL_CAP]}
