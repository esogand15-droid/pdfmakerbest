"""راند ۱۲ — سیستم رنگ گرم و نقش‌محور (Warm Medical).

قوانین سند: رنگ فقط از نقش (خانوادهٔ نشانه/نوع کادر/شمارهٔ مبحث) می‌آید،
هرگز از محتوا؛ مشتقات مبحث خودکار و کنتراست‌امن‌اند؛ راهنما شش کارت
خانواده است؛ جلسهٔ ساختگی با مباحث نامرتبط هم باید بی‌خطا رندر شود.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from humsyar.icons import (CALLOUT_ICONS, ICONS, ICON_FAMILY, KIND_FAMILY,  # noqa: E402
                           UNKNOWN_ICONS, family_of_icon, family_of_kind)
from humsyar.model import load_session, validate  # noqa: E402
from humsyar.palette import chapter_accent, chapter_vars, contrast, hex_of  # noqa: E402
from humsyar.planner import plan_session  # noqa: E402
from humsyar.typeset import Typesetter  # noqa: E402

PILOT = ROOT / "content" / "session01_pilot.yaml"
CSS = (ROOT / "engine" / "themes" / "humsyar.css").read_text(encoding="utf-8")


def test_warm_tokens_present():
    assert hex_of("paper") == "#FFFBF3"  # راند ۱۳: کرم صفحه روشن‌تر شد
    assert hex_of("ink") == "#26324B"
    assert hex_of("primary") == "#139A8E"
    assert hex_of("primary-deep") == "#0F5E63"
    assert hex_of("sun") == "#FFB627"
    for i, hx in enumerate(["#139A8E", "#FF7A45", "#7C5CFA", "#2F80ED",
                            "#E8508B", "#2EAD6B", "#F2A100", "#E5484D"], 1):
        assert hex_of(f"chapter-{i}") == hx
    for fam in ("fam1", "fam2", "fam3", "fam4w", "fam4c", "fam4e",
                "fam4u", "fam5", "fam6"):
        assert hex_of(fam) and hex_of(f"{fam}-deep")


def test_chapter_accent_cycles_by_number_only():
    assert chapter_accent(1) == "#139A8E"
    assert chapter_accent(4) == "#2F80ED"
    assert chapter_accent(6) == "#2EAD6B"
    assert chapter_accent(9) == chapter_accent(1)
    assert chapter_accent(14) == chapter_accent(6)


def test_chapter_derivatives_contrast_safe():
    for n in range(1, 9):
        v = chapter_vars(n)
        assert contrast("#FFFFFF", v["--chapter-header"]) >= 4.5, n
        assert contrast(v["--chapter-deep"], hex_of("paper")) >= 4.5, n


def test_every_icon_and_kind_has_family():
    for name in ICONS:
        if name == "note":
            assert family_of_icon(name) == "neutral"
        else:
            assert name in ICON_FAMILY, name
    for kind in CALLOUT_ICONS:
        assert family_of_kind(kind).startswith("fam"), kind
    assert set(KIND_FAMILY.values()) == {
        "fam1", "fam2", "fam3", "fam4w", "fam4c", "fam4e", "fam4u", "fam5"}


def test_unknown_icon_falls_back_with_warning_not_error():
    UNKNOWN_ICONS.discard("no-such-icon")
    assert family_of_icon("no-such-icon") == "neutral"
    assert "no-such-icon" in UNKNOWN_ICONS


def _pilot_html(**kw):
    s = load_session(str(PILOT))
    return Typesetter(plan_session(s, "final", ROOT), **kw).document("")


def test_topics_carry_distinct_chapter_vars():
    """راند ۱۳ (چرخش مستند): رنگ مبحث حذف شد؛ کل جزوه یک رنگ جلسه دارد.
    نام تست برای ردیابی تاریخچه نگه داشته شده است."""
    from humsyar.palette import session_vars
    html = _pilot_html()
    sv = session_vars(1)
    assert sv["--session-accent"] in html
    assert "--chapter-accent" not in html and "--chapter-header" not in html
    # سربرگ جدول از رنگ جلسه می‌آید که یک‌بار روی body سوار شده است
    assert "var(--session-header" in CSS
    # بج آیکون و کلاس خانواده روی کال‌اوت‌ها (بدون تغییر)
    assert 'class="icb fam ' in html
    assert "callout--" in html and " fam fam" in html


def test_legend_six_family_cards():
    s = load_session(str(PILOT))
    g = Typesetter(plan_session(s, "final", ROOT)).reading_guide()
    assert g.count("fguide__card") == 6
    for lbl in ("دانش پایه", "تأکید و یادگیری", "کاربرد و دنیای واقعی",
                "دقت و احتیاط", "حافظه و آزمون", "ساختار و ناوبری"):
        assert lbl in g
    assert "fguide__sample" not in g  # راند ۱۳: نوار نمونهٔ بزرگ حذف شد


def test_no_content_based_color_conditions_in_engine():
    """ممنوعیت سند: هیچ شرط رنگی بر اساس مبحث/سلول مشخص در کد موتور نیست."""
    # شناسهٔ مبحث مشخص در هیچ فایل موتور نباید باشد؛ نام مفهوم علمی هم در
    # فایل‌های منطق رنگ/چیدمان ممنوع است (موتیف هنری کاور مستثناست: نقاشی است، نه شرط رنگ)
    for fn in ("typeset.py", "frame.py", "diagrams.py", "cover.py",
               "palette.py", "icons.py", "ultra.py"):
        src = (ROOT / "engine" / "humsyar" / fn).read_text(encoding="utf-8")
        for lit in ("s01-t04", "s01-t06"):
            assert lit not in src, (fn, lit)
    banned_literals = ("آستروسیت", "شوان", "astrocyte", "schwann")
    for fn in ("typeset.py", "frame.py", "diagrams.py", "palette.py",
               "icons.py", "ultra.py"):
        src = (ROOT / "engine" / "humsyar" / fn).read_text(encoding="utf-8")
        for lit in banned_literals:
            assert lit not in src, (fn, lit)
    for lit in banned_literals:
        assert lit not in CSS, lit


def test_synthetic_session_renders_with_chapter_colors(tmp_path):
    """جلسهٔ ساختگی (شمارهٔ جلسهٔ ۳) با مباحث ۳، ۷ و ۹: رندر بی‌خطا؛
    راند ۱۳: رنگ فقط از شمارهٔ «جلسه» می‌آید و برای همهٔ مباحث یکی است."""
    import yaml
    doc = {
        "id": "syn_warm", "course": "درس آزمایشی", "session_number": 3,
        "session_total": 9, "title": "جلسهٔ ساختگی رنگ", "version": "۱٫۰",
        "frame_theme": "none",
        "session_map": [{"number": n, "title": f"مبحث نمونهٔ {n}"} for n in (3, 7, 9)],
        "topics": [{
            "id": f"syn-t{n:02d}", "number": n, "title": f"مبحث نمونهٔ {n}",
            "why": "چرایی نمونه", "objectives": ["هدف نمونه"],
            "key_terms": [{"fa": "واژهٔ نمونه", "en": "Sample"}],
            "blocks": [
                {"type": "section", "id": f"syn{n}-s1", "title": "بخش نمونه"},
                {"type": "paragraph", "id": f"syn{n}-p1",
                 "text": "متن نمونه برای آزمون رنگ‌بندی خودکار موتور است.",
                 "sources": []},
                {"type": "table", "id": f"syn{n}-tb1", "title": "جدول نمونه",
                 "headers": ["ویژگی", "الف", "ب"], "row_header": True,
                 "rows": [["ردیف نمونه", "یک", "دو"]], "sources": []},
                {"type": "callout", "id": f"syn{n}-c1", "kind": "warning",
                 "title": "عنوان نمونه", "text": "متن نمونهٔ کادر.", "sources": []},
            ],
        } for n in (3, 7, 9)],
        "closing": [],
    }
    p = tmp_path / "syn.yaml"
    p.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    s = load_session(str(p))
    assert validate(s) == []
    html = Typesetter(plan_session(s, "final", ROOT)).document("")
    from humsyar.palette import session_accent
    assert session_accent(3) in html  # رنگ جلسهٔ ۳ روی کل سند
    assert "--chapter-accent" not in html
    assert "fam4w" in html  # کادر هشدار خانوادهٔ خودش را گرفته است
    assert html.count("fguide__card") == 6


def test_bw_profile_class_and_css():
    html = _pilot_html(bw_theme=True)
    assert "bw-theme" in html
    assert "body.bw-theme table.tbl th" in CSS
    assert "body.bw-theme .callout.fam" in CSS
