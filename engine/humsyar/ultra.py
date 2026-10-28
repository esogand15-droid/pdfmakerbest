"""مرور فوق‌فشردهٔ دوصفحه‌ای (Ultra-Compact Revision Sheet).

راند ۱۴: این برگه بخش پایانیِ همان PDF نهایی جزوه است (پیش از واژه‌نامه) و
جای «مرور جامع» قدیمی را گرفته است؛ build آن را می‌سازد و ادغام می‌کند و
کاربر همیشه دقیقاً یک PDF نهایی تحویل می‌گیرد. فرمان `ultra` فقط ابزار
داخلی/آزمایشی است. حداکثر ۲ صفحهٔ A4 برای «بازیابی سریع»؛ مکمل متن کامل
جزوه، نه جایگزین آن.

اصول (طبق سند راند ۱۱):
  - خلاصه‌سازی مفهومی با «انتخاب + قالب» انجام می‌شود، نه بازنویسی: متن هر نکته
    عین عبارت منبع است (همان گزاره‌های ردیابی‌پذیر revision.extract_items).
    موتور هرگز جملهٔ علمی را پارافریز نمی‌کند؛ فشرده‌سازی یعنی حذف توضیحات
    تکراری/کم‌اولویت و نمایش ساختاری (جدول/رشته‌پیکان/چیپ/کادر) — با گزارش شفاف.
  - هر نکته شناسهٔ منبع دارد؛ پوشش A باید ۱۰۰٪ باشد یا موارد جامانده صریح در
    گزارش و فایل مکمل بیایند. بین «پوشش نکات ضروری مرور» و «پوشش کل منبع»
    تمایز صریح در گزارش ثبت می‌شود؛ این برگه ادعای پوشش کل منبع را ندارد.
  - بودجهٔ فضا از ابتدا دو صفحه است: انتخاب با اولویت A/B/C، سپس حلقهٔ
    رندر–اندازه‌گیری؛ فونت هرگز زیر کف پیکربندی نمی‌رود.
"""
from __future__ import annotations

import copy
import json
import math
import re
from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from typing import Any

from .model import Session, load_session, normalize_text
from .palette import session_style
from .revision import Item, extract_items
from .typeset import inline

# ---------------------------------------------------------------- اولویت‌بندی
_A_KINDS = {"definition", "formula", "exception", "source_conflict",
            "process", "key", "summary"}
_B_KINDS = {"clinical", "relationship", "mnemonic", "exam"}
_DEF_MARKERS = ("عبارت است از", "گفته می‌شود", "نامیده می‌شود", "می‌نامند",
                "نام دارد", "تعریف می‌شود")
_REL_MARKERS = ("باعث", "منجر", "در نتیجه", "زیرا", "به همین دلیل", "در مقایسه",
                "برخلاف", "در حالی که", "نسبت به", "افزایش", "کاهش")
_DIGITS = set("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩0123456789")


@dataclass
class UItem:
    item: Item
    priority: str = "C"      # A | B | C | X (خارج از دامنهٔ برگه)
    score: float = 0.0
    home: str = ""           # جزء نمایشی
    pool: int = 2
    dropped: str = ""        # دلیل حذف از برگه (خالی = حاضر)


def _numset(text: str) -> frozenset:
    return frozenset(re.findall(r"[۰-۹٠-٩0-9]+", str(text)))


# رقم ارجاعی (شمارهٔ شکل/جدول/صفحه/فصل/مبحث/جلسه) «عدد علمی» نیست؛ اولویت A و
# کادر «اعداد کلیدی» فقط برای کمیت‌های واقعی (اندازه/سرعت/تعداد/محدوده) است.
_REF_NUM = re.compile(
    r"(?:شکل|جدول|فصل|مبحث|جلسه|صفحه|ص|Fig\.?|Figure|Table)"
    r"\s*[۰-۹٠-٩0-9][۰-۹٠-٩0-9\s\-–—.٫,،و]*")
_DIGIT_RE = re.compile(r"[۰-۹٠-٩0-9]")


def _has_quantity(text: str) -> bool:
    """آیا متن — بیرون از ارجاع‌ها — کمیت عددی علمی دارد؟"""
    return bool(_DIGIT_RE.search(_REF_NUM.sub("", str(text or ""))))


