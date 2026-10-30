"""
بازرسی بصری خروجی واقعی (Visual Inspection) — راند ۴.

چرخهٔ Render → Inspect → Diagnose → Repair → Render Again روی PDF واقعی بدنه:
ایرادها با اندازه‌گیری مختصات و متنِ خود PDF پیدا می‌شوند (نه امتیاز زیبایی مدل):
صفحهٔ کم‌پُر، شکاف داخلی بزرگ، تیتر یتیم در انتهای صفحه، جدایی شکل و زیرنویس،
تراکم غیرعادی، و یکنواختی امضای صفحات متوالی. هر یافته علت محتمل دارد و اصلاحش
هدفمند و محدود است؛ حلقه حداکثر دو دور می‌چرخد و باقیمانده‌ها به گزارش QA می‌روند.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .model import Block, Session, normalize_text
from .planner import MAX_H_PORTRAIT, MAX_H_SIDECAP, MAX_H_WIDE, Plan, SIDECAP_COL_MM, TEXT_WIDTH_MM

MM = 72 / 25.4
ZONE_TOP = 14.0
ZONE_BOTTOM = 284.0
ZONE_H = ZONE_BOTTOM - ZONE_TOP

_KIND_LABELS = ["نکتهٔ کلیدی", "نکتهٔ بالینی", "استثنا / هشدار", "از ساختار تا عملکرد",
                "اختلاف منابع", "نکتهٔ امتحانی", "تعریف اصطلاح", "مثال آموزشی", "جمع‌بندی سریع"]


def _figs_in_order(session: Session) -> list[Block]:
    figs: list[Block] = []
    for t in session.topics:
        figs += [b for b in t.blocks if b.type == "figure"]
    figs += [b for b in session.closing if b.type == "figure"]
    return figs


def _page_geometry(doc) -> list[dict[str, Any]]:
    pages = []
    for pno, page in enumerate(doc):
        boxes: list[tuple[float, float]] = []
        headings: list[dict[str, Any]] = []
        for bl in page.get_text("dict")["blocks"]:
            if bl.get("type") != 0:
                continue
            boxes.append((bl["bbox"][1] / MM, bl["bbox"][3] / MM))
            for line in bl.get("lines", []):
                for sp in line.get("spans", []):
                    if sp.get("size", 0) >= 11.5 and sp.get("text", "").strip():
                        headings.append({"y1": sp["bbox"][3] / MM, "text": sp["text"]})
        images = []
        for img in page.get_images(full=True):
            for r in page.get_image_rects(img[0]):
                images.append(r)
                boxes.append((r.y0 / MM, r.y1 / MM))
        has_table = False
        for dr in page.get_drawings():
            fill = dr.get("fill")
            r = dr["rect"]
            if fill and abs(fill[0] - 0.043) < 0.03 and abs(fill[1] - 0.188) < 0.04 \
                    and abs(fill[2] - 0.314) < 0.05 and (r.x1 - r.x0) / MM > 60 \
                    and 2.5 < (r.y1 - r.y0) / MM < 12:
                has_table = True
                break
        bottom = max((b[1] for b in boxes), default=ZONE_TOP)
        pages.append({
            "page": pno + 1, "boxes": sorted(boxes), "headings": headings,
            "images": images, "has_table": has_table,
            "bottom": bottom, "fill": round((bottom - ZONE_TOP) / ZONE_H, 3),
            "chars": len(page.get_text()), "text_norm": normalize_text(page.get_text()),
        })
    return pages


def _match_block(session: Session, text: str, types: tuple[str, ...]) -> Block | None:
    def tri(t: str) -> set[str]:
        t = normalize_text(t)
        return {t[i:i + 3] for i in range(len(t) - 2)} if len(t) >= 3 else set()

    want = tri(text)
    best, best_score = None, 0.0
    for b in session.all_blocks():
        if b.type not in types:
            continue
        cand = tri(str(b.data.get("title", "") or b.data.get("title_fa", "")))
        if not cand:
            continue
        score = len(want & cand) / max(1, len(cand))
        if score > best_score:
            best, best_score = b, score
    return best if best_score >= 0.5 else None


def inspect_body(body_pdf: Path, session: Session, plan: Plan) -> list[dict[str, Any]]:
    """یافته‌های بازرسی روی PDF واقعی بدنه (صفحهٔ ۱ بدنه = فهرست، معاف است)."""
    import pymupdf

    doc = pymupdf.open(str(body_pdf))
    pages = _page_geometry(doc)
    findings: list[dict[str, Any]] = []

    def add(page: int, typ: str, severity: str, detail: str,
            cause: str, block_id: str | None = None) -> None:
        findings.append({"page": page, "type": typ, "severity": severity,
                         "detail": detail, "cause": cause, "block": block_id})

    content = pages[1:]  # صفحهٔ اول بدنه فهرست است
    chars = sorted(p["chars"] for p in content if p["chars"] > 0)
    med_chars = chars[len(chars) // 2] if chars else 0

    for idx, p in enumerate(content):
        is_last = idx == len(content) - 1
        if not is_last and p["fill"] < 0.72:
            add(p["page"], "low_fill", "warn",
                f"پُری صفحه {p['fill']:.0%} است", "بلوک نشکن بعدی در باقیمانده جا نشده")
        # شکاف داخلی بزرگ: با «خط آب» سنجیده می‌شود تا چیدمان دوستونه (کپشن‌کناری)
        # مثبت کاذب نسازد — شکاف واقعی جایی است که هیچ عنصری آن بازه را نپوشانده باشد.
        waterline = ZONE_TOP
        for y0, y1 in p["boxes"]:
            gap = y0 - waterline
            if gap > 38 and waterline > 45 and y0 < 260:
                add(p["page"], "internal_gap", "warn",
                    f"شکاف خالی {gap:.0f}mm در میانهٔ صفحه", "شکست صفحهٔ یک بلوک نشکن")
                break
            waterline = max(waterline, y1)
        for hd in p["headings"]:
            if hd["y1"] > ZONE_BOTTOM - 16:
                blk = _match_block(session, hd["text"], ("section",))
                add(p["page"], "orphan_heading", "warn",
                    f"تیتر در {hd['y1']:.0f}mm انتهای صفحه تنها مانده",
                    "محاسبهٔ فضای باقی‌مانده/قاعدهٔ همراهی تیتر",
                    blk.id if blk else None)
        if med_chars and p["chars"] > 1.4 * med_chars:
            add(p["page"], "overfull", "info",
                f"تراکم نویسه {p['chars']} در برابر میانهٔ {med_chars}",
                "تراکم بالای محتوای همان بخش")
        kinds = sum(p["text_norm"].count(normalize_text(k)) for k in _KIND_LABELS)
        if kinds >= 4:
            add(p["page"], "callout_overload", "info",
                f"{kinds} کادر معنایی در یک صفحه", "تراکم کادرها در بخش")

    # جدایی شکل و زیرنویس + نگاشت شکل‌ها به صفحات واقعی
    figs = _figs_in_order(session)
    all_imgs: list[tuple[int, Any]] = []
    for p in pages:
        for r in p["images"]:
            all_imgs.append((p["page"], r))
    if len(all_imgs) == len(figs):
        for b, (pg, _r) in zip(figs, all_imgs):
            probe = normalize_text(str(b.data.get("title_fa", "")))[:26]
            if len(probe) >= 8 and probe not in pages[pg - 1]["text_norm"]:
                add(pg, "caption_split", "warn",
                    "عنوان شکل در صفحهٔ تصویر پیدا نشد",
                    "شکستن قاب شکل بین دو صفحه", b.id)

    # یکنواختی امضای واقعی صفحات متوالی
    def sig(p: dict) -> str:
        d = "low" if p["fill"] < 0.55 else ("mid" if p["fill"] < 0.8 else "high")
        return f"I{bool(p['images'])}T{p['has_table']}D{d}"

    run: list[dict] = []
    for p in content + [None]:
        if p is not None and (not run or sig(run[-1]) == sig(p)):
            run.append(p)
            continue
        if len(run) >= 4:
            add(run[len(run) // 2]["page"], "monotony", "info",
                f"{len(run)} صفحهٔ متوالی با امضای بصری یکسان ({sig(run[0])})",
                "تکرار قالب در بخش‌های هم‌ساختار")
        run = [p] if p is not None else []
    doc.close()
    return findings


def repair_body(findings: list[dict[str, Any]], session: Session, plan: Plan,
                body_pdf: Path) -> list[str]:
    """اصلاح هدفمند یافته‌های قابل‌اصلاح؛ فهرست اقدام‌های انجام‌شده برمی‌گردد."""
    actions: list[str] = []
    by_id = {b.id: b for b in session.all_blocks()}
    for f in findings:
        if f["type"] == "orphan_heading" and f.get("block"):
            b = by_id.get(f["block"])
            if b is not None and not b.data.get("_break_before"):
                b.data["_break_before"] = True
                actions.append(f"{b.id}: [بازرسی بصری] تیتر یتیم در صفحهٔ {f['page']}؛ "
                               "بخش از صفحهٔ تازه شروع می‌شود")
        elif f["type"] == "caption_split" and f.get("block"):
            b = by_id.get(f["block"])
            if b is not None and not b.data.get("_break_before"):
                b.data["_break_before"] = True
                actions.append(f"{b.id}: [بازرسی بصری] زیرنویس از تصویر جدا افتاده بود؛ "
                               "شکل کامل به صفحهٔ بعد منتقل می‌شود")
    actions += _grow_to_fill(findings, session, plan, body_pdf)
    for a in actions:
        plan.log(a)
    return actions


def _grow_to_fill(findings: list[dict[str, Any]], session: Session,
                  plan: Plan, body_pdf: Path) -> list[str]:
    """بزرگ‌تر کردن آخرین شکلِ صفحهٔ کم‌پُر در سقف‌های سخت خوانایی/اندازه.

    مکمل کوچک‌سازی بازخوردی است و فقط وقتی انجام می‌شود که دست‌کم ۱۲mm از
    فضای خالی واقعاً مصرف شود؛ نسبت ابعاد و سقف‌ها هرگز نقض نمی‌شوند.
    """
    import pymupdf

    low_pages = {f["page"] for f in findings if f["type"] in ("low_fill", "internal_gap")}
    if not low_pages:
        return []
    doc = pymupdf.open(str(body_pdf))
    pages = _page_geometry(doc)
    figs = _figs_in_order(session)
    all_imgs: list[tuple[int, Any]] = []
    for p in pages:
        for r in p["images"]:
            all_imgs.append((p["page"], r))
    actions: list[str] = []
    if len(all_imgs) == len(figs):
        fig_at = {id(b): all_imgs[i] for i, b in enumerate(figs)}
        for p in pages:
            if p["page"] not in low_pages:
                continue
            blank = ZONE_BOTTOM - p["bottom"]
            if blank < 38:
                continue
            on_page = [b for b in figs if fig_at[id(b)][0] == p["page"]]
            if not on_page:
                continue
            b = on_page[-1]
            layout = b.data.get("_layout", "full")
            if layout == "side" or b.data.get("_pair_with") or b.data.get("_pair_first"):
                continue
            _pg, r = fig_at[id(b)]
            img_h = (r.y1 - r.y0) / MM
            img_w = (r.x1 - r.x0) / MM
            if img_h <= 0:
                continue
            aspect = img_w / img_h
            cap_h = MAX_H_SIDECAP if layout == "sidecap" else (
                MAX_H_WIDE if aspect >= 1.3 else MAX_H_PORTRAIT)
            pct_now = float(b.data.get("_width_pct", 100))
            col_w = SIDECAP_COL_MM if layout == "sidecap" else TEXT_WIDTH_MM
            pct_max = 100.0 if (layout == "sidecap" or b.data.get("min_width_mm")) else 75.0
            target_h = min(cap_h, img_h + blank * 0.7, img_h * 1.45)
            pct_new = min(pct_max, pct_now * (target_h / img_h))
            gain = img_h * (pct_new / max(pct_now, 1) - 1)
            if pct_new <= pct_now + 2 or gain < 12:
                continue
            b.data["_width_pct"] = round(pct_new)
            b.data["_img_h_mm"] = round(img_h * pct_new / pct_now, 1)
            actions.append(
                f"{b.id}: [بازرسی بصری] صفحهٔ {p['page']} بدنه {blank:.0f}mm خالی داشت؛ "
                f"تصویر در سقف مجاز تا عرض {round(pct_new)}٪ بزرگ‌تر شد (+{gain:.0f}mm)")
    doc.close()
    return actions
