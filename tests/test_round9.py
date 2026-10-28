"""تست‌های راند ۹ — حذف شناسنامه/چک‌لیست، صفحهٔ درخت جامع، واژه‌نامهٔ صفحهٔ آخر،
راهنمای فشردهٔ علائم و ترتیب نهایی صفحات پایانی."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))

from humsyar.diagrams import PAGE_STYLE, measure_tree, session_tree
from humsyar.icons import ICONS
from humsyar.model import load_session, normalize_text
from humsyar.planner import plan_session
from humsyar.typeset import Typesetter

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "content" / "session01_pilot.yaml"
PDF = ROOT / "output" / "neuroanat_s01_pilot_final.pdf"


def _plan():
    s = load_session(PILOT)
    return s, plan_session(s, "final", ROOT)


def _norm_pages():
    import pymupdf
    doc = pymupdf.open(str(PDF))
    return doc, [normalize_text(p.get_text()) for p in doc]


def test_no_colophon_or_checklist_anywhere():
    s, plan = _plan()
    assert all(b.type != "checklist" for b in s.all_blocks())
    html = Typesetter(plan).document("")
    assert "شناسنامه" not in html and "چک‌لیست خودآزمایی" not in html
    if PDF.exists():
        _doc, pages = _norm_pages()
        full = "".join(pages)
        assert normalize_text("شناسنامهٔ این نسخه") not in full
        assert normalize_text("چک‌لیست خودآزمایی") not in full


def test_back_matter_order_on_built_pdf():
    if not PDF.exists():
        return
    _doc, pages = _norm_pages()

    def first(probe, start=2):
        n = normalize_text(probe)
        return next((i + 1 for i in range(start, len(pages)) if n in pages[i]), None)

    rev = first("نقشهٔ جامع مرور")
    tree = first("نمودار درختی جامع جلسه")
    closing = max(i + 1 for i, t in enumerate(pages)
                  if normalize_text("جمع‌بندی و مرور جلسه") in t)
    gloss = first("واژه‌نامهٔ فارسی–انگلیسی")
    assert rev and tree and gloss
    assert rev < tree < closing <= gloss
    assert gloss == len(pages)  # واژه‌نامه در صفحهٔ پایانی است


def test_glossary_fully_on_last_page():
    if not PDF.exists():
        return
    s, plan = _plan()
    g = Typesetter(plan).glossary()
    fas = [x.strip() for x in re.findall(r'gloss__fa">([^<]+)', g)]
    assert len(fas) >= 40
    _doc, pages = _norm_pages()
    last = pages[-1]
    # تطابق با سه واژهٔ نخست مدخل (ترتیب پرانتز لاتین در استخراج متن دگرگون می‌شود)
    missing = [fa for fa in fas
               if normalize_text(" ".join(fa.split()[:3])) not in last]
    assert not missing, missing
    # و در صفحهٔ ماقبل آخر مدخل واژه‌نامه‌ای نیامده است (تقسیم نشده)
    assert normalize_text("واژه‌نامهٔ فارسی") not in pages[-2]


def test_session_tree_verbatim_and_complete():
    s, _plan_ = _plan()
    tree = session_tree(s, "جلسهٔ ۱")
    labels: list[str] = []

    def walk(n):
        labels.append(str(n.get("label", "")))
        if n.get("note"):
            labels.append(str(n["note"]))
        for c in n.get("children", []) or []:
            walk(c)

    walk(tree)
    assert len(labels) >= 30
    # هر برچسب/یادداشت عیناً از متن خود محتوا آمده است (ساخته نشده)
    corpus = normalize_text(" ".join(
        frag for b in s.all_blocks() for frag in b.text_fragments()))
    corpus += normalize_text(" ".join(
        [s.title, f"جلسهٔ {s.session_number}"] + [t.title for t in s.topics]
        + [str(k.get("fa", "")) for t in s.topics for k in (t.key_terms or [])]))
    foreign = []
    for lb in labels:
        for piece in lb.split(" · "):
            piece = piece.strip()
            if not piece or piece.startswith("مبحث "):
                continue
            # برچسب‌های ترکیبی مبحث (شماره + عنوان) جداگانه بررسی می‌شوند
            if normalize_text(piece) not in corpus:
                foreign.append(piece)
    assert not foreign, foreign
    # درخت تألیفی گلیا زیر مبحث ۶ پیوند خورده است
    t6 = tree["children"][1]
    assert t6["children"][0]["label"] == "نوروگلیا"
    # ابعاد چاپی: جا در صفحه و خوانایی حداقل
    w, h = measure_tree(tree, PAGE_STYLE)
    scale = min(516 / w, 574 / h, 1.0)
    assert PAGE_STYLE["fs_note"] * scale >= 7.5
    assert PAGE_STYLE["fs_label"] * scale >= 8.0


def test_tree_page_rendering_and_gate():
    s, plan = _plan()
    ts = Typesetter(plan)
    html = ts.tree_page()
    assert 'class="treepage"' in html
    m = re.search(r'<svg class="tree-svg" width="(\d+)" height="(\d+)"', html)
    assert m and int(m.group(1)) <= 516 and int(m.group(2)) <= 574
    assert "اصطلاحات کلیدی جلسه" in html
    plan.layout_cfg = dict(plan.layout_cfg or {}, tree_page={"enabled": False})
    assert Typesetter(plan).tree_page() == ""


def test_icon_guide_compact():
    """راند ۱۲ جایگزین شبکهٔ تک‌رنگ راند ۹ شد: راهنما شش کارت خانوادهٔ معنایی
    است؛ همچنان فشرده (برچسب‌های کوتاه) و در همان صفحهٔ فهرست."""
    s, plan = _plan()
    g = Typesetter(plan).reading_guide()
    assert 'class="fguide"' in g
    assert g.count("fguide__card") == 6
    for fam in ("fam1", "fam2", "fam3", "fam4", "fam5", "fam6"):
        assert f"fcard--{fam}" in g
    labels = re.findall(r'fguide__it">.*?<span>([^<]+)</span>', g, re.S)
    assert len(labels) >= 18
    assert all(len(l.split()) <= 4 for l in labels), labels


def test_icon_system_expanded_and_used():
    for name in ("target", "book", "branch", "compass"):
        assert name in ICONS
    assert len(ICONS) >= 31
    s, plan = _plan()
    html = Typesetter(plan).document("")
    for cls in ("ic--target", "ic--branch", "ic--book", "ic--compass",
                "ic--reference", "ic--terminology"):
        assert cls in html, cls


def test_sources_list_from_content():
    s, plan = _plan()
    sl = Typesetter(plan).sources_list()
    assert "منابع علمی این جلسه" in sl
    for book in ("جزوهٔ درس", "اسنل", "گری"):
        assert book in sl


def test_heading_pages_not_stolen_by_tree_page():
    if not PDF.exists():
        return
    from humsyar.build import _find_heading_pages
    s, plan = _plan()
    pages = _find_heading_pages(PDF, plan, start=2)
    assert len(pages) == len(plan.headings)
    assert pages["s01t6-s6"] == 13  # صفحهٔ واقعی بدنه، نه صفحهٔ درخت
    assert max(pages.values()) <= 13
