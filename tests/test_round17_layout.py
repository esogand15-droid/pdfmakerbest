"""دور چیدمان (درخواست کاربر با شماره‌صفحه):
- صفحهٔ ۲: فهرست شکل‌ها/جدول‌ها حذف؛ شبکهٔ کارت‌های مبحث با شمارهٔ واقعی.
- سیستم شکل: سقف ارتفاع عمومی ۹۰mm (یک‌سوم صفحه)، عریض ۶۲mm، کپشن‌کناری ۸۴mm.
- کپشن ۱۰pt و جدول ۱۰pt؛ عرض ستون‌ها داده‌محور؛ جدول بلند (>۴ ردیف) قابل‌شکستن.
- بهینه‌سازی تصویر ۱۶۰۰px/JPEG85 در بیلد.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

CSS = (ROOT / "engine" / "themes" / "humsyar.css").read_text(encoding="utf-8")
PLANNER = (ROOT / "engine" / "humsyar" / "planner.py").read_text(encoding="utf-8")
TYPESET = (ROOT / "engine" / "humsyar" / "typeset.py").read_text(encoding="utf-8")
PACKING = (ROOT / "engine" / "humsyar" / "packing.py").read_text(encoding="utf-8")
BUILD = (ROOT / "engine" / "humsyar" / "build.py").read_text(encoding="utf-8")

PILOT = ROOT / "content" / "session01_pilot.yaml"


def _typeset_html() -> str:
    from humsyar.model import load_session
    from humsyar.planner import plan_session
    from humsyar.typeset import Typesetter
    s = load_session(str(PILOT))
    plan = plan_session(s, "final", ROOT)
    return Typesetter(plan).document("")


def test_page2_card_grid_without_fig_table_lists():
    html = _typeset_html()
    assert "فهرست شکل‌ها" not in html and "فهرست جدول‌ها" not in html
    assert html.count('class="toc-card"') == 6
    assert 'class="toc-grid"' in html
    assert ".lists" not in CSS and "figure_table_lists" not in TYPESET
    # نقشهٔ جلسه و راهنمای خواندن سر جایشان‌اند
    assert "نقشهٔ جلسه" in html and "چطور این جزوه را بخوانیم؟" in html


def test_figure_height_caps_are_one_third_page():
    assert "MAX_H_WIDE = 62.0" in PLANNER
    assert "MAX_H_PORTRAIT = 90.0" in PLANNER
    assert "MAX_H_HARD = 90.0" in PLANNER
    assert "MAX_H_SIDECAP = 90.0" in PLANNER
    assert "SIDECAP_COL_MM = 84.0" in PLANNER  # تصویر ≈۴۶٪، توضیح ≈۵۴٪
    assert "grid-template-columns:0.86fr 1fr" in CSS


def test_caption_and_table_fonts_are_10pt():
    assert ".fig__cap{ padding:4pt 8pt 5pt; font-size:10pt; line-height:1.55;" in CSS
    assert "table.tbl{ width:100%; border-collapse:collapse; font-size:10pt; line-height:1.5; }" in CSS
    assert "text-align:right; font-size:10pt;" in CSS  # سربرگ جدول


def test_long_tables_split_and_columns_are_data_driven():
    assert ".tblwrap--split{ break-inside:auto; }" in CSS
    assert "len(d.get(\"rows\", [])) > 4" in TYPESET  # فقط جدول بلند
    assert "weights.append" in TYPESET  # عرض ستون از طول محتوا
    assert 'len(block.data.get("rows", [])) <= 4' in PACKING  # هم‌خوانی شبیه‌سازی
    html = _typeset_html()
    assert 'class="tblwrap tblwrap--split"' in html  # جدول ۸ردیفهٔ جسم سلولی
    assert "<colgroup>" in html and "tbl--fixed" in html


def test_image_optimization_1600_q85():
    assert "im.width > 1600" in BUILD and "quality=85" in BUILD
