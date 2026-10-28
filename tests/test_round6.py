"""تست‌های راند ۶ — کتابخانهٔ آیکون SVG، کادرهای معنایی گسترش‌یافته، قاب
یکپارچهٔ جدول، نوار پیشرفت راست‌به‌چپِ چاپ‌امن و حس نسخهٔ نهایی."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))

from humsyar.icons import CALLOUT_ICONS, ICONS, icon_svg
from humsyar.model import CALLOUT_KINDS, load_session, validate
from humsyar.planner import plan_session
from humsyar.typeset import KIND_LABELS, Typesetter

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "content" / "session01_pilot.yaml"
CSS = ((ROOT / "engine" / "themes" / "brand.css").read_text(encoding="utf-8") + (ROOT / "engine" / "themes" / "humsyar.css").read_text(encoding="utf-8"))


def _plan():
    s = load_session(str(PILOT))
    return s, plan_session(s, "final", ROOT)


# ------------------------------------------------------------------ آیکون‌ها
def test_icon_registry_integrity():
    assert len(ICONS) >= 24
    for name, (meaning, inner) in ICONS.items():
        assert meaning.strip(), name           # هر آیکون معنای ثبت‌شده دارد
        assert "<path" in inner or "<circle" in inner or "<rect" in inner
        assert "http" not in inner            # بدون منبع خارجی
    for kind, ic in CALLOUT_ICONS.items():
        assert ic in ICONS, kind
        svg = icon_svg(ic)
        assert svg.startswith("<svg") and 'stroke="currentColor"' in svg
    # شناسهٔ ناشناس هرگز خروجی خالی نمی‌دهد
    assert icon_svg("no-such-icon").startswith("<svg")


def test_callout_kinds_expanded_and_labeled():
    for kind in ("mnemonic", "exception", "formula", "terminology", "unresolved"):
        assert kind in CALLOUT_KINDS
        assert kind in KIND_LABELS
        assert kind in CALLOUT_ICONS
        assert f"--c-{kind}:" in CSS and f".callout--{kind}" in CSS
    # همهٔ گونه‌های مدل برچسب و آیکون دارند
    for kind in CALLOUT_KINDS:
        assert kind in KIND_LABELS, kind
        assert kind in CALLOUT_ICONS, kind


def test_new_kinds_validate_and_render(tmp_path):
    import yaml
    raw = yaml.safe_load(PILOT.read_text(encoding="utf-8"))
    for i, kind in enumerate(("mnemonic", "exception", "formula", "terminology", "unresolved")):
        raw["topics"][0]["blocks"].append({
            "id": f"x-ck{i}", "type": "callout", "kind": kind,
            "title": "عنوان آزمایشی", "text": "متن آزمایشی برای رندر گونهٔ تازه.",
            "status": "needs_review",
            "sources": [{"book": "جزوهٔ درس", "pages": "۱"}],
        })
    p = tmp_path / "kinds.yaml"
    p.write_text(yaml.dump(raw, allow_unicode=True), encoding="utf-8")
    s = load_session(str(p))
    assert validate(s) == []
    html = Typesetter(plan_session(s, "final", ROOT)).document("")
    for kind in ("mnemonic", "exception", "formula", "terminology", "unresolved"):
        assert f"callout--{kind}" in html
    assert 'class="ic ic--mnemonic"' in html


# ------------------------------------------------------------- قاب جدول
def test_table_frame_single_owner_css():
    assert "border:1pt solid var(--hairline); border-radius:9pt" in CSS  # قاب واحد روی wrapper (توکن برند)
    assert "overflow:hidden" in CSS
    # خط زیر سربرگ در همهٔ ستون‌ها هم‌وزن و یکدست است — بدون پله و بدون رنگ واژه
    assert "border-bottom:2.2pt" not in CSS
    assert "th-ent" not in CSS
    # راند ۱۳: راه‌راه گرم با توکن اختصاصی --zebra (ستون rowh همچنان مستثناست)
    assert "table.tbl tbody tr:nth-child(even) td:not(.rowh){ background:var(--zebra)" in CSS


# --------------------------------------------------------- حس نسخهٔ نهایی
def test_pilot_declared_final():
    s, plan = _plan()
    assert s.draft is False
    assert s.version == "۱٫۰"
    from humsyar.brand import load_brand
    from humsyar.cover import cover_html
    cover = cover_html(s, load_brand(ROOT), "")
    assert "پایلوت موتور" not in cover  # نشان پیش‌نویس روی کاور نیست
    html = Typesetter(plan).document("")
    assert "شناسنامه" not in html and "پیش‌نویس" not in html


# ------------------------------------------------- راهنمای رنگ و نقطه‌ها
def test_no_word_coloring_or_legend():
    """راند ۸: راهنمای رنگ و نقطه/قاب رنگیِ واژه‌ها حذف شده‌اند؛ رنگ فقط در
    اجزای ساختاری (شاخهٔ درخت، پیکان‌های ریل) می‌ماند."""
    s, plan = _plan()
    html = Typesetter(plan).document("")
    assert "رنگ ثابت مفاهیم این جلسه" not in html
    assert "chip--ent" not in html
    assert 'class="edot"' not in html
    # رنگ ساختاری ریل دوجهته از پالت یکپارچهٔ برند می‌آید (راند ۱۰)
    assert "#0F5E63" in html and "#FF7A45" in html


# --------------------------------------------------- نوار پیشرفت در PDF واقعی
def test_progress_bar_rtl_and_dark_in_built_pdf():
    """راند ۱۳: پُری نوار پیشرفت رنگ «جلسه» است؛ شیار تمام‌عرض محتواست
    (۱۴ تا ۱۹۶mm) و پُری همچنان از راست لنگر می‌گیرد."""
    pdf = ROOT / "output" / "neuroanat_s01_pilot_final.pdf"
    if not pdf.exists():
        return  # در محیط بدون خروجی ساخته‌شده رد می‌شود
    import pymupdf
    from humsyar.palette import session_accent
    doc = pymupdf.open(str(pdf))
    page = doc[min(8, doc.page_count - 1)]  # صفحهٔ ۹: داخل مبحث ۶
    MM = 72 / 25.4
    expect = tuple(int(session_accent(1)[i:i + 2], 16) / 255 for i in (1, 3, 5))
    dark = []
    for dr in page.get_drawings():
        r = dr["rect"]
        fill = dr.get("fill")
        if fill and r.y0 > 286 * MM and r.width > 10 * MM and r.height < 3 * MM:
            if all(abs(fill[i] - expect[i]) < 0.03 for i in range(3)):
                dark.append(r)
    assert dark, "پُری نوار پیشرفت با رنگ جلسه پیدا نشد"
    # لنگر از راست: لبهٔ راست پُری روی انتهای راست شیار تمام‌عرض (۱۹۶mm) است
    assert abs(max(r.x1 for r in dark) - 196 * MM) < 2 * MM
    # شیار حول مرکز صفحه (۱۰۵mm) متقارن است
    tracks = [dr["rect"] for dr in page.get_drawings()
              if dr["rect"].y0 > 286 * MM and dr["rect"].width > 50 * MM
              and dr["rect"].height < 3 * MM]
    assert tracks
    t = max(tracks, key=lambda r: r.width)
    assert abs((t.x0 + t.x1) / 2 - 105 * MM) < 1.5 * MM
