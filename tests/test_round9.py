"""تست‌های راند ۹ — حذف شناسنامه/چک‌لیست، صفحهٔ درخت جامع، درخت تک‌صفحه‌ای و حذف واژه‌نامه،
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

    # چرخش محصول (بازخورد کاربر): واژه‌نامه و فهرست منابع پایانی حذف‌اند و
    # درخت دقیقاً یک صفحه است: درخت ← جمع‌بندی تألیفی ← برگهٔ دوصفحه‌ای (پایان).
    assert not first("نقشهٔ جامع مرور")
    assert not first("واژه‌نامهٔ فارسی–انگلیسی")
    assert not first("منابع علمی این جلسه")
    tree = first("نمودار درختی جامع جلسه")
    closing = max(i + 1 for i, t in enumerate(pages)
                  if normalize_text("جمع‌بندی و مرور جلسه") in t)
    _n = normalize_text("مرور فوق‌فشرده")  # بعد از درخت؛ راهنمای صفحهٔ ۲ هم این عبارت را دارد
    ultra = next((i + 1 for i, t in enumerate(pages)
                  if tree and i + 1 > tree and _n in t), None)
    assert tree and ultra
    assert tree < closing < ultra
    assert ultra == len(pages) - 1  # برگهٔ دوصفحه‌ای پایان جزوه است
    tree_pages = [i + 1 for i, t in enumerate(pages)
                  if normalize_text("نمودار درختی جامع جلسه") in t]
    assert tree_pages == [tree]     # درخت دقیقاً یک صفحه است، هرگز دو صفحه


def test_no_glossary_anywhere_and_ultra_ends_booklet():
    """چرخش محصول: واژه‌نامه در هیچ صفحه‌ای نیست؛ دو صفحهٔ پایانی برگه‌اند."""
    if not PDF.exists():
        return
    _doc, pages = _norm_pages()
    assert all(normalize_text("واژه‌نامهٔ فارسی") not in t for t in pages)
    assert normalize_text("مرور فوق‌فشرده") in pages[-1]
    assert normalize_text("مرور فوق‌فشرده") in pages[-2]


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
    t6 = next(c for c in tree["children"] if "نوروگلیاها" in str(c.get("label", "")))
    assert t6["children"][0]["label"] == "نوروگلیا"
    # قرارداد تک‌صفحه‌ای (بازخورد کاربر؛ چرخش از پخش چندصفحه‌ای): درخت
    # کاملِ شش‌مبحثی با سبک فشردهٔ PAGE_STYLE دقیقاً در یک SVG می‌آید؛ هیچ
    # شاخه‌ای حذف نمی‌شود و فونت مؤثر از کف QA پایین‌تر نمی‌رود.
    html = Typesetter(_plan_).tree_page()
    svgs = re.findall(r'<svg class="tree-svg" width="(\d+)pt" height="(\d+)pt" '
                      r'viewBox="0 0 ([\d.]+) ([\d.]+)"', html)
    assert len(svgs) == 1, "درخت باید دقیقاً یک SVG (یک صفحه) باشد"
    for wp, hp, vw, _vh in svgs:
        eff = int(wp) / float(vw)
        assert PAGE_STYLE["fs_note"] * eff >= 7.0, eff
        assert PAGE_STYLE["fs_label"] * eff >= 7.4, eff
        assert int(hp) <= 676
    assert "بخش ۱ از" not in html


def test_tree_page_rendering_and_gate():
    s, plan = _plan()
    ts = Typesetter(plan)
    html = ts.tree_page()
    assert html.count('class="treepage"') == 1
    ms = re.findall(r'<svg class="tree-svg" width="(\d+)pt" height="(\d+)pt"', html)
    assert len(ms) == 1 and all(int(w) <= 516 and int(h) <= 676 for w, h in ms)
    # نوار اصطلاحات زیر درخت حذف است (بازخورد کاربر)
    assert "اصطلاحات کلیدی جلسه" not in html
    assert "treepage__terms" not in html
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


def test_no_closing_sources_list_but_inline_chips_stay():
    """چرخش محصول: بلوک پایانی «منابع علمی این جلسه» حذف است؛ چیپ‌های منبعِ
    کنار هر مطلب (ردیابی‌پذیری) همچنان در بدنه می‌مانند."""
    s, plan = _plan()
    ts = Typesetter(plan)
    assert not hasattr(ts, "sources_list")
    html = ts.document("")
    assert "منابع علمی این جلسه" not in html
    assert "srclist" not in html
    assert "جزوهٔ درس" in html  # چیپ‌های منبع درون‌متنی باقی‌اند


def test_heading_pages_not_stolen_by_tree_page():
    if not PDF.exists():
        return
    from humsyar.build import _find_heading_pages
    s, plan = _plan()
    pages = _find_heading_pages(PDF, plan, start=2)
    assert len(pages) == len(plan.headings)
    # صفحهٔ واقعی بدنه (همان که گزارش ساخت ثبت کرده)، نه صفحهٔ درخت پایانی
    import json as _json
    rep = _json.loads((ROOT / "output" / "build_report.json").read_text(encoding="utf-8"))
    assert pages["s01t6-s6"] == rep["toc_pages_found"]["s01t6-s6"]
    _doc, norm = _norm_pages()
    tree_pages = [i + 1 for i, t in enumerate(norm)
                  if normalize_text("نمودار درختی جامع جلسه") in t]
    assert tree_pages and max(pages.values()) < min(tree_pages)
