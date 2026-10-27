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
_MM = 72 / 25.4

# قانون برند (راند ۲، بند ۰): فقط «هامزیار» و «HumsYar» درست‌اند.
WRONG_BRAND_FORMS = ["هام‌یار", "هامیار", "هام یار", "هام زیار", "هامیر",
                     "Hamsyar", "HamsYar", "Humsyar"]


def brand_lint(text: str) -> list[str]:
    """شکل‌های غلط برندِ یافت‌شده در یک متن."""
    return [f for f in WRONG_BRAND_FORMS if f in text]


def ezafe_lint(text: str) -> list[str]:
    """همزهٔ اضافهٔ نادرست: «جلسٔه/نسخٔه/جزؤه» و نظایر آن.

    الگوها: حرفی غیر از «ه» + همزه (U+0654) + «ه»؛ و ترکیب «ؤه».
    روی متن منبع اجرا می‌شود (استخراج PDF ترتیب همزه را وارونه برمی‌گرداند).
    """
    import re as _re
    hits = []
    for m in _re.finditer(r"[^\sه]ٔه|ؤه", text):
        hits.append(text[max(0, m.start() - 6):m.end() + 6])
    return hits


def _pdf_text_pages(pdf_path: Path) -> list[str]:
    import pymupdf
    doc = pymupdf.open(str(pdf_path))
    return [p.get_text() for p in doc]


_BIDI_STRIP = None  # در نخستین فراخوانی ساخته می‌شود


def bidi_lint(session: Session) -> list[str]:
    """هشدار برای رشتهٔ لاتینِ برهنه در متن‌های رندرشوندهٔ درون‌خطی.

    متن علمی دست نمی‌خورد؛ فقط گزارش می‌شود که عبارت لاتین بدون ایزوله‌سازی
    ([en:...] یا [[term:...]]) آمده و در رندر ممکن است جهتش در جملهٔ فارسی
    به‌هم بریزد. برچسب‌های شکل و کپشن انگلیسی مستثنا هستند (رندرشان ایزوله است).
    """
    import re as _re
    pat_strip = _re.compile(r"\[\[term:[^\]]+\]\]|\[\[num:[^\]]+\]\]|\[en:[^\]]+\]")
    pat_lat = _re.compile(r"[A-Za-z][A-Za-z0-9 ,.\-/()]{2,}")

    def fields(b) -> list[str]:
        d = b.data
        if b.type == "paragraph":
            return [str(d.get("text", ""))]
        if b.type == "callout":
            return [str(d.get("text", "")), str(d.get("title", ""))]
        if b.type == "table":
            return ([str(d.get("title", ""))] + [str(h) for h in d.get("headers", [])]
                    + [str(c) for r in d.get("rows", []) for c in r])
        if b.type == "figure":
            return [str(d.get("explain_fa", "")), str(d.get("title_fa", "")),
                    str(d.get("side_text", ""))]
        if b.type == "section":
            return [str(d.get("title", ""))]
        if b.type == "summary_box":
            return [str(d.get("text", "")), str(d.get("title", ""))]
        if b.type == "checklist":
            return [str(x) for x in d.get("items", [])]
        if b.type in ("process", "dual_process"):
            out = [str(d.get("title", "")), str(d.get("rail", "")), str(d.get("note", ""))]
            for key in ("steps", "forward", "backward"):
                v = d.get(key)
                if isinstance(v, dict):
                    out.append(str(v.get("title", "")))
                    v = v.get("steps", [])
                for st in v or []:
                    if isinstance(st, dict):
                        out += [str(st.get("head", "")), str(st.get("text", ""))]
            return out
        return []

    hits: list[str] = []
    for b in session.all_blocks():
        for f in fields(b):
            cleaned = pat_strip.sub("", f).replace("**", "")
            for m in pat_lat.finditer(cleaned):
                hits.append(f"{b.id}: «{m.group(0).strip()[:40]}»")
    for t in session.topics:
        for f in [t.why, *t.objectives, *t.prereq_required, *t.prereq_suggested]:
            cleaned = pat_strip.sub("", str(f)).replace("**", "")
            for m in pat_lat.finditer(cleaned):
                hits.append(f"{t.id}: «{m.group(0).strip()[:40]}»")
    return hits


