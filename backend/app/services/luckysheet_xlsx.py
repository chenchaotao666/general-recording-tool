"""Luckysheet 编辑器 JSON → xlsx（openpyxl）。

浏览器内 Excel 模板编辑器的保存链路：前端 luckysheet.getAllSheets() 的结果
在这里还原成带样式的 xlsx，供 print_excel.fill_workbook 做占位符填充。

覆盖的样式：字体（名/号/粗/斜/下划线/删除线/颜色）、填充色、对齐/换行、
合并单元格、行高列宽、边框（13 种线型近似映射）。
"""
import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# luckysheet 字体下标 → 字体名（与 luckysheet 默认字体列表一致）
_FONT_LIST = [
    "Times New Roman", "Arial", "Tahoma", "Verdana", "Microsoft YaHei",
    "SimSun", "SimHei", "KaiTi", "FangSong", "NSimSun",
    "STXinwei", "STXihei", "STXingkai",
]

# luckysheet 边框线型 1~13 → openpyxl 线型
_BORDER_STYLES = {
    1: "thin", 2: "hair", 3: "dotted", 4: "dashed", 5: "dashDot",
    6: "dashDotDot", 7: "double", 8: "medium", 9: "mediumDashed",
    10: "mediumDashDot", 11: "slantDashDot", 12: "mediumDashDotDot", 13: "thick",
}

_HT = {0: "center", 1: "left", 2: "right"}     # 水平对齐
_VT = {0: "center", 1: "top", 2: "bottom"}     # 垂直对齐
_TR = {1: 45, 2: 135, 3: 255, 4: 90, 5: 180}   # 旋转（3=竖排文字）


def _argb(color) -> str | None:
    if not isinstance(color, str) or not color.startswith("#"):
        return None
    h = color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) not in (6, 8):
        return None
    return ("FF" + h if len(h) == 6 else h).upper()


def _font_name(ff):
    if ff is None:
        return None
    try:
        return _FONT_LIST[int(ff)]
    except (TypeError, ValueError, IndexError):
        return str(ff)


def _side(spec) -> Side | None:
    """borderInfo cell 值里的单边 {style, color} → openpyxl Side。"""
    if not isinstance(spec, dict):
        return None
    style = _BORDER_STYLES.get(int(spec.get("style") or 1), "thin")
    return Side(style=style, color=_argb(spec.get("color")) or "FF000000")


def _expand_range(rng: dict) -> tuple[range, range]:
    rows, cols = rng.get("row") or [0, 0], rng.get("column") or [0, 0]
    return range(rows[0], rows[-1] + 1), range(cols[0], cols[-1] + 1)


def _apply_borders(ws, border_info: list) -> None:
    """把 luckysheet 的 borderInfo 展开为逐单元格边框（模板体量小，直接展开）。

    后写的覆盖先写的，与 luckysheet「后设置优先」一致。
    """
    def set_border(r, c, **sides):
        cur = ws.cell(row=r + 1, column=c + 1).border
        merged = {k: v for k, v in {
            "left": cur.left, "right": cur.right, "top": cur.top, "bottom": cur.bottom,
            **sides}.items() if v is not None}
        ws.cell(row=r + 1, column=c + 1).border = Border(**merged)

    for info in border_info or []:
        if not isinstance(info, dict):
            continue
        if info.get("rangeType") == "cell":
            v = info.get("value") or {}
            sides = {k: _side(v.get(k)) for k in ("l", "r", "t", "b")}
            # LuckyExcel 导出用 col_index（部分版本写 column_index）
            set_border(v.get("row_index", 0), v.get("col_index", v.get("column_index", 0)),
                       left=sides["l"], right=sides["r"], top=sides["t"], bottom=sides["b"])
            continue
        if info.get("rangeType") != "range":
            continue
        btype, style, color = info.get("borderType"), info.get("style"), info.get("color")
        side = _side({"style": style, "color": color}) or Side(style="thin", color="FF000000")
        for rng in info.get("range") or []:
            rows, cols = _expand_range(rng)
            for r in rows:
                for c in cols:
                    kw = {}
                    if btype in ("border-all", "border-outside"):
                        if r == rows.start: kw["top"] = side
                        if r == rows.stop - 1: kw["bottom"] = side
                        if c == cols.start: kw["left"] = side
                        if c == cols.stop - 1: kw["right"] = side
                    if btype in ("border-all", "border-inside"):
                        if r > rows.start: kw["top"] = side
                        if r < rows.stop - 1: kw["bottom"] = side
                        if c > cols.start: kw["left"] = side
                        if c < cols.stop - 1: kw["right"] = side
                    if btype == "border-top" and r == rows.start: kw["top"] = side
                    if btype == "border-bottom" and r == rows.stop - 1: kw["bottom"] = side
                    if btype == "border-left" and c == cols.start: kw["left"] = side
                    if btype == "border-right" and c == cols.stop - 1: kw["right"] = side
                    if btype == "border-horizontal" and r < rows.stop - 1: kw["bottom"] = side
                    if btype == "border-vertical" and c < cols.stop - 1: kw["right"] = side
                    if kw:
                        set_border(r, c, **kw)


