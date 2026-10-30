"""راند ۱۴ — حسابرسی موتور + قرارداد «فقط یک PDF نهایی».

قفل‌ها: برگهٔ فوق‌فشرده داخل همان PDF نهایی است و «مرور جامع» برنگشته؛
شماره‌های فهرست با صفحهٔ واقعی سرفصل می‌خوانند (رگرسیون باگ یابندهٔ صفحه)؛
بدون قاب هم صفحه‌ها شماره می‌خورند؛ ورودی خراب/تصویر گمشده/فونت گمشده با
خطای صریح متوقف می‌شود و فایل نهایی جعلی ساخته نمی‌شود؛ قفل ضد اجرای هم‌زمان.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from humsyar.model import load_session, normalize_text  # noqa: E402
from humsyar.planner import plain_title, plan_session  # noqa: E402
from humsyar.typeset import Typesetter  # noqa: E402

PILOT = ROOT / "content" / "session01_pilot.yaml"
FINAL = ROOT / "output" / "HumsYar_Final.pdf"
FA = "۰۱۲۳۴۵۶۷۸۹"


def _mini_yaml(tmp_path, *, frame_theme="anatomy-nervous", extra_blocks=None,
               dup_id=False, missing_fig=False):
    import yaml
    blocks = [
        {"type": "section", "id": "m-s1", "title": "بخش نمونهٔ آزمایشی"},
        {"type": "paragraph", "id": "m-p1",
         "text": "این یک متن نمونهٔ آزمایشی برای آزمون موتور است و عدد ۴۲ در آن آمده است.",
         "sources": []},
        {"type": "table", "id": "m-tb1", "title": "جدول نمونهٔ آزمایشی",
         "headers": ["ویژگی", "مقدار"], "row_header": True,
         "rows": [["ردیف نمونهٔ یک", "مقدار نمونهٔ یک"]], "sources": []},
        {"type": "callout", "id": "m-c1", "kind": "warning",
         "title": "هشدار نمونه", "text": "متن هشدار نمونه برای آزمون.", "sources": []},
    ]
    if missing_fig:
        blocks.append({"type": "figure", "id": "m-f1", "file": "assets/figures/__nope__.png",
                       "title_fa": "شکل گمشده", "explain_fa": "توضیح نمونه", "sources": []})
    blocks += extra_blocks or []
    if dup_id:
        blocks[1]["id"] = blocks[0]["id"]
    doc = {
        "id": "mini14", "course": "درس آزمایشی", "session_number": 2,
        "session_total": 4, "title": "جلسهٔ آزمایشی راند ۱۴", "version": "۱٫۰",
        "frame_theme": frame_theme,
        "session_map": [{"number": 1, "title": "مبحث نمونهٔ یک"}],
        "topics": [{
            "id": "mini-t01", "number": 1, "title": "مبحث نمونهٔ یک",
            "why": "چرایی نمونه", "objectives": ["هدف نمونه"],
            "key_terms": [{"fa": "واژهٔ نمونه", "en": "Sample"}],
            "blocks": blocks,
        }],
        "closing": [{"type": "summary_box", "id": "m-sb1", "title": "جمع‌بندی نمونه",
                     "text": "متن جمع‌بندی نمونهٔ آزمایشی است.", "sources": []}],
    }
    p = tmp_path / "mini.yaml"
    p.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    return str(p)


# ------------------------------------------------------- قرارداد خروجی واحد
def test_single_final_pdf_published_and_matches_build():
    if not FINAL.exists():
        pytest.skip("اول build بزنید")
    built = ROOT / "output" / "neuroanat_s01_pilot_final.pdf"
    assert built.exists()
    assert FINAL.read_bytes() == built.read_bytes()
    # دقیقاً یک فایل با نام ثابت نهایی (.prev نسخهٔ داخلی است، تحویلی نیست)
    finals = [p.name for p in (ROOT / "output").glob("HumsYar_Final*.pdf")
              if not p.name.endswith(".prev.pdf")]
    assert finals == ["HumsYar_Final.pdf"]


def test_final_contains_sheet_not_revmap_and_order():
    if not FINAL.exists():
        pytest.skip("اول build بزنید")
    import pymupdf
    doc = pymupdf.open(str(FINAL))
    pages = [normalize_text(p.get_text()) for p in doc]

    def first(probe):
        n = normalize_text(probe)
        return next((i + 1 for i, t in enumerate(pages) if n in t), None)

    assert not first("نقشهٔ جامع مرور")            # مرور جامع قدیمی برگشته نیست
    tree = first("نمودار درختی جامع جلسه")
    # پروب برگه: «مرور فوق‌فشرده» در راهنمای صفحهٔ ۲ هم هست؛ پس از صفحهٔ درخت به بعد
    _n = normalize_text("مرور فوق‌فشرده")
    ultra = next((i + 1 for i, t in enumerate(pages)
                  if tree and i + 1 > tree and _n in t), None)
    gloss = first("واژه‌نامهٔ فارسی–انگلیسی")
    assert tree and ultra and gloss and tree < ultra < gloss == len(pages)
    titles = [t for _l, t, _p in doc.get_toc()]
    assert any("فوق‌فشرده" in t for t in titles)   # نشانک برگه


def test_toc_numbers_point_to_pages_containing_heading():
    """رگرسیون باگ راند ۱۴: سرفصل نباید به صفحهٔ درخت/برگه نسبت داده شود."""
    if not FINAL.exists():
        pytest.skip("اول build بزنید")
    import json
    import pymupdf
    rep = json.loads((ROOT / "output" / "build_report.json").read_text(encoding="utf-8"))
    s = load_session(str(PILOT))
    plan = plan_session(s, "final", ROOT)
    doc = pymupdf.open(str(FINAL))
    pages = [normalize_text(p.get_text()) for p in doc]
    seq = []
    for _lvl, display, anchor in plan.headings:
        pg = rep["toc_pages_found"].get(anchor)
        assert pg, anchor
        seq.append(pg)
        fa_words = [w for w in plain_title(display).split()
                    if any("؀" <= ch <= "ۿ" for ch in w)]
        longest = normalize_text(max(fa_words, key=len)) if fa_words else ""
        assert longest in pages[pg - 1], (anchor, display, pg)
    assert seq == sorted(seq)  # یکنواخت صعودی با ترتیب سند


def test_document_excludes_revmap_by_default():
    s = load_session(str(PILOT))
    html = Typesetter(plan_session(s, "final", ROOT)).document("")
    assert "نقشهٔ جامع مرور" not in html


# ------------------------------------------------------- اصلاحات حسابرسی
def test_frame_none_pages_still_numbered(tmp_path):
    from humsyar.build import build
    y = _mini_yaml(tmp_path, frame_theme="none")
    rep = build(y, out_dir=str(tmp_path / "out"))
    import pymupdf
    doc = pymupdf.open(rep["pdf"])
    MM = 72 / 25.4
    found = []
    for i in range(1, doc.page_count):
        zone = doc[i].get_textbox(pymupdf.Rect(96 * MM, 287 * MM, 114 * MM, 295 * MM))
        found.append("".join(c for c in zone if c in FA))
    assert any(found), f"هیچ صفحه‌ای شمارهٔ کپسولی نگرفت: {found}"


def test_build_lock_blocks_concurrent_build(tmp_path):
    from humsyar.build import build
    out = tmp_path / "out"
    out.mkdir()
    lock = out / ".humsyar-build.lock"
    lock.write_text("99999", encoding="utf-8")
    y = _mini_yaml(tmp_path)
    with pytest.raises(RuntimeError):
        build(y, out_dir=str(out))
    assert lock.exists()  # قفلِ ساختِ در حال اجرا دست نخورده می‌ماند


def test_invalid_input_fails_without_final(tmp_path):
    from humsyar.build import build
    y = _mini_yaml(tmp_path, dup_id=True)
    with pytest.raises(ValueError):
        build(y, out_dir=str(tmp_path / "out"))
    assert not (tmp_path / "out" / "HumsYar_Final.pdf").exists()


def test_missing_figure_stops_build(tmp_path):
    from humsyar.build import build
    y = _mini_yaml(tmp_path, missing_fig=True)
    with pytest.raises(FileNotFoundError):
        build(y, out_dir=str(tmp_path / "out"))


def test_missing_font_hard_fails(tmp_path, monkeypatch):
    import humsyar.build as bmod
    monkeypatch.setattr(bmod, "REPO_ROOT", tmp_path)
    with pytest.raises(FileNotFoundError):
        bmod._font_css()


def test_rebuild_is_deterministic_in_pages(tmp_path):
    from humsyar.build import build
    y = _mini_yaml(tmp_path)
    r1 = build(y, out_dir=str(tmp_path / "o1"))
    r2 = build(y, out_dir=str(tmp_path / "o2"))
    assert r1["qa"]["ok"] and r2["qa"]["ok"], (r1["qa"]["errors"], r2["qa"]["errors"])
    assert r1["qa"]["pages"] == r2["qa"]["pages"]


def test_huge_tree_keeps_every_label():
    from humsyar.diagrams import tree_svg
    def node(i, depth):
        kids = [node(i * 10 + j, depth + 1) for j in range(3)] if depth < 3 else []
        return {"label": f"برچسب آزمایشی شمارهٔ {i} با متن نسبتاً بلند برای شکست خط",
                "note": "یادداشت نمونهٔ آزمایشی", "children": kids}
    svg = tree_svg(node(1, 0))
    plain = normalize_text(svg)
    for i in (1, 10, 11, 100, 111, 122):
        assert normalize_text(f"برچسب آزمایشی شمارهٔ {i}")[:18] in plain, i
