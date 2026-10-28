"""تست‌های راند ۳ (مرحلهٔ ۸ پرامپت ارتقا): سناریوهای الزامی جدول/شکل/خطا/پایداری.

فیکسچرها اسناد مصنوعی‌اند (tests/fixtures) و هیچ محتوای علمی ندارند؛ بیلد هر فیکسچر
یک بار در سطح ماژول انجام می‌شود و چند سناریو روی همان خروجی سنجیده می‌شوند.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))

from humsyar.build import build  # noqa: E402
from humsyar.model import load_session, normalize_text  # noqa: E402
from humsyar.packing import chunk_table  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
OUT = ROOT / "tests" / "_out"


def _build(name: str, yaml_name: str) -> dict:
    out = OUT / name
    return build(str(FIX / yaml_name), edition="final", theme="a", out_dir=str(out))


@pytest.fixture(scope="module")
def rep_a():
    return _build("a", "tables_basic.yaml")


@pytest.fixture(scope="module")
def rep_b():
    return _build("b", "table_long.yaml")


@pytest.fixture(scope="module")
def rep_c():
    return _build("c", "mixed.yaml")


def _pages_with(pdf_path: str, probe: str) -> list[int]:
    import pymupdf
    doc = pymupdf.open(pdf_path)
    n = normalize_text(probe)[:30]
    # صفحات ۱–۲ (کاور و فهرست‌ها) شمرده نمی‌شوند؛ عنوان جدول در «فهرست جدول‌ها» هم می‌آید
    # برگهٔ جمع‌بندی فوق‌فشرده (راند ۱۴، پیش‌تر نقشهٔ مرور) متن ردیف‌ها را
    # عیناً تکرار می‌کند؛ صفحات آن از جست‌وجوی «تکرار ناخواسته» کنار گذاشته می‌شوند.
    # برگه همیشه صفحهٔ مستقل خودش است، پس سقف جست‌وجو انحصاری است.
    rev_start = next((i + 1 for i, p in enumerate(doc)
                      if i + 1 >= 3
                      and (normalize_text("مرور فوق‌فشرده") in normalize_text(p.get_text())
                           or normalize_text("نقشهٔ جامع مرور") in normalize_text(p.get_text()))),
                     doc.page_count + 1)
    return [i + 1 for i, p in enumerate(doc)
            if 3 <= i + 1 < rev_start and n in normalize_text(p.get_text())]


# سناریو ۱ و ۶: جدول کوتاه با فارسی/انگلیسی/عدد، سالم و یکپارچه
def test_short_mixed_table_intact(rep_a):
    assert rep_a["qa"]["ok"], rep_a["qa"]["errors"]
    assert rep_a["qa"]["tables_split_badly"] == []
    cap = _pages_with(rep_a["pdf"], "جدول آزمایشی کوتاه با عدد و اصطلاح لاتین")
    last = _pages_with(rep_a["pdf"], "ردیف پایانی جدول کوتاه آزمایشی")
    assert cap and last and cap[0] in last


# سناریو ۲ و ۳ و ۵ و ۷: جدول متوسط چندخطی نزدیک انتهای صفحه — نشکن و کامل
def test_medium_multiline_table_never_split_badly(rep_a):
    cap = _pages_with(rep_a["pdf"], "جدول آزمایشی متوسط با سلول‌های چندخطی طولانی")
    # متن مشترک همهٔ ردیف‌ها فقط باید در همان یک صفحهٔ عنوان دیده شود (نشانهٔ نشکستن)
    rows_pages = _pages_with(rep_a["pdf"], "شرحی طولانی برای چندخطی شدن سلول جدول آزمایشی")
    assert cap and rows_pages == cap[:1]


# سناریو ۴: جدول بلندتر از یک صفحه — ادامهٔ کنترل‌شده + تکرار سربرگ
def test_long_table_controlled_continuation(rep_b):
    assert rep_b["qa"]["ok"], rep_b["qa"]["errors"]
    assert rep_b["qa"]["tables_split_badly"] == []
    cont = _pages_with(rep_b["pdf"], "ادامهٔ جدول — جدول آزمایشی بلندتر از یک صفحه")
    assert cont, "برچسب ادامهٔ جدول باید روی صفحه(های) بعد باشد"
    head = _pages_with(rep_b["pdf"], "مورد آزمایشی")
    assert len(head) >= 2, "سربرگ ستون‌ها باید در هر قطعه تکرار شود"
    last = _pages_with(rep_b["pdf"], "شرح نمایشی دربارهٔ حرکت و ارتباط آن با گلیال")
    assert last and last[0] >= cont[0]


# واحد: الگوریتم قطعه‌بندی ردیفی
def test_chunk_table_row_boundaries_only():
    meta = {"cap": 10.0, "head": 8.0, "rows": [20.0] * 30}
    chunks = chunk_table(meta, page_h=266.0)
    flat = [i for c in chunks for i in c]
    assert flat == list(range(30))           # هیچ ردیفی گم/تکرار/جابه‌جا نشده
    assert all(len(c) >= 1 for c in chunks)
    # ردیف منفردِ بلندتر از صفحه تنها می‌نشیند و بقیه گم نمی‌شوند
    meta2 = {"cap": 10.0, "head": 8.0, "rows": [300.0, 10.0, 10.0]}
    flat2 = [i for c in chunk_table(meta2, page_h=266.0) for i in c]
    assert flat2 == [0, 1, 2]


# سناریو ۸: شکل بزرگ — تصویر و زیرنویس در یک صفحه
def test_large_figure_caption_same_page(rep_c):
    import pymupdf
    doc = pymupdf.open(rep_c["pdf"])
    img_pages = [i + 1 for i, p in enumerate(doc) if p.get_images(full=True)]
    cap_pages = _pages_with(rep_c["pdf"], "تصویر آزمایشی بزرگ با زیرنویس کامل")
    assert cap_pages and cap_pages[0] in img_pages


# سناریو ۹ و ۱۰: پاراگراف دوزبانه + سند چندمبحثی با فهرستِ راستی‌آزمایی‌شده
def test_bilingual_and_multitopic_toc(rep_c):
    assert rep_c["qa"]["ok"], rep_c["qa"]["errors"]
    assert rep_c["qa"].get("toc_verified") is True
    assert rep_c["toc_links"] >= 4
    assert _pages_with(rep_c["pdf"], "Axonal transport")


# سناریو ۱۱: تصویر گمشده → خطای واضح با نام بلوک (Fail Fast)
def test_missing_figure_fails_with_block_name(tmp_path):
    src = (FIX / "mixed.yaml").read_text(encoding="utf-8")
    bad = tmp_path / "bad.yaml"
    bad.write_text(src.replace("p26_x103.png", "p26_x103_missing.png"), encoding="utf-8")
    with pytest.raises(FileNotFoundError) as ei:
        build(str(bad), edition="final", out_dir=str(tmp_path / "out"))
    assert "fxc-f1" in str(ei.value)


# سناریو ۱۲: بازتولید پایدار — صفحات و شمار تصاویر ثابت، بدون تکرار محتوا
def test_rebuild_is_stable(rep_c):
    rep2 = _build("c2", "mixed.yaml")
    assert rep2["qa"]["pages"] == rep_c["qa"]["pages"]
    assert rep2["qa"]["figures_pdf"] == rep_c["qa"]["figures_pdf"] == rep_c["qa"]["figures_model"]


# کادرهای معنایی جدید واقعاً رندر و در راهنمای خواندن فهرست می‌شوند
def test_new_callout_kinds_render(rep_a):
    assert _pages_with(rep_a["pdf"], "تعریف اصطلاح")
    assert _pages_with(rep_a["pdf"], "مثال آموزشی")
    s = load_session(str(FIX / "tables_basic.yaml"))
    kinds = {b.data.get("kind") for b in s.all_blocks() if b.type == "callout"}
    assert {"definition", "example"} <= kinds


# ── هویت بصری: لوگوی رسمی ────────────────────────────────────
def test_brand_logo_assets_exist_and_resolve():
    from humsyar.brand import load_brand
    b = load_brand(ROOT)
    for k in ("logo", "logo_mono", "favicon"):
        assert (ROOT / b[k]).exists(), k
    assert b["logo_uri"].startswith("file:///")
    assert b["logo_mono_uri"].startswith("file:///")


def test_brand_logo_missing_falls_back_without_fake_path(tmp_path):
    from humsyar.brand import load_brand
    b = load_brand(tmp_path)  # ریشه‌ای بدون کانفیگ و بدون دارایی
    assert b["fa"] == "هامزیار" and b["en"] == "HumsYar"
    assert b["logo_uri"] == "" and b["logo_mono_uri"] == ""


def test_cover_contains_logo_image_and_brand_text():
    import pymupdf
    pdf = ROOT / "output" / "neuroanat_s01_pilot_final.pdf"
    if not pdf.exists():
        pytest.skip("PDF پایلوت ساخته نشده")
    doc = pymupdf.open(str(pdf))
    assert len(doc[0].get_images(full=True)) >= 1  # لوگوی رنگی روی کاور
    # نام برند همچنان متنی هم هست (قانون برند؛ لوگو وردمارک ندارد)
    assert "هامزیار" in doc[0].get_text()
    # تصاویر محتوایی با مدل برابرند (دارایی برند در شمارش شکل‌ها نیست)
    import json
    qa = json.loads((ROOT / "output" / "build_report.json").read_text(encoding="utf-8"))["qa"]
    assert qa["figures_pdf"] == qa["figures_model"] == 11
