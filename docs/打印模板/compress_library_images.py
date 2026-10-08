# -*- coding: utf-8 -*-
"""把 docs/工单打印截图 的模板库对照图发布到 frontend/public/print-library/。

用法：backend/.venv/Scripts/python.exe docs/打印模板/compress_library_images.py

策略：q80 重编码 + 尺寸不变（原图仅 716-820px 宽，再缩会影响点击放大预览）；
若重编码没有比原图小 15% 以上则直接拷贝原文件。输出已是最终部署形态，
frontend/public 下内容会随 npm run build 进入 dist。
"""
import shutil
import sys
from io import BytesIO
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent
SRC = ROOT.parent / "工单打印截图"
DST = ROOT.parent.parent / "frontend" / "public" / "print-library"

QUALITY = 80
MIN_GAIN = 0.85  # 重编码后体积 ≤ 原图 85% 才采用，否则拷原图


def main():
    files = sorted(SRC.glob("*/*.jpg"))
    if not files:
        print("未找到源图:", SRC)
        sys.exit(1)

    total_src = total_dst = 0
    n_reencode = n_copy = 0
    for f in files:
        rel = f.relative_to(SRC)
        out = DST / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        src_size = f.stat().st_size
        total_src += src_size

        try:
            im = Image.open(f).convert("RGB")
            buf = BytesIO()
            im.save(buf, "JPEG", quality=QUALITY, optimize=True, progressive=True)
            data = buf.getvalue()
        except OSError:
            data = b""  # 截断/异常图：走原样拷贝

        if data and len(data) <= src_size * MIN_GAIN:
            out.write_bytes(data)
            n_reencode += 1
        else:
            shutil.copy2(f, out)
            n_copy += 1
        total_dst += out.stat().st_size

    print(f"共 {len(files)} 张：重编码 {n_reencode}，原样拷贝 {n_copy}")
    print(f"体积 {total_src/1024/1024:.1f}MB → {total_dst/1024/1024:.1f}MB")
    print("输出目录:", DST)


if __name__ == "__main__":
    main()
