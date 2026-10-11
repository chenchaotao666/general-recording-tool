"""Excel 上传解析 + AI 结构分析。"""
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import AnalyzeRequest
from ..services import excel_parser
from ..services.excel_parser import ExcelParseError, build_headers, cell_str, parse_file, read_sheet
from ..services.llm import LLMError, analyze_excel
from ..services.llm.prompts import mask_sensitive
from ..services.typemap import infer_column_type
from ..services.uploads import UploadNotFound, get_upload_filename, get_upload_path, save_upload
from ..utils.auth import get_current_user

router = APIRouter(prefix="/api/excel", tags=["excel"])

LOCAL_INFER_SAMPLE = 50   # 本地类型推断取样行数
LLM_SAMPLE = 8            # 发给 LLM 的每列样例值个数
PREVIEW_ROWS = 8          # 预览返回的数据行数


@router.post("/upload")
async def upload(file: UploadFile):
    try:
        file_id, path = await save_upload(file)
        parsed = parse_file(path)
    except (ValueError, ExcelParseError) as e:
        raise HTTPException(400, str(e))
    return {"file_id": file_id, "file_name": file.filename, "sheets": parsed["sheets"]}


@router.get("/preview")
def preview(file_id: str, sheet_name: str, header_row: int = Query(1, ge=1, le=50),
            user=Depends(get_current_user)):
    """按指定表头行重新解析预览（上传后调整「表头所在行」时即时刷新，不用等到 AI 分析）。"""
    try:
        path = get_upload_path(file_id)
        rows = read_sheet(path, sheet_name)
    except (UploadNotFound, ExcelParseError) as e:
        raise HTTPException(400, str(e))
    h_idx = header_row - 1
    if h_idx >= len(rows):
        raise HTTPException(400, f"表头行号超出范围（1~{len(rows)}）")
    headers = build_headers(rows[h_idx])
    sample = [[cell_str(v) for v in r] for r in rows[h_idx + 1: h_idx + 1 + PREVIEW_ROWS]]
    return {"headers": headers, "sample": sample, "total_rows": max(0, len(rows) - h_idx - 1)}


@router.post("/analyze")
def analyze(req: AnalyzeRequest, db: Session = Depends(get_db)):
    try:
        path = get_upload_path(req.file_id)
        rows = read_sheet(path, req.sheet_name)
    except (UploadNotFound, ExcelParseError) as e:
        raise HTTPException(400, str(e))

    h_idx = req.header_row - 1
    if h_idx < 0 or h_idx >= len(rows):
        raise HTTPException(400, f"表头行号超出范围（1~{len(rows)}）")
    headers = build_headers(rows[h_idx])
    # 允许只有表头没有数据：仅建表结构（类型一律保守按表头名推断，样例为空）
    data_rows = rows[h_idx + 1:]

    # 本地统计推断 + 脱敏样例，一起发给 LLM
    columns = []
    for i in range(len(headers)):
        vals = [r[i] for r in data_rows[:LOCAL_INFER_SAMPLE] if i < len(r)]
        samples = [mask_sensitive(cell_str(v)) for v in vals if v not in (None, "")][:LLM_SAMPLE]
        columns.append({"local_type": infer_column_type(vals), "samples": samples})

    try:
        return analyze_excel(db, headers, columns)
    except LLMError as e:
        raise HTTPException(400, str(e))