def run_qa(session: Session, pdf_path: Path,
           control_facts: list[str] | None = None) -> dict[str, Any]:
    import pymupdf
    doc = pymupdf.open(str(pdf_path))
    errors: list[str] = []
    warnings: list[str] = []
    from .revision import coverage_report as _cov
    _coverage = _cov(session)
    if _coverage["unassigned"]:
        errors.append(
            f"ماتریس پوشش: {len(_coverage['unassigned'])} گزاره بدون گرهٔ نقشه مانده است: "
            + "، ".join(_coverage["unassigned"][:5]))
    if _coverage["unresolved"]:
        warnings.append(
            f"ماتریس پوشش: {len(_coverage['unresolved'])} مورد جزئیات درون‌تصویر "
            f"ماشینی قابل استخراج نیست و به خود شکل ارجاع داده شده است")
    bidi_hits = bidi_lint(session)
    if bidi_hits:
        warnings.append(
            f"رشتهٔ لاتین بدون ایزوله‌سازی bidi ({len(bidi_hits)} مورد): "
            + "؛ ".join(bidi_hits[:5]) + ("؛ …" if len(bidi_hits) > 5 else ""))

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
    # نمای دوم: اسپن‌ها با فاصله — جلوی چسبیدن عدد به شمارهٔ صفحهٔ چیپِ منبع را می‌گیرد
    # شمارش اسپن‌به‌اسپن و جمع (نرمال‌سازی فاصله‌ها را حذف می‌کند، پس اتصال با فاصله کافی نیست)
    _span_nums: _Counter = _Counter()
    for _pg in doc:
        for _bl in _pg.get_text("dict")["blocks"]:
            if _bl.get("type") != 0:
                continue
            for _ln in _bl["lines"]:
                for _sp in _ln["spans"]:
                    _span_nums += numbers(_sp["text"])
    for _n, _c in _span_nums.items():
        if _c > pdf_nums[_n]:
            pdf_nums[_n] = _c
    lost = {n: c - pdf_nums[n] for n, c in model_nums.items() if pdf_nums[n] < c}
    if lost:
        errors.append(f"اعدادی از مدل در PDF کم است (چک‌سام اعداد): {lost}")

    # —— تصاویر: شمارش در برابر مدل
    model_figs = [b for b in session.all_blocks() if b.type == "figure"]
    # تصاویر محتوایی شمرده می‌شوند؛ دارایی برند (لوگوی کاور و نشان تک‌رنگ سربرگ)
    # اسباب صفحه‌اند، نه شکل علمی: صفحهٔ کاور و تصاویر بسیار کوچک کنار گذاشته می‌شوند.
    pdf_img_count = 0
    for i, p in enumerate(doc):
        if i == 0:
            continue
        for img in p.get_images(full=True):
            keep = False
            for r in p.get_image_rects(img[0]):
                if (r.x1 - r.x0) / _MM >= 8 and (r.y1 - r.y0) / _MM >= 8:
                    keep = True
            pdf_img_count += 1 if keep else 0
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
    unembedded = []
    seen_xref: set[int] = set()
    for p in doc:
        for f in p.get_fonts(full=True):
            if f[0] in seen_xref or not f[3]:
                continue
            seen_xref.add(f[0])
            try:
                content = doc.extract_font(f[0])[3]
            except Exception:
                content = None
            if not content:
                unembedded.append(f[3])
    if unembedded:
        warnings.append(f"فونت(های) تعبیه‌نشده در PDF: {unembedded}")
    if min_size < MIN_FONT_PT:
        errors.append(f"فونت ریزتر از آستانه در PDF هست: {min_size:.1f}pt < {MIN_FONT_PT}pt")

    # —— صفحات سفید و تراکم
    chars_per_page = [len(t.strip()) for t in page_texts]
    for i, (c, p) in enumerate(zip(chars_per_page, doc), 1):
        if i > 1 and c < BLANK_PAGE_CHARS and not p.get_images():
            errors.append(f"صفحهٔ {i} تقریباً خالی است ({c} نویسه)")
    # صفحهٔ ۱ کاور است و ذاتاً متن کمی دارد؛ در آمار تراکم شمرده نمی‌شود
    content_pages = [c for i, c in enumerate(chars_per_page) if i >= 1 and c >= BLANK_PAGE_CHARS]
    avg_chars = round(sum(content_pages) / len(content_pages)) if content_pages else 0
    sparse = [i + 1 for i, c in enumerate(chars_per_page)
              if i >= 1 and BLANK_PAGE_CHARS <= c < avg_chars * 0.35]
    if sparse:
        warnings.append(f"صفحات کم‌تراکم نسبت به میانگین (بررسی فضای سفید): {sparse}")

    # —— قانون برند روی متن نهایی PDF + lint همزهٔ اضافه روی متن منبع
    bad_brand = brand_lint(" ".join(page_texts))
    if bad_brand:
        errors.append(f"شکل غلط برند در PDF نهایی: {bad_brand}")
    ezafe_hits: list[str] = []
    for b in session.all_blocks():
        for frag in b.text_fragments():
            ezafe_hits += [f"{b.id}: …{h}…" for h in ezafe_lint(frag)]
    if ezafe_hits:
        errors.append(f"همزهٔ اضافهٔ نادرست در متن منبع: {ezafe_hits[:6]}")

    # —— کاور تمام‌صفحه: نمونه‌برداری پیکسل گوشه‌ها و وسط لبه‌ها نباید سفید خالی باشد
    cover_ok = None
    if doc.page_count >= 1:
        pix = doc[0].get_pixmap(dpi=36)
        pts = [(2, 2), (pix.width - 3, 2), (2, pix.height - 3), (pix.width - 3, pix.height - 3),
               (pix.width // 2, 2), (pix.width // 2, pix.height - 3),
               (2, pix.height // 2), (pix.width - 3, pix.height // 2)]
        whites = [pt for pt in pts if all(c > 240 for c in pix.pixel(*pt)[:3])]
        cover_ok = not whites
        if whites:
            errors.append(f"کاور تمام‌صفحه نیست؛ نقاط سفید در لبه‌ها: {whites}")

    # —— پُری صفحات محتوایی + ناحیهٔ امن قاب
    # نوار مبلمان قاب (بالای ۱۱٫۵mm و پایین ۲۸۶mm) از محاسبهٔ محتوا کنار گذاشته می‌شود.
    fill_per_page: list = []
    bbox_violations: list[str] = []
    for i, page in enumerate(doc):
        if i == 0:
            fill_per_page.append(None)  # کاور تمام‌صفحه است؛ ناحیهٔ امن قاب ندارد
            continue
        ys: list[float] = []
        for bl in page.get_text("dict")["blocks"]:
            bb = bl.get("bbox")
            if not bb:
                continue
            if bb[3] < 11.5 * _MM or bb[1] > 286 * _MM:
                continue  # متن مبلمان قاب
            if (bb[3] - bb[1]) > 3 * max(1.0, bb[2] - bb[0]) and (bb[2] - bb[0]) < 10 * _MM:
                continue  # زبانهٔ انگشت‌نمای عمودی قاب (مبلمان لبه‌ای)
            if bl.get("type") == 0 and not any(
                    sp["text"].strip() for ln in bl["lines"] for sp in ln["spans"]):
                continue
            ys.append(bb[3])
            if bb[0] < 12 * _MM - 2 or bb[2] > 198 * _MM + 2:
                bbox_violations.append(f"صفحهٔ {i + 1}: محتوا بیرون از ناحیهٔ امن قاب (x={bb[0]:.0f}..{bb[2]:.0f})")
        for img in page.get_images(full=True):
            for r in page.get_image_rects(img[0]):
                ys.append(r.y1)
                if r.x0 < 12 * _MM - 2 or r.x1 > 198 * _MM + 2:
                    bbox_violations.append(f"صفحهٔ {i + 1}: تصویر بیرون از ناحیهٔ امن قاب")
        if i == 1 or not ys:
            fill_per_page.append(None if i == 1 else 0)
        else:
            fill_per_page.append(round(min(1.0, max(0.0, (max(ys) - 14 * _MM) / (270 * _MM))) * 100))
    if bbox_violations:
        errors.append("؛ ".join(dict.fromkeys(bbox_violations)))
    content_fills = [f for i, f in enumerate(fill_per_page)
                     if f is not None and i not in (0, 1, len(fill_per_page) - 1)]
    fill_avg = round(sum(content_fills) / len(content_fills)) if content_fills else 0
    sparse_pages = [i + 1 for i, f in enumerate(fill_per_page)
                    if f is not None and f < 70 and i not in (0, 1, len(fill_per_page) - 1)]
    if fill_avg and fill_avg < 88:
        warnings.append(f"میانگین پُری صفحات محتوایی {fill_avg}٪ است (هدف ≥۸۸٪)")
    if sparse_pages:
        warnings.append(f"صفحات با پُری زیر ۷۰٪ (نیازمند توضیح/اصلاح): {sparse_pages}")

    # —— Preflight: یکپارچگی جدول‌ها — عنوان و آخرین ردیف هر جدولِ تقسیم‌نشده
    # باید در یک صفحه باشند؛ جدول قطعه‌بندی‌شده باید برچسب «ادامهٔ جدول» داشته باشد.
    page_norms = [normalize_text(t) for t in page_texts]

    def _pages_with(slice_text: str) -> list[int]:
        """صفحاتی (جز کاور/فهرست) که برشِ نرمال‌شدهٔ متن دقیقاً در آن‌ها هست.

        عنوان جدول و سلول‌ها در رندر اسپن واحدند و استخراج معمولاً ترتیب درون‌اسپن
        را حفظ می‌کند؛ تطابق دقیقِ برش بلند، مثبت کاذبِ روش سه‌گرمی را ندارد.
        """
        probe = normalize_text(slice_text)[:30]
        if len(probe) < 10:
            return []
        return [i for i, t in enumerate(page_norms) if i >= 2 and probe in t]

    tables_checked = 0
    tables_split_badly: list[str] = []
    for b in session.all_blocks():
        if b.type != "table":
            continue
        rows = b.data.get("rows", [])
        if not rows:
            continue
        chunks = b.data.get("_chunks") or []
        if len(chunks) > 1:
            cont_hits = sum(t.count(normalize_text("ادامهٔ جدول")) for t in page_norms)
            if cont_hits < len(chunks) - 1:
                tables_split_badly.append(
                    f"{b.id}: برچسب «ادامهٔ جدول» برای {len(chunks)} قطعه پیدا نشد")
            tables_checked += 1
            continue
        cap_pages = _pages_with(str(b.data.get("title", "")))
        last_cells = [str(c) for c in rows[-1] if len(normalize_text(str(c))) >= 12]
        if not cap_pages or not last_cells:
            continue  # شاهد قابل اتکا نیست؛ چک رد می‌شود (نه خطا)
        last_pages = _pages_with(max(last_cells, key=len))
        # عبارت‌های جدول ممکن است در عنوان بخش/پاراگراف هم تکرار شوند؛ اثبات
        # یکپارچگی = یک صفحه که عنوان + ردیف نخست + ردیف آخر را با هم داشته باشد.
        first_cells = [str(c) for c in rows[0] if len(normalize_text(str(c))) >= 12]
        common = set(cap_pages) & set(last_pages)
        if first_cells:
            _fp = _pages_with(max(first_cells, key=len))
            if _fp:  # نبودِ شاهد، مخالفِ شاهد نیست
                common &= set(_fp)
        tables_checked += 1
        if last_pages and not common:
            tables_split_badly.append(
                f"{b.id}: عنوان در صفحات {[p + 1 for p in cap_pages]} ولی ردیف آخر در "
                f"{[p + 1 for p in last_pages]} (هیچ صفحه‌ای هر سه را با هم ندارد)")
    if tables_split_badly:
        errors.append("جدول(های) شکستهٔ غیرمجاز: " + "؛ ".join(tables_split_badly))

    # —— وضعیت‌های بازبینی برای گزارش انسانی
    review_items: list[str] = []
    for b in session.all_blocks():
        if b.status in ("needs_review", "unresolved_conflict"):
            review_items.append(f"{b.id} [{b.status}] ({b.type})")
    needs_review_topics = [t.id for t in session.topics if t.status == "needs_review"]

    return {
        "ok": not errors,
        "coverage": _coverage,
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
        "cover_full_bleed": cover_ok,
        "fill_per_page": fill_per_page,
        "fill_avg_pct": fill_avg,
        "tables_checked": tables_checked,
        "tables_split_badly": tables_split_badly,
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
