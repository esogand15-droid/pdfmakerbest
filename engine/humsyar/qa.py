"""
کنترل کیفیت (QA) خروجی PDF — هیچ PDFای صرفاً به‌خاطر موفقیت فرمان تولید معتبر نیست.

بررسی‌ها:
- پوشش محتوا: متن هر بلوک متنی مدل باید در PDF نهایی پیدا شود (نرمال‌شده).
- حقایق کنترلی جلسه (اعداد/اصطلاحات حساس) بدون تغییر مانده باشند.
- هر تصویر مدل دقیقاً یک‌بار در PDF آمده باشد.
- فونت‌ها تعبیه (subset) شده باشند و متن قابل انتخاب باشد.
- صفحهٔ سفید ناخواسته نباشد؛ حداقل اندازهٔ فونت از آستانه پایین‌تر نباشد.
- آمار تراکم: نویسه در هر صفحه و صفحات پرت (خیلی خالی/خیلی متراکم).
خروجی: دیکشنری گزارش + متن Markdown برای review_report.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .model import Session, normalize_text

MIN_FONT_PT = 7.0
BLANK_PAGE_CHARS = 30


def _pdf_text_pages(pdf_path: Path) -> list[str]:
    import pymupdf
    doc = pymupdf.open(str(pdf_path))
    return [p.get_text() for p in doc]


def run_qa(session: Session, pdf_path: Path,
           control_facts: list[str] | None = None) -> dict[str, Any]:
    import pymupdf
    doc = pymupdf.open(str(pdf_path))
    errors: list[str] = []
    warnings: list[str] = []

    page_texts = [p.get_text() for p in doc]
    full_norm = normalize_text(" ".join(page_texts))

    # —— پوشش متن در سطح بلوک: ترتیب و مرزبندی استخراج متن از PDF (ستون‌ها، اسپن‌های
    # بولد، چسبیدن علائم) محلّی و ناپایدار است؛ پوشش سه‌تایی نویسه‌ایِ تجمیع‌شدهٔ هر بلوک
    # در برابر این نویز مقاوم و به حذف واقعیِ یک بلوک/پاراگراف حساس است.
    def trigrams(t: str) -> set[str]:
        return {t[i:i + 3] for i in range(len(t) - 2)} if len(t) >= 3 else set()

    pdf_tri = trigrams(full_norm)
    missing: list[str] = []
    checked_fragments = 0
    for b in session.all_blocks():
        frags = [normalize_text(f) for f in b.text_fragments()
                 if len(normalize_text(f)) >= 8 and not f.endswith((".png", ".jpg", ".jpeg"))]
        if not frags:
            continue
        checked_fragments += len(frags)
        bt = trigrams("".join(frags))
        recall = len(bt & pdf_tri) / len(bt) if bt else 1.0
        if recall < 0.80:
            missing.append(f"{b.id} ({b.type}): پوشش {recall:.0%}")
    if missing:
        errors.append(f"{len(missing)} بلوک در PDF پوشش متنی کافی ندارند: " + "؛ ".join(missing[:8]))

    # —— حقایق کنترلی: ترتیب عدد و واژه در استخراج RTL جابه‌جا می‌شود؛ پس حضور
    # همهٔ توکن‌های هر حقیقت (بی‌حساس به ترتیب) لازم است.
    for fact in control_facts or []:
        toks = [normalize_text(t) for t in fact.split() if normalize_text(t)]
        absent = [t for t in toks if t not in full_norm]
        if absent:
            errors.append(f"حقیقت کنترلی ناقص است: «{fact}» (غایب: {absent})")

    # —— چک‌سام اعداد: چندمجموعهٔ همهٔ اعداد مدل باید در PDF حاضر باشد
    import re as _re2
    from collections import Counter as _Counter

    def numbers(t: str) -> _Counter:
        return _Counter(_re2.findall(r"\d+(?:\.\d+)?", normalize_text(t)))

    model_nums: _Counter = _Counter()
    for b in session.all_blocks():
        for frag in b.text_fragments():
            model_nums += numbers(frag)
    pdf_nums = numbers(full_norm)
    lost = {n: c - pdf_nums[n] for n, c in model_nums.items() if pdf_nums[n] < c}
    if lost:
        errors.append(f"اعدادی از مدل در PDF کم است (چک‌سام اعداد): {lost}")

    # —— تصاویر: شمارش در برابر مدل
    model_figs = [b for b in session.all_blocks() if b.type == "figure"]
    pdf_img_count = sum(len(p.get_images(full=True)) for p in doc)
    if pdf_img_count != len(model_figs):
        errors.append(f"تعداد تصاویر PDF ({pdf_img_count}) با مدل ({len(model_figs)}) نمی‌خواند")

    # —— فونت‌های تعبیه‌شده + حداقل اندازه
    fonts: set[str] = set()
    min_size = 999.0
    for p in doc:
        for f in p.get_fonts():
            fonts.add(f[3])
        for bl in p.get_text("dict")["blocks"]:
            if bl.get("type") != 0:
                continue
            for ln in bl["lines"]:
                for sp in ln["spans"]:
                    if sp["text"].strip():
                        min_size = min(min_size, sp["size"])
    unembedded = [f for f in fonts if "+" not in f and f]
    if unembedded:
        warnings.append(f"فونت(های) بدون تعبیهٔ subset: {unembedded}")
    if min_size < MIN_FONT_PT:
        errors.append(f"فونت ریزتر از آستانه در PDF هست: {min_size:.1f}pt < {MIN_FONT_PT}pt")

    # —— صفحات سفید و تراکم
    chars_per_page = [len(t.strip()) for t in page_texts]
    for i, (c, p) in enumerate(zip(chars_per_page, doc), 1):
        if c < BLANK_PAGE_CHARS and not p.get_images():
            errors.append(f"صفحهٔ {i} تقریباً خالی است ({c} نویسه)")
    content_pages = [c for c in chars_per_page if c >= BLANK_PAGE_CHARS]
    avg_chars = round(sum(content_pages) / len(content_pages)) if content_pages else 0
    sparse = [i + 1 for i, c in enumerate(chars_per_page)
              if BLANK_PAGE_CHARS <= c < avg_chars * 0.35]
    if sparse:
        warnings.append(f"صفحات کم‌تراکم نسبت به میانگین (بررسی فضای سفید): {sparse}")

    # —— وضعیت‌های بازبینی برای گزارش انسانی
    review_items: list[str] = []
    for b in session.all_blocks():
        if b.status in ("needs_review", "unresolved_conflict"):
            review_items.append(f"{b.id} [{b.status}] ({b.type})")
    needs_review_topics = [t.id for t in session.topics if t.status == "needs_review"]

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "pages": doc.page_count,
        "checked_fragments": checked_fragments,
        "figures_model": len(model_figs),
        "figures_pdf": pdf_img_count,
        "fonts": sorted(fonts),
        "min_font_pt": round(min_size, 1) if min_size != 999 else None,
        "chars_per_page": chars_per_page,
        "avg_chars_per_page": avg_chars,
        "review_items": review_items,
        "needs_review_topics": needs_review_topics,
    }


def render_pages_png(pdf_path: Path, out_dir: Path, dpi: int = 100) -> list[Path]:
    """رندر همهٔ صفحات برای بازبینی چشمی (تست تصویری مکمل تست متنی است)."""
    import pymupdf
    doc = pymupdf.open(str(pdf_path))
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, page in enumerate(doc, 1):
        p = out_dir / f"page_{i:02d}.png"
        page.get_pixmap(dpi=dpi).save(str(p))
        paths.append(p)
    return paths
