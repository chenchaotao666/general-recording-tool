"""智能表 AI 能力路由（设计文档 §10、§16.2）：场景市场 / 配额 / AI 字段批量刷新 / AI 生成公式 / AI 匹配标签；
以及「文件」字段附件上传下载（PDF 转文本的输入来源）。"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Record, SmartAiRun
from ..services import ai_field_service, perm_service, smart_files
from ..services.llm import LLMError
from ..services.meta_service import get_meta_fields
from ..utils.access import TableAccess, get_table_access, require_table
from ..utils.context import Context, get_current_context

router = APIRouter(prefix="/api/smart", tags=["smart-ai"])


@router.get("/ai/scenes")
def scenes():
    return ai_field_service.scene_catalog()


@router.get("/ai/quota")
def quota(db: Session = Depends(get_db), ctx: Context = Depends(get_current_context)):
    return ai_field_service.quota_status(db, ctx.tenant.id)


def _field(db: Session, table_id: int, field_name: str):
    f = next((x for x in get_meta_fields(db, table_id) if x.field_name == field_name), None)
    if f is None:
        raise HTTPException(404, "字段不存在")
    return f


def _require_edit(db: Session, access: TableAccess) -> perm_service.Effective:
    eff = perm_service.effective_for_access(db, access)
    perm_service.require_level(eff, "EDIT", "没有编辑记录的权限")
    return eff


@router.post("/tables/{table_id}/fields/{field_name}/ai-run")
def ai_run(table_id: int, field_name: str, payload: dict | None = None, db: Session = Depends(get_db),
           access: TableAccess = Depends(require_table("edit"))):
    """AI 字段批量刷新：record_ids 指定行；否则 scope=all（全部）/ empty（仅空值）/ failed（仅失败）。"""
    _require_edit(db, access)
    f = _field(db, table_id, field_name)
    if f.field_type != "ai":
        raise HTTPException(400, "该字段不是 AI 字段")
    payload = payload or {}
    ids = payload.get("record_ids")
    if not ids:
        scope = payload.get("scope", "all")
        rows = db.query(Record).filter_by(table_id=table_id).order_by(Record.id).all()
        if scope == "empty":
            rows = [r for r in rows if (r.data or {}).get(field_name) in (None, "", [])]
        elif scope == "failed":
            failed = {x.record_id for x in db.query(SmartAiRun).filter_by(
                table_id=table_id, field_name=field_name, status="error").all()}
            rows = [r for r in rows if r.id in failed]
        ids = [r.id for r in rows]
        if payload.get("limit"):   # 「生成前 N 行」
            ids = ids[:max(1, int(payload["limit"]))]
    n = ai_field_service.enqueue(db, table_id, field_name, [int(x) for x in ids])
    return {"queued": n, "quota": ai_field_service.quota_status(db, access.table.tenant_id)}


@router.post("/tables/{table_id}/ai/configure")
def ai_configure(table_id: int, payload: dict, db: Session = Depends(get_db),
                 access: TableAccess = Depends(require_table("edit"))):
    """AI 字段配置生成 + 真实数据效果预览（不落库）。payload: scene / input_fields / instruction /
    base（修改已有配置时的当前配置）/ field_name（编辑中的字段，排除自身）/ output_type。"""
    _require_edit(db, access)
    return ai_field_service.configure(db, access.table, payload or {})


@router.post("/tables/{table_id}/ai/preview")
def ai_preview(table_id: int, payload: dict, db: Session = Depends(get_db),
               access: TableAccess = Depends(require_table("edit"))):
    """按（手动编辑过的）配置重新试算效果预览。"""
    _require_edit(db, access)
    cfg = dict((payload or {}).get("config") or {})
    editing = (payload or {}).get("field_name")
    scene = ai_field_service.SCENE_BY_KEY.get(cfg.get("scene") or "custom", ai_field_service.SCENE_BY_KEY["custom"])
    if not ai_field_service._is_local(scene) and not ai_field_service._quota_ok(db, access.table.tenant_id):
        raise HTTPException(403, "本月 AI 调用次数已用完，请升级套餐")
    fields = [f for f in get_meta_fields(db, table_id) if f.field_name != editing]
    return {"config": cfg, "preview": ai_field_service.preview_rows(db, access.table, cfg, fields),
            "quota": ai_field_service.quota_status(db, access.table.tenant_id)}


@router.post("/ai/generate-formula")
def generate_formula(payload: dict, db: Session = Depends(get_db), ctx: Context = Depends(get_current_context)):
    table_id = int(payload.get("table_id") or 0)
    get_table_access(db, table_id, ctx.user, ctx)
    prompt = str(payload.get("prompt") or "").strip()
    if not prompt:
        raise HTTPException(400, "请描述要计算的内容")
    try:
        return ai_field_service.generate_formula(db, table_id, prompt[:1000])
    except LLMError as e:
        raise HTTPException(502, str(e))


@router.post("/tables/{table_id}/fields/{field_name}/ai-match-tags")
def ai_match_tags(table_id: int, field_name: str, payload: dict, db: Session = Depends(get_db),
                  access: TableAccess = Depends(require_table("edit"))):
    eff = _require_edit(db, access)
    f = _field(db, table_id, field_name)
    if f.field_type not in ("singleSelect", "multiSelect"):
        raise HTTPException(400, "AI 匹配标签仅适用于单选/多选字段")
    if not eff.managed and not eff.field_rights_map(get_meta_fields(db, table_id))[field_name]["edit"]:
        raise HTTPException(403, "没有编辑该字段的权限")
    try:
        return ai_field_service.match_tags(
            db, access.table, f, payload.get("source_fields") or [], bool(payload.get("only_empty", True)),
            bool(payload.get("allow_new", True)), access.ctx.user.id)
    except LLMError as e:
        raise HTTPException(502, str(e))


# ---------- 文件字段附件 ----------

@router.post("/tables/{table_id}/files")
async def upload_file(table_id: int, file: UploadFile, db: Session = Depends(get_db),
                      access: TableAccess = Depends(require_table("view"))):
    content = await file.read()
    try:
        return smart_files.save(content, file.filename or "file", table_id, access.ctx.user.id)
    except smart_files.SmartFileError as e:
        raise HTTPException(400, str(e))


@router.get("/tables/{table_id}/files/recent")
def recent_files(table_id: int, access: TableAccess = Depends(require_table("view"))):
    return smart_files.recent(table_id, access.ctx.user.id)


@router.get("/files/{file_id}")
def download_file(file_id: str, preview: bool = False, db: Session = Depends(get_db), ctx: Context = Depends(get_current_context)):
    try:
        path, meta = smart_files.locate(file_id)
    except smart_files.SmartFileError as e:
        raise HTTPException(404, str(e))
    if meta.get("uploader_id") != ctx.user.id:
        if not meta.get("table_id"):
            raise HTTPException(404, "文件不存在")
        get_table_access(db, int(meta["table_id"]), ctx.user, ctx)
    preview_types = {'.pdf': 'application/pdf', '.png': 'image/png', '.jpg': 'image/jpeg',
                     '.jpeg': 'image/jpeg', '.gif': 'image/gif', '.webp': 'image/webp', '.bmp': 'image/bmp',
                     '.txt': 'text/plain'}
    media_type = preview_types.get(path.suffix.lower()) if preview else None
    return FileResponse(path, filename=meta["filename"], media_type=media_type,
                        content_disposition_type='inline' if media_type else 'attachment')
