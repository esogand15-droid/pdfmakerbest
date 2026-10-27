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
from .model import Block, Session, Source, Topic
from .planner import Plan, fa_num

# آیکون‌های مینیمال اینلاین برای کادرها (stroke=currentColor)
_ICONS = {
    "key": '<path d="M7 1 L13 7 L7 13 L1 7 Z" fill="currentColor"/>',
    "clinical": '<circle cx="7" cy="7" r="6" fill="none" stroke="currentColor" stroke-width="1.6"/>'
                '<path d="M7 4 v6 M4 7 h6" stroke="currentColor" stroke-width="1.8"/>',
    "warning": '<path d="M7 1.5 L13.5 12.5 H0.5 Z" fill="none" stroke="currentColor" stroke-width="1.6"/>'
               '<path d="M7 5.5 v3.4" stroke="currentColor" stroke-width="1.8"/><circle cx="7" cy="11" r="1" fill="currentColor"/>',
    "bridge": '<path d="M1 5 h9 M7.5 2.5 L10.5 5 L7.5 7.5 M13 9 H4 M6.5 6.5 L3.5 9 L6.5 11.5" fill="none" stroke="currentColor" stroke-width="1.5"/>',
    "conflict": '<path d="M7 13 V7 M7 7 C7 4 3 4 3 1.8 M7 7 C7 4 11 4 11 1.8" fill="none" stroke="currentColor" stroke-width="1.6"/>'
                '<circle cx="3" cy="1.8" r="1.2" fill="currentColor"/><circle cx="11" cy="1.8" r="1.2" fill="currentColor"/>',
    "exam": '<circle cx="7" cy="7" r="5.6" fill="none" stroke="currentColor" stroke-width="1.5"/>'
            '<circle cx="7" cy="7" r="2.8" fill="none" stroke="currentColor" stroke-width="1.5"/>'
            '<circle cx="7" cy="7" r="0.9" fill="currentColor"/>',
    "definition": '<path d="M7 3 C5.8 1.9 3.8 1.6 1.8 1.9 V11.6 C3.8 11.3 5.8 11.7 7 12.7 C8.2 11.7 10.2 11.3 12.2 11.6 V1.9 C10.2 1.6 8.2 1.9 7 3 Z" fill="none" stroke="currentColor" stroke-width="1.4"/>'
                  '<path d="M7 3 V12.7" stroke="currentColor" stroke-width="1.2"/>',
    "example": '<circle cx="6" cy="6" r="4.4" fill="none" stroke="currentColor" stroke-width="1.5"/>'
               '<path d="M9.3 9.3 L13 13" stroke="currentColor" stroke-width="1.7"/>'
               '<circle cx="6" cy="6" r="1.5" fill="currentColor"/>',
    "summary": '<path d="M1.5 3.5 h11 M1.5 7 h11 M1.5 10.5 h7" stroke="currentColor" stroke-width="1.7"/>',
}
KIND_LABELS = {
    "key": "نکتهٔ کلیدی", "clinical": "نکتهٔ بالینی", "warning": "استثنا / هشدار",
    "bridge": "از ساختار تا عملکرد", "conflict": "اختلاف منابع", "exam": "نکتهٔ امتحانی",
    "definition": "تعریف اصطلاح", "example": "مثال آموزشی", "summary": "جمع‌بندی سریع",
}
# ترتیب استاندارد نمایش راهنمای کادرها
KIND_ORDER = ["key", "clinical", "warning", "bridge", "conflict", "exam",
              "definition", "example", "summary"]


def icon(kind: str) -> str:
    return (f'<svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">'
            f'{_ICONS.get(kind, _ICONS["key"])}</svg>')


