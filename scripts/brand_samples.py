"""ساخت تصاویر نمونهٔ رنگی و Grayscale از PDF نهایی برای بازبینی بصری برند.

خروجی: output/brand_samples/{cover,guide,table,figure,svg,tree,glossary}.png
و نسخهٔ خاکستری هرکدام با پسوند _gray. اجرا: python scripts/brand_samples.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pymupdf
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from humsyar.model import normalize_text  # noqa: E402

PDF = ROOT / "output" / "neuroanat_s01_pilot_final.pdf"
OUT = ROOT / "output" / "brand_samples"
OUT.mkdir(parents=True, exist_ok=True)

doc = pymupdf.open(str(PDF))
texts = [normalize_text(p.get_text()) for p in doc]


def find(probe: str, start: int = 0) -> int:
    n = normalize_text(probe)
    return next(i for i in range(start, len(texts)) if n in texts[i])


PAGES = {
    "cover": 0,
    "guide": 1,
    "table": find("مقایسهٔ آکسون و دندریت", 2),
    "figure": find("آرایش چهار نوع سلول", 2),
    "svg": find("دو مسیر گام‌به‌گام انتقال", 2),
    "tree": find("نمودار درختی جامع جلسه", 2),
    "glossary": find("واژه‌نامهٔ فارسی–انگلیسی", 2),
}
for name, idx in PAGES.items():
    pix = doc[idx].get_pixmap(dpi=130)
    color_path = OUT / f"{name}.png"
    pix.save(str(color_path))
    Image.open(color_path).convert("L").save(str(OUT / f"{name}_gray.png"))
    print(f"{name}: صفحهٔ {idx + 1} → {color_path.name} + {name}_gray.png")
print("done:", OUT)
