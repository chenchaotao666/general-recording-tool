# -*- coding: utf-8 -*-
"""把生成的 xlsx 模板渲染成独立 HTML（复用后端 print_html 的单元格还原），供截图对比。"""
import html as _html
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from openpyxl import load_workbook

from app.services.print_html import _sheet_html

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "_renders"

CSS = """
  body { margin: 0; background: #888; font-family: SimSun, 'Microsoft YaHei', serif; }
  .page { background: #fff; width: 190mm; margin: 12px auto; padding: 6mm 4mm;
          box-shadow: 0 1px 4px rgba(0,0,0,.4); box-sizing: border-box; }
  .doc table { margin: 0 auto; }
  .doc td { overflow: hidden; padding: 1px 3px; }
  .placeholder { color: #888; }
"""


def main():
    import re
    files = sorted(f for f in (ROOT.parent / "打印模板").glob("*/*.xlsx")
                   if not f.name.startswith("~$"))
    for f in files:
        rel = f.relative_to(ROOT.parent / "打印模板")
        ws = load_workbook(f).active
        html = _sheet_html(ws)
        # 占位符替换为灰色短标记：预览只看版式，避免长占位符干扰列宽判断
        html = re.sub(r"\{[^{}]+\}", '<span style="color:#9aa">×××</span>', html)
        doc = f"""<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<title>{_html.escape(rel.stem)}</title><style>{CSS}</style></head>
<body><div class="page"><div class="doc">{html}</div></div></body></html>"""
        out = OUT / rel.parent / f"{rel.stem}.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(doc, encoding="utf-8")
    print(f"渲染 {len(files)} 个 HTML → {OUT}")


if __name__ == "__main__":
    main()
