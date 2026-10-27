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

from .model import Block, Session, Topic

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
                 assets_root: Path) -> Plan:
    plan = Plan(session=session, edition=edition)

    def process_blocks(blocks: list[Block], topic_no: int | None, plan: Plan) -> list[Block]:
        counters = {"section": 0, "table": 0, "figure": 0, "process": 0}
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
            elif b.type == "table":
                counters["table"] += 1
                plan.labels[b.id] = f"جدول {prefix}-{fa_num(counters['table'])}"
            elif b.type in ("process", "dual_process"):
                counters["process"] += 1
                plan.labels[b.id] = f"مسیر {prefix}-{fa_num(counters['process'])}"
            elif b.type == "figure":
                counters["figure"] += 1
                plan.labels[b.id] = f"شکل {prefix}-{fa_num(counters['figure'])}"
                _plan_figure(b, plan, assets_root)
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


def _plan_figure(b: Block, plan: Plan, assets_root: Path) -> None:
    """تصمیم چیدمان + اندازهٔ چاپ تصویر با سقف ارتفاع و کف خوانایی؛ دلیل ثبت می‌شود.

    قواعد راند ۲: ارتفاع تصویر عریض ≤ ≈۳۲٪ و عمودی/مربعی ≤ ≈۴۲٪ ارتفاع مفید صفحه؛
    عرض تک‌ستونه معمولاً ≤ ۷۵٪ مگر `min_width_mm` (کف خوانایی برچسب‌های داخل تصویر)
    در داده آمده باشد. تصویر اصلی هرگز دستکاری نمی‌شود؛ فقط اندازهٔ چاپ تعیین می‌شود.
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
    aspect_wh = w / h            # عرض/ارتفاع
    h_over_w = h / w
    portraitish = h_over_w >= 0.8  # عمودی یا مربعی

    if want == "side" and has_side_text:
        layout, why = "side", "درخواست صریح در داده + متن لنگر موجود است"
    elif want == "full":
        layout, why = "full", "درخواست صریح در داده (سقف‌های اندازه همچنان اعمال می‌شوند)"
    elif portraitish and has_side_text:
        layout, why = "side", "تصویر عمودی/مربعی با متن لنگر؛ دو ستونه کنار متن"
    elif portraitish:
        layout, why = "sidecap", "تصویر عمودی/مربعی؛ کپشن در ستون کناری (پیش‌فرض راند ۲)"
    else:
        layout, why = "full", "تصویر عریض؛ تک‌ستونه با سقف ارتفاع"
    if want == "side" and not has_side_text:
        plan.warn(f"{b.id}: چیدمان side خواسته شده ولی side_text نیست؛ به sidecap/full برگشت")
        layout, why = ("sidecap", "نبود متن لنگر") if portraitish else ("full", "نبود متن لنگر")
    if layout == "sidecap" and min_w > SIDECAP_COL_MM:
        layout, why = "full", f"کف خوانایی برچسب ({min_w:.0f}mm) از ستون کناری بزرگ‌تر است"
    b.data["_layout"] = layout

    honest_mm = w / (135 / 25.4)  # بزرگ‌نمایی صادقانه بر اساس وضوح بومی
    if layout == "side":
        disp_mm = SIDE_WIDTH_MM
        img_h = disp_mm * h_over_w
        # تصویر خیلی بلند در ستون کناری کل صفحه را می‌بلعد؛ عرضش را کم می‌کنیم
        b.data["_width_pct"] = 100 if img_h <= 102 else max(45, round(102 / img_h * 100))
        disp_mm = SIDE_WIDTH_MM * b.data["_width_pct"] / 100
    elif layout == "sidecap":
        disp_mm = SIDECAP_COL_MM
        img_h = disp_mm * h_over_w
        b.data["_width_pct"] = 100 if img_h <= MAX_H_SIDECAP else max(42, round(MAX_H_SIDECAP / img_h * 100))
        disp_mm = SIDECAP_COL_MM * b.data["_width_pct"] / 100
    else:  # full
        max_h = MAX_H_WIDE if aspect_wh >= 1.3 else MAX_H_PORTRAIT
        width_mm = min(TEXT_WIDTH_MM, max_h * aspect_wh, DEFAULT_WIDTH_CAP_MM, honest_mm)
        if min_w:
            width_mm = max(width_mm, min(min_w, MAX_H_HARD * aspect_wh, TEXT_WIDTH_MM))
        width_mm = max(width_mm, 52.0)
        b.data["_width_pct"] = round(width_mm / TEXT_WIDTH_MM * 100)
        disp_mm = width_mm
    b.data["_img_h_mm"] = round(disp_mm * h_over_w, 1)
    eff_dpi = w / (disp_mm / 25.4)
    b.data["_eff_dpi"] = round(eff_dpi)
    plan.log(f"{b.id}: چیدمان تصویر «{layout}» — {why}؛ عرض چاپ ≈{disp_mm:.0f}mm، "
             f"ارتفاع تصویر ≈{b.data['_img_h_mm']:.0f}mm، وضوح مؤثر ≈{round(eff_dpi)} DPI")
    if eff_dpi < MIN_FIG_DPI:
        plan.warn(
            f"{b.id}: وضوح مؤثر تصویر پایین است (≈{round(eff_dpi)} DPI در عرض {disp_mm:.0f}mm)؛ "
            "نیازمند بازبینی/جایگزینی انسانی — موتور تصویر را دستکاری نمی‌کند")
    for flag in b.data.get("quality_flags", []):
        plan.warn(f"{b.id}: پرچم کیفی تصویر از استخراج: {flag}")


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
