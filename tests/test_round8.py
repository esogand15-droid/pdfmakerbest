"""تست‌های راند ۸ — فونت لاتین Inter تیره، حذف رنگ‌بندی واژه‌ها، زبانهٔ فقط راست."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))

from humsyar.model import load_session
from humsyar.planner import plan_session
from humsyar.typeset import Typesetter

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "content" / "session01_pilot.yaml"
CSS = (ROOT / "engine" / "themes" / "humsyar.css").read_text(encoding="utf-8")


def test_latin_font_is_inter_and_dark():
    assert '"Inter"' in CSS
    assert "DejaVu" not in CSS
    # رنگ لاتین تیره است، نه آبی روشن (accent)
    assert "bdi,.en{ direction:ltr; unicode-bidi:isolate;" in CSS
    import re as _re
    m = _re.search(r"bdi,\.en\{[^}]*\}", CSS)
    assert m and "color:var(--ink)" in m.group(0)  # لاتین تیره از توکن جوهر است
    assert ".term .en{ font-weight:600; color:var(--accent)" not in CSS
    for f in ("Inter-Regular.woff2", "Inter-SemiBold.woff2", "Inter-Bold.woff2"):
        assert (ROOT / "assets" / "fonts" / f).exists()


def test_inter_embedded_in_built_pdf():
    pdf = ROOT / "output" / "neuroanat_s01_pilot_final.pdf"
    if not pdf.exists():
        return
    import pymupdf
    doc = pymupdf.open(str(pdf))
    fonts = {f[3] for p in doc for f in p.get_fonts()}
    assert any("Inter" in f for f in fonts), fonts
    assert not any("DejaVu" in f for f in fonts), fonts


def test_thumb_tabs_always_on_right_edge():
    pdf = ROOT / "output" / "neuroanat_s01_pilot_final.pdf"
    if not pdf.exists():
        return
    import pymupdf
    MM = 72 / 25.4
    doc = pymupdf.open(str(pdf))
    tab_pages = 0
    for i in range(2, doc.page_count):
        for bl in doc[i].get_text("dict")["blocks"]:
            if bl.get("type") != 0:
                continue
            x0, y0, x1, y1 = bl["bbox"]
            # متن عمودی زبانه: بلند و باریک در لبه‌ها
            if (y1 - y0) > 25 * MM and (x1 - x0) < 10 * MM and y0 < 280 * MM:
                tab_pages += 1
                assert x0 > 190 * MM, (i + 1, bl["bbox"])  # فقط سمت راست
    assert tab_pages >= 5  # زبانه روی صفحات مباحث هست


def test_no_entity_word_styles_in_css():
    for bad in ("th-ent", "chip--ent", ".edot", "guide__ents"):
        assert bad not in CSS, bad
