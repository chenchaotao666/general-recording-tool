"""图片预处理：压缩到 1024px 以内、统一转 JPEG，控制 LLM 调用成本。"""
from io import BytesIO

from PIL import Image

MAX_SIDE = 1024
MAX_IMAGES = 5


class ImageError(Exception):
    pass


def compress_image(data: bytes) -> bytes:
    try:
        im = Image.open(BytesIO(data))
        im.load()
    except Exception:
        raise ImageError("图片文件无法解析，请上传 JPG/PNG 等常见格式")
    if im.mode != "RGB":
        im = im.convert("RGB")
    im.thumbnail((MAX_SIDE, MAX_SIDE))
    buf = BytesIO()
    im.save(buf, "JPEG", quality=85)
    return buf.getvalue()