def inline(text: str) -> str:
    """رندر نشانه‌گذاری درون‌متنی با ایزوله‌سازی bidi."""
    s = escape(str(text))
    s = re.sub(r"\[\[term:(.+?)\|(.+?)\]\]",
               r'<span class="term">\1 <bdi class="en">(\2)</bdi></span>', s)
    s = re.sub(r"\[en:([^\]]+)\]", r'<bdi class="en">\1</bdi>', s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    return s


def src_chips(sources: list[Source], show: bool = True) -> str:
    if not show or not sources:
        return ""
    return " ".join(f'<span class="src"><b>منبع:</b> {escape(s.label())}</span>' for s in sources)


class Typesetter:
    def __init__(self, plan: Plan, *, show_sources: bool = True,
                 toc_pages: dict[str, int] | None = None,
                 assets_uri: str = "", brand: dict | None = None) -> None:
        self.plan = plan
        self.session = plan.session
        self.show_sources = show_sources
        self.toc_pages = toc_pages or {}
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
            f'<style>{css}</style></head><body>{"".join(body)}</body></html>'
        )

    def toc_page(self) -> str:
        """صفحهٔ اختصاصی فهرست: نقشهٔ جلسه + فهرست پیونددار + نوار راهنمای خواندن."""
        return (f'<div class="tocpage">{self.session_map()}{self.toc()}'
                f'{self.reading_guide()}</div>')

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
        items = []
        for lvl, text, anchor in self.plan.headings:
            pg = self.toc_pages.get(anchor)
            items.append(
                f'<li class="lvl{lvl}"><a href="#{escape(anchor)}"><span>{escape(text)}</span>'
                f'<span class="dots"></span>'
                f'<span class="pno">{fa_num(pg) if pg else "…"}</span></a></li>')
        return (f'<nav class="toc" style="--toc-lh:{lh}"><h2>فهرست مطالب</h2>'
                f'<ol>{"".join(items)}</ol></nav>')

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
        }
        # راهنما فقط کادرهایی را توضیح می‌دهد که واقعاً در همین جلسه به کار رفته‌اند
        used = {b.data.get("kind") for b in self.session.all_blocks() if b.type == "callout"}
        items = [(k, KIND_LABELS[k], guide_texts[k]) for k in KIND_ORDER if k in used]
        rows = "".join(
            f'<div class="guide__item guide__item--{k}">{icon(k)}<span><b>{t}:</b> {d}</span></div>'
            for k, t, d in items)
        return f"""
<div class="guide avoid-break">
  <h2>چطور این جزوه را بخوانیم؟</h2>
  <p>کنار هر مطلب، برچسب <span class="src"><b>منبع:</b> جزوهٔ درس، ص ۹</span> می‌بینید؛ یعنی آن
  جمله دقیقاً از کجای جزوهٔ درس، اسنل یا گری آمده است. اصطلاح‌ها در نخستین ورودشان به صورت
  <span class="term">فارسی <bdi class="en">(English)</bdi></span> می‌آیند. کادرها هم هر کدام معنای ثابتی دارند:</p>
  <div class="guide__grid">{rows}</div>
</div>"""

    # -------------------------------------------------------------- مبحث
    def topic(self, t: Topic) -> str:
        terms = "".join(
            f'<span class="chip">{escape(term["fa"])}'
            + (f' · <bdi class="en">{escape(term["en"])}</bdi>' if term.get("en") else "")
            + "</span>"
            for term in t.key_terms)
        objs = "".join(f"<li>{inline(o)}</li>" for o in t.objectives)
        pre = "".join(f'<span class="chip chip--pre">{inline(p)}</span>' for p in t.prereq_required)
        pre_s = "".join(f'<span class="chip">{inline(p)}</span>' for p in t.prereq_suggested)
        head = f"""
<section class="topic" id="{escape(t.id)}">
  <div class="topic-head" data-bid="topichead:{escape(t.id)}">
    <div class="topic-head__row">
      <div class="topic-num">مبحث<b>{fa_num(t.number)}</b></div>
      <h2>{escape(t.title)}</h2>
      <span class="topic-head__pages">جزوهٔ مادر: ص {escape(t.mother_pages)}</span>
    </div>
    <div class="topic-card">
      <p class="why"><b>چرا مهم است؟</b> {inline(t.why)}</p>
      <div class="topic-card__grid">
        <div><h3>پس از این مبحث می‌توانید:</h3><ul>{objs}</ul></div>
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
        head = "".join(f"<th>{inline(h)}</th>" for h in d["headers"])
        colgroup = ""
        if d.get("col_widths"):
            colgroup = "<colgroup>" + "".join(
                f'<col style="width:{float(w)}%">' for w in d["col_widths"]) + "</colgroup>"
        dense = " tbl--dense" if len(d.get("rows", [])) > 10 else ""
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
        return "".join(parts)

    def _caption_inner(self, b: Block) -> str:
        d = b.data
        labels = ""
        if d.get("labels"):
            labels = '<div class="fig__labels">' + "".join(
                f'<span class="chip">{escape(l["fa"])} · <bdi class="en">{escape(l["en"])}</bdi></span>'
                for l in d["labels"]) + "</div>"
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
        return f"""
<div class="dual" data-bid="{escape(b.id)}">
  <div class="process__title"><span class="pno">{escape(self.plan.labels.get(b.id, "مسیر"))}</span>
  <span>{inline(d["title"])}</span>{src_chips(b.sources, self.show_sources)}</div>
  <div class="dual__lanes">
    <div class="lane lane--fwd"><div class="lane__head">◀ {inline(fwd["title"])}</div>{self._steps(fwd["steps"])}</div>
    <div class="lane lane--bwd"><div class="lane__head">{inline(bwd["title"])} ▶</div>{self._steps(bwd["steps"])}</div>
  </div>
  <div class="dual__rail">{inline(d.get("rail_note", ""))}</div>
</div>"""

    def b_tree(self, b: Block) -> str:
        return f"""
<figure class="tree" data-bid="{escape(b.id)}">
  <div class="process__title"><span class="pno">نمودار</span>
  <span>{inline(b.data["title"])}</span>{src_chips(b.sources, self.show_sources)}</div>
  {tree_svg(b.data["root"])}
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
