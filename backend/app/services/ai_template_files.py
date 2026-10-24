"""Local attachment transforms used by AI templates; sources remain unchanged."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from . import smart_files

ASSETS = {"qrcode", "fiPdfImage", "fiPdfWatermark", "fiImagePdf", "imWatermarkAdd", "imSharpen"}


def input_type(field):
    return (field.options or {}).get("outputType", "text") if field.field_type == "ai" else field.field_type


def source_files(db, fields, record, inputs):
    from . import images
    sources = []
    for name in inputs:
        field = next((f for f in fields if f.field_name == name), None)
        if not field or input_type(field) not in ("image", "file"):
            continue
        value = record.get(name) or []
        for item in (value if isinstance(value, list) else [value]):
            sources.append((field, item))
    if len(sources) > 4:
        raise ValueError("单次最多处理 4 个图片或文件，请减少输入附件")
    for field, item in sources:
        fid = str(item.get("id") if isinstance(item, dict) else item)
        if input_type(field) == "image":
            row, path = images.get_image(db, fid)
            if row.table_id and row.table_id != field.table_id:
                raise ValueError("图片不属于当前表")
            yield path, row.filename or "image.png"
        else:
            path, meta = smart_files.locate(fid)
            if meta.get("table_id") != field.table_id:
                raise ValueError("文件不属于当前表")
            yield path, meta["filename"]


def _font(size):
    for name in ("C:/Windows/Fonts/msyh.ttc", "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


def transform(db, key, cfg, fields, record):
    inputs = cfg.get("inputFields") or []
    table_id = next((getattr(f, "table_id", None) for f in fields if getattr(f, "table_id", None)), None)
    if not table_id:
        raise ValueError("无法确定生成附件所属表")
    result = []
    def save(content, name):
        result.append(smart_files.save(content, name, table_id, None))
    if key == "qrcode":
        import qrcode
        value = record.get(inputs[0]) if inputs else None
        text = "" if value is None else str(value)
        if not text:
            return None
        if len(text.encode("utf-8")) > 1800:
            raise ValueError("二维码内容过长，请控制在 1800 字节以内")
        image = qrcode.make(text)
        out = BytesIO(); image.save(out, format="PNG")
        save(out.getvalue(), "二维码.png")
        return result
    sources = list(source_files(db, fields, record, inputs))[:4]
    if not sources:
        return None
    watermark = str((cfg.get("parameters") or {}).get("watermark") or "仅供内部使用")[:60]
    if key == "fiImagePdf":
        images = []
        for path, _ in sources:
            with Image.open(path) as source:
                if source.width * source.height > 25_000_000:
                    raise ValueError("图片超过 2500 万像素，请先缩小")
                images.append(ImageOps.exif_transpose(source).convert("RGB"))
        out = BytesIO()
        images[0].save(out, format="PDF", save_all=True, append_images=images[1:])
        save(out.getvalue(), "图片合并.pdf")
        return result
    for path, name in sources:
        if key == "fiPdfImage":
            import pypdfium2 as pdfium
            with pdfium.PdfDocument(str(path)) as document:
                for index in range(min(len(document), 10)):
                    page = document[index]
                    width, height = page.get_size()
                    scale = min(1.5, 2400 / max(width, height))
                    bitmap = page.render(scale=scale)
                    out = BytesIO(); bitmap.to_pil().save(out, format="PNG")
                    save(out.getvalue(), f"{name}-第{index + 1}页.png")
                    bitmap.close(); page.close()
        elif key == "fiPdfWatermark":
            from pypdf import PdfReader, PdfWriter
            from reportlab.pdfgen import canvas
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.cidfonts import UnicodeCIDFont
            pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
            reader = PdfReader(str(path)); writer = PdfWriter()
            if len(reader.pages) > 100:
                raise ValueError("PDF 水印单次最多处理 100 页")
            for original in reader.pages:
                page = writer.add_page(original)
                width, height = float(page.mediabox.width), float(page.mediabox.height)
                overlay = BytesIO(); c = canvas.Canvas(overlay, pagesize=(width, height))
                c.setFillColorRGB(.65, .65, .65); c.setFont("STSong-Light", min(24, width / max(len(watermark), 1)))
                c.saveState(); c.translate(width / 2, height / 2); c.rotate(30)
                c.drawCentredString(0, 0, watermark); c.restoreState(); c.save()
                page.merge_page(PdfReader(BytesIO(overlay.getvalue())).pages[0])
            out = BytesIO(); writer.write(out); save(out.getvalue(), f"水印-{name}")
        else:
            with Image.open(path) as source:
                if source.width * source.height > 25_000_000:
                    raise ValueError("图片超过 2500 万像素，请先缩小")
                im = ImageOps.exif_transpose(source).convert("RGBA")
                if key == "imSharpen":
                    im = im.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))
                else:
                    overlay = Image.new("RGBA", im.size)
                    draw = ImageDraw.Draw(overlay); font = _font(max(12, min(40, im.width // max(len(watermark), 8))))
                    draw.text((im.width - 12, im.height - 12), watermark, anchor="rs", font=font, fill=(80, 80, 80, 190), stroke_width=1, stroke_fill=(255, 255, 255, 180))
                    im = Image.alpha_composite(im, overlay)
                out = BytesIO(); im.save(out, format="PNG"); save(out.getvalue(), f"处理-{Path(name).stem}.png")
    return result
