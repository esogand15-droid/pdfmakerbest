"""
بسته‌بندی فضا با look-ahead — پلنر چیدمانِ مرحلهٔ دوم.

روش: ارتفاع واقعی هر بلوک در خود موتور رندر اندازه گرفته می‌شود (measure.mjs)،
بعد صفحه‌بندی در پایتون شبیه‌سازی می‌شود و فقط عملیات مجاز اعمال می‌گردد:
  ۱) کوچک‌کردن تصویر در بازهٔ خوانایی تا در باقیماندهٔ صفحه جا شود؛
  ۲) عقب‌انداختن یک تصویر به اندازهٔ یک بلوک (متن/کادر بعدی جای خالی را پر کند)
     فقط داخل همان بخش و بدون عبور از تیتر؛
  ۳) شکست صفحهٔ تمیز (پیش‌فرض).
تابع هدف: کمینهٔ فضای هدررفته بدون نقض وابستگی معنایی. هر تصمیم لاگ می‌شود.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .model import Block, Session
from .planner import Plan

PAGE_H_MM = 266.0          # ارتفاع مفید شبیه‌سازی (۲۷۰ واقعی منهای حاشیهٔ اطمینان)
MIN_FIG_H_MM = 30.0        # کوچک‌تر از این، تصویر را برای جا شدن خفه نمی‌کنیم
KEEP_TYPES = {"figure", "callout", "process", "dual_process", "tree",
              "checklist", "summary_box", "team_note"}
DEFERRABLE_AFTER = {"paragraph", "callout", "table", "process", "dual_process"}
# پاراگرافی که به شکلِ بعدی اشارهٔ صریح دارد نباید از آن جلو بزند
_FWD_REF_CUES = ("این شکل", "شکل زیر", "این قاب", "این اسلاید", "در تصویر", "این تصویر", "شکل روبه‌رو")


class _Item:
    __slots__ = ("bid", "h", "block", "topic_id", "is_head", "keep")

    def __init__(self, bid: str, h: float, block: Block | None,
                 topic_id: str, is_head: bool = False) -> None:
        self.bid, self.h, self.block = bid, h, block
        self.topic_id, self.is_head = topic_id, is_head
        if block is None or is_head:
            self.keep = True
        elif block.type == "table":
            # سیاست راند ۳: هر جدولی که در یک صفحه جا می‌شود، واحد نشکن است
            # (بلندتر از صفحه → تقسیم کنترل‌شده روی مرز ردیف‌ها در pack)
            self.keep = h <= PAGE_H_MM
        else:
            self.keep = block.type in KEEP_TYPES


CONT_CAP_MM = 9.0          # ارتفاع برچسب «ادامهٔ جدول» در قطعه‌های بعدی جدول بلند


def measure_blocks(html_path: Path, work: Path,
                   engine_dir: Path) -> tuple[dict[str, float], list[dict], dict]:
    out = work / "measure.json"
    proc = subprocess.run(
        ["node", str(engine_dir / "measure.mjs"), str(html_path), str(out)],
        cwd=engine_dir, capture_output=True, text=True, timeout=600)
    if proc.returncode != 0 or "MEASURE_OK" not in proc.stdout:
        raise RuntimeError(f"اندازه‌گیری بلوک‌ها ناموفق بود:\n{proc.stdout}\n{proc.stderr}")
    data = json.loads(out.read_text(encoding="utf-8"))
    return ({it["bid"]: it["height"] for it in data["blocks"]},
            data.get("tocLinks", []), data.get("tables", {}))


def chunk_table(meta: dict, page_h: float = PAGE_H_MM) -> list[list[int]]:
    """تقسیم جدولِ بلندتر از یک صفحه به قطعه‌هایی روی مرز ردیف‌ها.

    قطعهٔ اول عنوان کامل را دارد؛ قطعه‌های بعد سربرگ ستون‌ها + برچسب «ادامهٔ جدول».
    هیچ ردیفی نصف نمی‌شود؛ ردیفِ منفردِ بلندتر از صفحه، تنها در قطعهٔ خودش می‌نشیند.
    """
    rows = meta.get("rows", [])
    head = float(meta.get("head", 0))
    budget = page_h - float(meta.get("cap", 0)) - head - 6.0
    chunks: list[list[int]] = []
    cur: list[int] = []
    h = 0.0
    for idx, rh in enumerate(rows):
        if cur and h + rh > budget:
            chunks.append(cur)
            cur, h = [], 0.0
            budget = page_h - CONT_CAP_MM - head - 6.0
        cur.append(idx)
        h += float(rh)
    if cur:
        chunks.append(cur)
    return chunks


def _chunk_height(meta: dict, chunk: list[int], first: bool) -> float:
    rows = meta.get("rows", [])
    cap = float(meta.get("cap", 0)) if first else CONT_CAP_MM
    return cap + float(meta.get("head", 0)) + sum(float(rows[i]) for i in chunk) + 6.0


def _flatten(session: Session, heights: dict[str, float]) -> list[_Item]:
    items: list[_Item] = []
    for t in session.topics:
        items.append(_Item(f"topichead:{t.id}", heights.get(f"topichead:{t.id}", 40.0),
                           None, t.id, is_head=True))
        for b in t.blocks:
            # عضو دوم جفت‌تصویر داخل ارتفاع جفت حساب شده است
            h = 0.0 if b.data.get("_pair_with") else heights.get(b.id, 12.0)
            items.append(_Item(b.id, h, b, t.id, is_head=(b.type == "section")))
    for b in session.closing:
        items.append(_Item(b.id, heights.get(b.id, 12.0), b, "closing",
                           is_head=(b.type == "section")))
    return items


def pack(session: Session, plan: Plan, heights: dict[str, float],
         tables: dict | None = None) -> list[str]:
    """شبیه‌سازی و اعمال اصلاح‌ها؛ لاگ تصمیم‌ها برگردانده و به plan هم افزوده می‌شود."""
    logs: list[str] = []
    items = _flatten(session, heights)
    tables = tables or {}

    # پیش‌پردازش جدول‌های بلندتر از یک صفحه: تقسیم کنترل‌شده روی مرز ردیف‌ها
    for it in items:
        b = it.block
        if b is None or b.type != "table" or it.h <= PAGE_H_MM:
            continue
        meta = tables.get(b.id)
        if not meta or not meta.get("rows"):
            continue
        chunks = chunk_table(meta)
        if len(chunks) > 1:
            b.data["_chunks"] = chunks
            b.data["_break_before"] = True  # جدول بلند از ابتدای صفحهٔ تازه شروع می‌شود
            tall = [meta["rows"][c[0]] for c in chunks
                    if len(c) == 1 and meta["rows"][c[0]] > PAGE_H_MM - 30]
            if tall:
                plan.log(f"[بسته‌بندی] هشدار: جدول «{b.id}» ردیفی بلندتر از فضای مفید "
                         "صفحه دارد و نیازمند بازطراحی دستی همان ردیف است")
    # ترتیب جدید بلوک‌ها در هر مبحث (برای اعمال defer)
    order: dict[str, list[Block]] = {t.id: list(t.blocks) for t in session.topics}
    order["closing"] = list(session.closing)

    def note(msg: str) -> None:
        logs.append(msg)
        plan.log(f"[بسته‌بندی] {msg}")

    used = 0.0
    page = 1
    i = 0
    deferred: dict[str, int] = {}
    while i < len(items):
        it = items[i]
        # جدول قطعه‌بندی‌شده: از صفحهٔ تازه شروع و هر قطعه یک صفحه می‌گیرد
        if it.block is not None and it.block.data.get("_chunks"):
            meta = tables.get(it.bid, {})
            chunks = it.block.data["_chunks"]
            if used > 0:
                page += 1
            page += len(chunks) - 1
            used = _chunk_height(meta, chunks[-1], first=False)
            note(f"{it.bid}: جدول بلندتر از یک صفحه؛ تقسیم کنترل‌شده در {len(chunks)} قطعه "
                 "روی مرز ردیف‌ها با تکرار سربرگ و برچسب «ادامهٔ جدول»")
            i += 1
            continue
        # تیتر باید با دست‌کم بخشی از بلوک بعدی هم‌صفحه بماند
        need = it.h
        if it.is_head and it.block is not None and i + 1 < len(items):
            need += min(items[i + 1].h, 14.0)
        residual = PAGE_H_MM - used
        if need <= residual or used == 0:
            used += it.h
            if used >= PAGE_H_MM:  # بلوکِ قابل‌شکست صفحه را پر کرد
                used = max(0.0, used - PAGE_H_MM)
                page += 1
            i += 1
            continue

        # ——— بلوک جا نمی‌شود؛ عملیات مجاز را امتحان کن ———
        b = it.block
        if (b is not None and b.type == "figure" and b.data.get("_layout") == "full"
                and residual >= MIN_FIG_H_MM + 12):
            # ۱) کوچک‌کردن تصویر برای جا شدن در همین صفحه
            img_h = float(b.data.get("_img_h_mm", it.h))
            cap_h = max(0.0, it.h - img_h)
            target_img_h = residual - cap_h - 3.0
            min_w = float(b.data.get("min_width_mm") or 0)
            w_now = 182.0 * float(b.data.get("_width_pct", 100)) / 100.0
            if target_img_h >= MIN_FIG_H_MM and img_h > 0:
                w_new = w_now * (target_img_h / img_h)
                if w_new >= max(min_w, 55.0):
                    b.data["_width_pct"] = max(30, round(w_new / 182.0 * 100))
                    b.data["_img_h_mm"] = round(target_img_h, 1)
                    note(f"{b.id}: تصویر برای جا شدن در صفحهٔ جاری تا عرض "
                         f"{b.data['_width_pct']}٪ کوچک شد (خوانایی حفظ شده)")
                    used += residual  # صفحه عملاً پر شد
                    used, page = 0.0, page + 1
                    i += 1
                    continue
        if (b is not None and b.type == "figure" and b.data.get("_layout") == "sidecap"
                and residual >= MIN_FIG_H_MM + 12):
            # ۱-ب) کوچک‌کردن تصویرِ کپشن‌کناری برای جا شدن در همین صفحه
            img_h = float(b.data.get("_img_h_mm", it.h))
            if img_h > residual - 3 and img_h > 0:
                from .planner import SIDECAP_COL_MM
                w_now = SIDECAP_COL_MM * float(b.data.get("_width_pct", 100)) / 100.0
                w_new = w_now * ((residual - 3.0) / img_h)
                min_w = float(b.data.get("min_width_mm") or 0)
                if w_new >= max(min_w, 50.0):
                    b.data["_width_pct"] = max(35, round(w_new / SIDECAP_COL_MM * 100))
                    b.data["_img_h_mm"] = round(residual - 3.0, 1)
                    note(f"{b.id}: تصویر کپشن‌کناری برای جا شدن در صفحهٔ جاری کوچک شد")
                    used, page = 0.0, page + 1
                    i += 1
                    continue
        if (b is not None and deferred.get(b.id, 0) < 2
                and (b.type == "figure" or (b.type == "table" and it.keep))):
            # ۲) کشیدن بلوک‌های مستقل از پنجرهٔ سه بلوک بعدی به جای خالی همین صفحه (حداکثر دو بار)
            pulled = False
            for j in range(i + 1, min(i + 4, len(items))):
                nxt = items[j]
                if nxt.topic_id != it.topic_id or nxt.is_head:
                    break
                nb = nxt.block
                if nb is None or nb.type not in DEFERRABLE_AFTER or nxt.h > residual:
                    continue
                txt = str(nb.data.get("text", ""))
                if nb.type == "paragraph" and any(c in txt for c in _FWD_REF_CUES):
                    continue
                # متنی که خود جدول را بحث می‌کند نباید جلوتر از جدول بیاید
                if b.type == "table" and nb.type == "paragraph" and "جدول" in txt:
                    continue
                lst = order[it.topic_id]
                ia, ib = lst.index(b), lst.index(nb)
                lst.insert(ia, lst.pop(ib))
                items.insert(i, items.pop(j))
                deferred[b.id] = deferred.get(b.id, 0) + 1
                note(f"{b.id}: بلوک «{nxt.bid}» از پنجرهٔ بعدی جلو کشیده شد تا جای خالی "
                     f"انتهای صفحه پر شود (همان بخش، بدون ارجاع پیش‌رو به شکل)")
                pulled = True
                break
            if pulled:
                continue
        # ۳) شکست تمیز صفحه — برای جدول یکپارچه، شکست به رندر هم تحمیل می‌شود
        # تا Chromium دقیقاً همان‌جا بشکند که شبیه‌سازی تصمیم گرفته است.
        if b is not None and b.type == "table" and it.keep and used > 0:
            b.data["_break_before"] = True
            note(f"{b.id}: جدول در باقیماندهٔ صفحه جا نشد و کامل به صفحهٔ بعد منتقل شد "
                 "(Keep Together؛ تقسیم نشد)")
        used = 0.0
        page += 1

    for t in session.topics:
        t.blocks = order[t.id]
    session.closing = order["closing"]
    note(f"شبیه‌سازی بسته‌بندی: ≈{page} صفحهٔ بدنه")
    return logs


# ————————————————————————————————————————————————————————————————
# گذر بازخورد از PDF واقعی: اصلاح رانش شبیه‌سازی ↔ Chromium
# ————————————————————————————————————————————————————————————————
def feedback_adjust(session: Session, body_pdf: Path, plan: Plan,
                    heights: dict[str, float] | None = None) -> list[str]:
    """بعد از رندر واقعی بدنه، صفحات کم‌پُر را با PDF واقعی پیدا می‌کند.

    اگر انتهای صفحه‌ای خالی مانده و شکلِ ابتدای صفحهٔ بعد فقط اندکی بزرگ‌تر از
    آن فضای خالی است، شکل در محدودهٔ خوانایی کوچک می‌شود تا بالا بیاید.
    ترتیب بلوک‌ها هرگز عوض نمی‌شود؛ فقط اندازهٔ تصویر در بازهٔ مجاز پلنر.
    """
    import pymupdf

    logs: list[str] = []
    doc = pymupdf.open(str(body_pdf))
    mm = 72 / 25.4
    zone_bottom = 283.0  # پایین ناحیهٔ محتوا در رندر بدنه (حاشیهٔ پایین ۱۴mm)

    # شکل‌های قابل‌تنظیم به ترتیب رندر + تصویرهای واقعی PDF به همان ترتیب
    figs: list[Block] = []
    for t in session.topics:
        figs += [b for b in t.blocks if b.type == "figure"]
    figs += [b for b in session.closing if b.type == "figure"]
    images: list[tuple[int, float, float]] = []  # (page, y0_mm, h_mm)
    bottoms: list[float] = []
    for pno, page in enumerate(doc):
        bottom = 0.0
        for bl in page.get_text("dict")["blocks"]:
            bottom = max(bottom, bl["bbox"][3] / mm)
        for img in page.get_images(full=True):
            try:
                rects = page.get_image_rects(img[0])
            except Exception:
                rects = []
            for r in rects:
                images.append((pno, r.y0 / mm, (r.y1 - r.y0) / mm))
                bottom = max(bottom, r.y1 / mm)
        bottoms.append(bottom)
    if len(images) != len(figs):
        return logs  # تطبیق قطعی ممکن نیست؛ دست نمی‌زنیم
    fig_at = {id(b): images[i] for i, b in enumerate(figs)}

    adjusted = 0
    for pno in range(len(doc) - 1):
        if adjusted >= 3:
            break
        blank = zone_bottom - bottoms[pno]
        if blank < 45.0:
            continue
        # اولین شکلِ صفحهٔ بعد
        nxt = None
        for b in figs:
            pg, y0, img_h = fig_at[id(b)]
            if pg == pno + 1:
                nxt = (b, y0, img_h)
                break
        if nxt is None:
            continue
        b, y0, img_h = nxt
        layout = b.data.get("_layout", "full")
        if layout not in ("full", "sidecap") or b.data.get("_pair_with") or b.data.get("_paired_with_next"):
            continue
        # ارتفاع واقعی کپشن+قاب از اندازه‌گیری همان بیلد (نه حدس ثابت)
        if heights and b.id in heights:
            cap_allow = max(6.0, heights[b.id] - float(b.data.get("_img_h_mm", img_h)))
        else:
            cap_allow = 22.0 if layout == "full" else 5.0
        block_h = img_h + cap_allow
        if block_h <= blank - 6 or block_h > blank + 34:
            continue  # یا خودش جا می‌شده (علت دیگری دارد) یا بیش از حد بزرگ است
        target_img = blank - cap_allow - 8.0
        if target_img < MIN_FIG_H_MM or img_h <= 0:
            continue
        from .planner import SIDECAP_COL_MM, TEXT_WIDTH_MM
        col = TEXT_WIDTH_MM if layout == "full" else SIDECAP_COL_MM
        w_now = col * float(b.data.get("_width_pct", 100)) / 100.0
        w_new = w_now * (target_img / img_h)
        min_w = max(float(b.data.get("min_width_mm") or 0), 55.0 if layout == "full" else 50.0)
        if w_new < min_w:
            continue
        b.data["_width_pct"] = max(30, round(w_new / col * 100))
        b.data["_img_h_mm"] = round(target_img, 1)
        msg = (f"{b.id}: [بازخورد PDF واقعی] صفحهٔ قبل {blank:.0f}mm فضای خالی داشت؛ "
               f"تصویر تا عرض {b.data['_width_pct']}٪ کوچک شد تا در همان صفحه جا شود")
        logs.append(msg)
        plan.log(f"[بسته‌بندی] {msg}")
        adjusted += 1
    doc.close()
    return logs