def prioritize(session: Session, items: list[Item]) -> list[UItem]:
    """اولویت‌بندی قطعی بر پایهٔ گونهٔ گزاره و نشانه‌های ساختاری خود منبع.

    هیچ فرضی دربارهٔ «پرتکرار بودن در آزمون» اعمال نمی‌شود؛ گونهٔ exam فقط
    وقتی معتبر است که در دادهٔ منبع صریح آمده باشد."""
    topic_ids = {t.id for t in session.topics}
    seen_example_sections: set[str] = set()
    out: list[UItem] = []
    for it in items:
        u = UItem(item=it)
        k, txt = it.kind, it.text
        if k == "figure_visual":
            u.priority, u.dropped = "X", "جزئیات درون تصویر؛ در خودِ جزوه مرور می‌شود"
        elif it.meta.get("lang") == "en":
            u.priority = "C"  # کپشن انگلیسی شکل؛ کنار خود شکل در جزوه مرور می‌شود
        elif k == "detail" and any(m in txt for m in ("قاب پایانی", "همین جزوه", "در این جزوه")):
            u.priority = "C"  # جملهٔ ناوبریِ سند است، نه نکتهٔ علمی
        elif k in _A_KINDS or _has_quantity(txt):
            u.priority = "A"
        elif k == "table_row":
            u.priority = "A"
        elif k == "terminology":
            # اصطلاحات کلیدیِ تدوین‌شدهٔ هر مبحث A؛ برچسب‌های شکل B (چیپ ارزان‌قیمت)
            u.priority = "A" if it.block_id in topic_ids else "B"
        elif k in _B_KINDS:
            u.priority = "B"
        elif k == "example":
            u.priority = "B" if it.section_id not in seen_example_sections else "C"
            seen_example_sections.add(it.section_id)
        elif k == "detail":
            if any(m in txt for m in _DEF_MARKERS):
                u.priority = "A"
            elif any(m in txt for m in _REL_MARKERS):
                u.priority = "B"
            else:
                u.priority = "C"
        else:
            u.priority = "C"
        kind_w = {"definition": 30, "formula": 30, "exception": 28,
                  "source_conflict": 28, "process": 24, "table_row": 22,
                  "summary": 20, "key": 20, "clinical": 14, "relationship": 13,
                  "terminology": 10, "detail": 8, "example": 6}.get(k, 5)
        u.score = kind_w + (6 if _has_quantity(txt) else 0) + 14.0 / math.sqrt(
            max(len(txt), 1))
        out.append(u)
    return out


def dedup(uitems: list[UItem]) -> list[dict[str, str]]:
    """حذف تکرار معناییِ محافظه‌کارانه: فقط وقتی دو گزاره مجموعه‌عدد یکسان و
    هم‌پوشانی واژگانی ≥۸۵٪ دارند (عملاً یک گزاره‌اند). طولانی‌تر (کامل‌تر)
    می‌ماند و ادغام در گزارش ثبت می‌شود. زوج‌های تعارضی (اعداد متفاوت) هرگز
    ادغام نمی‌شوند."""
    merges: list[dict[str, str]] = []
    alive = [u for u in uitems if u.priority != "X" and u.item.kind != "table_row"]
    toks = {id(u): set(normalize_text(u.item.text).split()) for u in alive}
    for i, a in enumerate(alive):
        if a.dropped:
            continue
        for b in alive[i + 1:]:
            if b.dropped or a.item.kind != b.item.kind:
                continue
            if _numset(a.item.text) != _numset(b.item.text):
                continue
            ta, tb = toks[id(a)], toks[id(b)]
            if not ta or not tb:
                continue
            jac = len(ta & tb) / len(ta | tb)
            threshold = 0.85 if min(len(ta), len(tb)) >= 4 else 1.0
            if jac >= threshold:
                def richness(u):
                    return (bool(u.item.meta.get("en")), len(u.item.text))
                keep, drop = ((a, b) if richness(a) >= richness(b) else (b, a))
                drop.dropped = f"ادغام معنایی با {keep.item.id} (شباهت {jac:.2f})"
                merges.append({"kept": keep.item.id, "merged": drop.item.id,
                               "similarity": f"{jac:.2f}"})
    return merges


# ---------------------------------------------------------------- اجزای نمایشی
@dataclass
class Comp:
    kind: str                      # skeleton|defs|proc|table|numbers|alerts|confuse|points|chips
    title: str
    pool: int
    uitems: list[UItem] = field(default_factory=list)
    block: Any = None              # برای جدول/فرایند: بلوک منبع
    movable: bool = True
    min_priority: str = "A"


def _is_comparison_table(b) -> bool:
    title = str(b.data.get("title", ""))
    return "مقایسه" in title or len(b.data.get("headers", [])) <= 3


