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

# عرض ناحیهٔ متن A4 با حاشیه‌های پیش‌فرض موتور (میلی‌متر)
TEXT_WIDTH_MM = 178.0
SIDE_WIDTH_MM = 84.0
MIN_FIG_DPI = 110  # زیر این آستانه در گزارش بازبینی پرچم می‌خورد


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
        if edition == "workbook":
            # کادر خالی یادداشتِ تیم در پایان هر مبحث — مبلمان نسخهٔ کاری، نه محتوای علمی
            topic.blocks.append(Block(
                id=f"{topic.id}-teamnote", type="team_note", status="editorial",
                data={"title": f"مبحث {fa_num(topic.number)} — این کادر برای نوشتن شماست: چرا این مبحث اهمیت دارد؟"}))
            plan.log(f"{topic.id}: در نسخهٔ workbook کادر یادداشت تیم افزوده شد")
    session.closing = process_blocks(session.closing, None, plan)
    return plan


def _plan_figure(b: Block, plan: Plan, assets_root: Path) -> None:
    """تصمیم side/full و پایش DPI؛ دلیل تصمیم ثبت می‌شود."""
    fpath = assets_root / str(b.data["file"])
    size = _image_size(fpath) if fpath.exists() else None
    want = str(b.data.get("layout", "auto"))
    has_side_text = bool(b.data.get("side_text"))
    if size is None:
        plan.warn(f"{b.id}: فایل تصویر پیدا نشد یا خوانا نیست: {b.data['file']}")
        b.data["_layout"] = "full"
        return
    w, h = size
    portrait = h > w * 1.05
    if want == "side" and has_side_text:
        layout, why = "side", "درخواست صریح در داده + متن لنگر موجود است"
    elif want == "full":
        layout, why = "full", "درخواست صریح در داده"
    elif portrait and has_side_text:
        layout, why = "side", "تصویر عمودی است و متن لنگر دارد؛ کنار متن خواناتر و کم‌حجم‌تر است"
    elif portrait:
        layout, why = "sidecap", "تصویر عمودی بدون متن لنگر؛ کپشن در ستون کناری تا ارتفاع قاب هدر نرود"
    else:
        layout, why = "full", "تصویر افقی/بدون متن لنگر؛ تمام‌عرض در سطر مستقل"
    if want == "side" and not has_side_text:
        plan.warn(f"{b.id}: چیدمان side خواسته شده ولی side_text نیست؛ به full برگشت")
        layout, why = "full", "نبود متن لنگر"
    b.data["_layout"] = layout
    # قاعدهٔ عرض نمایش (تصویر اصلی دستکاری نمی‌شود؛ فقط اندازهٔ چاپ تعیین می‌شود):
    #  الف) سقف ارتفاع: نسبت ارتفاع/عرض نمایشی حداکثر ۱٫۱۵ تا قاب+کپشن در یک صفحه جا شود.
    #  ب) صداقت وضوح: تصویر کم‌پیکسل را تا تمام‌عرض بزرگ نمی‌کنیم (هدف ≈۱۳۵ DPI، کف ۵۵٪
    #      برای خوانایی برچسب‌های داخل خود تصویر).
    ratio = h / w
    pct_tall = 100 if ratio <= 1.15 else max(42, round(115 / ratio))
    if layout in ("side", "sidecap"):
        b.data["_width_pct"] = 100
    else:
        honest_mm = w / (135 / 25.4)
        pct_res = max(55, min(100, round(honest_mm / TEXT_WIDTH_MM * 100)))
        b.data["_width_pct"] = min(pct_tall, pct_res)
    if layout == "side":
        disp_mm = SIDE_WIDTH_MM
    elif layout == "sidecap":
        disp_mm = TEXT_WIDTH_MM * 0.52
    else:
        disp_mm = TEXT_WIDTH_MM * b.data["_width_pct"] / 100
    eff_dpi = w / (disp_mm / 25.4)
    b.data["_eff_dpi"] = round(eff_dpi)
    plan.log(f"{b.id}: چیدمان تصویر «{layout}» — {why} (وضوح مؤثر ≈ {round(eff_dpi)} DPI)")
    if eff_dpi < MIN_FIG_DPI:
        plan.warn(
            f"{b.id}: وضوح مؤثر تصویر پایین است (≈{round(eff_dpi)} DPI در عرض {disp_mm:.0f}mm)؛ "
            "نیازمند بازبینی/جایگزینی انسانی — موتور تصویر را دستکاری نمی‌کند")
    for flag in b.data.get("quality_flags", []):
        plan.warn(f"{b.id}: پرچم کیفی تصویر از استخراج: {flag}")
