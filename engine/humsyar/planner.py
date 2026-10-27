"""
موتور تصمیم چیدمان (Layout Planner) — نسخهٔ ۱: قواعد صریح و قابل‌ممیزی.

وظایف:
۱) شماره‌گذاری خودکار و پایدار: بخش‌ها، جدول‌ها، شکل‌ها و مسیرها در هر مبحث
   (مثلاً «شکل ۴-۲»)؛ تا فهرست و ارجاعات هیچ‌وقت دستی و ناهماهنگ نشوند.
۲) تصمیم چیدمان تصویر: کنار متن (side) یا تمام‌عرض (full) بر اساس نسبت تصویر
   و وجود متن لنگر — با ثبت دلیل هر تصمیم در گزارش ساخت.
۳) پایش وضوح تصویر در اندازهٔ نمایش واقعی (DPI مؤثر) و هشدار، نه دستکاری.
۴) پالایش نسخه: در نسخهٔ دانشجو (final) بلوک‌های کاری (یادداشت تیم) حذف می‌شوند؛
   در نسخهٔ workbook می‌مانند. هر دو از یک مدل داده.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .analyze import analyze_session, archetype_of_block
from .model import Block, Session, Topic
from .scoring import load_layout_config, score_figure_candidate, score_process_variant

PLAIN_REPLACEMENTS = None  # پر می‌شود پایین‌تر (از وابستگی چرخه‌ای جلوگیری)


def plain_title(raw: str) -> str:
    """عنوان خامِ دارای نشانه‌گذاری را به متن سادهٔ نمایشی (برای فهرست/نشانک) تبدیل می‌کند."""
    import re
    t = re.sub(r"\[\[term:([^\]|]+)\|[^\]]+\]\]", r"\1", raw)
    t = re.sub(r"\[en:([^\]]+)\]", r"\1", t)
    return t.replace("**", "")

FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")

# هندسهٔ صفحهٔ A4 با حاشیه‌های موتور (میلی‌متر) — راند ۲: قاب در ۶mm، متن از ۱۴mm
TEXT_WIDTH_MM = 182.0
TEXT_HEIGHT_MM = 270.0
SIDE_WIDTH_MM = 86.0
SIDECAP_COL_MM = 94.6       # ستون تصویر در چیدمان «کپشن کناری»
MIN_FIG_DPI = 110           # زیر این آستانه در گزارش بازبینی پرچم می‌خورد
# سقف ارتفاع تصویر از ارتفاع مفید صفحه (راند ۲، بند ۳)
MAX_H_WIDE = 0.32 * TEXT_HEIGHT_MM        # تصویر عریض: ≈۸۶mm
MAX_H_PORTRAIT = 0.42 * TEXT_HEIGHT_MM    # عمودی/مربعی تمام‌عرض: ≈۱۱۳mm
MAX_H_HARD = 0.45 * TEXT_HEIGHT_MM        # سقف مطلق حتی با کف خوانایی برچسب
MAX_H_SIDECAP = 118.0
DEFAULT_WIDTH_CAP_MM = 0.75 * TEXT_WIDTH_MM  # ≈۱۳۶mm مگر تصویر برچسب‌دار ریز


def fa_num(v: int | str) -> str:
    return str(v).translate(FA_DIGITS)


@dataclass
class Plan:
    session: Session
    edition: str = "final"
    decisions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # نگاشت شناسهٔ بلوک ← برچسب نمایشی (مثلاً «شکل ۴-۱»)
    labels: dict[str, str] = field(default_factory=dict)
    # سرفصل‌ها برای فهرست مطالب: (سطح، متن، شناسهٔ لنگر)
    headings: list[tuple[int, str, str]] = field(default_factory=list)
    # راند ۴: تحلیل معنایی بخش‌ها + تصمیم‌های ساختاریافتهٔ چیدمان (حافظهٔ طراحی)
    analysis: list = field(default_factory=list)
    layout_decisions: list[dict] = field(default_factory=list)
    page_map: dict[str, int] = field(default_factory=dict)   # از شبیه‌سازی بسته‌بندی پر می‌شود
    page_signatures: list = field(default_factory=list)      # امضای بصری هر صفحه (حافظهٔ چیدمان)
    layout_cfg: dict = field(default_factory=dict)

    def log(self, msg: str) -> None:
        self.decisions.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


def _image_size(path: Path) -> tuple[int, int] | None:
    try:
        import pymupdf
        pix = pymupdf.Pixmap(str(path))
        return pix.width, pix.height
    except Exception:
        return None


def plan_session(session: Session, edition: str,
                 assets_root: Path, layout_cfg: dict | None = None) -> Plan:
    plan = Plan(session=session, edition=edition)
    plan.layout_cfg = layout_cfg if layout_cfg is not None else load_layout_config(assets_root)
    # تحلیل معنایی پیش از هر تصمیم چیدمان (Content-First)
    plan.analysis = analyze_session(session)
    cfg = plan.layout_cfg

    def process_blocks(blocks: list[Block], topic_no: int | None, plan: Plan) -> list[Block]:
        counters = {"section": 0, "table": 0, "figure": 0, "process": 0}
        ctx: dict = {"prev_fig_layout": None, "prev_variant": None}
        kept: list[Block] = []
        for b in blocks:
            if b.type == "team_note" and edition == "final":
                plan.log(f"{b.id}: کادر یادداشت تیم در نسخهٔ دانشجو حذف شد (قاعدهٔ نسخه)")
                continue
            prefix = fa_num(topic_no) if topic_no else "ج"
            if b.type == "section":
                counters["section"] += 1
                lbl = f"{prefix}-{fa_num(counters['section'])}"
                plan.labels[b.id] = lbl
                plan.headings.append((2, plain_title(str(b.data['title'])), b.id))
                # ریتم تنفسی برای بخش توضیحیِ آرام (ترجیح طراحی، نه تزئین)
                if (archetype_of_block(plan.analysis, b.id) == "explanatory"
                        and cfg["preferences"].get("prefer_calm_text_pages", True)):
                    b.data["_rhythm"] = "airy"
                    plan.log(f"{b.id}: بخش توضیحی بلند؛ ریتم صفحه «آرام/تنفسی» انتخاب شد")
            elif b.type == "table":
                counters["table"] += 1
                plan.labels[b.id] = f"جدول {prefix}-{fa_num(counters['table'])}"
                _plan_table_columns(b, plan)
            elif b.type in ("process", "dual_process"):
                counters["process"] += 1
                plan.labels[b.id] = f"مسیر {prefix}-{fa_num(counters['process'])}"
                if b.type == "process":
                    _plan_process_variant(b, plan, ctx)
            elif b.type == "figure":
                counters["figure"] += 1
                plan.labels[b.id] = f"شکل {prefix}-{fa_num(counters['figure'])}"
                _plan_figure(b, plan, assets_root, ctx)
            kept.append(b)
        return kept

    for topic in session.topics:
        plan.headings.append((1, f"مبحث {fa_num(topic.number)}: {topic.title}", topic.id))
        topic.blocks = process_blocks(topic.blocks, topic.number, plan)
        _plan_pairs(topic.blocks, plan, topic.id)
        if edition == "workbook":
            # کادر خالی یادداشتِ تیم در پایان هر مبحث — مبلمان نسخهٔ کاری، نه محتوای علمی
            topic.blocks.append(Block(
                id=f"{topic.id}-teamnote", type="team_note", status="editorial",
                data={"title": f"مبحث {fa_num(topic.number)} — این کادر برای نوشتن شماست: چرا این مبحث اهمیت دارد؟"}))
            plan.log(f"{topic.id}: در نسخهٔ workbook کادر یادداشت تیم افزوده شد")
    session.closing = process_blocks(session.closing, None, plan)
    return plan


def _size_for(layout: str, w: int, h: int, min_w: float) -> dict:
    """اندازهٔ چاپ یک گونهٔ چیدمان (همان سقف‌ها و کف‌های سخت راند ۲/۳)."""
    aspect_wh = w / h
    h_over_w = h / w
    honest_mm = w / (135 / 25.4)  # بزرگ‌نمایی صادقانه بر اساس وضوح بومی
    if layout == "side":
        img_h = SIDE_WIDTH_MM * h_over_w
        width_pct = 100 if img_h <= 102 else max(45, round(102 / img_h * 100))
        disp_mm = SIDE_WIDTH_MM * width_pct / 100
    elif layout == "sidecap":
        img_h = SIDECAP_COL_MM * h_over_w
        width_pct = 100 if img_h <= MAX_H_SIDECAP else max(42, round(MAX_H_SIDECAP / img_h * 100))
        disp_mm = SIDECAP_COL_MM * width_pct / 100
    else:  # full
        max_h = MAX_H_WIDE if aspect_wh >= 1.3 else MAX_H_PORTRAIT
        width_mm = min(TEXT_WIDTH_MM, max_h * aspect_wh, DEFAULT_WIDTH_CAP_MM, honest_mm)
        if min_w:
            width_mm = max(width_mm, min(min_w, MAX_H_HARD * aspect_wh, TEXT_WIDTH_MM))
        width_mm = max(width_mm, 52.0)
        width_pct = round(width_mm / TEXT_WIDTH_MM * 100)
        disp_mm = width_mm
    return {"layout": layout, "width_pct": int(width_pct), "disp_mm": round(disp_mm, 1),
            "img_h_mm": round(disp_mm * h_over_w, 1),
            "eff_dpi": round(w / (disp_mm / 25.4))}


def _plan_figure(b: Block, plan: Plan, assets_root: Path, ctx: dict) -> None:
    """تصمیم چیدمان تصویر به‌روش کاندید + امتیاز (راند ۴).

    فیلترهای سخت اول اعمال می‌شوند (درخواست صریح داده، نیاز side به متن لنگر،
    کف خوانایی برچسب، سقف‌های ارتفاع در _size_for)؛ بعد کاندیدهای باقی‌مانده با
    تابع امتیاز قابل‌تنظیم سنجیده می‌شوند و همهٔ امتیازها در حافظهٔ طراحی ثبت می‌گردند.
    """
    fpath = assets_root / str(b.data["file"])
    size = _image_size(fpath) if fpath.exists() else None
    want = str(b.data.get("layout", "auto"))
    has_side_text = bool(b.data.get("side_text"))
    min_w = float(b.data.get("min_width_mm") or 0)
    if size is None:
        plan.warn(f"{b.id}: فایل تصویر پیدا نشد یا خوانا نیست: {b.data['file']}")
        b.data["_layout"] = "full"
        return
    w, h = size
    aspect_wh = w / h
    h_over_w = h / w
    portraitish = h_over_w >= 0.8

    # ——— فیلتر سخت: مجموعهٔ کاندیدهای مجاز ———
    feasible: list[str] = []
    forced = None
    if want == "side" and has_side_text:
        forced = "side"
    elif want == "full":
        forced = "full"
    elif want == "sidecap" and h_over_w >= 0.7 and min_w <= SIDECAP_COL_MM:
        forced = "sidecap"
    if want == "side" and not has_side_text:
        plan.warn(f"{b.id}: چیدمان side خواسته شده ولی side_text نیست؛ کاندیدها از نو ساخته شدند")
    if forced:
        feasible = [forced]
    else:
        feasible = ["full"]
        if h_over_w >= 0.7 and min_w <= SIDECAP_COL_MM:
            feasible.append("sidecap")
        if has_side_text and min_w <= SIDE_WIDTH_MM:
            feasible.append("side")

    archetype = archetype_of_block(plan.analysis, b.id)
    candidates = []
    for lay in feasible:
        cand = _size_for(lay, w, h, min_w)
        cand["score"] = score_figure_candidate(
            cand, archetype=archetype, aspect_wh=aspect_wh, h_over_w=h_over_w,
            prev_layout=ctx.get("prev_fig_layout"), cfg=plan.layout_cfg)
        cand["forced"] = bool(forced)
        candidates.append(cand)
    candidates.sort(key=lambda c: c["score"]["total"], reverse=True)
    best = candidates[0]
    layout = best["layout"]
    b.data["_layout"] = layout
    b.data["_width_pct"] = best["width_pct"]
    b.data["_img_h_mm"] = best["img_h_mm"]
    b.data["_eff_dpi"] = best["eff_dpi"]
    b.data["_candidates"] = candidates
    ctx["prev_fig_layout"] = layout

    alt = (f"؛ رقیب بعدی: {candidates[1]['layout']} با {candidates[1]['score']['total']:.2f}"
           if len(candidates) > 1 else "")
    why = ("درخواست صریح در داده" if forced else
           f"کهن‌الگوی بخش «{archetype}» و بالاترین امتیاز {best['score']['total']:.2f}{alt}")
    plan.layout_decisions.append({
        "block": b.id, "kind": "figure", "archetype": archetype, "chosen": layout,
        "candidates": [{"layout": c["layout"], "width_pct": c["width_pct"],
                        "img_h_mm": c["img_h_mm"], "score": c["score"]} for c in candidates],
    })
    plan.log(f"{b.id}: چیدمان تصویر «{layout}» — {why}؛ عرض چاپ ≈{best['disp_mm']:.0f}mm، "
             f"ارتفاع تصویر ≈{best['img_h_mm']:.0f}mm، وضوح مؤثر ≈{best['eff_dpi']} DPI")
    if best["eff_dpi"] < MIN_FIG_DPI:
        plan.warn(
            f"{b.id}: وضوح مؤثر تصویر پایین است (≈{best['eff_dpi']} DPI در عرض {best['disp_mm']:.0f}mm)؛ "
            "نیازمند بازبینی/جایگزینی انسانی — موتور تصویر را دستکاری نمی‌کند")
    for flag in b.data.get("quality_flags", []):
        plan.warn(f"{b.id}: پرچم کیفی تصویر از استخراج: {flag}")


def _plan_process_variant(b: Block, plan: Plan, ctx: dict) -> None:
    """گونهٔ نمایش فرایند: گام عمودی یا نوار افقی (فقط وقتی گام‌ها کوتاه و کم‌اند)."""
    steps = b.data.get("steps", [])

    def step_len(st) -> int:
        if isinstance(st, dict):
            return len(str(st.get("head", ""))) + len(str(st.get("text", "")))
        return len(str(st))

    strip_ok = 2 <= len(steps) <= 4 and all(step_len(st) <= 72 for st in steps)
    cands = ["vertical"] + (["strip"] if strip_ok else [])
    scored = []
    for v in cands:
        sc = score_process_variant(v, steps=len(steps),
                                   prev_variant=ctx.get("prev_variant"), cfg=plan.layout_cfg)
        scored.append({"variant": v, "score": sc})
    scored.sort(key=lambda c: c["score"]["total"], reverse=True)
    best = scored[0]
    b.data["_variant"] = best["variant"]
    ctx["prev_variant"] = best["variant"]
    plan.layout_decisions.append({
        "block": b.id, "kind": "process", "chosen": best["variant"], "candidates": scored})
    if best["variant"] == "strip":
        plan.log(f"{b.id}: فرایند {len(steps)}گامهٔ کوتاه؛ نمایش «نوار افقی» "
                 f"(امتیاز {best['score']['total']:.2f}) به‌جای گام عمودی")


def _plan_table_columns(b: Block, plan: Plan) -> None:
    """راهبرد عرض ستون‌ها از آمار طول سلول‌ها (فقط وقتی نامتوازنی واقعی هست)."""
    import math
    if b.data.get("col_widths"):
        return
    headers = [str(h) for h in b.data.get("headers", [])]
    rows = b.data.get("rows", [])
    if len(headers) < 3 or not rows:
        return
    avgs = []
    for ci in range(len(headers)):
        lens = [len(headers[ci])] + [len(str(r[ci])) for r in rows if ci < len(r)]
        avgs.append(sum(lens) / max(1, len(lens)))
    if max(avgs) / max(1.0, min(avgs)) < 1.8:
        return  # ستون‌ها هم‌وزن‌اند؛ عرض خودکار مرورگر بهتر است
    raw = [math.sqrt(a) for a in avgs]
    tot = sum(raw)
    widths = [min(45, max(10, round(x / tot * 100))) for x in raw]
    widths[widths.index(max(widths))] += 100 - sum(widths)
    b.data["col_widths"] = widths
    plan.layout_decisions.append({
        "block": b.id, "kind": "table_columns", "chosen": "proportional",
        "col_widths": widths, "avg_cell_chars": [round(a, 1) for a in avgs]})
    plan.log(f"{b.id}: عرض ستون‌ها متناسب با طول محتوای سلول‌ها تنظیم شد: {widths}")


def _plan_pairs(topic_blocks: list[Block], plan: Plan, topic_id: str) -> None:
    """جفت‌تصویر: دو شکلِ پشت‌سرهم و هم‌مبحث در یک ردیف، فقط وقتی هر دو در نیم‌عرض خوانا می‌مانند."""
    i = 0
    while i + 1 < len(topic_blocks):
        a, b = topic_blocks[i], topic_blocks[i + 1]
        if (a.type == b.type == "figure"
                and a.data.get("_layout") == b.data.get("_layout") == "full"
                and not a.data.get("min_width_mm") and not b.data.get("min_width_mm")
                and float(a.data.get("_img_h_mm", 0)) >= 26
                and float(b.data.get("_img_h_mm", 0)) >= 26):
            a.data["_pair_first"] = b.id
            b.data["_pair_with"] = a.id
            plan.log(f"{a.id}+{b.id}: جفت‌تصویر در یک ردیف (هر دو در نیم‌عرض خوانا می‌مانند)")
            i += 2
            continue
        i += 1