def build_components(session: Session, uitems: list[UItem]) -> list[Comp]:
    comps: list[Comp] = []
    by_id = {u.item.id: u for u in uitems}
    used: set[str] = set()

    def take(pred) -> list[UItem]:
        sel = [u for u in uitems if not u.dropped and u.item.id not in used and pred(u)]
        used.update(u.item.id for u in sel)
        return sel

    # اسکلت مبحث (فقط عنوان‌های عین منبع) — صفحهٔ ۱، غیرقابل جابه‌جایی
    comps.append(Comp("skeleton", "اسکلت مبحث", 1, movable=False))

    # جدول‌ها: اجزای مستقل با ردیف‌های خودشان
    for b in session.all_blocks():
        if b.type != "table":
            continue
        rows = take(lambda u, bid=b.id: u.item.block_id == bid and u.item.kind == "table_row")
        if rows:
            comps.append(Comp("table", str(b.data.get("title", "جدول")),
                              2 if _is_comparison_table(b) else 1,
                              uitems=rows, block=b))

    # تعریف‌ها و اصول (A): definition + جزئیات تعریف‌گونه + key/summary
    defs = take(lambda u: u.priority == "A" and u.item.kind in
                ("definition", "key", "summary", "formula") or
                (u.priority == "A" and u.item.kind == "detail" and not _has_quantity(u.item.text)))
    if defs:
        comps.append(Comp("defs", "تعریف‌ها و اصول پایه", 1, uitems=defs))

    # فرایندها: رشتهٔ پیکان از سرخط گام‌ها (عین داده) — گروه‌بندی بر اساس بلوک/مسیر
    procs: dict[str, list[UItem]] = {}
    for u in take(lambda u: u.item.kind == "process"):
        procs.setdefault(u.item.block_id, []).append(u)
    blocks = {b.id: b for b in session.all_blocks()}
    for bid, steps in procs.items():
        b = blocks.get(bid)
        comps.append(Comp("proc", str((b.data.get("title") if b else "") or "فرایند"),
                          1, uitems=steps, block=b))

    # اعداد کلیدی: گزاره‌های عدددارِ باقی‌مانده (خانهٔ واحد هر گزاره)
    nums = take(lambda u: _has_quantity(u.item.text) and u.priority == "A")
    if nums:
        comps.append(Comp("numbers", "اعداد و مقادیر کلیدی", 1, uitems=nums))

    # استثنا/تعارض — صفحهٔ ۲، کادر هشدار
    alerts = take(lambda u: u.item.kind in ("exception", "source_conflict"))
    if alerts:
        comps.append(Comp("alerts", "استثناها و اختلاف منابع", 2, uitems=alerts,
                          movable=False))

    # نکات B (بالینی/رابطه/…) — صفحهٔ ۲
    bpts = take(lambda u: u.priority == "B" and u.item.kind != "terminology")
    if bpts:
        comps.append(Comp("points", "نکات متمایزکننده", 2, uitems=bpts,
                          min_priority="B"))

    # اصطلاحات: چیپ فارسی+انگلیسی — صفحهٔ ۲
    terms = take(lambda u: u.item.kind == "terminology")
    if terms:
        comps.append(Comp("chips", "اصطلاحات کلیدی", 2, uitems=terms,
                          min_priority="B"))

    # «با هم اشتباه نکن» مشتق از جدول‌های مقایسه‌ای خود منبع — صفحهٔ ۲
    comps.append(Comp("confuse", "این‌ها را با هم اشتباه نکن", 2, movable=False))

    # باقی‌مانده‌ها کاندید پرکردن فضای خالی‌اند (نکات تکمیلی)؛ پیش‌فرض حذف با دلیل
    rest = [u for u in uitems if not u.dropped and u.item.id not in used]
    if rest:
        filler = Comp("points", "نکات تکمیلی", 2, uitems=[], min_priority="C")
        filler.uitems = rest
        comps.append(filler)

    # توازن دو صفحه: جدول‌ها صفحهٔ ثابت ندارند؛ بر اساس وزن متنی میان دو استخر
    # پخش می‌شوند تا هیچ صفحه‌ای از ابتدا سرریز نباشد (ترتیب درون هر صفحه حفظ
    # می‌شود و اسکلت/تعریف/فرایند در صفحهٔ ۱ و اعداد/هشدار/چیپ در صفحهٔ ۲ می‌مانند).
    # وزن هر جزء ≈ طول متن × ضریب سربار نمایشی گونه‌اش (جدول تمام‌عرض و اسکلت و
    # زنجیرهٔ فرایند به‌ازای هر نویسه گران‌تر از فهرست دوستونه‌اند).
    _WF = {"table": 1.5, "proc": 1.3, "chips": 1.25, "defs": 1.05,
           "numbers": 1.05, "alerts": 1.05, "points": 1.05}
    def _w(c: Comp) -> float:
        return _WF.get(c.kind, 1.0) * sum(
            len(u.item.text) for u in c.uitems if not u.dropped)
    skel_w = 1.6 * sum(len(t.title) + sum(len(str(b.data.get("title", "")))
                                          for b in t.blocks if b.type == "section")
                       for t in session.topics)
    w1 = skel_w + sum(_w(c) for c in comps if c.kind in ("defs", "proc", "numbers"))
    w2 = sum(_w(c) for c in comps if c.kind in ("alerts", "chips"))
    for c in comps:
        if c.kind != "table":
            continue
        tw = _w(c) + 90
        if w1 <= w2:
            c.pool, w1 = 1, w1 + tw
        else:
            c.pool, w2 = 2, w2 + tw
    for c in comps:
        for u in c.uitems:
            u.home, u.pool = c.kind, c.pool
    return comps


# ---------------------------------------------------------------- رندر HTML
def _bold_numbers(html_txt: str) -> str:
    return re.sub(r"([۰-۹٠-٩0-9][۰-۹٠-٩0-9.,:٫٬/٪%]*)", r'<b class="un">\1</b>', html_txt)


def _confuse_rows(session: Session, trimmed_row_ids: set[str] | None = None) -> list[str]:
    """«با هم اشتباه نکن»: فقط وقتی ردیفی از جدول مقایسه‌ای به‌علت بودجه بریده
    شده باشد — که برگه آن تفاوت را به شکل فشرده نگه دارد. اگر جدول کامل در
    برگه هست، تکرارش در این کادر اتلاف بودجه است. سلول‌ها عین منبع."""
    if not trimmed_row_ids:
        return []
    lines: list[str] = []
    for b in session.all_blocks():
        if b.type != "table" or not _is_comparison_table(b):
            continue
        hdrs = [str(h) for h in b.data.get("headers", [])]
        if len(hdrs) < 3:
            continue
        for i, row in enumerate(b.data.get("rows", [])):
            if f"{b.id}#{i}" not in trimmed_row_ids:
                continue
            if len(row) >= 3 and str(row[1]).strip() != str(row[2]).strip():
                lines.append(
                    f'<li><b>{inline(str(row[0]))}:</b> '
                    f'{inline(hdrs[1])} ← {inline(str(row[1]))} '
                    f'<span class="uvs">در برابر</span> '
                    f'{inline(hdrs[2])} ← {inline(str(row[2]))}</li>')
    return lines


