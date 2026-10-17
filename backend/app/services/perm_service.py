"""智能表内容权限（设计文档 §13）：等级预设 / 归一化 / grant-only 合并 / 行列级判定 / 摘要语。

判定对象：表主人与租户 admin 是「内容管理者」，不受内容权限约束（他们配置权限）；
其余成员 = 全员基线 ∪ 所属各指定成员组的额外权限（行范围取并、布尔取或、字段三态逐位取或），
再与 L0 表级授权（table_shares / 角色表权限的 view/create/edit/delete）取交。

无权限配置行 = 全员「全部权限」（与 V2 行为一致，存量表不受影响）。
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import MetaField, SmartDocEntry, SmartEntryPermission, SmartGroupGrant, SmartPermGroup
from .field_registry import FIELD_TYPES, SYSTEM_TYPES
from .smart_cond import match_conditions, with_system_values

LEVELS = ["NONE", "VIEW", "EDIT", "FULL"]
LEVEL_RANK = {lv: i for i, lv in enumerate(LEVELS)}
LEVEL_LABELS = {"NONE": "无权限", "VIEW": "仅浏览", "EDIT": "可编辑", "FULL": "全部权限"}

# 字段三态被锁定（不可编辑/首次提交）的类型：计算类 + 系统字段（§13.4 约束矩阵）
LOCKED_EDIT_TYPES = {"formula", "autoNumber", "lookup"} | SYSTEM_TYPES
# AI 字段：值由 AI 生成，新建记录/表单不填（无首次提交），但网格里允许手动修正（可编辑）
NO_FIRST_SUBMIT_TYPES = LOCKED_EDIT_TYPES | {"ai"}


def _rights(view=True, first=True, edit=True) -> dict:
    return {"view": view, "firstSubmit": first, "edit": edit}


def level_profile(level: str) -> dict:
    """等级 = 预设模板（§13.1）。"""
    if level not in LEVEL_RANK:
        level = "FULL"
    if level == "NONE":
        return {"level": "NONE", "viewManage": False, "schemaEdit": False,
                "record": {"viewScope": "ALL", "viewConditions": [], "editScope": "ALL", "editConditions": [],
                           "editFallback": "VIEW_ONLY", "add": False, "delete": False},
                "fields": {"mode": "ALL", "newFieldDefault": _rights(False, False, False), "items": {}}}
    if level == "VIEW":
        return {"level": "VIEW", "viewManage": False, "schemaEdit": False,
                "record": {"viewScope": "ALL", "viewConditions": [], "editScope": "ALL", "editConditions": [],
                           "editFallback": "VIEW_ONLY", "add": False, "delete": False},
                "fields": {"mode": "ALL", "newFieldDefault": _rights(True, False, False), "items": {}}}
    return {"level": level, "viewManage": True, "schemaEdit": level == "FULL",
            "record": {"viewScope": "ALL", "viewConditions": [], "editScope": "ALL", "editConditions": [],
                       "editFallback": "VIEW_ONLY", "add": True, "delete": True},
            "fields": {"mode": "ALL", "newFieldDefault": _rights(), "items": {}}}


def _clean_conditions(conds) -> list[dict]:
    out = []
    for c in conds or []:
        if isinstance(c, dict) and c.get("fieldId") and c.get("operator"):
            out.append({"fieldId": c["fieldId"], "operator": c["operator"], "value": c.get("value")})
    return out[:20]


def _clean_rights(r, level: str) -> dict:
    r = r if isinstance(r, dict) else {}
    view = bool(r.get("view", True))
    edit = bool(r.get("edit", False)) and view and level in ("EDIT", "FULL")
    first = bool(r.get("firstSubmit", False)) and view and level in ("EDIT", "FULL")
    return _rights(view, first, edit)


def normalize_profile(p: dict | None, entry_type: str = "sheet") -> dict:
    """任意输入 → 完整 PermissionProfile（缺省键按等级预设补齐，非法值回落）。"""
    p = p if isinstance(p, dict) else {}
    level = p.get("level") if p.get("level") in LEVEL_RANK else "FULL"
    if entry_type == "dashboard":
        # 仪表盘/报告类条目仅 全部权限/仅浏览/无权限（§13.8）
        if level == "EDIT":
            level = "FULL"
        return level_profile(level)
    out = level_profile(level)
    if level == "NONE":
        return out
    rec_in = p.get("record") if isinstance(p.get("record"), dict) else {}
    rec = out["record"]
    if level == "VIEW":
        rec["viewScope"] = "PARTIAL" if rec_in.get("viewScope") == "PARTIAL" else "ALL"
        rec["viewConditions"] = _clean_conditions(rec_in.get("viewConditions"))
    else:
        # 可编辑及以上：查看范围恒为全部，只暴露编辑范围 + fallback（§13.3 UI 规则）
        rec["editScope"] = "PARTIAL" if rec_in.get("editScope") == "PARTIAL" else "ALL"
        rec["editConditions"] = _clean_conditions(rec_in.get("editConditions"))
        rec["editFallback"] = "NO_ACCESS" if rec_in.get("editFallback") == "NO_ACCESS" else "VIEW_ONLY"
        rec["add"] = bool(rec_in.get("add", True))
        rec["delete"] = bool(rec_in.get("delete", True))
        out["viewManage"] = bool(p.get("viewManage", True))
    if rec["viewScope"] == "PARTIAL" and not rec["viewConditions"]:
        rec["viewScope"] = "ALL"
    if rec["editScope"] == "PARTIAL" and not rec["editConditions"]:
        rec["editScope"] = "ALL"
    f_in = p.get("fields") if isinstance(p.get("fields"), dict) else {}
    if f_in.get("mode") == "PER_FIELD":
        out["fields"] = {
            "mode": "PER_FIELD",
            "newFieldDefault": _clean_rights(f_in.get("newFieldDefault") or out["fields"]["newFieldDefault"], level),
            "items": {str(k): _clean_rights(v, level) for k, v in (f_in.get("items") or {}).items()},
        }
    return out


# ---------- 字段权限 ----------

def primary_field_name(fields: list[MetaField]) -> str | None:
    return fields[0].field_name if fields else None


def field_rights(profile: dict, f: MetaField, primary: str | None) -> dict:
    """单个 profile 下某字段的三态（已应用 §13.4 约束矩阵）。"""
    level = profile["level"]
    if level == "NONE":
        return _rights(False, False, False)
    fcfg = profile["fields"]
    if fcfg["mode"] == "ALL":
        r = _rights(True, level in ("EDIT", "FULL"), level in ("EDIT", "FULL"))
    else:
        r = dict(fcfg["items"].get(f.field_name) or fcfg["newFieldDefault"])
    ft = f.field_type or ""
    if ft in SYSTEM_TYPES or f.field_name == primary:
        r["view"] = True   # 系统字段与主列强制可见（灰勾锁定）
    if ft in LOCKED_EDIT_TYPES:
        r["edit"] = r["firstSubmit"] = False
    if ft in NO_FIRST_SUBMIT_TYPES:
        r["firstSubmit"] = False
    if not r["view"]:
        r["edit"] = r["firstSubmit"] = False
    return r


# ---------- 有效权限（多 profile 并集） ----------

@dataclass
class Effective:
    """managed=True：内容管理者（主人/admin）或表未配置内容权限 → 不做内容裁剪。"""
    managed: bool
    profiles: list[dict] = field(default_factory=list)
    viewer_id: int | None = None
    can_create: bool = True        # L0 表级授权
    can_edit: bool = True
    can_delete: bool = True

    @property
    def level(self) -> str:
        if self.managed:
            return "FULL"
        return max((p["level"] for p in self.profiles), key=lambda lv: LEVEL_RANK[lv], default="NONE")

    @property
    def view_manage(self) -> bool:
        return self.managed or any(p.get("viewManage") for p in self.profiles)

    @property
    def schema_edit(self) -> bool:
        return self.managed or any(p.get("schemaEdit") for p in self.profiles)

    @property
    def can_add_record(self) -> bool:
        return self.can_create and (self.managed or any(p["record"]["add"] for p in self.profiles))

    @property
    def can_delete_record(self) -> bool:
        return self.can_delete and (self.managed or any(p["record"]["delete"] for p in self.profiles))

    def field_rights_map(self, fields: list[MetaField]) -> dict[str, dict]:
        primary = primary_field_name(fields)
        out = {}
        for f in fields:
            if self.managed:
                ft = f.field_type or ""
                r = _rights(True, ft not in NO_FIRST_SUBMIT_TYPES, ft not in LOCKED_EDIT_TYPES)
            else:
                r = _rights(False, False, False)
                for p in self.profiles:
                    pr = field_rights(p, f, primary)
                    r = {k: r[k] or pr[k] for k in r}
            if not self.can_edit:
                r["edit"] = False
            if not self.can_create:
                r["firstSubmit"] = False
            out[f.field_name] = r
        return out

    def row_viewable(self, rec: dict, fields: list) -> bool:
        if self.managed:
            return True
        r = with_system_values(rec, fields)
        for p in self.profiles:
            lv, rc = p["level"], p["record"]
            if lv == "NONE":
                continue
            if lv == "VIEW":
                if rc["viewScope"] == "ALL" or match_conditions(r, fields, rc["viewConditions"], "all",
                                                                self.viewer_id, prepared=True):
                    return True
                continue
            if rc["editScope"] == "ALL" or rc["editFallback"] == "VIEW_ONLY":
                return True
            if match_conditions(r, fields, rc["editConditions"], "all", self.viewer_id, prepared=True):
                return True
        return False

    def row_editable(self, rec: dict, fields: list) -> bool:
        if not self.can_edit:
            return False
        if self.managed:
            return True
        r = with_system_values(rec, fields)
        for p in self.profiles:
            if p["level"] not in ("EDIT", "FULL"):
                continue
            rc = p["record"]
            if rc["editScope"] == "ALL" or match_conditions(r, fields, rc["editConditions"], "all",
                                                            self.viewer_id, prepared=True):
                return True
        return False

    def to_client(self, fields: list[MetaField]) -> dict:
        return {
            "managed": self.managed, "level": self.level,
            "viewManage": self.view_manage, "schemaEdit": self.schema_edit,
            "canAddRecord": self.can_add_record, "canDeleteRecord": self.can_delete_record,
            "rowScoped": (not self.managed) and any(
                p["record"]["editScope"] == "PARTIAL" or p["record"]["viewScope"] == "PARTIAL"
                for p in self.profiles),
            "fieldRights": self.field_rights_map(fields),
        }


def entry_of_table(db: Session, table_id: int) -> SmartDocEntry | None:
    return (db.query(SmartDocEntry)
            .filter(SmartDocEntry.ref_table_id == table_id, SmartDocEntry.type.in_(("sheet", "form")))
            .first())


def user_groups(db: Session, doc_id: int, user_id: int) -> list[SmartPermGroup]:
    rows = db.query(SmartPermGroup).filter_by(doc_id=doc_id).order_by(SmartPermGroup.order_no, SmartPermGroup.id).all()
    return [g for g in rows if user_id in [int(x) for x in (g.member_ids or []) if str(x).isdigit()]]


def base_profile_of(db: Session, entry: SmartDocEntry) -> dict:
    row = db.query(SmartEntryPermission).filter_by(entry_id=entry.id).first()
    return normalize_profile(row.base_profile if row else {"level": "FULL"}, entry.type)


def effective_for_entry(db: Session, entry: SmartDocEntry | None, user_id: int, is_manager: bool,
                        can_create=True, can_edit=True, can_delete=True) -> Effective:
    eff = Effective(managed=True, viewer_id=user_id, can_create=can_create, can_edit=can_edit,
                    can_delete=can_delete)
    if is_manager or entry is None:
        return eff
    row = db.query(SmartEntryPermission).filter_by(entry_id=entry.id).first()
    if row is None:
        return eff   # 未配置内容权限：全员全部权限
    profiles = [normalize_profile(row.base_profile, entry.type)]
    for g in user_groups(db, entry.doc_id, user_id):
        grant = db.query(SmartGroupGrant).filter_by(group_id=g.id, entry_id=entry.id).first()
        if grant:
            profiles.append(normalize_profile(grant.profile, entry.type))
    eff.managed = False
    eff.profiles = profiles
    return eff


def effective_for_access(db: Session, access) -> Effective:
    """路由层入口：TableAccess → Effective（主人/租户 admin 为内容管理者）。"""
    entry = entry_of_table(db, access.table.id)
    return effective_for_entry(db, entry, access.ctx.user.id if access.ctx else None,
                               access.is_owner or access.is_admin,
                               access.can_create, access.can_edit, access.can_delete)


def require_level(eff: Effective, level: str, msg: str = "没有该操作的内容权限") -> None:
    if LEVEL_RANK[eff.level] < LEVEL_RANK[level]:
        raise HTTPException(403, msg)


# ---------- 摘要语（§13.7） ----------

def summarize(profile: dict | None, fields: list[MetaField] | None = None, grant: bool = False) -> str:
    """无权限 / 仅浏览 / 仅浏览部分内容 / 可编辑 / 可编辑部分内容 / 全部权限；组额外权限缺省=无额外权限。"""
    if profile is None:
        return "无额外权限" if grant else "全部权限"
    lv = profile["level"]
    if lv == "NONE":
        return "无额外权限" if grant else "无权限"
    if lv == "FULL":
        return "全部权限"
    rc = profile["record"]
    fcfg = profile["fields"]
    partial_fields = False
    if fcfg["mode"] == "PER_FIELD" and fields:
        primary = primary_field_name(fields)
        for f in fields:
            r = field_rights(profile, f, primary)
            if not r["view"] or (lv == "EDIT" and (f.field_type or "") not in LOCKED_EDIT_TYPES and not r["edit"]):
                partial_fields = True
                break
    if lv == "VIEW":
        return "仅浏览部分内容" if rc["viewScope"] == "PARTIAL" or partial_fields else "仅浏览"
    partial = rc["editScope"] == "PARTIAL" or partial_fields or not rc["add"] or not rc["delete"]
    return "可编辑部分内容" if partial else "可编辑"


def copy_profile(p: dict) -> dict:
    return copy.deepcopy(p)
