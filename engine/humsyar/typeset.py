"""
حروف‌چین (Typesetter): تبدیل مدل محتوا + پلان چیدمان به HTML معنایی.

نشانه‌گذاری درون‌متنی در دادهٔ YAML (حداقلی و مستند):
  **متن**              ← برجسته‌سازی
  [[term:فارسی|English]] ← اصطلاح دوزبانه در نخستین ورود (فارسی برجسته + لاتین ایزوله)
  [en:Term]            ← عبارت لاتین ایزوله (bdi) برای سلامت bidi
همهٔ عبارت‌های لاتین در <bdi> قرار می‌گیرند تا ترتیب راست‌به‌چپ خراب نشود.
"""
from __future__ import annotations

import re
from html import escape

from .diagrams import tree_svg
from .entities import entity_color, entity_css_vars
from .icons import CALLOUT_ICONS, icon_svg
from .revision import extract_items
from .model import Block, Session, Source, Topic
from .planner import Plan, fa_num

KIND_LABELS = {
    "key": "نکتهٔ کلیدی", "clinical": "نکتهٔ بالینی", "warning": "هشدار",
    "exception": "استثنا", "bridge": "از ساختار تا عملکرد", "conflict": "اختلاف منابع",
    "exam": "نکتهٔ امتحانی", "definition": "تعریف اصطلاح", "example": "مثال آموزشی",
    "summary": "جمع‌بندی سریع", "mnemonic": "یادیار", "formula": "فرمول",
    "terminology": "اصطلاح‌شناسی", "unresolved": "نیازمند بررسی",
}
# ترتیب استاندارد نمایش راهنمای کادرها
KIND_ORDER = ["key", "definition", "clinical", "bridge", "warning", "exception",
              "conflict", "exam", "mnemonic", "formula", "terminology",
              "example", "summary", "unresolved"]


def icon(kind: str) -> str:
    """آیکون ثابت هر گونهٔ کادر از کتابخانهٔ مرکزی SVG."""
    return icon_svg(CALLOUT_ICONS.get(kind, "note"), 15)


