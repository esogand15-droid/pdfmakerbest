"""تست‌های راند ۵ — کیفیت نهادی: رنگِ معنایی، یادگیری فعالِ مشتق از متن،
مادهٔ پایانی، قاب چندواریانتی و سخت‌سازی‌های QA.

مهم‌ترین اثبات: TL;DR و خودآزمایی سریعِ پایلوت کلمه‌به‌کلمه از جمله‌های خود
جزوه مشتق شده‌اند (نه دانش بیرونی) و برچسب «پیشنهاد برای تأیید تیم علمی» دارند.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))

from humsyar.build import _page_topics
from humsyar.model import load_session, normalize_text, validate
from humsyar.planner import plan_session
from humsyar.qa import bidi_lint
from humsyar.typeset import Typesetter

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "content" / "session01_pilot.yaml"
BLANK = "……"


def _plan():
    s = load_session(str(PILOT))
    return s, plan_session(s, "final", ROOT)


def _sentences(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"(?<=\.)\s+", str(text)) if p.strip()]


# -+ سربرگ جدول
def test_comparison_table_headers_uniform_no_word_coloring():
    """راند ۸ (تصمیم محصول): واژه‌ها رنگ‌بندی نمی‌شوند؛ سربرگ جدول یکدست است."""
    s, plan = _plan()
    html = Typesetter(plan).document("")
    assert "th-ent" not in html
    assert "--th-ent:" not in html
    assert "tbl--compare" in html


# ---------------------------------------------------------------- bidi
def test_bidi_lint_pilot_is_clean():
    assert bidi_lint(load_session(str(PILOT))) == []


def test_bidi_lint_flags_bare_latin(tmp_path):
    import yaml
    raw = yaml.safe_load(PILOT.read_text(encoding="utf-8"))
    # یک پاراگراف با لاتین برهنه به انتهای نخستین مبحث اضافه کن
    raw["topics"][0]["blocks"].append({
        "id": "x-bidi", "type": "paragraph", "status": "needs_review",
        "sources": [{"book": "جزوهٔ درس", "pages": "۱"}],
        "text": "این جمله دارای عبارت Bare Latin Term بدون ایزوله‌سازی است.",
    })
    p = tmp_path / "bad.yaml"
    p.write_text(yaml.dump(raw, allow_unicode=True), encoding="utf-8")
    hits = bidi_lint(load_session(str(p)))
    assert hits and any("x-bidi" in h for h in hits)


# ------------------------------------------------- TL;DR و خودآزمایی (اشتقاق)
def _section_paragraphs(session, sec_id):
    out, on = [], False
    for b in session.all_blocks():
        if b.type == "section":
            on = b.id == sec_id
            continue
        if on and b.type == "paragraph":
            out.append(b)
    return out


def _section_of(session, block_id):
    cur = None
    for b in session.all_blocks():
        if b.type == "section":
            cur = b.id
        if b.id == block_id:
            return cur
    return None


def test_no_tldr_blocks_in_pilot():
    """راند ۱۰ (تصمیم محصول): بلوک‌های «در یک نگاه» (TL;DR) به‌طور کامل حذف‌اند."""
    s = load_session(str(PILOT))
    assert [b for b in s.all_blocks() if b.type == "tldr"] == []
    assert validate(s) == []


def _synthetic_session(tmp_path):
    import yaml
    doc = {
        "id": "syn_qc", "course": "درس آزمایشی", "session_number": 1, "session_total": 1,
        "title": "جلسهٔ آزمایشی", "version": "۱٫۰",
        "frame_theme": "none",
        "topics": [{
            "id": "t1", "number": 1, "title": "مبحث آزمایشی", "mother_pages": "۱",
            "why": "برای آزمون موتور.", "objectives": ["بدانید."],
            "prereq_required": [], "prereq_suggested": [], "key_terms": [],
            "blocks": [
                {"id": "s1", "type": "section", "title": "بخش یک"},
                {"id": "p1", "type": "paragraph", "status": "approved",
                 "sources": [{"book": "منبع", "pages": "۱"}],
                 "text": "سلول عصبی از [[term:جسم سلولی|Cell body]] منشأ می‌گیرد و پیام را منتقل می‌کند."},
                {"id": "qc1", "type": "quick_check", "status": "approved",
                 "sources": [{"book": "منبع", "pages": "۱"}],
                 "items": [{"q": "سلول عصبی از …… منشأ می‌گیرد و پیام را منتقل می‌کند.",
                            "a": "جسم سلولی ([en:Cell body])"}]},
            ],
        }],
    }
    p = tmp_path / "syn.yaml"
    p.write_text(yaml.dump(doc, allow_unicode=True), encoding="utf-8")
    return load_session(str(p))


def test_quick_check_engine_cloze_and_answer_key(tmp_path):
    """موتور خودآزمایی را پشتیبانی می‌کند (اختیاری)؛ در پایلوت نهایی استفاده نشده است."""
    s = _synthetic_session(tmp_path)
    assert validate(s) == []
    qb = [b for b in s.all_blocks() if b.type == "quick_check"][0]
    item = qb.data["items"][0]
    sent = _sentences([b for b in s.all_blocks() if b.id == "p1"][0].data["text"])[0]
    assert normalize_text(item["q"].replace(BLANK, item["a"])) == normalize_text(sent)
    plan = plan_session(s, "final", ROOT)
    ts = Typesetter(plan)
    html = ts.document("")
    assert "پاسخ‌نامهٔ خودآزمایی سریع" in html
    assert ts._qc_items and ts._qc_items[0][1] == item["a"]


def test_pilot_is_final_without_quickcheck_or_provisional_labels():
    s, plan = _plan()
    assert not [b for b in s.all_blocks() if b.type == "quick_check"]
    html = Typesetter(plan).document("")
    assert "پیشنهاد برای تأیید تیم علمی" not in html
    assert "پاسخ‌نامهٔ خودآزمایی" not in html


# ---------------------------------------------------------- مادهٔ پایانی
def test_glossary_only_session_terms_with_pages():
    s, plan = _plan()
    ts = Typesetter(plan, toc_pages={})
    g = ts.glossary()
    assert "واژه‌نامه" in g
    # هر اصطلاح واژه‌نامه باید در دادهٔ جلسه ریشه داشته باشد
    known = set()
    for t in s.topics:
        for kt in t.key_terms:
            known.add(str(kt.get("fa", "")).strip())
    fafound = [x.strip() for x in re.findall(r'gloss__fa">([^<]+)', g)]
    assert len(fafound) >= 20
    assert "تپهٔ آکسونی" in fafound  # از برچسب شکل/اصطلاح درون‌متنی
    # بدون toc_pages جای شماره‌ها «…» است (پایداری ارتفاع بین گذrها)
    assert "…" in g


def test_no_colophon_or_doc_end():
    """راند ۹ (تصمیم محصول): شناسنامه و امضای پایانی به‌طور ساختاری حذف شده‌اند."""
    s, plan = _plan()
    assert not hasattr(Typesetter(plan), "colophon")
    html = Typesetter(plan).document("")
    assert "شناسنامه" not in html
    assert "doc-end" not in html
    css = (ROOT / "engine" / "themes" / "humsyar.css").read_text(encoding="utf-8")
    assert ".colophon" not in css


# ------------------------------------------------------------- نمودار ریلی
def test_dual_rail_svg_from_block_data():
    s, plan = _plan()
    html = Typesetter(plan).document("")
    assert 'class="dualrail"' in html
    from humsyar.palette import hex_of
    assert hex_of("dir-forward") in html and hex_of("dir-reverse") in html  # دو توکن عمومی جهت
    assert "آنتروگراد: از سوما به پایانه" in html  # عین عنوان داده


# ---------------------------------------------- صفحهٔ ۲: کارت‌های مطالب (بدون فهرست شکل/جدول)
def test_lists_render_stable_across_passes():
    """تصمیم کاربر: فهرست شکل‌ها و جدول‌ها از صفحهٔ ۲ حذف شده‌اند؛ به‌جای آن
    شبکهٔ کارت‌های مبحث است و شماره‌ها از toc_pages واقعی می‌آیند."""
    s, plan = _plan()
    assert not hasattr(Typesetter(plan), "figure_table_lists")
    html = Typesetter(plan).toc_page()
    assert "فهرست شکل‌ها" not in html and "فهرست جدول‌ها" not in html
    assert html.count('class="toc-card"') == len(s.topics)
    pages = {h[2]: 7 for h in plan.headings}
    html2 = Typesetter(plan, toc_pages=pages).toc_page()
    assert html2.count('class="toc-card"') == len(s.topics)  # همان ساختار، فقط عدد
    assert "ص ۷" in html2


# ---------------------------------------------------------- قاب چندواریانتی
def test_page_topics_mapping():
    s, plan = _plan()
    toc = {t.id: (3 if t.number == 4 else 8) for t in s.topics}
    pt = _page_topics(s, plan, toc, total_pages=16)
    assert pt[2] == {}                      # صفحهٔ فهرست: بدون مبحث
    assert pt[3]["number"] == 4 and pt[7]["number"] == 4
    assert pt[8]["number"] == 6 and pt[16]["number"] == 6
    assert pt[8]["order"] > pt[3]["order"]  # زبانه پایین‌تر می‌رود


# ---------------------------------------------------------------- کاور
def test_cover_brand_plate_present():
    from humsyar.brand import load_brand
    from humsyar.cover import cover_html
    s = load_session(str(PILOT))
    brand = load_brand(ROOT)
    html = cover_html(s, brand, "")
    assert ".cv-brand::before" in html  # صفحهٔ تیرهٔ پشت برند (رفع تداخل با نورون)


# ---------------------------------------------------------------- نشان عدد
def test_number_badge_markup_roundtrip():
    from humsyar.model import normalize_text as nz
    assert nz("تا [[num:۶۰ قطعه]] میلین") == nz("تا ۶۰ قطعه میلین")
    s, plan = _plan()
    html = Typesetter(plan).document("")
    assert 'class="numbadge"' in html
    assert "۶۰ قطعهٔ بین‌گره‌ای" in html


def test_new_block_types_validate():
    s = load_session(str(PILOT))
    assert validate(s) == []
    types = {b.type for b in s.all_blocks()}
    assert "tldr" not in types and "quick_check" not in types  # راند ۱۰: TL;DR حذف