def _cell_value(cell: dict):
    v = cell.get("v")
    if v is None:
        return cell.get("m") or None
    ct = cell.get("ct") or {}
    if ct.get("t") == "n" or isinstance(v, (int, float)):
        try:
            return float(v)
        except (TypeError, ValueError):
            pass
    return str(v)


def _write_images(ws, images: dict) -> None:
    """luckysheet 工具栏插入的图片（sheet.images）→ xlsx 浮动图片。
    模型：{imgId: {src: dataURL, default: {left, top, width, height}, ...}}（位置为表内绝对像素）。"""
    if not images:
        return
    import base64
    import io as _io
    import urllib.request

    from openpyxl.drawing.image import Image as XlImage
    from openpyxl.drawing.spreadsheet_drawing import AbsoluteAnchor
    from openpyxl.drawing.xdr import XDRPoint2D, XDRPositiveSize2D
    from openpyxl.utils.units import pixels_to_EMU

    for im in images.values():
        try:
            src = (im or {}).get("src") or ""
            if src.startswith("data:"):
                data = base64.b64decode(src.split(",", 1)[1])
            elif src.startswith(("http://", "https://")):
                data = urllib.request.urlopen(src, timeout=10).read()
            else:
                continue
            dft = im.get("default") or {}
            w = int(dft.get("width") or im.get("originWidth") or 100)
            h = int(dft.get("height") or im.get("originHeight") or 100)
            left = int(dft.get("left") or 0)
            top = int(dft.get("top") or 0)
            xi = XlImage(_io.BytesIO(data))
            xi.anchor = AbsoluteAnchor(
                pos=XDRPoint2D(pixels_to_EMU(left), pixels_to_EMU(top)),
                ext=XDRPositiveSize2D(pixels_to_EMU(w), pixels_to_EMU(h)),
            )
            ws.add_image(xi)
        except Exception:
            continue   # 单张图片失败不影响整体转换


def _write_sheet(ws, sheet: dict) -> None:
    ws.title = (sheet.get("name") or "Sheet")[:31]
    config = sheet.get("config") or {}

    # data 缺失时用 celldata 稀疏还原
    data = sheet.get("data")
    if not data and sheet.get("celldata"):
        n_r, n_c = int(sheet.get("row") or 0), int(sheet.get("column") or 0)
        data = [[None] * n_c for _ in range(n_r)]
        for cd in sheet["celldata"]:
            if cd.get("r", 0) < n_r and cd.get("c", 0) < n_c:
                data[cd["r"]][cd["c"]] = cd.get("v")
    data = data or []

    for r, row in enumerate(data):
        if not row:
            continue
        for c, cell in enumerate(row):
            if not isinstance(cell, dict):
                continue
            xc = ws.cell(row=r + 1, column=c + 1)
            val = _cell_value(cell)
            if val is not None:
                xc.value = val
            fc, bg = _argb(cell.get("fc")), _argb(cell.get("bg"))
            xc.font = Font(
                name=_font_name(cell.get("ff")),
                size=cell.get("fs") if isinstance(cell.get("fs"), (int, float)) else None,
                bold=bool(cell.get("bl")), italic=bool(cell.get("it")),
                underline="single" if cell.get("un") else None,
                strike=bool(cell.get("cl")), color=fc,
            )
            if bg:
                xc.fill = PatternFill("solid", fgColor=bg)
            xc.alignment = Alignment(
                horizontal=_HT.get(cell.get("ht")), vertical=_VT.get(cell.get("vt")),
                wrap_text=cell.get("tb") == 2, text_rotation=_TR.get(cell.get("tr"), 0),
            )

    for key, m in (config.get("merge") or {}).items():
        if not isinstance(m, dict):
            continue
        r, c, rs, cs = (int(m.get(k) or 0) for k in ("r", "c", "rs", "cs"))
        if rs and cs and (rs > 1 or cs > 1):
            ws.merge_cells(start_row=r + 1, start_column=c + 1,
                           end_row=r + rs, end_column=c + cs)

    for idx, px in (config.get("columnlen") or {}).items():
        try:
            width = max(1.0, (float(px) - 5) / 7)   # px ≈ 字符宽×7+5
        except (TypeError, ValueError):
            continue
        ws.column_dimensions[get_column_letter(int(idx) + 1)].width = width
    for idx, px in (config.get("rowlen") or {}).items():
        try:
            ws.row_dimensions[int(idx) + 1].height = float(px) * 0.75   # px → pt
        except (TypeError, ValueError):
            continue

    _apply_borders(ws, config.get("borderInfo"))
    _write_images(ws, sheet.get("images"))


def sheets_to_xlsx(sheets: list) -> bytes:
    if not sheets:
        raise ValueError("编辑器内容为空")
    wb = Workbook()
    wb.remove(wb.active)
    for i, sheet in enumerate(sheets):
        _write_sheet(wb.create_sheet(f"Sheet{i + 1}"), sheet or {})
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
