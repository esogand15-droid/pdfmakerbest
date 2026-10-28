"""راند ۱۳ — پولیش نسخهٔ رنگی: یک رنگ جلسه، کاغذ تمام‌صفحه، کارت سفید،
هایلایت یگانه، فوتر/هدر متقارن، راهنمای بدون نمونه، الگو فقط در BW.

این تست‌ها قوانین سند راند ۱۳ را قفل می‌کنند؛ هر برگشت (رنگ مبحث، درز
سفید لبه، گرادیان/سایه روی هایلایت، نوار نمونه، الگوی رنگی) باید قرمز شود.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from humsyar.model import load_session  # noqa: E402
from humsyar.palette import hex_of, session_accent, session_vars  # noqa: E402
from humsyar.planner import plan_session  # noqa: E402
from humsyar.typeset import Typesetter  # noqa: E402

PILOT = ROOT / "content" / "session01_pilot.yaml"
BRAND_CSS = (ROOT / "engine" / "themes" / "brand.css").read_text(encoding="utf-8")
CSS = (ROOT / "engine" / "themes" / "humsyar.css").read_text(encoding="utf-8")
FINAL_PDF = ROOT / "output" / "neuroanat_s01_pilot_final.pdf"
MM = 72 / 25.4


def _pilot_html(**kw):
    s = load_session(str(PILOT))
    return Typesetter(plan_session(s, "final", ROOT), **kw).document("")


# ---------------------------------------------------------------- قانون ۱
def test_session_palette_13_cycle_from_number_only():
    assert session_accent(1) == "#139A8E"          # جلسهٔ ۱ = سبزآبی برند
    assert session_vars(1)["--session-deep"]       # مشتقات خودکار حاضرند
    assert session_accent(14) == session_accent(1)  # چرخهٔ ۱۳تایی
    assert session_accent(15) == session_accent(2)
    assert len({session_accent(i) for i in range(1, 14)}) == 13


def test_chapter_accent_off_by_default_and_no_chapter_vars_in_doc():
    import yaml
    cfg = yaml.safe_load((ROOT / "config" / "layout.yaml").read_text(encoding="utf-8"))
    assert cfg["color_system"]["chapter_accent_mode"] == "off"
    html = _pilot_html()
    assert "--session-accent" in html
    assert "--chapter-accent" not in html and "--chapter-header" not in html
    assert "--chapter" not in CSS


# ---------------------------------------------------------------- قانون ۲
def test_paper_only_on_page_and_tokens_final_hex():
    m = re.search(r"@page\s*\{[^}]*background:\s*(#[0-9A-Fa-f]{6})", BRAND_CSS)
    assert m, "پس‌زمینهٔ @page در brand.css نیست"
    assert m.group(1).upper() == hex_of("paper") == "#FFFBF3"
    # هیچ کانتینری پس‌زمینهٔ کاغذ ندارد؛ کاغذ فقط مال صفحه است
    assert "background:var(--paper)" not in CSS
    assert not re.search(r"(^|\n)html\{[^}]*background", CSS)
    assert not re.search(r"(^|\n)body\{[^}]*background", CSS)


def test_no_runtime_color_computation_in_css():
    cover_src = (ROOT / "engine" / "humsyar" / "cover.py").read_text(encoding="utf-8")
    for src in (BRAND_CSS, CSS, cover_src):
        assert "color-mix(" not in src
        assert "rgba(" not in src


# ---------------------------------------------------------------- قانون ۳
def test_white_cards_and_table_session_header():
    assert "table.tbl th{\n  background:var(--session-header" in CSS
    assert "td:not(.rowh){ background:var(--zebra)" in CSS
    assert "td.rowh{ font-weight:700; color:var(--session-deep" in CSS
    assert "background:var(--session-soft" in CSS
    # کادر معنایی کارت سفید است و فقط نوار آغازین رنگ خانواده را دارد
    assert (".callout.fam{ background:var(--surface); "
            "border-inline-start:5px solid var(--fam); }") in CSS
    assert "background:var(--fam-soft);\n  border-inline-start" not in CSS
    # چیپ سفید با خط خنثی
    assert "border:1px solid var(--line-chip)" in CSS
    assert hex_of("zebra") == "#FFF8EC" and hex_of("line-chip") == "#E2D6C3"


# ---------------------------------------------------------------- قانون ۴
def test_single_flat_highlight_everywhere():
    assert hex_of("hl") == "#FFE9A8"
    m = re.search(r"\.term,\.numbadge\{(.*?)\}", CSS, re.S)
    assert m, "قاعدهٔ مشترک .term,.numbadge نیست"
    rule = m.group(1)
    assert "background-color:var(--hl)" in rule
    assert "display:inline" in rule and "box-decoration-break:clone" in rule
    assert "border:0" in rule and "line-height:inherit" in rule
    # هیچ گرادیان/سایه‌ای روی عناصر درون‌خطی نیست
    assert "linear-gradient" not in rule
    assert "box-shadow:none" in rule and "text-shadow:none" in rule
    assert "font-weight" not in rule          # بولد اضافه ممنوع
    # قاعدهٔ جداگانه‌ای برای نشان عدد (pill قدیمی) برنگردد
    assert not re.search(r"\.numbadge\{\s*display:inline-block", CSS)
    # برگهٔ فوق‌فشرده هم همان قانون را دارد
    ultra = (ROOT / "engine" / "humsyar" / "ultra.py").read_text(encoding="utf-8")
    assert ".term,.numbadge,.un{ background-color:var(--hl)" in ultra


# ---------------------------------------------------------------- قانون ۶ و ۷
def test_legend_without_samples_equal_height():
    s = load_session(str(PILOT))
    g = Typesetter(plan_session(s, "final", ROOT)).reading_guide()
    assert g.count("fguide__card") == 6
    assert "fguide__sample" not in g
    assert "fguide__sample" not in CSS
    assert "grid-auto-rows:1fr" in CSS


def test_border_patterns_only_in_bw():
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", CSS):
        if "bw-theme" in sel:
            continue
        if ".callout" in sel or ".rev__" in sel:
            for pat in ("dashed", "dotted", "double", "groove"):
                assert pat not in body, (sel.strip(), pat)
    assert "body.bw-theme .callout.fam2{ border-inline-start-style:double" in CSS
    assert "body.bw-theme .callout--conflict" in CSS


# ------------------------------------------------- پیکسل لبه و تقارن (خروجی واقعی)
def test_page_edges_are_exactly_paper():
    """قانون ۲ روی PDF واقعی: گوشه‌ها و میانه‌های لبه = کاغذ (بدون درز سفید).
    مقدار برداری فایل دقیقاً #FFFBF3 است؛ رندر ICC حداکثر ۱ پله خطای گردکردن دارد."""
    if not FINAL_PDF.exists():
        return
    import pymupdf
    doc = pymupdf.open(str(FINAL_PDF))
    paper = tuple(int(hex_of("paper")[i:i + 2], 16) for i in (1, 3, 5))
    pts_mm = [(2, 2), (208, 2), (2, 295), (208, 295), (60, 2),
              (2, 150), (208, 20), (60, 295), (150, 295)]
    for pno in (2, 3, 5, 7, 15):
        pix = doc[pno - 1].get_pixmap(matrix=pymupdf.Matrix(2, 2))
        vals = []
        for x_mm, y_mm in pts_mm:
            x = min(int(x_mm * MM * 2), pix.width - 1)
            y = min(int(y_mm * MM * 2), pix.height - 1)
            vals.append(pix.pixel(x, y)[:3])
        assert len(set(vals)) == 1, (pno, vals)          # یکدست، بدون درز
        got = vals[0]
        assert all(abs(got[i] - paper[i]) <= 1 for i in range(3)), (pno, got)
        assert got != (255, 255, 255)                     # سفیدِ خالص برنگردد


