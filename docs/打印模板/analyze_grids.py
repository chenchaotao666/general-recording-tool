# -*- coding: utf-8 -*-
"""分析截图中的表格网格线 → 每列像素宽度比例 → widths_override.json（供 generate_samples 使用）。

原理：网格线是贯穿整个表高的深色竖线，文字不会产生那么高的列向深色计数；
按列统计深色像素得到峰值 → 竖线位置 → 相邻线间距即列宽。
虚线式模板（无竖边框）检测线数不足则跳过，沿用启发式宽度。
"""
import json
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent
SRC = ROOT.parent / "工单打印截图"
OUT = ROOT / "widths_override.json"

DARK = 110          # 灰度低于此值视为线条像素
MIN_LINE_RATIO = 0.45   # 列向深色计数 ≥ 45% 峰值的才算网格竖线
MERGE_PX = 3        # 相邻多少像素内归为同一条线


def vlines(gray: np.ndarray, h: int, w: int) -> list[int]:
    dark = gray < DARK
    profile = dark.sum(axis=0)                       # 每列深色像素数
    peak = profile.max()
    if peak < h * 0.25:                              # 没有足够高的线（虚线式）
        return []
    thresh = max(peak * MIN_LINE_RATIO, h * 0.3)
    xs = np.where(profile > thresh)[0]
    lines = []
    for x in xs:
        if lines and x - lines[-1][-1] <= MERGE_PX:
            lines[-1].append(x)
        else:
            lines.append([x])
    return [int(np.mean(g)) for g in lines]


def analyze(img_path: Path, expect_cols: int):
    """返回 (状态, 宽度比例列表|None)。状态: ok / few-lines / count-mismatch"""
    from PIL import ImageFile
    ImageFile.LOAD_TRUNCATED_IMAGES = True   # 个别图片尾部轻微截断，容错加载
    img = Image.open(img_path).convert("L")
    w, h = img.size
    gray = np.asarray(img)
    lines = vlines(gray, h, w)
    if len(lines) < 4:
        return ("few-lines", None)
    # 用最长连续区段：剔除页面边线等离群线（主线群间距相对均匀）
    # 直接取覆盖范围最大的一组相邻线
    best = lines
    spans = [(lines[i], lines[i + 1]) for i in range(len(lines) - 1)]
    widths = [b - a for a, b in spans]
    if len(widths) < expect_cols:
        return ("count-mismatch", None)
    # 列数对不上时：取与期望列数最接近的连续子序列（总宽度最大者）
    if len(widths) > expect_cols:
        sub = [sum(widths[i:i + expect_cols]) for i in range(len(widths) - expect_cols + 1)]
        i0 = int(np.argmax(sub))
        widths = widths[i0:i0 + expect_cols]
    return ("ok", widths)


def main():
    import sys
    sys.path.insert(0, str(ROOT))
    from generate_samples import SPECS

    overrides = {}
    stats = {"ok": 0, "few-lines": 0, "count-mismatch": 0, "no-image": 0}
    for spec in SPECS:
        img = SRC / f"{spec['f']}.jpg"
        if not img.exists():
            stats["no-image"] += 1
            continue
        expect = len(spec["cols"])   # 联注竖排在表格外，不参与竖线映射
        status, widths = analyze(img, expect)
        stats[status] = stats.get(status, 0) + 1
        if status == "ok":
            if spec.get("side"):
                widths = widths + [max(8, round(np.mean(widths) * 0.3))]   # 联注窄列
            overrides[spec["f"]] = widths
    OUT.write_text(json.dumps(overrides, ensure_ascii=False, indent=1), encoding="utf-8")
    print(stats, f"→ {OUT}")


if __name__ == "__main__":
    main()
