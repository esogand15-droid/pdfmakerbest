"""نسخهٔ کامل جلسهٔ ۱ — هر شش مبحث از روی جزوهٔ مادر (رونویسی مباحث ۱، ۲، ۳، ۵).

قراردادها: شش مبحث به ترتیب، هر ۳۱ شکل مادر دقیقاً یک بار، بدون برچسب
«در نسخهٔ کامل»/«پایلوت»، درخت جامع روی صفحه(های) اختصاصی با برچسب خوانا،
پیکان‌های متنی بدون فونت جایگزین بی‌صدا، و قاعدهٔ «عدد علمی» در برگهٔ مرور.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from humsyar.model import load_session  # noqa: E402
from humsyar.planner import Plan  # noqa: E402
from humsyar.typeset import Typesetter, inline  # noqa: E402
from humsyar.ultra import _has_quantity  # noqa: E402

PILOT = ROOT / "content" / "session01_pilot.yaml"


def _session():
    return load_session(str(PILOT))


def test_six_topics_in_order_with_mother_titles():
    s = _session()
    assert [t.number for t in s.topics] == [1, 2, 3, 4, 5, 6]
    assert [t.id for t in s.topics] == [f"s01-t0{i}" for i in range(1, 7)]
    titles = [t.title for t in s.topics]
    assert titles[0] == "تقسیم‌بندی سیستم عصبی: مرکزی و محیطی"
    assert titles[4] == "انواع نورون و سیناپس"
    # هر مبحث شناسنامهٔ کامل دارد (از کارت آموزشی مادر)
    for t in s.topics:
        assert t.why and t.objectives and t.key_terms, t.id
        assert any(b.type == "section" for b in t.blocks), t.id


def test_all_31_mother_figures_used_exactly_once():
    s = _session()
    files = [str(b.data.get("file", "")).rsplit("/", 1)[-1]
             for t in s.topics for b in t.blocks if b.type == "figure"]
    assets = {p.name for p in (ROOT / "assets/figures/session01").glob("*")}
    assert len(files) == 31 and len(set(files)) == 31
    assert set(files) == assets


def test_no_pilot_residue_in_meta_or_map():
    s = _session()
    assert "پایلوت" not in s.note
    assert "دو مبحث" not in s.note
    for m in s.session_map:
        assert "در نسخهٔ کامل" not in str(m.get("tag", ""))
    # همهٔ مدخل‌های نقشه به مبحث واقعی وصل‌اند
    assert {str(m["id"]) for m in s.session_map} == {t.id for t in s.topics}


def test_every_new_topic_block_has_sources():
    s = _session()
    for t in s.topics:
        if t.number not in (1, 2, 3, 5):
            continue
        for b in t.blocks:
            if b.type in ("paragraph", "figure", "table", "callout"):
                assert b.sources, f"{b.id} بدون منبع"


def test_tree_pages_cover_all_six_topics_readably():
    s = _session()
    plan = Plan(session=s)
    html = Typesetter(plan).tree_page()
    # برچسب گره‌ها در SVG چندخطی می‌شکنند؛ متنِ بی‌تگ و تک‌فاصله را مقایسه کن
    flat = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    for t in s.topics:
        assert re.sub(r"\s+", " ", t.title) in flat, t.id
    svgs = re.findall(r'<svg class="tree-svg" width="(\d+)pt" height="(\d+)pt" '
                      r'viewBox="0 0 ([\d.]+) ([\d.]+)"', html)
    assert svgs
    for wp, hp, vw, _vh in svgs:
        eff = int(wp) / float(vw)
        assert eff >= 0.82          # یادداشت ۸٫۶واحدی → ≥۷٫۰۵pt مؤثر
        assert int(hp) <= 540       # سقف ارتفاع چاپی صفحهٔ اختصاصی
    if len(svgs) > 1:
        assert "بخش ۱ از" in html   # شماره‌گذاری شفاف بخش‌های درخت


def test_textual_arrows_render_as_svg_not_fallback_glyph():
    out = inline("اکتودرم ← صفحهٔ عصبی ← لولهٔ عصبی")
    assert "←" not in out and out.count("<svg") == 2
    assert "→" not in inline("الف → ب")


def test_quantity_rule_distinguishes_reference_digits():
    # رقم ارجاعیِ تنها کمیت علمی نیست
    assert not _has_quantity("شکل ۲-۱ اسنل ساده‌ترین نسخهٔ همین نقشه است")
    assert not _has_quantity("در متن ص ۵ جزوه توصیف شد")
    assert not _has_quantity("شکل ۲-۲۸ اسنل چهار نوع گلیال مرکزی را می‌چیند")
    # کمیت‌های واقعی همچنان عدد علمی‌اند
    assert _has_quantity("وزیکول ۸ نانومتری")
    assert _has_quantity("بیش از ۴۰۰ میلی‌متر در روز")
    assert _has_quantity("در ۴ نورون دیده می‌شود")
    assert _has_quantity("فیلامنت ۱۰ نانومتری در شکل ۲-۲ جدول آمده است")
