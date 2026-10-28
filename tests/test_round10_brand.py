"""تست‌های راند ۱۰ — یکپارچگی هویت بصری برند (T1/T2/T3/T5/T12 سند مأموریت).

T1: هر HEX در کد تولیدی باید مقدار یکی از توکن‌های brand.css باشد.
T2: هیچ رنگ سبز/مینت قدیمی (Hue بین ۹۵ تا ۱۶۵ درجه، اشباع محسوس) در کد تولیدی
    نیست؛ توکن‌های مجازِ فیروزه‌ای/سیان برند صریحاً در فهرست مجازند.
T3: کنتراست جفت‌های واقعی متن/زمینه با محاسبهٔ WCAG.
T5: مؤلفه‌های حذف‌شده (بلوک «در یک نگاه»، چک‌لیست، شناسنامه) در خروجی نیستند.
T12: املای برند فقط «هامزیار»/HumsYar است.
تصاویر اصلی کتاب‌ها از T1/T2 مستثنا هستند (فقط کد قالب اسکن می‌شود).
"""
import colorsys
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))

from humsyar.model import load_session
from humsyar.palette import hex_of, tokens
from humsyar.planner import plan_session
from humsyar.typeset import Typesetter

ROOT = Path(__file__).resolve().parents[1]
CODE_FILES = (
    list((ROOT / "engine" / "humsyar").glob("*.py"))
    + list((ROOT / "engine" / "themes").glob("*.css"))
    + [ROOT / "engine" / "render.mjs", ROOT / "engine" / "measure.mjs"]
)
BRAND_CSS = ROOT / "engine" / "themes" / "brand.css"
_HEX = re.compile(r"#[0-9A-Fa-f]{6}\b|#[0-9A-Fa-f]{3}\b")


def _norm_hex(h: str) -> str:
    h = h.upper()
    return "#" + "".join(c * 2 for c in h[1:]) if len(h) == 4 else h


def _scan_hexes():
    for f in CODE_FILES:
        if f == BRAND_CSS:
            continue
        for m in _HEX.finditer(f.read_text(encoding="utf-8", errors="ignore")):
            yield f.name, _norm_hex(m.group(0))


def test_T1_only_palette_hex_values_in_code():
    allowed = set(tokens().values()) | {"#FFFFFF"}
    bad = sorted({f"{f}:{h}" for f, h in _scan_hexes() if h not in allowed})
    assert not bad, bad


def test_T2_no_legacy_cold_blues():
    """راند ۱۲ جایگزین ممنوعیت سبز راند ۱۰ شد: خانواده‌های سبز/فیروزه‌ایِ گرمِ
    داخل brand.css مشروع‌اند؛ آبی‌های سرد قدیمی نباید در هیچ فایلی برگردند."""
    banned = {"#061E4E", "#0636AE", "#0666F6", "#06D2DE", "#04B9D3",
              "#0B1B3A", "#050D18", "#0A2A7E"}
    bad = [f"{f}:{h}" for f, h in _scan_hexes() if h in banned]
    assert not bad, bad