def test_footer_symmetric_full_width_progress():
    """قانون ۵ روی PDF واقعی: شیار ۱۴→۱۹۶mm، کپسول دقیقاً ۱۰۵mm، پُری از راست."""
    if not FINAL_PDF.exists():
        return
    import pymupdf
    doc = pymupdf.open(str(FINAL_PDF))
    page = doc[6]  # صفحهٔ ۷
    acc = tuple(int(session_accent(1)[i:i + 2], 16) / 255 for i in (1, 3, 5))
    track = fill = None
    for dr in page.get_drawings():
        r, f = dr["rect"], dr.get("fill")
        if f and abs(r.y0 - 286.6 * MM) < 1.5 * MM and r.height < 3 * MM:
            if r.width > 170 * MM:
                track = r
            elif all(abs(f[i] - acc[i]) < 0.03 for i in range(3)) and r.width > 10 * MM:
                fill = r
    assert track is not None and fill is not None
    assert abs(track.x0 - 14 * MM) < 1 * MM and abs(track.x1 - 196 * MM) < 1 * MM
    assert abs((track.x0 + track.x1) / 2 - 105 * MM) < 0.6 * MM   # متقارن حول مرکز
    assert abs(fill.x1 - 196 * MM) < 1 * MM                        # لنگر راست
    assert fill.x0 > 14 * MM                                       # از راست پر شده
    # رقم صفحه در کپسول دقیقاً وسط صفحه است
    centers = []
    for b in page.get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            for sp in ln["spans"]:
                if sp["bbox"][1] > 288 * MM and sp["text"].strip() in "۷7":
                    centers.append((sp["bbox"][0] + sp["bbox"][2]) / 2)
    assert centers and abs(centers[0] - 105 * MM) < 0.6 * MM


def test_frame_overlay_is_transparent():
    fp = ROOT / "output" / "_work" / "frame_4.pdf"
    if not fp.exists():
        return
    import pymupdf
    doc = pymupdf.open(str(fp))
    pg = doc[0]
    full = [d for d in pg.get_drawings()
            if d.get("fill") and d["rect"].width > 0.9 * pg.rect.width
            and d["rect"].height > 0.9 * pg.rect.height]
    assert full == [], "قاب نباید صفحهٔ مات روی جزوه مهر کند"