def _comp_html(c: Comp, session: Session, trimmed_ids: set[str] | None = None) -> str:
    live = [u for u in c.uitems if not u.dropped]
    if c.kind == "skeleton":
        parts = []
        for t in session.topics:
            secs = [inline(str(b.data.get("title", ""))) for b in t.blocks
                    if b.type == "section"]
            parts.append(
                f'<div class="usk"><b>{escape(t.title)}</b>'
                + "".join(f'<span>{s}</span>' for s in secs) + "</div>")
        body = "".join(parts)
    elif c.kind == "confuse":
        lines = _confuse_rows(session, trimmed_ids)
        if not lines:
            return ""
        body = f'<ul class="up">{"".join(lines)}</ul>'
    elif not live:
        return ""
    elif c.kind == "table":
        b = c.block
        hdrs = "".join(f"<th>{inline(str(h))}</th>" for h in b.data.get("headers", []))
        rows_html = []
        live_ids = {u.item.id for u in live}
        for i, row in enumerate(b.data.get("rows", [])):
            if f"{b.id}#{i}" not in live_ids:
                continue
            tds = "".join(
                f'<td class="{"rowh" if j == 0 else ""}">{inline(str(cell))}</td>'
                for j, cell in enumerate(row))
            rows_html.append(f"<tr>{tds}</tr>")
        body = (f'<table class="utbl"><thead><tr>{hdrs}</tr></thead>'
                f'<tbody>{"".join(rows_html)}</tbody></table>')
    elif c.kind == "proc":
        lanes: dict[str, list[UItem]] = {}
        for u in live:
            lanes.setdefault(str(u.item.meta.get("lane_title") or ""), []).append(u)
        parts = []
        for lane, steps in lanes.items():
            _arr = (' <svg class="uarr" viewBox="0 0 10 10" aria-hidden="true">'
                    '<polygon points="10,1 10,9 2,5"/></svg> ')
            flow = _arr.join(
                f'<span class="ustep"><b>{u.item.meta.get("step_no", "")}.</b> '
                f'{inline(u.item.text)}</span>' for u in steps)
            parts.append((f'<div class="ulane">{f"<b>{inline(lane)}</b>" if lane else ""}'
                          f'<div class="uchain">{flow}</div></div>'))
        body = "".join(parts)
    elif c.kind == "chips":
        body = "".join(
            f'<span class="uchip">{inline(u.item.text)}'
            + (f' <bdi class="en">({escape(str(u.item.meta.get("en", "")))})</bdi>'
               if u.item.meta.get("en") else "") + "</span>"
            for u in live)
    elif c.kind == "numbers":
        body = '<ul class="up">' + "".join(
            f"<li>{_bold_numbers(inline(u.item.text))}</li>" for u in live) + "</ul>"
    elif c.kind == "alerts":
        body = '<ul class="up">' + "".join(
            f'<li class="ual">{"<b>" + escape(str(u.item.meta.get("title"))) + ":</b> " if u.item.meta.get("title") else ""}'
            f'{inline(u.item.text)}</li>' for u in live) + "</ul>"
    else:  # defs | points
        body = '<ul class="up">' + "".join(
            f"<li>{inline(u.item.text)}</li>" for u in live) + "</ul>"
    return (f'<section class="uc uc--{c.kind}"><h3>{escape(c.title)}</h3>{body}</section>')


