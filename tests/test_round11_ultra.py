"""راند ۱۱ — برگهٔ مرور فوق‌فشردهٔ حداکثر دوصفحه‌ای (خروجی سوم مستقل).

معیارها از سند راند ۱۱: بودجهٔ دو صفحه از ابتدا، اولویت A/B/C شفاف، بدون
بازنویسی علمی (متن‌ها عین گزاره‌های منبع‌اند)، کف فونت، ضدِ «دیوار متن»
(سقف نسبت حجم متن و سقف طول نکتهٔ تکمیلی)، ردیابی هر نکته با شناسهٔ منبع.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from humsyar.model import load_session, normalize_text  # noqa: E402
from humsyar.revision import extract_items  # noqa: E402
from humsyar.ultra import _cfg, _has_quantity, build_components, dedup, prioritize  # noqa: E402

PILOT = ROOT / "content" / "session01_pilot.yaml"
ULTRA_PDF = ROOT / "output" / "session01_pilot_ultra.pdf"
ULTRA_REPORT = ROOT / "output" / "session01_pilot_ultra_report.json"


def _uitems():
    s = load_session(str(PILOT))
    return s, prioritize(s, extract_items(s))


# ---------------------------------------------------------------- اولویت‌بندی
def test_priority_rules():
    s, us = _uitems()
    by_kind = {}
    for u in us:
        by_kind.setdefault(u.item.kind, set()).add(u.priority)
    assert by_kind["exception"] == {"A"}
    assert by_kind["source_conflict"] == {"A"}
    assert by_kind["process"] == {"A"}
    assert by_kind["table_row"] == {"A"}
    assert by_kind["figure_visual"] == {"X"}
    # هر گزارهٔ عدددار علمی دست‌کم A است؛ استثناهای مجاز: کپشن انگلیسی شکل و
    # جملهٔ ارجاعی به خودِ سند (ناوبری، نه نکتهٔ علمی). «عدد» یعنی کمیت علمی؛
    # رقم ارجاعیِ تنها (شمارهٔ شکل/جدول/صفحه/فصل/مبحث/جلسه) کمیت نیست —
    # پالایش نسخهٔ کامل: با ۳۱ شکل، شرح‌های پر از ارجاع A کاذب می‌ساختند.
    for u in us:
        if (_has_quantity(u.item.text) and u.priority != "X"
                and u.item.meta.get("lang") != "en"
                and not any(m in u.item.text for m in ("قاب پایانی", "همین جزوه", "در این جزوه"))):
            assert u.priority == "A", u.item.id
    # کپشن انگلیسی شکل هرگز «عدد کلیدی» نمی‌شود
    for u in us:
        if u.item.meta.get("lang") == "en":
            assert u.priority == "C"
    # اصطلاحات کلیدی مبحث A و برچسب‌های شکل B
    topic_ids = {t.id for t in s.topics}
    for u in us:
        if u.item.kind == "terminology" and u.item.block_id in topic_ids:
            assert u.priority == "A"


def test_dedup_conservative_and_deterministic():
    s, us = _uitems()
    merges1 = dedup(us)
    dropped1 = sorted(u.item.id for u in us if u.dropped)
    s2, us2 = _uitems()
    dedup(us2)
    assert dropped1 == sorted(u.item.id for u in us2 if u.dropped)
    # زوج تعارضی (اعداد متفاوت) هرگز ادغام نمی‌شود
    for m in merges1:
        assert m["similarity"] in ("en",) or float(m["similarity"]) >= 0.85
    conflict = [u for u in us if u.item.kind == "source_conflict"]
    assert conflict and all(not u.dropped for u in conflict)


def test_components_cover_and_assign_single_home():
    s, us = _uitems()
    dedup(us)
    comps = build_components(s, us)
    homes = [u.item.id for c in comps for u in c.uitems]
    assert len(homes) == len(set(homes))  # هر نکته فقط یک خانهٔ نمایشی
    kinds = {c.kind for c in comps}
    assert {"skeleton", "table", "proc", "alerts"} <= kinds
    assert any(c.pool == 1 for c in comps) and any(c.pool == 2 for c in comps)


# ---------------------------------------------------------------- خروجی ساخته‌شده
def _report():
    if not ULTRA_REPORT.exists():
        pytest.skip("برگهٔ فوق‌فشرده ساخته نشده است (make ultra)")
    return json.loads(ULTRA_REPORT.read_text(encoding="utf-8"))


def test_sheet_is_at_most_two_pages_and_a_complete():
    import pymupdf
    rep = _report()
    assert ULTRA_PDF.exists()
    doc = pymupdf.open(str(ULTRA_PDF))
    assert doc.page_count <= 2
    assert rep["fits_two_pages"] and rep["status"] == "standard"
    a = rep["coverage"]["A"]
    # پوشش A کامل است: حاضر یا ادغام‌شده با گزارهٔ هم‌معنا (با ثبت در گزارش)
    assert a["in_sheet"] + a["merged"] == a["total"]
    assert rep["overflow_a_count"] == 0
    assert rep["missing_numbers_check"] == []


def test_sheet_is_not_a_rewrite_wall():
    rep = _report()
    cfg = _cfg()
    # سقف نسبت متن: برگه نباید بیشتر متن منبع را به شکل جمله برگرداند
    kept_ratio = rep["text_chars"]["in_sheet"] / rep["text_chars"]["source_items"]
    assert kept_ratio <= float(cfg["max_text_ratio"]) + 0.15  # A کامل ممکن است از سقف C بگذرد؛ C مقید است
    assert rep["text_chars"]["reduction_pct"] >= 40
    # نکته‌های C حاضر همگی کوتاه‌اند (توضیح بلند به متن اصلی برمی‌گردد)
    s, us = _uitems()
    rep_dropped = {d["id"] for d in rep["dropped"]}
    for u in us:
        if u.priority == "C" and u.item.id not in rep_dropped and not u.dropped:
            assert len(u.item.text) <= int(cfg["filler_max_chars"]) + 5, u.item.id


def test_sheet_fonts_above_floor_and_markup_clean():
    import pymupdf
    rep = _report()
    cfg = _cfg()
    assert rep["font"]["base_pt"] >= cfg["font_floor_pt"]
    doc = pymupdf.open(str(ULTRA_PDF))
    sizes = []
    full = ""
    for pg in doc:
        full += pg.get_text()
        for block in pg.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    if span["text"].strip():
                        sizes.append(span["size"])
    assert sizes and min(sizes) >= cfg["font_floor_pt"] - 0.6, min(sizes)
    assert "[en:" not in full and "[[term" not in full and "[[num" not in full
    # تعارض منبع در برگه هم هر دو روایت را نشان می‌دهد (حل‌شدهٔ خودکار ممنوع)؛
    # ترتیب استخراج متن فارسی از PDF قابل اتکا نیست، اجزا جدا بررسی می‌شوند
    norm = normalize_text(full)
    assert normalize_text("اسنل") in norm
    assert normalize_text("۴۰۰") in norm and normalize_text("۱۰۰") in norm
    assert "HumsYar" in full and "هامزیار" in full


def test_every_dropped_item_has_reason_and_trace():
    rep = _report()
    for d in rep["dropped"]:
        assert d["reason"].strip() and d["id"] and d["priority"] in "ABC"
    steps = [t["step"] for t in rep["fit_trace"]]
    assert steps and steps[0] == "A-only"  # بودجه از ابتدا: اول A جا می‌شود
    assert rep["excluded_figure_visual"] > 0  # جزئیات درون تصویر شفاف بیرون است
