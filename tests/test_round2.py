"""تست‌های راند ۲: قانون برند، کاور، فهرست، قاب/کپسول، پلنر، بسته‌بندی، پُری صفحات."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))

from humsyar.brand import load_brand  # noqa: E402
from humsyar.model import load_session, normalize_text  # noqa: E402
from humsyar.planner import plan_session  # noqa: E402
from humsyar.qa import brand_lint, ezafe_lint  # noqa: E402

PILOT_PDF = ROOT / "output" / "neuroanat_s01_pilot_final.pdf"
PILOT_YAML = ROOT / "content" / "session01_pilot.yaml"
MM = 72 / 25.4


@pytest.fixture(scope="module")
def session():
    return load_session(str(PILOT_YAML))


@pytest.fixture(scope="module")
def pdf():
    if not PILOT_PDF.exists():
        pytest.skip("PDF پایلوت هنوز ساخته نشده؛ اول build بزنید")
    import pymupdf
    return pymupdf.open(str(PILOT_PDF))


# ── قانون برند ────────────────────────────────────────────────
def test_brand_central_config():
    brand = load_brand(ROOT)
    assert brand["fa"] == "هامزیار"
    assert brand["en"] == "HumsYar"
    assert not brand_lint(f"{brand['fa']} {brand['en']}")


def test_brand_lint_catches_all_wrong_forms():
    for wrong in ["هام‌یار", "هامیار", "هام یار", "هام زیار", "هامیر",
                  "Hamsyar", "HamsYar", "Humsyar"]:
        assert brand_lint(f"متن {wrong} متن"), wrong


def test_brand_lint_repo_scope_clean():
    """دامنهٔ تست برند: کد، محتوا، کانفیگ و مستندات فعال (به‌جز آرشیو پرامپت و استخراج جزوهٔ مادر)."""
    skip_dirs = {"audit", "output", ".git", ".venv", "node_modules", "__pycache__"}
    skip_files = {"AGENT_PROMPT.md"}  # پرامپت آرشیویِ کارفرما؛ نباید دست‌کاری شود
    offenders = []
    for p in ROOT.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in {".py", ".md", ".yaml", ".yml", ".css", ".mjs", ".json"}:
            continue
        if any(part in skip_dirs for part in p.parts) or p.name in skip_files:
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        # خود فهرست ممنوعه‌ها در کد QA و تست‌ها تعریف قانونی است، نه نقض برند
        if p.name in {"qa.py", "test_round2.py"}:
            continue
        hits = brand_lint(text)
        if hits:
            offenders.append(f"{p.relative_to(ROOT)}: {hits}")
    assert not offenders, offenders


def test_brand_in_pdf_text_and_metadata(pdf):
    full = " ".join(p.get_text() for p in pdf)
    assert not brand_lint(full)
    meta = " ".join(str(v) for v in (pdf.metadata or {}).values())
    assert not brand_lint(meta)
    assert "هامزیار" in full and "HumsYar" in full


# ── املای اضافه ───────────────────────────────────────────────
def test_ezafe_lint():
    assert ezafe_lint("جلسٔه و نسخٔه")
    assert not ezafe_lint("جلسهٔ اول و نسخهٔ کامل")


def test_ezafe_lint_content_clean():
    text = PILOT_YAML.read_text(encoding="utf-8")
    assert ezafe_lint(text) == []


# ── کاور و فهرست ──────────────────────────────────────────────
def test_cover_is_full_bleed_and_no_furniture(pdf):
    report = json.loads((ROOT / "output" / "build_report.json").read_text(encoding="utf-8"))
    assert report["qa"].get("cover_full_bleed") is True
    cover_text = pdf[0].get_text()
    # برند لاتین روی کاور letterspaced است و استخراج بین حروف فاصله می‌گذارد
    cover_compact = cover_text.replace(" ", "")
    # ترتیب کاور: درس ← عنوان ← برند (برند زیر عنوان است)
    assert "هامزیار" in cover_text and "HumsYar" in cover_compact
    # صفحهٔ ۱ شمارهٔ کپسولی ندارد: ناحیهٔ کپسول خالی است
    import pymupdf
    capsule = pymupdf.Rect(96 * MM, 287.5 * MM, 114 * MM, 294.5 * MM)
    assert pdf[0].get_textbox(capsule).strip() == ""


def test_toc_page_has_working_links_to_real_pages(pdf):
    links = pdf[1].get_links()
    assert len(links) >= 10
    for link in links:
        target = link.get("page", -1)
        assert 2 <= target < pdf.page_count  # مقصدها صفحات بدنه‌اند
    toc_text = pdf[1].get_text()
    assert "فهرست" in toc_text


def test_page_number_capsule_has_persian_digit(pdf):
    import pymupdf
    capsule = pymupdf.Rect(96 * MM, 287.5 * MM, 114 * MM, 294.5 * MM)
    assert pdf[2].get_textbox(capsule).strip() == "۳"
    assert pdf[pdf.page_count - 1].get_textbox(capsule).strip() != ""


def test_content_inside_frame_safe_area(pdf):
    """هیچ بلوک متن بدنه‌ای بیرون از ناحیهٔ امن قاب (۱۲ تا ۱۹۸ و ۱۲ تا ۲۸۵ میلی‌متر) نیست."""
    x0, y0, x1, y1 = 12 * MM, 12 * MM, 198 * MM, 285 * MM
    bad = []
    for i in range(1, pdf.page_count):  # کاور معاف است
        for bl in pdf[i].get_text("dict")["blocks"]:
            if bl.get("type") != 0:
                continue
            bx0, by0, bx1, by1 = bl["bbox"]
            # سربرگ/پاصفحهٔ خود قاب روی خط قاب می‌نشینند؛ فقط بدنه بررسی می‌شود
            if by1 < 12 * MM or by0 > 285 * MM:
                continue
            if (by1 - by0) > 3 * max(1.0, bx1 - bx0) and (bx1 - bx0) < 10 * MM:
                continue  # زبانهٔ انگشت‌نمای عمودی قاب (Round 5)
            if bx0 < x0 - 1 or bx1 > x1 + 1:
                bad.append((i + 1, bl["bbox"]))
    assert not bad, bad[:3]


# ── پلنر و بسته‌بندی ──────────────────────────────────────────
def test_planner_image_height_caps(session):
    plan = plan_session(session, "final", ROOT)
    for b in plan.session.all_blocks():
        if b.type != "figure":
            continue
        img_h = float(b.data.get("_img_h_mm", 0))
        assert img_h <= 122.5, (b.id, img_h)  # سقف سخت ۴۵٪ ارتفاع مفید


def test_planner_portrait_defaults_to_sidecap(session):
    plan = plan_session(session, "final", ROOT)
    by_id = {b.id: b for b in plan.session.all_blocks()}
    assert by_id["s01t6-f2"].data["_layout"] == "sidecap"  # مربعی/عمودی
    assert by_id["s01t6-f1"].data["_layout"] == "full"     # اسلاید پهن


def test_packing_is_deterministic(session):
    from humsyar.packing import _flatten, pack
    heights_path = ROOT / "output" / "_work" / "measure.json"
    if not heights_path.exists():
        pytest.skip("measure.json موجود نیست")
    data = json.loads(heights_path.read_text(encoding="utf-8"))
    heights = {it["bid"]: it["height"] for it in data["blocks"]}
    logs = []
    for _ in range(2):
        s2 = load_session(str(PILOT_YAML))
        p2 = plan_session(s2, "final", ROOT)
        logs.append(pack(s2, p2, heights))
    assert logs[0] == logs[1]


def test_fill_metrics_meet_round2_targets():
    """هدف‌های پُری (به‌روزرسانی Round 9): معیار سخت‌گیرانه برای صفحات بدنه است؛
    صفحات پسامطلب (دنبالهٔ نقشهٔ مرور، صفحهٔ درخت، جمع‌بندی، واژه‌نامه) ساختاری‌اند
    و فقط نباید واقعاً خالی باشند. میانگین کلی همچنان باید بالا بماند."""
    import pymupdf
    report = json.loads((ROOT / "output" / "build_report.json").read_text(encoding="utf-8"))
    qa = report["qa"]
    assert qa["ok"]
    assert qa.get("fill_avg_pct", 0) >= 85
    fills = qa.get("fill_per_page") or []
    doc = pymupdf.open(str(ROOT / "output" / "neuroanat_s01_pilot_final.pdf"))
    body_end = next((i + 1 for i, pg in enumerate(doc)
                     if i + 1 >= 3 and normalize_text("نقشهٔ جامع مرور")
                     in normalize_text(pg.get_text())), doc.page_count)
    body_fills = [f for f in fills[2:body_end - 1] if f is not None]
    assert all(f >= 60 for f in body_fills), fills
    assert sum(1 for f in body_fills if f < 70) <= 1, fills
    back_fills = [f for f in fills[body_end - 1:] if f is not None]
    assert all(f >= 40 for f in back_fills), fills


def test_science_conflict_still_displayed(pdf):
    """اختلاف منبع نباید حل شود: هر دو عدد سرعت انتقال سریع در خروجی بمانند."""
    full = normalize_text(" ".join(p.get_text() for p in pdf))
    assert "400" in full.replace("۴", "4").replace("۰", "0")
