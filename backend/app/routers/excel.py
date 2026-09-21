"""Excel 上传解析 + AI 结构分析。"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import AnalyzeRequest
from ..services import excel_parser
from ..services.excel_parser import ExcelParseError, build_headers, cell_str, parse_file, read_sheet
from ..services.llm import LLMError, analyze_excel
from ..services.llm.prompts import mask_sensitive
from ..services.typemap import infer_column_type
from ..services.uploads import UploadNotFound, get_upload_filename, get_upload_path, save_upload

router = APIRouter(prefix="/api/excel", tags=["excel"])

LOCAL_INFER_SAMPLE = 50   # 本地类型推断取样行数
LLM_SAMPLE = 8            # 发给 LLM 的每列样例值个数


@router.post("/upload")
async def upload(file: UploadFile):
    try:
        file_id, path = await save_upload(file)
        parsed = parse_file(path)
    except (ValueError, ExcelParseError) as e:
        raise HTTPException(400, str(e))
    return {"file_id": file_id, "file_name": file.filename, "sheets": parsed["sheets"]}


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
    data_rows = rows[h_idx + 1:]
    if not data_rows:
        raise HTTPException(400, "表头之下没有数据行，请检查表头行号")

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