ULTRA_CSS = """
@page{ size:A4; margin:0 }
*{ box-sizing:border-box }
body{ font-family:Vazirmatn,sans-serif; color:var(--ink); margin:0;
      font-size:var(--u-base,8.8pt); line-height:1.47 }
.upage{ padding:2mm 1mm 0 }
.upage+.upage{ break-before:page }
.uhead{ display:flex; justify-content:space-between; align-items:center;
  border-bottom:2pt solid var(--session-header,var(--royal-600)); padding-bottom:2mm; margin-bottom:3mm }
.uhead .ut{ font-weight:800; color:var(--session-deep,var(--navy-900)); font-size:1.5em }
.uhead .ub{ color:var(--session-deep,var(--royal-600)); font-weight:700 }
.uhead .ubadge{ background:var(--session-header,var(--royal-600)); color:#fff; border-radius:20pt;
  padding:1pt 7pt; font-weight:700; font-size:max(.82em,7.05pt) }
.ucols{ columns:2; column-gap:5mm }
.uc{ break-inside:avoid; border:1pt solid var(--hairline); border-radius:5pt;
  padding:1.9mm 2.3mm; margin:0 0 2.4mm; background:#fff }
.uc--skeleton,.uc--table,.uc--proc{ column-span:all }
.uc h3{ margin:0 0 1.6mm; color:var(--session-deep,var(--royal-600)); font-size:1.06em }
.uc--alerts{ border-color:var(--line-warm); border-inline-start:3pt solid var(--fam4w); background:var(--surface) }
.uc--alerts h3{ color:var(--c-warning) }
.uc--numbers{ background:var(--surface) }
.up{ margin:0; padding-inline-start:4.2mm }
.up li{ margin:.4mm 0 }
.usk b{ color:var(--session-deep,var(--navy-900)); display:block; margin-top:1mm }
.usk span{ display:inline-block; background:var(--surface-warm); border-radius:10pt;
  padding:0 5pt; margin:.6mm 0 .6mm 1.2mm; font-size:max(.86em,7.05pt) }
.utbl{ width:100%; border-collapse:collapse; font-size:max(.92em,7.05pt) }
.utbl th{ background:var(--session-header,var(--royal-600)); color:#fff; padding:1.2mm 1.6mm; text-align:start }
.utbl td{ border-bottom:.5pt solid var(--hairline); padding:.7mm 1.4mm; vertical-align:top }
.utbl td.rowh{ background:var(--session-soft,var(--ice-100)); font-weight:700; color:var(--session-deep,var(--navy-900)) }
.utbl tbody tr:nth-child(even) td:not(.rowh){ background:var(--zebra) }
.uchain{ margin:1mm 0; line-height:2 }
.ustep{ background:var(--surface); border:1pt solid var(--line-chip); border-radius:10pt;
  padding:0 6pt; white-space:nowrap }
.uarr{ width:7pt; height:7pt; fill:var(--session-deep,var(--royal-600)); vertical-align:-1pt }
.uchip{ display:inline-block; border:1pt solid var(--line-chip); background:var(--surface);
  border-radius:10pt; padding:0 5pt; margin:.6mm 0 .6mm 1.2mm; font-size:max(.9em,7.05pt) }
.uvs{ color:var(--slate-deep); font-size:max(.85em,7.05pt) }
.ufoot{ border-top:1pt solid var(--hairline); margin-top:2mm; padding-top:1.6mm;
  color:var(--slate-deep); font-size:max(.8em,7.05pt); display:flex; justify-content:space-between }
body.tight{ line-height:1.35 }
.tight .ucols{ column-gap:4mm }
.tight .uchain{ line-height:1.62 }
.tight .uchip{ font-size:max(.85em,7.05pt) }
.tight .upage{ padding-top:1mm }
.tight .uhead{ margin-bottom:2mm; padding-bottom:1.4mm }
.tight .uc{ margin-bottom:1.6mm; padding:1.4mm 2.1mm }
.tight .uc h3{ margin-bottom:1mm }
.tight .up li{ margin:.2mm 0 }
.tight .utbl{ line-height:1.3 }
.tight .utbl td{ padding:.35mm 1.3mm }
.tight .utbl th{ padding:.7mm 1.4mm }
.tight .usk b{ display:inline; margin:0 0 0 2mm }
.tight .usk span{ margin:.35mm 0 .35mm 1mm; font-size:max(.82em,7.05pt) }
.tight .uchip{ margin:.35mm 0 .35mm 1mm }
.tight .ufoot{ margin-top:1.2mm; padding-top:1mm }
.up li{ break-inside:avoid }
.term,.numbadge,.un{ background-color:var(--hl); color:inherit; border:0; padding:0 .2em;
  border-radius:.2em; display:inline; line-height:inherit; box-decoration-break:clone;
  -webkit-box-decoration-break:clone; box-shadow:none; text-shadow:none }
.en, bdi.en{ font-family:Inter,Vazirmatn,sans-serif; direction:ltr; color:var(--ink) }
"""


def render_html(session: Session, comps: list[Comp], *, base_pt: float,
                tight: bool, brand_css: str, font_css: str,
                trimmed_ids: set[str] | None = None, single: bool = False,
                brand_fa: str = "هامزیار", brand_en: str = "HumsYar",
                extra_css: str = "") -> str:
    pages = []
    titles = {1: "اسکلت مفهومی مبحث", 2: "جزئیات تعیین‌کننده و مرور نهایی"}
    for pool in ((1,) if single else (1, 2)):
        body = "".join(_comp_html(c, session, trimmed_ids) for c in comps
                       if single or c.pool == pool)
        badge = ("مرور فوق‌فشرده · تک‌صفحه" if single
                 else f'{titles[pool]} · صفحهٔ {"۱" if pool == 1 else "۲"} از ۲')
        head = (
            f'<div class="uhead"><span class="ut">{escape(session.course)} — '
            f'{escape(session.title)}</span>'
            f'<span class="ubadge">{badge}</span>'
            f'<span class="ub">{escape(brand_fa)} · {escape(brand_en)}</span></div>')
        foot = ('<div class="ufoot"><span>مرور فوق‌فشرده — مکمل جزوهٔ کامل است، نه جایگزین آن؛ '
                'جزئیات کامل در متن اصلی جزوه آمده است.</span>'
                f'<span>{escape(brand_fa)}</span></div>')
        pages.append(f'<div class="upage">{head}<div class="ucols">{body}</div>{foot}</div>')
    return (f'<!DOCTYPE html><html lang="fa" dir="rtl"><head><meta charset="utf-8">'
            f'<style>{font_css}\n{brand_css}\n:root{{--u-base:{base_pt}pt}}\n{ULTRA_CSS}{extra_css}</style>'
            f'</head><body style="{session_style(session.session_number)}" class="{"tight" if tight else ""}">{"".join(pages)}</body></html>')