def _lum(hexv: str) -> float:
    def ch(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (int(hexv[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def _ratio(fg: str, bg: str) -> float:
    l1, l2 = _lum(fg), _lum(bg)
    lo, hi = min(l1, l2), max(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def test_T3_contrast_pairs():
    """جفت‌های واقعی متن/زمینه؛ آستانهٔ متن معمولی ۴٫۵ و متن درشت/بولد ۳٫۵."""
    pairs_normal = [
        ("ink", "paper"), ("ink", "white"), ("ink", "surface-warm"),
        ("ink-soft", "paper"), ("primary-deep", "paper"),
        ("white", "primary-deep"), ("teal-ink", "paper"),
        ("fam1-deep", "paper"), ("fam2-deep", "paper"), ("fam3-deep", "paper"),
        ("fam4w-deep", "paper"), ("fam4c-deep", "paper"), ("fam4e-deep", "paper"),
        ("fam4u-deep", "paper"), ("fam5-deep", "paper"), ("fam6-deep", "paper"),
    ]
    for fg, bg in pairs_normal:
        assert _ratio(hex_of(fg), hex_of(bg)) >= 4.5, (fg, bg)
    # عنوان‌های درشت کاور روی سرمه‌ای گرم
    assert _ratio(hex_of("white"), hex_of("cover-deep")) >= 10
    assert _ratio(hex_of("aqua-300"), hex_of("primary-deep")) >= 3.0
    # متن هشدار تیره‌شده با color-mix (۵۰٪ warn + ۵۰٪ ink) روی زمینهٔ هشدار
    def mix(h1, h2, w1):
        c1 = [int(h1[i:i + 2], 16) for i in (1, 3, 5)]
        c2 = [int(h2[i:i + 2], 16) for i in (1, 3, 5)]
        return "#" + "".join(f"{round(a * w1 + b * (1 - w1)):02X}" for a, b in zip(c1, c2))

    warn_ink = mix(hex_of("warn"), hex_of("ink"), 0.5)
    assert _ratio(warn_ink, hex_of("warn-bg")) >= 4.5


def test_T5_banned_components_absent():
    s = load_session(ROOT / "content" / "session01_pilot.yaml")
    assert all(b.type not in ("tldr", "checklist") for b in s.all_blocks())
    ts = Typesetter(plan_session(s, "final", ROOT))
    assert not hasattr(ts, "b_tldr") and not hasattr(ts, "b_checklist")
    html = ts.document("")
    assert 'class="tldr' not in html and 'class="checklist' not in html
    assert "شناسنامه" not in html
    # راهنمای صفحهٔ دوم مدخل «در یک نگاه» ندارد (عنوان علمیِ داخل متن دست‌نخورده است)
    guide = ts.reading_guide()
    assert "در یک نگاه" not in guide


def test_T12_brand_spelling():
    pdf = ROOT / "output" / "neuroanat_s01_pilot_final.pdf"
    if not pdf.exists():
        return
    import pymupdf

    from humsyar.model import normalize_text
    doc = pymupdf.open(str(pdf))
    full = normalize_text(" ".join(p.get_text() for p in doc))
    # هجی‌های ممنوع برنامه‌ای ساخته می‌شوند تا lint مخزن، خودِ این تست را نگیرد
    yar = "\u06cc\u0627\u0631"
    for wrong in ("هام" + yar, "هام" + "\u06cc\u0631"):
        assert normalize_text(wrong) not in full, wrong
    raw_txt = " ".join(p.get_text() for p in doc)
    # گونهٔ فاصله‌دار/نیم‌فاصله‌دار پس از نرمال‌سازی با هجی درست یکی می‌شود؛
    # فقط روی متن خام قابل تفکیک است:
    assert "هام" + " " + yar not in raw_txt
    assert "هام" + "\u200c" + yar not in raw_txt
    assert "هام" + " \u0632" + yar not in raw_txt
    assert normalize_text("هامزیار") in full
    raw = " ".join(p.get_text() for p in doc)
    assert "HumsYar" in raw
    for wrong_en in ("Ham" + "syar", "Ham" + "sYar", "Hum" + "syar"):
        assert wrong_en not in raw


def test_no_concept_color_system():
    """§۱۲: رنگ مفهومی علمی (موجودیت‌ها) به‌طور کامل بازنشسته شده است."""
    assert not (ROOT / "engine" / "humsyar" / "entities.py").exists()
    assert not (ROOT / "config" / "entities.yaml").exists()
    s = load_session(ROOT / "content" / "session01_pilot.yaml")
    html = Typesetter(plan_session(s, "final", ROOT)).document("")
    for old in ("#B45309", "#EA580C", "#0284C7", "entity"):
        assert old not in html, old
    # جهت‌های ریل از پالت برند می‌آیند
    assert hex_of("royal-600") in html and hex_of("tealcyan-500") in html


def test_glossary_two_columns_on_last_page():
    css = (ROOT / "engine" / "themes" / "humsyar.css").read_text(encoding="utf-8")
    assert ".gloss--page .gloss__grid{ columns:2;" in css


def test_frame_and_progress_use_palette():
    import humsyar.build as build_mod
    import humsyar.frame as frame_mod
    assert frame_mod._BRAND == hex_of("primary-deep")
    assert frame_mod._DEEP == hex_of("ink")
    src = Path(build_mod.__file__).read_text(encoding="utf-8")
    # پیشرفت و کپسول از رنگ مبحث همان صفحه می‌آیند (راند ۱۲)
    assert "chapter_vars(int(key))" in src and "rgb_of_hex" in src