def inline(text: str) -> str:
    """رندر نشانه‌گذاری درون‌متنی با ایزوله‌سازی bidi."""
    s = escape(str(text))
    s = re.sub(r"\[\[term:(.+?)\|(.+?)\]\]",
               r'<span class="term">\1 <bdi class="en">(\2)</bdi></span>', s)
    s = re.sub(r"\[\[num:(.+?)\]\]", r'<span class="numbadge">\1</span>', s)
    s = re.sub(r"\[en:([^\]]+)\]", r'<bdi class="en">\1</bdi>', s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    return s


def _tree_color(node: dict) -> str | None:
    """رنگ ثابت موجودیت از روی برچسب گرهٔ درخت (نام دقیق؛ حدس فازی ممنوع)."""
    lab = str(node.get("label") or " ".join(node.get("label_lines", [])))
    cands = [lab, lab.split("(")[0].strip(),
             lab.rstrip(")").split("(")[-1].strip()]
    return next((c for c in (entity_color(c) for c in cands) if c), None)


def src_chips(sources: list[Source], show: bool = True) -> str:
    if not show or not sources:
        return ""
    return " ".join(f'<span class="src"><b>منبع:</b> {escape(s.label())}</span>' for s in sources)


class Typesetter:
    def __init__(self, plan: Plan, *, show_sources: bool = True,
                 toc_pages: dict[str, int] | None = None,
                 fig_pages: dict[str, int] | None = None,
                 print_theme: bool = False,
                 assets_uri: str = "", brand: dict | None = None) -> None:
        self.plan = plan
        self.session = plan.session
        self.show_sources = show_sources
        self.toc_pages = toc_pages or {}
        self.fig_pages = fig_pages or {}
        self._qc_items: list[tuple[int, str]] = []  # (شماره، پاسخ) برای پاسخ‌نامهٔ پایانی
        self.print_theme = print_theme
        self.assets_uri = assets_uri  # پیشوند file:// برای مسیر دارایی‌ها
        self.brand = brand or {"fa": "هامزیار", "en": "HumsYar"}

    # -------------------------------------------------------------- اجزای سند
    def document(self, css: str, theme: str = "a") -> str:
        s = self.session
        body = [self.toc_page()]
        for topic in s.topics:
            body.append(self.topic(topic))
        if s.closing:
            body.append('<div class="section" style="margin-top:16pt"><h3>جمع‌بندی و مرور جلسه</h3></div>')
            body.append(self.render_blocks(s.closing))
        body.append(self.revision_map())
        body.append(self.glossary())
        body.append(self.answer_key())
        body.append(self.colophon())
        body.append(
            f'<div class="doc-end"><span class="en">{escape(self.brand["en"])}</span> · جزوهٔ '
            f'{escape(s.course)} — جلسهٔ {fa_num(s.session_number)} · نسخهٔ {escape(s.version)}'
            f'<br>این سند با موتور جزوه‌ساز {escape(self.brand["fa"])} از روی جزوهٔ مادر تولید شده است؛ '
            f'ارجاع هر مطلب با برچسب منبع در کنار آن آمده است.</div>'
        )
        favicon = (f'<link rel="icon" type="image/png" href="{self.brand["favicon_uri"]}">'
                   if self.brand.get("favicon_uri") else "")
        return (
            '<!DOCTYPE html><html lang="fa" dir="rtl"'
            + (f' data-theme="{theme}"' if theme != "a" else "") + '><head><meta charset="utf-8">'
            f'<title>{escape(s.course)} — جلسهٔ {fa_num(s.session_number)}: {escape(s.title)}</title>{favicon}'
            f'<style>{css}{entity_css_vars()}</style></head>'
            f'<body class="{"print-theme" if self.print_theme else ""}">{"".join(body)}</body></html>'
        )

    def toc_page(self) -> str:
        """صفحهٔ اختصاصی فهرست: نقشهٔ جلسه + فهرست پیونددار + نوار راهنمای خواندن."""
        return (f'<div class="tocpage">{self.session_map()}{self.toc()}'
                f'{self.figure_table_lists()}{self.reading_guide()}</div>')

    def render_blocks(self, blocks: list[Block]) -> str:
        """رندر ترتیبی بلوک‌ها در بازه‌های بخشی (secpan) با پشتیبانی جفت‌تصویر.

        بازهٔ هر بخش یک wrapper می‌گیرد تا ریتم صفحه (مثلاً تنفسی برای بخش توضیحی)
        در سطح بخش اعمال شود؛ شکست صفحه داخل بازه آزاد است و ترتیب عوض نمی‌شود.
        """
        groups: list[tuple[str, list[Block]]] = []
        cur: list[Block] = []
        rhythm = ""
        for b in blocks:
            if b.type == "section" and cur:
                groups.append((rhythm, cur))
                cur, rhythm = [], ""
            if b.type == "section":
                rhythm = str(b.data.get("_rhythm", ""))
            cur.append(b)
        if cur:
            groups.append((rhythm, cur))

        out: list[str] = []
        for rhythm, grp in groups:
            inner: list[str] = []
            i = 0
            while i < len(grp):
                b = grp[i]
                if b.data.get("_pair_first") and i + 1 < len(grp) \
                        and grp[i + 1].id == b.data["_pair_first"]:
                    sty = ' style="break-before:page"' if b.data.get("_break_before") else ""
                    inner.append(f'<div class="figpair" data-bid="{escape(b.id)}"{sty}>'
                                 f'{self._figure_frame(b, with_bid=False)}'
                                 f'{self._figure_frame(grp[i + 1], with_bid=False)}</div>')
                    i += 2
                    continue
                inner.append(self.block(b))
                i += 1
            cls = "secpan secpan--airy" if rhythm == "airy" else "secpan"
            out.append(f'<div class="{cls}">{"".join(inner)}</div>')
        return "".join(out)

    def session_map(self) -> str:
        s = self.session
        if not s.session_map:
            return ""
        included = {t.number for t in s.topics}
        items = []
        for m in s.session_map:
            n = int(m["number"])
            pg = self.toc_pages.get(str(m.get("id", "")))
            pg_txt = f'ص {fa_num(pg)}' if pg else str(m.get("tag", ""))
            items.append(
                f'<li class="{"in" if n in included else ""}">'
                f'<span class="n">{fa_num(n)}</span><span>{escape(str(m["title"]))}</span>'
                f'<span class="pg">{escape(pg_txt)}</span></li>')
        return f'<nav class="session-map"><h2>نقشهٔ جلسه در یک نگاه</h2><ol>{"".join(items)}</ol></nav>'

    def toc(self) -> str:
        n = len(self.plan.headings)
        lh = 2.35 if n <= 12 else (2.05 if n <= 20 else 1.8)
        if any(b.type in ("figure", "table") for b in self.session.all_blocks()):
            lh = max(1.58, lh - 0.62)  # جای فهرست شکل‌ها/جدول‌ها و راهنمای رنگ در همان صفحه
        items = []
        for lvl, text, anchor in self.plan.headings:
            pg = self.toc_pages.get(anchor)
            items.append(
                f'<li class="lvl{lvl}"><a href="#{escape(anchor)}"><span>{escape(text)}</span>'
                f'<span class="dots"></span>'
                f'<span class="pno">{fa_num(pg) if pg else "…"}</span></a></li>')
        return (f'<nav class="toc" style="--toc-lh:{lh}"><h2>فهرست مطالب</h2>'
                f'<ol>{"".join(items)}</ol></nav>')

    def figure_table_lists(self) -> str:
        """فهرست شکل‌ها و جدول‌ها — فقط وقتی صفحهٔ واقعی هر مورد از بدنه خوانده شده باشد."""
        figs, tbls = [], []
        for b in self.session.all_blocks():
            if b.type not in ("figure", "table"):
                continue
            pg = self.fig_pages.get(b.id)
            label = escape(self.plan.labels.get(b.id, ""))
            if b.type == "figure":
                t = escape(str(b.data.get("title_fa", "")))
                figs.append(f'<li><span class="ln">{label}</span><span>{t}</span>'
                            f'<span class="dots"></span><span class="pno">{fa_num(pg) if pg else "…"}</span></li>')
            elif b.type == "table":
                t = escape(str(b.data.get("title", "")))
                tbls.append(f'<li><span class="ln">{label}</span><span>{t}</span>'
                            f'<span class="dots"></span><span class="pno">{fa_num(pg) if pg else "…"}</span></li>')
        if not figs and not tbls:
            return ""
        col_f = (f'<div class="lists__col"><h2>فهرست شکل‌ها</h2><ol>{"".join(figs)}</ol></div>'
                 if figs else "")
        col_t = (f'<div class="lists__col"><h2>فهرست جدول‌ها</h2><ol>{"".join(tbls)}</ol></div>'
                 if tbls else "")
        return f'<div class="lists">{col_f}{col_t}</div>'

    def reading_guide(self) -> str:
        """راهنمای خواندن: معنای کادرها و برچسب منبع — مبلمان ثابت جزوه، نه محتوای علمی."""
        guide_texts = {
            "key": "مفهومی که باید در نگاه اول دیده شود.",
            "clinical": "کاربرد بالینی همان مطلب، به نقل از خود جزوه/منابع.",
            "warning": "جای اشتباه رایج یا استثنای قاعده.",
            "bridge": "پل میان آناتومی و کارکرد.",
            "conflict": "جایی که دو منبع عدد/عبارت متفاوت دارند؛ هر دو می‌مانند تا تیم علمی تصمیم بگیرد.",
            "exam": "فقط وقتی خود منبع چنین برچسبی زده باشد.",
            "definition": "تعریف کوتاه و دقیق یک اصطلاح.",
            "example": "مثال آموزشیِ موجود در خود محتوا.",
            "summary": "جمع‌بندی سریع همان بخش.",
            "exception": "جایی که قاعدهٔ کلی صدق نمی‌کند؛ مرز اعتبار قاعده.",
            "mnemonic": "یادیار کوتاهِ موجود در خود محتوا برای به‌خاطرسپاری.",
            "formula": "فرمول یا رابطهٔ عددیِ خود منبع، با نمادهای دقیق خودش.",
            "terminology": "ریشه و کاربرد اصطلاح، به نقل از خود منبع.",
            "unresolved": "موردی که هنوز پاسخ قطعی در منابع این جلسه ندارد.",
        }
        # راهنما فقط کادرهایی را توضیح می‌دهد که واقعاً در همین جلسه به کار رفته‌اند
        used = {b.data.get("kind") for b in self.session.all_blocks() if b.type == "callout"}
        items = [(k, KIND_LABELS[k], guide_texts[k]) for k in KIND_ORDER if k in used]
        rows = ""  # نمونهٔ واقعی کادر خودش راهنماست؛ ردیف توضیحی تکراری حذف شد
        # نمونهٔ واقعی قالب کادر (متن نمونهٔ رابط کاربر است، نه محتوای علمی)
        sample_texts = {
            "key": "نمونهٔ کادر: جملهٔ محوری بخش این‌جا برجسته می‌شود.",
            "clinical": "نمونهٔ کادر: کاربرد بالینی، فقط به نقل از خود منبع.",
            "warning": "نمونهٔ کادر: استثنا یا دام رایج این‌جا جدا می‌شود.",
            "conflict": "نمونهٔ کادر: اختلاف دو منبع، بدون دست‌کاری، کنار هم می‌ماند.",
            "definition": "نمونهٔ کادر: تعریف کوتاه اصطلاح این‌جا می‌آید.",
            "bridge": "نمونهٔ کادر: پیوند ساختار و کارکرد این‌جا نشان داده می‌شود.",
            "example": "نمونهٔ کادر: مثال موجود در خود محتوا این‌جا می‌نشیند.",
            "summary": "نمونهٔ کادر: جمع‌بندی همان بخش این‌جا می‌آید.",
            "exam": "نمونهٔ کادر: فقط با برچسب صریح خود منبع.",
        }
        samples = "".join(
            f'<aside class="callout callout--{k} guide-sample"><div class="callout__head">'
            f'{icon(k)}<span>{KIND_LABELS[k]}</span></div><p>{guide_texts[k]}</p></aside>'
            for k in KIND_ORDER if k in used and k in guide_texts)
        return f"""
<div class="guide avoid-break">
  <h2>چطور این جزوه را بخوانیم؟</h2>
  <p>کنار هر مطلب، برچسب <span class="src"><b>منبع:</b> جزوهٔ درس، ص ۹</span> می‌بینید؛ یعنی آن
  جمله دقیقاً از کجای جزوهٔ درس، اسنل یا گری آمده است. اصطلاح‌ها در نخستین ورودشان به صورت
  <span class="term">فارسی <bdi class="en">(English)</bdi></span> می‌آیند. کادرها هم هر کدام معنای ثابتی دارند:</p>
  <div class="guide__samples">{samples}</div>
  {self._entity_legend()}
</div>"""

    def _entity_legend(self) -> str:
        """راهنمای رنگ ثابت مفاهیم: فقط موجودیت‌هایی که واقعاً در همین جلسه به کار رفته‌اند."""
        from .entities import _load as _ent_load, CONFIG_PATH as _ENT_PATH
        _by_name, by_id = _ent_load(str(_ENT_PATH))
        haystacks: list[str] = []
        for b in self.session.all_blocks():
            haystacks += [str(f) for f in b.text_fragments()]
            if b.type == "figure":
                for lb in b.data.get("labels", []) or []:
                    if isinstance(lb, dict):
                        haystacks += [str(lb.get("fa", "")), str(lb.get("en", ""))]
        hay = " ".join(haystacks)
        chips = []
        for eid, ent in by_id.items():
            names = list(ent.get("fa", [])) + list(ent.get("en", []))
            if not any(n and n in hay for n in names):
                continue
            fa = (ent.get("fa") or [""])[0]
            en = (ent.get("en") or [""])[0]
            en_html = f' · <bdi class="en">{escape(en)}</bdi>' if en else ""
            chips.append(f'<span class="chip chip--ent" style="--chip-ent:{ent["color"]}">'
                         f'<i class="edot"></i>{escape(fa)}{en_html}</span>')
        if not chips:
            return ""
        return ('<div class="guide__ents"><b>رنگ ثابت مفاهیم این جلسه:</b> '
                + "".join(chips) + "</div>")

    # -------------------------------------------------------------- مبحث
    def topic(self, t: Topic) -> str:
        terms = "".join(
            f'<span class="chip">{escape(term["fa"])}'
            + (f' · <bdi class="en">{escape(term["en"])}</bdi>' if term.get("en") else "")
            + "</span>"
            for term in t.key_terms)
        objs = "".join(f"<li>{inline(o)}</li>" for o in t.objectives)
        # نوار پیشرفت: جایگاه این مبحث در نقشهٔ جلسه (از دادهٔ خود جلسه؛ متن تازه‌ای نیست)
        smap = self.session.session_map or []
        strip = ""
        if smap:
            cells = []
            for m in smap:
                n = int(m["number"])
                st = "cur" if n == t.number else ("done" if n < t.number else "todo")
                cells.append(f'<span class="pstrip__c pstrip__c--{st}"><b>{fa_num(n)}</b>'
                             f'{escape(str(m["title"]))}</span>')
            strip = (f'<div class="pstrip" aria-hidden="true">{"".join(cells)}</div>')
        pre = "".join(f'<span class="chip chip--pre">{inline(p)}</span>' for p in t.prereq_required)
        pre_s = "".join(f'<span class="chip">{inline(p)}</span>' for p in t.prereq_suggested)
        head = f"""
<section class="topic" id="{escape(t.id)}">
  <div class="topic-head" data-bid="topichead:{escape(t.id)}">
    <div class="topic-head__row">
      <div class="topic-num">مبحث<b>{fa_num(t.number)}</b></div>
      <h2>{escape(t.title)}</h2>
      <span class="topic-head__pages">جزوهٔ مادر: ص {escape(t.mother_pages)}</span>
    </div>{strip}
    <div class="topic-card">
      <p class="why"><b>چرا مهم است؟</b> {inline(t.why)}</p>
      <div class="topic-card__grid">
        <div><h3>در این مبحث یاد می‌گیرید:</h3><ul class="objlist">{objs}</ul></div>
        <div><h3>پیش‌نیاز ضروری</h3><div class="chips">{pre}</div>
             <h3 style="margin-top:4pt">پیش‌نیاز پیشنهادی</h3><div class="chips">{pre_s}</div></div>
      </div>
      <div class="topic-card__foot">اصطلاحات کلیدی:
        <span class="chips" style="display:inline-flex">{terms}</span></div>
    </div>
  </div>"""
        body = self.render_blocks(t.blocks)
        return head + body + "</section>"

    # -------------------------------------------------------------- بلوک‌ها
    def block(self, b: Block) -> str:
        fn = getattr(self, f"b_{b.type}", None)
        if fn is None:  # pragma: no cover - اعتبارسنجی قبلاً جلوی آن را می‌گیرد
            return f"<!-- بلوک پشتیبانی‌نشده: {escape(b.type)} -->"
        return fn(b)

    def b_section(self, b: Block) -> str:
        lbl = self.plan.labels.get(b.id, "")
        sty = ' style="break-before:page"' if b.data.get("_break_before") else ""
        return (f'<div class="section" id="{escape(b.id)}" data-bid="{escape(b.id)}"{sty}>'
                f'<h3>{inline(b.data["title"])}</h3><span class="sno">{escape(lbl)}</span></div>')

    def b_paragraph(self, b: Block) -> str:
        return (f'<p class="body" data-bid="{escape(b.id)}">{inline(b.data["text"])}'
                f'{src_chips(b.sources, self.show_sources)}</p>')

    # ---------------------------------------------------------- مادهٔ پایانی
    def revision_map(self) -> str:
        """نقشهٔ جامع مرور: همهٔ گزاره‌های علمی جلسه، عین عبارت منبع، زیر بخش خودشان.

        سطح ۱ = ساختار (مبحث ← بخش + ارجاع صفحه)؛ سطح ۲ = جزئیات کامل هر بخش.
        چیزی خلاصه یا بازنویسی نمی‌شود؛ جزئیات درون تصویرها با ارجاع به خود شکل می‌آیند.
        """
        cfg = (self.plan.layout_cfg or {}).get("revision_map", {})
        if not cfg.get("enabled", True):
            return ""
        items = extract_items(self.session)
        if len(items) < 8:
            return ""
        # عنوان بخش‌ها و ترتیب سند
        sec_titles: dict[str, str] = {}
        for t in self.session.topics:
            sec_titles[t.id] = f"مبحث {fa_num(t.number)}: {t.title}"
            for b in t.blocks:
                if b.type == "section":
                    sec_titles[b.id] = str(b.data.get("title", ""))
        sec_titles["closing"] = "جمع‌بندی و مرور جلسه"
        order: list[str] = []
        by_sec: dict[str, list] = {}
        for it in items:
            if it.section_id not in by_sec:
                by_sec[it.section_id] = []
                order.append(it.section_id)
            by_sec[it.section_id].append(it)
        n_visual = sum(1 for it in items if it.kind == "figure_visual")
        n_real = len(items) - n_visual

        def item_html(it) -> str:
            if it.kind == "figure_visual":
                lbl = escape(self.plan.labels.get(it.block_id, "شکل"))
                pg = self.fig_pages.get(it.block_id)
                pg_txt = f"ص {fa_num(pg)}" if pg else "…"
                return (f'<div class="rev__it rev__it--visual">{icon_svg("microscope", 11)}'
                        f'<span><b>{lbl}:</b> جزئیات درون تصویر را سرِ خود شکل مرور کنید '
                        f'({pg_txt})</span></div>')
            if it.kind == "terminology":
                en = it.meta.get("en", "")
                col = entity_color(it.text) or entity_color(en)
                sty = f' style="--chip-ent:{col}"' if col else ""
                dot = '<i class="edot"></i>' if col else ""
                en_h = f' · <bdi class="en">{escape(en)}</bdi>' if en else ""
                return (f'<span class="chip rev__term{" chip--ent" if col else ""}"{sty}>'
                        f'{dot}{escape(it.text)}{en_h}</span>')
            pre = ""
            if it.meta.get("table_title"):
                pre = (f'<div class="rev__sub">{icon_svg("compare", 11)}'
                       f'{escape(it.meta["table_title"])}</div>')
            if it.meta.get("lane_title"):
                pre = (f'<div class="rev__sub">{icon_svg("process", 11)}'
                       f'{escape(it.meta["lane_title"])}</div>')
            if it.meta.get("title"):
                pre = f'<div class="rev__sub">{escape(it.meta["title"])}</div>'
            step = (f'<b class="rev__step">{fa_num(it.meta["step_no"])}</b>'
                    if it.kind == "process" and it.meta.get("step_no") else "")
            num = f'<span class="rev__num">{icon_svg("formula", 10)}</span>' if it.has_number else ""
            lang = ' dir="ltr" lang="en"' if it.meta.get("lang") == "en" else ""
            body = inline(it.text) if not lang else escape(it.text)
            return (f'{pre}<div class="rev__it rev__it--{it.kind}">{step}'
                    f'<span{lang}>{body}</span>{num}</div>')

        panels = []
        for sec in order:
            its = by_sec[sec]
            pg = self.toc_pages.get(sec)
            pg_txt = f'<span class="rev__pg">ص {fa_num(pg)}</span>' if pg else ""
            # اصطلاح‌ها پشت سر هم به‌صورت ردیف چیپ می‌آیند؛ بقیه خط‌به‌خط
            parts: list[str] = []
            term_buf: list[str] = []

            def flush_terms() -> None:
                if term_buf:
                    parts.append(f'<div class="rev__terms">{"".join(term_buf)}</div>')
                    term_buf.clear()

            for it in its:
                if it.kind == "terminology":
                    term_buf.append(item_html(it))
                else:
                    flush_terms()
                    parts.append(item_html(it))
            flush_terms()
            panels.append(
                f'<section class="rev__panel"><header class="rev__head">'
                f'<span>{escape(sec_titles.get(sec, ""))}</span>{pg_txt}</header>'
                f'<div class="rev__items">{"".join(parts)}</div></section>')
        legend = (
            f'<span class="rev__lg rev__lg--exception">استثنا</span>'
            f'<span class="rev__lg rev__lg--source_conflict">اختلاف منابع</span>'
            f'<span class="rev__lg">{icon_svg("formula", 10)} دارای عدد/مقدار</span>'
            f'<span class="rev__lg">{icon_svg("microscope", 10)} مرور سرِ شکل</span>')
        return (f'<div class="revmap"><h2>نقشهٔ جامع مرور</h2>'
                f'<p class="rev__intro">همهٔ {fa_num(n_real)} گزارهٔ علمی این جلسه — جمله‌به‌جمله و '
                f'ردیف‌به‌ردیف — با همان عبارت خود جزوه، زیر بخش مربوطشان کنار هم چیده شده‌اند؛ '
                f'چیزی خلاصه یا بازنویسی نشده است. شمارهٔ کنار هر بخش، صفحهٔ متن کامل آن است. '
                f'جزئیات درون خودِ تصویرها ({fa_num(n_visual)} شکل) در نقشه نمی‌آید و با '
                f'نشانهٔ میکروسکوپ به خود شکل ارجاع داده شده است.</p>'
                f'<div class="rev__legend">{legend}</div>'
                f'{"".join(panels)}</div>')

    def glossary(self) -> str:
        """واژه‌نامهٔ فارسی–انگلیسی: فقط معادل‌هایی که در خود جلسه آمده‌اند + صفحهٔ نخستین کاربرد."""
        terms: dict[str, dict[str, str]] = {}
        order: list[str] = []

        def add(fa: str, en: str, anchor: str) -> None:
            fa = str(fa).strip()
            if not fa or fa in terms:
                return
            terms[fa] = {"en": str(en or "").strip(), "anchor": anchor}
            order.append(fa)

        def scan(blocks: list[Block], anchor: str) -> None:
            for b in blocks:
                if b.type == "section":
                    anchor = b.id
                if b.type == "figure":
                    for lb in b.data.get("labels", []) or []:
                        if isinstance(lb, dict):
                            add(str(lb.get("fa", "")), str(lb.get("en", "")), anchor)
                for frag in b.text_fragments():
                    for m in re.finditer(r"\[\[term:(.+?)\|(.+?)\]\]", str(frag)):
                        add(m.group(1), m.group(2), anchor)

        for t in self.session.topics:
            for kt in t.key_terms:
                if isinstance(kt, dict):
                    add(str(kt.get("fa", "")), str(kt.get("en", "")), t.id)
            scan(t.blocks, t.id)
        scan(self.session.closing, self.session.topics[-1].id if self.session.topics else "")
        if len(order) < 4:
            return ""
        items = []
        for fa in order:
            en = terms[fa]["en"]
            pg = self.toc_pages.get(terms[fa]["anchor"])
            pg_txt = f"ص {fa_num(pg)}" if pg else "…"
            en_html = f' <bdi class="en">({escape(en)})</bdi>' if en else ""
            col = entity_color(fa) or entity_color(en)
            dot = f'<i class="edot" style="--ed:{col}"></i>' if col else ""
            items.append(f'<div class="gloss__it"><span class="gloss__fa">{dot}{escape(fa)}{en_html}</span>'
                         f'<span class="dots"></span><span class="gloss__pg">{pg_txt}</span></div>')
        return (f'<div class="glossary"><h2>واژه‌نامهٔ فارسی–انگلیسی همین جلسه</h2>'
                f'<p class="gloss__note">فقط اصطلاح‌هایی که در متن همین جلسه آمده‌اند؛ '
                f'شمارهٔ صفحه، نخستین کاربرد هر اصطلاح است.</p>'
                f'<div class="gloss__grid">{"".join(items)}</div></div>')

    def answer_key(self) -> str:
        """پاسخ‌نامهٔ خودآزمایی‌های سریع — پاسخ‌ها عین عبارت‌های متن جلسه‌اند."""
        if not self._qc_items:
            return ""
        rows = "".join(
            f'<div class="ak__it"><b>{fa_num(n)}.</b> {inline(a)}</div>'
            for n, a in self._qc_items)
        return (f'<div class="answerkey"><h2>پاسخ‌نامهٔ خودآزمایی سریع</h2>'
                f'<p class="gloss__note">اول خودتان پاسخ دهید، بعد با این صفحه چک کنید؛ '
                f'پاسخ درست، همان عبارتی است که در متن بخش آمده بود.</p>{rows}</div>')

    def colophon(self) -> str:
        """شناسنامهٔ نسخه — همهٔ سطرها از دادهٔ خود جلسه؛ نام/نشانی ساخته نمی‌شود."""
        s = self.session
        books: list[str] = []
        for b in s.all_blocks():
            for src in b.sources:
                if src.book and src.book not in books:
                    books.append(src.book)
        needs = s.draft  # وضعیت انتشار را خود سند اعلام می‌کند، نه حدس موتور
        topics_txt = "؛ ".join(f"مبحث {fa_num(t.number)}: {t.title}" for t in s.topics)
        rows = [
            ("درس و جلسه", f"{s.course} — جلسهٔ {fa_num(s.session_number)}: {s.title}"),
            ("مباحث این نسخه", topics_txt),
            ("نسخهٔ جزوه", s.version),
            ("منابع به‌کاررفته", "؛ ".join(books) if books else "—"),
            ("وضعیت انتشار",
             "پیش‌نویس (پایلوت موتور)" if needs else "نسخهٔ نهایی"),
            ("گزارش خطا",
             "اگر جایی خطا یا ناهماهنگی دیدید، شمارهٔ صفحه و عنوان بخش را یادداشت کنید و به تیم علمی برسانید."),
            ("یادداشت",
             "این جزوه ابزار کمکیِ مطالعه است و جایگزین منابع اصلی و نظر استاد نیست؛ "
             "مرجع نهایی هر مطلب، برچسب منبع کنار همان مطلب است."),
        ]
        rows_html = "".join(
            f'<div class="col__row"><b>{escape(k)}</b><span>{escape(v)}</span></div>'
            for k, v in rows)
        return (f'<div class="colophon"><h2>شناسنامهٔ این نسخه</h2>{rows_html}'
                f'<div class="col__brand">{escape(self.brand["fa"])} · '
                f'<bdi class="en">{escape(self.brand["en"])}</bdi></div></div>')

    # ---------------------------------------------------------- بلوک‌های یادگیری
    def b_tldr(self, b: Block) -> str:
        return f"""
<aside class="tldr" data-bid="{escape(b.id)}">
  <div class="tldr__head"><span class="tldr__tag">در یک نگاه</span></div>
  <p>{inline(b.data["text"])}</p>
  <div class="srcrow">{src_chips(b.sources, self.show_sources)}</div>
</aside>"""

    def b_quick_check(self, b: Block) -> str:
        items_html = []
        for it in b.data.get("items", []):
            n = len(self._qc_items) + 1
            self._qc_items.append((n, str(it.get("a", ""))))
            items_html.append(
                f'<div class="qc__it"><span class="qc__n">{fa_num(n)}</span>'
                f'<div class="qc__body"><p>{inline(str(it.get("q", "")))}</p>'
                f'<div class="qc__line"></div></div></div>')
        return f"""
<aside class="qcheck" data-bid="{escape(b.id)}">
  <div class="qcheck__head"><span class="qc__tag">خودآزمایی سریع</span>
  <span class="qc__hint">بدون نگاه‌کردن به متن پاسخ دهید؛ پاسخ‌نامه در پایان جلسه است.</span></div>
  {"".join(items_html)}
  <div class="srcrow">{src_chips(b.sources, self.show_sources)}</div>
</aside>"""

    def b_callout(self, b: Block) -> str:
        kind = b.data["kind"]
        return f"""
<aside class="callout callout--{kind}" data-bid="{escape(b.id)}">
  <div class="callout__head">{icon(kind)}<span>{inline(b.data["title"])}</span>
  <span class="kind">{KIND_LABELS.get(kind, kind)}</span></div>
  <p>{inline(b.data["text"])}</p>
  <div class="srcrow">{src_chips(b.sources, self.show_sources)}</div>
</aside>"""

    def _tbl_rows_html(self, d: dict, idxs: list[int]) -> str:
        first_col_head = bool(d.get("row_header"))
        rows = []
        for ri in idxs:
            cells = []
            for i, cell in enumerate(d["rows"][ri]):
                cls = ' class="rowh"' if (i == 0 and first_col_head) else ""
                cells.append(f"<td{cls}>{inline(str(cell))}</td>")
            rows.append(f"<tr>{''.join(cells)}</tr>")
        return "".join(rows)

    def b_table(self, b: Block) -> str:
        d = b.data
        label = escape(self.plan.labels.get(b.id, "جدول"))
        def _th(h):
            raw = re.sub(r"\[en:([^\]]+)\]", r"\1", str(h))
            raw = re.sub(r"\[\[term:(.+?)\|(.+?)\]\]", r"\1", raw).strip()
            cands = [raw, raw.split("(")[0].strip(),
                     raw.rstrip(")").split("(")[-1].strip()]
            col = next((c for c in (entity_color(c) for c in cands) if c), None)
            sty = f' style="--th-ent:{col}"' if col else ""
            cls = ' class="th-ent"' if col else ""
            return f"<th{cls}{sty}>{inline(h)}</th>"
        head = "".join(_th(h) for h in d["headers"])
        colgroup = ""
        if d.get("col_widths"):
            colgroup = "<colgroup>" + "".join(
                f'<col style="width:{float(w)}%">' for w in d["col_widths"]) + "</colgroup>"
        dense = " tbl--dense" if len(d.get("rows", [])) > 10 else ""
        # سبک متناسب با نقش جدول: مقایسه‌ای (۳ ستونه) یا مرجع راه‌راه (بلند)
        style_cls = str(d.get("style", ""))
        if not style_cls and len(d["headers"]) == 3:
            style_cls = "compare"
        elif not style_cls and len(d.get("rows", [])) > 6:
            style_cls = "zebra"
        dense += f" tbl--{style_cls}" if style_cls in ("compare", "zebra") else ""
        chunks = d.get("_chunks") or [list(range(len(d["rows"])))]
        parts = []
        for ci, idxs in enumerate(chunks):
            style = ""
            if ci == 0 and d.get("_break_before"):
                style = ' style="break-before:page"'
            elif ci > 0:
                style = ' style="break-before:page"'
            bid = f' data-bid="{escape(b.id)}"' if ci == 0 else ""
            if ci == 0:
                cap = (f'<div class="tblwrap__cap"><span class="tno">{label}</span>\n'
                       f'  <span class="tt">{inline(d["title"])}</span>'
                       f'{src_chips(b.sources, self.show_sources)}</div>')
            else:
                # ادامهٔ همان جدول: همان شماره و عنوان، بدون شمارهٔ مستقل تازه
                cap = (f'<div class="tblwrap__cap tblwrap__cap--cont"><span class="tno">{label}</span>\n'
                       f'  <span class="tt">ادامهٔ جدول — {inline(d["title"])}</span></div>')
            parts.append(f"""
<div class="tblwrap"{bid}{style}>
  {cap}
  <table class="tbl{dense}">{colgroup}<thead><tr>{head}</tr></thead><tbody>{self._tbl_rows_html(d, idxs)}</tbody></table>
</div>""")
        if d.get("takeaway"):
            parts.append(f'<p class="tbl__takeaway"><b>برداشت کلیدی:</b> '
                         f'{inline(str(d["takeaway"]))}</p>')
        return "".join(parts)

    def _caption_inner(self, b: Block) -> str:
        d = b.data
        labels = ""
        if d.get("labels"):
            def _lchip(l):
                col = entity_color(str(l.get("fa", ""))) or entity_color(str(l.get("en", "")))
                sty = f' style="--chip-ent:{col}"' if col else ""
                dot = '<i class="edot"></i>' if col else ""
                cls = " chip--ent" if col else ""
                return (f'<span class="chip{cls}"{sty}>{dot}{escape(str(l["fa"]))} · '
                        f'<bdi class="en">{escape(str(l["en"]))}</bdi></span>')
            labels = '<div class="fig__labels">' + "".join(_lchip(l) for l in d["labels"]) + "</div>"
        encap = (f'<div class="fig__encap">{escape(d["caption_en"])}</div>'
                 if d.get("caption_en") else "")
        srcs = " · ".join(s.label() for s in b.sources)
        return f"""
    <span class="fno">{escape(self.plan.labels.get(b.id, "شکل"))}</span>
    <span class="ft">{inline(d["title_fa"])}</span>
    <span class="fsrc">{escape(srcs)}</span>
    <p class="fexpl">{inline(d["explain_fa"])}</p>
    {encap}{labels}"""

    def _figure_frame(self, b: Block, with_bid: bool = True, caption: bool = True) -> str:
        d = b.data
        sidecap = ' fig--sidecap' if d.get("_layout") == "sidecap" else ""
        pct = d.get("_width_pct", 100)
        img_w = f' style="width:{pct}%"' if pct < 100 else ""
        cap = f'<figcaption class="fig__cap">{self._caption_inner(b)}</figcaption>' if caption else ""
        sty = ' style="break-before:page"' if d.get("_break_before") and with_bid else ""
        return f"""
<figure class="fig{sidecap}"{' data-bid="' + escape(b.id) + '"' if with_bid else ''}{sty}><div class="fig__frame">
  <img src="{self.assets_uri}{escape(str(d.get("_opt_file", d["file"])))}" alt="{escape(str(d["title_fa"]))}"{img_w}>
  {cap}
</div></figure>"""

    def b_figure(self, b: Block) -> str:
        if b.data.get("_layout") == "side" and b.data.get("side_text"):
            # کپشن زیر کل گرید تمام‌عرض می‌نشیند (نه زیر تصویر) تا ارتفاع بلوک باد نکند
            sty = ' style="break-before:page"' if b.data.get("_break_before") else ""
            return (f'<div class="figside" data-bid="{escape(b.id)}"{sty}>'
                    f'<div class="figside__grid">{self._figure_frame(b, with_bid=False, caption=False)}'
                    f'<div class="figside__txt"><p class="body">{inline(b.data["side_text"])}'
                    f'{src_chips(b.sources, self.show_sources)}</p></div></div>'
                    f'<div class="fig__cap fig__cap--below">{self._caption_inner(b)}</div></div>')
        return self._figure_frame(b)

    def _steps(self, steps: list) -> str:
        items = []
        for i, st in enumerate(steps, 1):
            if isinstance(st, dict):
                txt = f'<b class="st">{inline(st.get("head", ""))}:</b> {inline(st.get("text", ""))}'
            else:
                txt = inline(str(st))
            items.append(f'<li class="step"><span class="n">{fa_num(i)}</span>{txt}</li>')
        return f'<ol class="steps">{"".join(items)}</ol>'

    def _steps_strip(self, steps: list) -> str:
        cells = []
        for i, st in enumerate(steps, 1):
            if isinstance(st, dict):
                txt = (f'<b class="st">{inline(st.get("head", ""))}</b>'
                       + (f'<span>{inline(st.get("text", ""))}</span>' if st.get("text") else ""))
            else:
                txt = inline(str(st))
            cells.append(f'<li class="sstep"><span class="n">{fa_num(i)}</span>{txt}</li>')
        return f'<ol class="ssteps">{"".join(cells)}</ol>'

    def b_process(self, b: Block) -> str:
        strip = b.data.get("_variant") == "strip"
        body = self._steps_strip(b.data["steps"]) if strip else self._steps(b.data["steps"])
        return f"""
<div class="process{' process--strip' if strip else ''}" data-bid="{escape(b.id)}">
  <div class="process__title"><span class="pno">{escape(self.plan.labels.get(b.id, "مسیر"))}</span>
  <span>{inline(b.data["title"])}</span>{src_chips(b.sources, self.show_sources)}</div>
  {body}
</div>"""

    def b_dual_process(self, b: Block) -> str:
        d = b.data
        fwd, bwd = d["forward"], d["backward"]
        cf = entity_color("Anterograde") or "#0284C7"
        cb = entity_color("Retrograde") or "#EA580C"
        # برچسب‌های نمودار فقط از متن خود بلوک: عنوان دو مسیر + سوما/پایانه اگر در داده هست
        titles = str(fwd.get("title", "")) + str(bwd.get("title", ""))
        node_r = "سوما" if "سوما" in titles else ""
        node_l = "پایانه" if "پایانه" in titles else ""
        rail_svg = f"""
<svg class="dualrail" viewBox="0 0 182 31" dir="ltr" role="img"
     aria-label="{escape(str(d["title"]))}">
  <circle cx="169" cy="13" r="6.2" fill="#0B3050"/>
  <circle cx="167.4" cy="11.4" r="1.7" fill="#FFFFFF" opacity=".85"/>
  <g fill="#0B7A6E"><circle cx="9" cy="8.5" r="2.6"/><circle cx="7" cy="14.5" r="2.6"/>
  <circle cx="10" cy="20" r="2.6"/></g>
  <g stroke="#9FB4C6" stroke-width=".55">
    <line x1="16" y1="11.6" x2="162" y2="11.6"/><line x1="16" y1="14.4" x2="162" y2="14.4"/></g>
  <line x1="158" y1="7.6" x2="24" y2="7.6" stroke="{cf}" stroke-width="1.15"/>
  <polygon points="24,7.6 29.5,5.4 29.5,9.8" fill="{cf}"/>
  <circle cx="95" cy="7.6" r="2.1" fill="{cf}"/>
  <line x1="24" y1="18.4" x2="158" y2="18.4" stroke="{cb}" stroke-width="1.15"/>
  <polygon points="158,18.4 152.5,16.2 152.5,20.6" fill="{cb}"/>
  <circle cx="80" cy="18.4" r="2.1" fill="{cb}"/>
  <text x="91" y="4.6" font-size="3.1" font-weight="700" fill="{cf}" text-anchor="middle"
        font-family="Vazirmatn">{escape(str(fwd.get("title", "")))}</text>
  <text x="91" y="26.6" font-size="3.1" font-weight="700" fill="{cb}" text-anchor="middle"
        font-family="Vazirmatn">{escape(str(bwd.get("title", "")))}</text>
  {f'<text x="169" y="23.6" font-size="2.6" fill="#0B3050" text-anchor="middle" font-family="Vazirmatn">{node_r}</text>' if node_r else ""}
  {f'<text x="9" y="26.6" font-size="2.6" fill="#0B7A6E" text-anchor="middle" font-family="Vazirmatn">{node_l}</text>' if node_l else ""}
</svg>"""
        return f"""
<div class="dual" data-bid="{escape(b.id)}">
  <div class="process__title"><span class="pno">{escape(self.plan.labels.get(b.id, "مسیر"))}</span>
  <span>{inline(d["title"])}</span>{src_chips(b.sources, self.show_sources)}</div>
  {rail_svg}
  <div class="dual__lanes">
    <div class="lane lane--fwd"><div class="lane__head" style="--lane:{cf}">◀ {inline(fwd["title"])}</div>{self._steps(fwd["steps"])}</div>
    <div class="lane lane--bwd"><div class="lane__head" style="--lane:{cb}">{inline(bwd["title"])} ▶</div>{self._steps(bwd["steps"])}</div>
  </div>
  <div class="dual__rail">{inline(d.get("rail_note", ""))}</div>
</div>"""

    def b_tree(self, b: Block) -> str:
        return f"""
<figure class="tree" data-bid="{escape(b.id)}">
  <div class="process__title"><span class="pno">نمودار</span>
  <span>{inline(b.data["title"])}</span>{src_chips(b.sources, self.show_sources)}</div>
  {tree_svg(b.data["root"], color_for=lambda n: _tree_color(n))}
</figure>"""

    def b_checklist(self, b: Block) -> str:
        items = "".join(f"<li>{inline(i)}</li>" for i in b.data["items"])
        return (f'<div class="checklist" data-bid="{escape(b.id)}"><h3>{inline(b.data["title"])}</h3>'
                f'<ul>{items}</ul>{src_chips(b.sources, self.show_sources)}</div>')

    def b_summary_box(self, b: Block) -> str:
        return (f'<div class="summarybox" data-bid="{escape(b.id)}"><h3>{inline(b.data["title"])}</h3>'
                f'<p>{inline(b.data["text"])}</p>{src_chips(b.sources, self.show_sources)}</div>')

    def b_team_note(self, b: Block) -> str:
        return (f'<div class="teamnote" data-bid="{escape(b.id)}"><span class="tn-t">یادداشت عضو تیم — '
                f'{inline(b.data["title"])}</span></div>')