# ---------------------------------------------------------------- حلقهٔ جاگیری
def _cfg() -> dict[str, Any]:
    import yaml
    p = Path(__file__).resolve().parents[2] / "config" / "layout.yaml"
    cfg = (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("ultra_revision", {})
    return {"enabled": True, "max_pages": 2, "base_font_pt": 8.8,
            "font_floor_pt": 7.5, "max_text_ratio": 0.5,
            "filler_max_chars": 200, **cfg}


def build_ultra(content_path: str, *, out_dir: str = "output",
                topic_ids: list[str] | None = None,
                stem_suffix: str = "", extra_css: str = "") -> dict[str, Any]:
    """ساخت برگهٔ مرور فوق‌فشرده + گزارش پوشش/حذف شفاف."""
    from .build import _render_pdf, _font_css
    from .palette import brand_css_text
    import pymupdf

    cfg = _cfg()
    session = load_session(content_path)
    full_session = session
    if topic_ids:
        session = copy.deepcopy(session)
        session.topics = [t for t in session.topics if t.id in topic_ids]
        session.closing = []
        if not session.topics:
            raise ValueError(f"هیچ مبحثی با شناسه‌های {topic_ids} یافت نشد")

    items = extract_items(session)
    uitems = prioritize(session, items)
    merges = dedup(uitems)
    seen_en: set[str] = set()
    for u in uitems:
        en = str(u.item.meta.get("en", "")).strip().lower()
        if u.item.kind == "terminology" and en and not u.dropped:
            if en in seen_en:
                u.dropped = "معادل انگلیسی تکراری در ناحیهٔ چیپ‌ها"
                merges.append({"kept": en, "merged": u.item.id, "similarity": "en"})
            seen_en.add(en)
    comps = build_components(session, uitems)
    # ---- راهبرد بودجه از ابتدا: اول A، بعد افزودن پلکانی B و C
    # Bها (به‌جز هشدارها که Aند) ابتدا بیرون‌اند و به ترتیب «ارزش بر حجم» اضافه می‌شوند.
    filler = next((c for c in comps if c.min_priority == "C"), None)
    c_pool = sorted((filler.uitems if filler else []), key=lambda u: -u.score)
    b_pool_all = [u for u in uitems if u.priority == "B" and not u.dropped
                  and u not in c_pool]
    b_pool_all.sort(key=lambda u: -(u.score / math.sqrt(max(len(u.item.text), 1))))
    for u in b_pool_all + c_pool:
        u.dropped = f"اولویت {u.priority} — بیرون از بودجهٔ برگه؛ در جزوهٔ کامل هست"

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    work = out / "_ultra_work"
    work.mkdir(exist_ok=True)
    stem = Path(content_path).stem + "_ultra" + stem_suffix
    pdf_path = out / f"{stem}.pdf"
    floor = float(cfg["font_floor_pt"])
    base = float(cfg["base_font_pt"])
    tight = False
    trace: list[dict[str, Any]] = []

    def trimmed_ids() -> set[str]:
        return {u.item.id for u in uitems if u.item.kind == "table_row" and u.dropped}

    single_mode = False

    def render_now() -> tuple[int, int | None, float, float]:
        html = render_html(session, comps, base_pt=base, tight=tight,
                           brand_css=brand_css_text(), font_css=_font_css(),
                           trimmed_ids=trimmed_ids(), single=single_mode,
                           extra_css=extra_css)
        _render_pdf(html, pdf_path, work, session,
                    margin={"top": "6.5mm", "bottom": "6.5mm",
                            "left": "7.5mm", "right": "7.5mm"}, tag="ultra")
        doc = pymupdf.open(str(pdf_path))
        marker = None
        probe = normalize_text("جزئیات تعیین‌کننده")
        for i, pg in enumerate(doc):
            if probe in normalize_text(pg.get_text()):
                marker = i + 1
                break
        def _used(pg) -> float:
            bs = [b for b in pg.get_text("blocks") if b[4].strip()]
            return max((b[3] for b in bs), default=0) / pg.rect.height if bs else 0
        used = _used(doc[-1])
        p1_used = _used(doc[0]) if doc.page_count >= 1 else 0
        return doc.page_count, marker, round(float(used), 2), round(float(p1_used), 2)

    def over_pool(marker) -> int:
        return 1 if (marker or 99) > 2 else 2

    def drop_lowest(pool: int, prios: tuple[str, ...], frac: float = 1.0) -> int:
        cand = [u for c in comps if c.pool == pool for u in c.uitems
                if not u.dropped and u.priority in prios]
        cand.sort(key=lambda u: u.score)
        n = max(1, math.ceil(len(cand) * frac)) if cand else 0
        for u in cand[:n]:
            u.dropped = f"حذف بودجه‌ای (اولویت {u.priority}) — در جزوهٔ کامل هست"
        return n

    # فاز ۱: فقط A باید در دو صفحه جا شود
    pages, marker, used, p1_used = render_now()
    trace.append({"step": "A-only", "pages": pages, "p2_marker": marker,
                  "base_pt": base, "tight": tight, "last_used": used})
    guard = 0
    while pages > 2 and guard < 12:
        guard += 1
        pool = over_pool(marker)
        if not tight:
            tight, acted = True, "tighten"
        elif pool == 1 and any(c.movable and c.pool == 1 and c.kind in ("table", "defs", "numbers")
                               and any(not u.dropped for u in c.uitems) for c in comps):
            mv = next(c for c in reversed(comps)
                      if c.movable and c.pool == 1 and c.kind in ("table", "defs", "numbers")
                      and any(not u.dropped for u in c.uitems))
            mv.pool = 2
            mv.movable = False  # قفل ضد رفت‌وبرگشت در نردبان جاگیری
            for u in mv.uitems:
                u.pool = 2
            acted = f"move:{mv.kind}->p2"
        elif pool == 2 and p1_used < 0.92 and any(
                c.movable and c.pool == 2 and c.kind in ("numbers", "chips", "points")
                and any(not u.dropped for u in c.uitems) for c in comps):
            # دم خالی صفحهٔ ۱ را با کامپوننت متحرک صفحهٔ ۲ پر کن (قرارداد دوصفحه‌ای
            # و همهٔ Aها سر جایشان می‌مانند؛ فقط جای نمایشی عوض می‌شود).
            mv = next(c for c in comps
                      if c.movable and c.pool == 2
                      and c.kind in ("numbers", "chips", "points")
                      and any(not u.dropped for u in c.uitems))
            mv.pool = 1
            mv.movable = False  # قفل ضد رفت‌وبرگشت در نردبان جاگیری
            for u in mv.uitems:
                u.pool = 1
            acted = f"move:{mv.kind}->p1"
        elif base - 0.3 >= floor:
            base = round(base - 0.3, 1)
            acted = f"font:{base}"
        elif drop_lowest(pool, ("A",), 0.15):
            acted = f"overflowA:p{pool}"
        else:
            break
        pages, marker, used, p1_used = render_now()
        trace.append({"step": acted, "pages": pages, "p2_marker": marker,
                      "base_pt": base, "tight": tight, "last_used": used})

    # فاز ۲ و ۳: افزودن پلکانی B سپس C تا لبهٔ بودجه (با عقب‌نشینی امن)
    total_chars_all = sum(len(i.text) for i in items)
    ratio_cap = float(cfg.get("max_text_ratio", 0.5)) * total_chars_all

    def kept_chars() -> int:
        return sum(len(u.item.text) for u in uitems if not u.dropped)

    def fill(pool_items: list[UItem], label: str, pages_now: int) -> int:
        remaining = list(pool_items)
        if label == "C":
            # جملهٔ توضیحی بلند هرگز «نکتهٔ تکمیلی» نمی‌شود؛ برگه دیوار متن نیست
            cap_len = int(cfg.get("filler_max_chars", 200))
            kept_pool = [u for u in remaining if len(u.item.text) <= cap_len]
            for u in remaining:
                if len(u.item.text) > cap_len:
                    u.dropped = "توضیح بلند (اولویت C) — جایش متن اصلی جزوه است"
            remaining = kept_pool
        while remaining and pages_now <= 2:
            if label == "C" and kept_chars() >= ratio_cap:
                trace.append({"step": "fillC:ratio-cap", "kept_chars": kept_chars()})
                break
            tranche = remaining[: max(1, math.ceil(len(remaining) * 0.34))]
            for u in tranche:
                u.dropped = ""
            p, m, usd, _p1 = render_now()
            if p <= 2:
                pages_now = p
                remaining = remaining[len(tranche):]
                trace.append({"step": f"fill{label}:+{len(tranche)}", "pages": p,
                              "last_used": usd})
                if usd > 0.96:
                    break
            else:
                # پس‌زدن نیمی از ترانش و تلاش دوباره با نیم دیگر
                back = tranche[len(tranche) // 2:] if len(tranche) > 1 else tranche
                for u in back:
                    u.dropped = f"اولویت {u.priority} — بیرون از بودجهٔ برگه؛ در جزوهٔ کامل هست"
                p, m, usd, _p1 = render_now()
                trace.append({"step": f"fill{label}:trim->{len(tranche) - len(back)}",
                              "pages": p, "last_used": usd})
                pages_now = p
                if p > 2:  # حتی نیم‌ترانش هم جا نشد: کل ترانش برگردد
                    for u in tranche:
                        u.dropped = f"اولویت {u.priority} — بیرون از بودجهٔ برگه؛ در جزوهٔ کامل هست"
                    pages_now, _, _, _ = render_now()
                    trace.append({"step": f"fill{label}:revert", "pages": pages_now})
                break
        return pages_now

    if pages <= 2:
        # تعادل دو صفحه: اگر صفحهٔ ۱ خالی‌تر است، جزء متحرک از صفحهٔ ۲ بالا بیاید
        for _ in range(3):
            if p1_used >= 0.74:
                break
            cand = [c for c in comps if c.pool == 2 and c.movable
                    and c.kind in ("table", "numbers", "chips", "points")
                    and any(not u.dropped for u in c.uitems)]
            if not cand:
                break
            cand.sort(key=lambda c: sum(len(u.item.text) for u in c.uitems if not u.dropped))
            mv = cand[0]
            mv.pool = 1
            for u in mv.uitems:
                u.pool = 1
            p, m, usd, p1u = render_now()
            trace.append({"step": f"balance:{mv.kind}->p1", "pages": p,
                          "p1_used": p1u, "last_used": usd})
            if p > 2:
                mv.pool = 2
                for u in mv.uitems:
                    u.pool = 2
                pages, marker, used, p1_used = render_now()
                trace.append({"step": "balance:revert", "pages": pages})
                break
            pages, used, p1_used = p, usd, p1u
        # بازیابی فونت: خوانایی بر تراکم مقدم است (B بعداً با فضای باقی‌مانده می‌آید)
        while base + 0.3 <= float(cfg["base_font_pt"]) + 1e-9:
            prev = base
            base = round(base + 0.3, 1)
            p, m, usd, p1u = render_now()
            if p > 2:
                base = prev
                pages, marker, used, p1_used = render_now()
                trace.append({"step": f"font-restore-stop:{base}", "pages": pages})
                break
            pages, used, p1_used = p, usd, p1u
            trace.append({"step": f"font-restore:{base}", "pages": p,
                          "p1_used": p1u, "last_used": usd})
    if pages <= 2:
        pages = fill(b_pool_all, "B", pages)
    # اگر صفحهٔ ۲ کم‌تراکم است، برگهٔ تک‌صفحه‌ای صادقانه‌تر از صفحهٔ دومِ خالی است
    if pages == 2:
        pages, marker, used, p1_used = render_now()
        trace.append({"step": "measure", "p1_used": p1_used, "last_used": used})
        if used < 0.5:
            snapshot = [(c, c.pool) for c in comps]
            for c in comps:
                c.pool = 1
                for u in c.uitems:
                    u.pool = 1
            single_mode = True
            p, m, usd, p1u = render_now()
            trace.append({"step": "single-try", "pages": p, "last_used": usd})
            if p == 1:
                pages, used, p1_used = p, usd, p1u
            else:
                single_mode = False
                for c, pl in snapshot:
                    c.pool = pl
                    for u in c.uitems:
                        u.pool = pl
                pages, marker, used, p1_used = render_now()
                trace.append({"step": "single-revert", "pages": pages})
    if pages <= 2 and not single_mode:
        pages = fill(c_pool, "C", pages)


    # تعادل بصری نهایی: اختلاف پرشدگی دو صفحه نباید فاحش باشد
    if pages == 2 and not single_mode:
        pages, marker, used, p1_used = render_now()
        for _ in range(2):
            if abs(p1_used - used) <= 0.3:
                break
            src, dst = (1, 2) if p1_used > used else (2, 1)
            cand = [c for c in comps if c.pool == src and c.movable
                    and c.kind in ("points", "chips", "numbers", "defs")
                    and any(not u.dropped for u in c.uitems)]
            if not cand:
                break
            cand.sort(key=lambda c: sum(len(u.item.text) for u in c.uitems if not u.dropped))
            mv = cand[0]
            mv.pool = dst
            for u in mv.uitems:
                u.pool = dst
            p, m, usd, p1u = render_now()
            trace.append({"step": f"final-balance:{mv.kind}->{dst}", "pages": p,
                          "p1_used": p1u, "last_used": usd})
            if p > 2 or abs(p1u - usd) >= abs(p1_used - used):
                mv.pool = src
                for u in mv.uitems:
                    u.pool = src
                pages, marker, used, p1_used = render_now()
                trace.append({"step": "final-balance:revert", "pages": pages})
                break
            pages, used, p1_used = p, usd, p1u

    overflow_a = [u for u in uitems if u.priority == "A" and u.dropped
                  and "بودجه‌ای (اولویت A" in u.dropped]
    if overflow_a:
        (out / f"{stem}_overflow.md").write_text(
            "# نکات ضروریِ جامانده از برگهٔ دوصفحه‌ای (مکمل شفافیت)\n\n"
            "این نکات اولویت A در بودجهٔ دو صفحه با کف خوانایی جا نشدند؛ "
            "در متن کامل همین جزوه حاضرند:\n\n"
            + "".join(f"- [{u.item.id}] {u.item.text}\n" for u in overflow_a),
            encoding="utf-8")

    # ---- گزارش پوشش
    def cov(prio: str) -> dict[str, int]:
        sel = [u for u in uitems if u.priority == prio]
        kept = [u for u in sel if not u.dropped]
        return {"total": len(sel), "in_sheet": len(kept),
                "merged": sum(1 for u in sel if u.dropped.startswith("ادغام"))}

    doc = pymupdf.open(str(pdf_path))
    pdf_text = normalize_text(" ".join(p.get_text() for p in doc))
    # اعدادِ نکات A حاضر باید عیناً در خروجی باشند
    missing_numbers = []
    for u in uitems:
        if u.priority == "A" and not u.dropped and u.item.has_number:
            for num in _numset(u.item.text):
                if normalize_text(num) not in pdf_text:
                    missing_numbers.append({"id": u.item.id, "num": num})
    total_chars = sum(len(i.text) for i in items)
    kept_chars = sum(len(u.item.text) for u in uitems if not u.dropped)
    report = {
        "pdf": str(pdf_path),
        "pages": pages,
        "fits_two_pages": pages <= 2,
        "single_page": single_mode,
        "status": ("standard" if pages <= 2 and not overflow_a
                   else "standard_with_a_overflow" if pages <= 2 else "OVERFLOW"),
        "font": {"base_pt": base, "floor_pt": floor},
        "items_total": len(items),
        "coverage": {"A": cov("A"), "B": cov("B"), "C": cov("C")},
        "excluded_figure_visual": cov("X")["total"],
        "merges": merges,
        "dropped": [{"id": u.item.id, "priority": u.priority, "reason": u.dropped}
                    for u in uitems if u.dropped and u.priority != "X"
                    and not u.dropped.startswith("ادغام")],
        "overflow_a_count": len(overflow_a),
        "missing_numbers_check": missing_numbers,
        "text_chars": {"source_items": total_chars, "in_sheet": kept_chars,
                       "reduction_pct": round(100 * (1 - kept_chars / max(total_chars, 1)), 1)},
        "note": "پوشش A یعنی پوشش نکات ضروریِ مرور؛ این برگه ادعای پوشش همهٔ جزئیات منبع را ندارد (جزئیات کامل در متن خود جزوه است).",
        "fit_trace": trace,
    }
    (out / f"{stem}_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return report
