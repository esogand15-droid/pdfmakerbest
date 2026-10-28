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

from .diagrams import PAGE_STYLE as TREE_PAGE_STYLE, measure_tree, session_tree, tree_svg
from .palette import chapter_vars, hex_of, session_style, session_vars
from .icons import (CALLOUT_ICONS, FAMILY_LABELS, ICON_FAMILY, family_of_kind,
                    icon_svg)
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


def icon_color_css() -> str:
    """رنگ هر آیکون = رنگ deep خانواده‌اش (تولید خودکار از نگاشت مرکزی)."""
    rules = []
    for name, fam in sorted(ICON_FAMILY.items()):
        rules.append(f".ic--{name}{{color:var(--{fam}-deep)}}")
    return "".join(rules)


def icon_badge(name: str, size: float = 12) -> str:
    """آیکون داخل نشان دایره‌ای خانواده (پس‌زمینهٔ نرم + خط رنگی خانواده)."""
    from .icons import family_of_icon
    return f'<span class="icb fam {family_of_icon(name)}">{icon_svg(name, size)}</span>'


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
    # پیکان‌های متنی ←/→ در هیچ‌کدام از فونت‌های خودمیزبان نیستند و کرومیوم
    # بی‌صدا DejaVu جایگزین می‌کند؛ مثل راند ۱۴ با SVG درون‌خطی رسم می‌شوند.
    def _arr(left: bool) -> str:
        pts = "1.5,5 6,1 6,3.4 14,3.4 14,6.6 6,6.6 6,9" if left else \
              "14.5,5 10,1 10,3.4 2,3.4 2,6.6 10,6.6 10,9"
        return (f'<svg viewBox="0 0 16 10" aria-hidden="true" '
                f'style="width:1.05em;height:.66em;vertical-align:-.08em">'
                f'<polygon points="{pts}" fill="currentColor"/></svg>')
    s = s.replace("←", _arr(True)).replace("→", _arr(False))
    return s



def src_chips(sources: list[Source], show: bool = True) -> str:
    if not show or not sources:
        return ""
    return " ".join(
        f'<span class="src">{icon_svg("reference", 9)}<b>منبع:</b> {escape(s.label())}</span>'
        for s in sources)


class Typesetter:
    def __init__(self, plan: Plan, *, show_sources: bool = True,
                 toc_pages: dict[str, int] | None = None,
                 fig_pages: dict[str, int] | None = None,
                 print_theme: bool = False, bw_theme: bool = False,
                 assets_uri: str = "", brand: dict | None = None) -> None:
        self.plan = plan
        self.session = plan.session
        self.show_sources = show_sources
        self.toc_pages = toc_pages or {}
        self.fig_pages = fig_pages or {}
        self._qc_items: list[tuple[int, str]] = []  # (شماره، پاسخ) برای پاسخ‌نامهٔ پایانی
        self.print_theme = print_theme
        self.bw_theme = bw_theme
        self.assets_uri = assets_uri  # پیشوند file:// برای مسیر دارایی‌ها
        self.brand = brand or {"fa": "هامزیار", "en": "HumsYar"}

    # -------------------------------------------------------------- اجزای سند
    def document(self, css: str, theme: str = "a") -> str:
        s = self.session
        body = [self.toc_page()]
        for topic in s.topics:
            body.append(self.topic(topic))
        body.append(self.revision_map())
        tree_html = self.tree_page()
        body.append(tree_html)
        # درخت‌های تألیفیِ پایانی در صفحهٔ درخت مصرف شده‌اند؛ این‌جا فقط جمع‌بندی‌ها می‌آیند
        closing_blocks = [b for b in s.closing
                          if not (tree_html and b.type == "tree")]
        if closing_blocks:
            body.append(
                '<div class="section closing-head"><h2 class="h-ic">'
                + icon_svg("summary", 15) + 'جمع‌بندی و مرور جلسه</h2></div>')
            body.append(self.render_blocks(closing_blocks))
            body.append(self.sources_list())
        body.append(self.answer_key())
        body.append(self.glossary())
        favicon = (f'<link rel="icon" type="image/png" href="{self.brand["favicon_uri"]}">'
                   if self.brand.get("favicon_uri") else "")
        _paper_white = (self.print_theme or self.bw_theme
                        or ((self.plan.layout_cfg or {}).get("color_system", {})
                            or {}).get("paper") == "white")
        _paper_css = "@page{background:#FFFFFF}:root{--paper:#FFFFFF}" if _paper_white else ""
        return (
            '<!DOCTYPE html><html lang="fa" dir="rtl"'
            + (f' data-theme="{theme}"' if theme != "a" else "") + '><head><meta charset="utf-8">'
            f'<title>{escape(s.course)} — جلسهٔ {fa_num(s.session_number)}: {escape(s.title)}</title>{favicon}'
            f'<style>{css}{icon_color_css()}{_paper_css}</style></head>'
            f'<body style="{session_style(s.session_number)}" class="{"print-theme" if self.print_theme else ""}{" bw-theme" if self.bw_theme else ""}">{"".join(body)}</body></html>'
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
        for idx, m in enumerate(s.session_map):
            n = int(m["number"])
            pg = self.toc_pages.get(str(m.get("id", "")))
            pg_txt = f'ص {fa_num(pg)}' if pg else str(m.get("tag", ""))
            items.append(
                f'<li class="{"in" if n in included else ""}" '
                f'style="--topic-c:{session_vars(s.session_number)["--session-header"]}">'
                f'<span class="n">{fa_num(n)}</span><span>{escape(str(m["title"]))}</span>'
                f'<span class="pg">{escape(pg_txt)}</span></li>')
        return f'<nav class="session-map"><h2>نقشهٔ جلسه</h2><ol>{"".join(items)}</ol></nav>'

    def toc(self) -> str:
        n = len(self.plan.headings)
        lh = 2.35 if n <= 12 else (2.05 if n <= 20 else 1.8)
        if any(b.type in ("figure", "table") for b in self.session.all_blocks()):
            lh = max(1.42, lh - 0.62)  # جای فهرست‌ها و راهنمای خانوادگی نشانه‌ها در همان صفحه
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
        """راهنمای نشانه‌ها: شش کارت خانوادهٔ معنایی؛ رنگ نشانه از خانواده‌اش
        می‌آید (نقش)، و کنار هر خانواده نمونهٔ کوچک همان کادر دیده می‌شود."""
        seen: dict[str, str] = {}

        def add(icon_name: str, label: str) -> None:
            if icon_name not in seen:
                seen[icon_name] = label

        for k in KIND_ORDER:  # معنای ثابت کادرهای آموزشی در کل جزوه
            add(CALLOUT_ICONS.get(k, "note"), KIND_LABELS[k])
        for name, label in (("target", "هدف‌های یادگیری"),
                            ("terminology", "اصطلاحات کلیدی"), ("process", "فرایند گام‌به‌گام"),
                            ("compare", "مقایسه"), ("branch", "نمودار درختی/طبقه‌بندی"),
                            ("compass", "مرور فوق‌فشرده"), ("microscope", "جزئیات درون شکل"),
                            ("book", "واژه‌نامه"), ("reference", "منبع مطلب")):
            add(name, label)

        from .icons import family_of_icon
        groups: dict[str, list[tuple[str, str]]] = {}
        for n, l in seen.items():
            fam = family_of_icon(n)
            key = "fam4" if fam.startswith("fam4") else fam
            groups.setdefault(key, []).append((n, l))
        fam_order = ["fam1", "fam2", "fam3", "fam4", "fam5", "fam6"]
        cards = []
        for key in fam_order:
            entries = groups.get(key, [])
            if not entries:
                continue
            items = "".join(
                f'<span class="fguide__it">{icon_badge(n, 11)}<span>{escape(l)}</span></span>'
                for n, l in entries)
            sample = ""  # نوار نمونه حذف شد (راند ۱۳): کارت تمیز با ارتفاع برابر
            cards.append(
                f'<div class="fguide__card fcard--{key}">'
                f'<div class="fguide__h"><span class="fguide__dot"></span>{escape(FAMILY_LABELS[key])}</div>'
                f'<div class="fguide__items">{items}</div>{sample}</div>')
        return f"""
<div class="guide avoid-break">
  <h2>چطور این جزوه را بخوانیم؟</h2>
  <p class="guide__line">کنار هر مطلب، منبعش آمده است: <span class="src">{icon_svg("reference", 9)}<b>منبع:</b> جزوهٔ درس، ص ۹</span>
  و اصطلاح‌ها در نخستین ورود با معادل <bdi class="en">(English)</bdi> می‌آیند. رنگ هر نشانه از خانواده‌اش می‌آید و در کل جزوه ثابت است؛ رنگ جلسه از شمارهٔ جلسه می‌آید و روی تب کناری و سربرگ جدول‌ها دیده می‌شود.</p>
  <div class="fguide">{"".join(cards)}</div>
</div>"""

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
            for idx, m in enumerate(smap):
                n = int(m["number"])
                st = "cur" if n == t.number else ("done" if n < t.number else "todo")
                cells.append(f'<span class="pstrip__c pstrip__c--{st}">'
                             f'<b>{fa_num(n)}</b>{escape(str(m["title"]))}</span>')
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
      <p class="why"><b class="h-ic">{icon_svg('bridge', 12)}چرا مهم است؟</b> {inline(t.why)}</p>
      <div class="topic-card__grid">
        <div><h3 class="h-ic tc-obj">{icon_svg('target', 12)}در این مبحث یاد می‌گیرید:</h3><ul class="objlist">{objs}</ul></div>
        <div><h3 class="h-ic tc-pre">{icon_svg('compass', 12)}پیش‌نیاز ضروری</h3><div class="chips">{pre}</div>
             <h3 class="tc-pre" style="margin-top:3pt">پیش‌نیاز پیشنهادی</h3><div class="chips">{pre_s}</div></div>
      </div>
      <div class="topic-card__foot"><span class="h-ic tc-term">{icon_svg('terminology', 12)}اصطلاحات کلیدی:</span>
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
    def tree_page(self) -> str:
        """صفحهٔ اختصاصی نمودار درختی جامع جلسه — ساخته‌شدهٔ مکانیکی از ساختار محتوا.

        ریشه ← مبحث ← بخش ← طبقه‌بندی‌ها/جدول‌ها/فرایندها + درخت(های) تألیفیِ
        خود محتوا (با attach_to). هیچ برچسبی ساخته یا بازنویسی نمی‌شود.
        """
        cfg = (self.plan.layout_cfg or {}).get("tree_page", {})
        if not cfg.get("enabled", True):
            return ""
        root = session_tree(self.session,
                            root_label=f"جلسهٔ {fa_num(self.session.session_number)}")
        if len(root.get("children", [])) < 1:
            return ""
        # ابعاد صریح چاپی (pt): عنوان + درخت + نوار اصطلاحات باید با هم در صفحهٔ
        # اختصاصی جا شوند و برچسب‌ها هرگز زیر کف خوانایی نروند (یادداشت ۸٫۶ واحد
        # ← مقیاس ≥۰٫۸۲). اگر درخت کامل در یک صفحه با این مقیاس جا نشد، شاخه‌های
        # ریشه (مبحث‌ها) دست‌نخورده میان چند صفحهٔ اختصاصی پیاپی پخش می‌شوند —
        # هیچ شاخه‌ای حذف یا ریز نمی‌شود.
        def _scale_of(sub: dict) -> float:
            tw, th = measure_tree(sub, TREE_PAGE_STYLE)
            return min(516 / tw, 540 / th, 1.0)

        min_scale = 0.82
        groups: list[list[dict]] = []
        cur: list[dict] = []
        for child in root.get("children", []):
            trial = {**root, "children": cur + [child]}
            if cur and _scale_of(trial) < min_scale:
                groups.append(cur)
                cur = [child]
            else:
                cur.append(child)
        if cur:
            groups.append(cur)

        def _svg_for(children: list[dict]) -> str:
            sub = {**root, "children": children}
            out = tree_svg(sub, style=TREE_PAGE_STYLE)
            tw, th = measure_tree(sub, TREE_PAGE_STYLE)
            sc = _scale_of(sub)
            return out.replace('<svg class="tree-svg"',
                               f'<svg class="tree-svg" width="{tw * sc:.0f}pt" '
                               f'height="{th * sc:.0f}pt"', 1)
        # نوار یکپارچهٔ اصطلاحات کلیدی جلسه، زیر درخت (فهرست‌های خود مباحث)
        parts = []
        for t in self.session.topics:
            if not t.key_terms:
                continue
            chips = "".join(
                f'<span class="chip">{escape(str(kt.get("fa", "")))}'
                + (f' · <bdi class="en">{escape(str(kt["en"]))}</bdi>' if kt.get("en") else "")
                + "</span>"
                for kt in t.key_terms)
            parts.append(f'<b>مبحث {fa_num(t.number)}:</b> {chips}')
        srcs = ""
        tree_blocks = [b for b in self.session.closing if b.type == "tree"]
        if tree_blocks and self.show_sources:
            srcs = " " + "".join(src_chips(b.sources, True) for b in tree_blocks)
        term_rows = (f'<div class="treepage__terms"><b>اصطلاحات کلیدی جلسه —</b> '
                     + " ".join(parts) + srcs + "</div>") if parts else ""
        n_pages = len(groups)
        out_pages = []
        for gi, children in enumerate(groups):
            suffix = (f" (بخش {fa_num(gi + 1)} از {fa_num(n_pages)})"
                      if n_pages > 1 else "")
            span = "یک صفحه" if n_pages == 1 else f"{fa_num(n_pages)} صفحهٔ پیاپی"
            out_pages.append(f"""
<div class="treepage">
  <h2 class="h-ic">{icon_svg("branch", 15)}نمودار درختی جامع جلسه{suffix}</h2>
  <p class="treepage__sub">اسکلت طبقه‌بندی همین جلسه در {span}؛ برای مرور سریع. جزئیات کامل هر شاخه در متن آمده و جمع‌بندی دوصفحه‌ای پایان جزوه آن‌ها را یکجا مرور می‌کند.</p>
  {_svg_for(children)}
  {term_rows if gi == n_pages - 1 else ""}
</div>""")
        return "".join(out_pages)

    def revision_map(self) -> str:
        """نقشهٔ جامع مرور: همهٔ گزاره‌های علمی جلسه، عین عبارت منبع، زیر بخش خودشان.

        سطح ۱ = ساختار (مبحث ← بخش + ارجاع صفحه)؛ سطح ۲ = جزئیات کامل هر بخش.
        چیزی خلاصه یا بازنویسی نمی‌شود؛ جزئیات درون تصویرها با ارجاع به خود شکل می‌آیند.
        """
        cfg = (self.plan.layout_cfg or {}).get("revision_map", {})
        if not cfg.get("enabled", False):  # راند ۱۴: پیش‌فرض خاموش (جایگزین: برگهٔ فوق‌فشرده)
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
                en_h = f' · <bdi class="en">{escape(en)}</bdi>' if en else ""
                return f'<span class="chip rev__term">{escape(it.text)}{en_h}</span>'
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
        return (f'<div class="revmap"><h2 class="h-ic">{icon_svg("compass", 15)}نقشهٔ جامع مرور</h2>'
                f'<p class="rev__intro">همهٔ {fa_num(n_real)} گزارهٔ علمی این جلسه — جمله‌به‌جمله و '
                f'ردیف‌به‌ردیف — با همان عبارت خود جزوه، زیر بخش مربوطشان کنار هم چیده شده‌اند؛ '
                f'چیزی خلاصه یا بازنویسی نشده است. شمارهٔ کنار هر بخش، صفحهٔ متن کامل آن است. '
                f'جزئیات درون خودِ تصویرها ({fa_num(n_visual)} شکل) در نقشه نمی‌آید و با '
                f'نشانهٔ میکروسکوپ به خود شکل ارجاع داده شده است.</p>'
                f'<div class="rev__legend">{legend}</div>'
                f'{"".join(panels)}</div>')

    def sources_list(self) -> str:
        """منابع علمی همین جلسه — گردآوری مکانیکی برچسب‌های منبعِ خود بلوک‌ها."""
        if not self.show_sources:
            return ""
        by_book: dict[str, list[str]] = {}
        seen: set[tuple[str, str]] = set()
        for b in self.session.all_blocks():
            for src in b.sources or []:
                detail = "، ".join(x for x in (
                    f"شکل {src.figure}" if src.figure else "",
                    f"ص {src.pages}" if src.pages else "") if x)
                key = (src.book, detail)
                if key in seen:
                    continue
                seen.add(key)
                by_book.setdefault(src.book, []).append(detail)
        if not by_book:
            return ""
        rows = ""
        for book, details in by_book.items():
            chips = "".join(f'<span class="chip">{escape(d)}</span>'
                            for d in details if d)
            rows += (f'<div class="srclist__row"><b>{icon_svg("reference", 11)}'
                     f'{escape(book)}</b><span class="chips">{chips}</span></div>')
        return (f'<div class="srclist"><h3 class="h-ic">{icon_svg("book", 13)}'
                f'منابع علمی این جلسه</h3>{rows}</div>')

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
            items.append(f'<div class="gloss__it"><span class="gloss__fa">{escape(fa)}{en_html}</span>'
                         f'<span class="dots"></span><span class="gloss__pg">{pg_txt}</span></div>')
        return (f'<div class="glossary gloss--page"><h2 class="h-ic">' + icon_svg("book", 15) + 'واژه‌نامهٔ فارسی–انگلیسی همین جلسه</h2>'
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

    # ---------------------------------------------------------- بلوک‌های یادگیری
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
        fam = family_of_kind(kind)
        return f"""
<aside class="callout callout--{kind} fam {fam}" data-bid="{escape(b.id)}">
  <div class="callout__head"><span class="icb fam {fam}">{icon(kind)}</span><span>{inline(b.data["title"])}</span>
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
            labels = '<div class="fig__labels">' + "".join(
                f'<span class="chip">{escape(str(l["fa"]))} · '
                f'<bdi class="en">{escape(str(l["en"]))}</bdi></span>'
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
        cf = hex_of("royal-600")    # جهت روبه‌جلو: آبی سلطنتی برند
        cb = hex_of("tealcyan-500")  # جهت برگشت: فیروزه‌ای برند
        ct = hex_of("teal-ink")     # متن برچسب جهت برگشت (کنتراست متن ≥۴٫۵ روی سفید)
        # برچسب‌های نمودار فقط از متن خود بلوک: عنوان دو مسیر + سوما/پایانه اگر در داده هست
        titles = str(fwd.get("title", "")) + str(bwd.get("title", ""))
        node_r = "سوما" if "سوما" in titles else ""
        node_l = "پایانه" if "پایانه" in titles else ""
        rail_svg = f"""
<svg class="dualrail" viewBox="0 0 182 31" dir="ltr" role="img"
     aria-label="{escape(str(d["title"]))}">
  <circle cx="169" cy="13" r="6.2" fill="{hex_of('navy-900')}"/>
  <circle cx="167.4" cy="11.4" r="1.7" fill="#FFFFFF" opacity=".85"/>
  <g fill="{cb}"><circle cx="9" cy="8.5" r="2.6"/><circle cx="7" cy="14.5" r="2.6"/>
  <circle cx="10" cy="20" r="2.6"/></g>
  <g stroke="{hex_of('sky-400')}" stroke-width=".55">
    <line x1="16" y1="11.6" x2="162" y2="11.6"/><line x1="16" y1="14.4" x2="162" y2="14.4"/></g>
  <line x1="158" y1="7.6" x2="24" y2="7.6" stroke="{cf}" stroke-width="1.15"/>
  <polygon points="24,7.6 29.5,5.4 29.5,9.8" fill="{cf}"/>
  <circle cx="95" cy="7.6" r="2.1" fill="{cf}"/>
  <line x1="24" y1="18.4" x2="158" y2="18.4" stroke="{cb}" stroke-width="1.15"/>
  <polygon points="158,18.4 152.5,16.2 152.5,20.6" fill="{cb}"/>
  <circle cx="80" cy="18.4" r="2.1" fill="{cb}"/>
  <text x="91" y="4.6" font-size="3.1" font-weight="700" fill="{cf}" text-anchor="middle"
        font-family="Vazirmatn">{escape(str(fwd.get("title", "")))}</text>
  <text x="91" y="26.6" font-size="3.1" font-weight="700" fill="{ct}" text-anchor="middle"
        font-family="Vazirmatn">{escape(str(bwd.get("title", "")))}</text>
  {f'<text x="169" y="23.6" font-size="2.6" fill="{hex_of("navy-900")}" text-anchor="middle" font-family="Vazirmatn">{node_r}</text>' if node_r else ""}
  {f'<text x="9" y="26.6" font-size="2.6" fill="{ct}" text-anchor="middle" font-family="Vazirmatn">{node_l}</text>' if node_l else ""}
</svg>"""
        return f"""
<div class="dual" data-bid="{escape(b.id)}">
  <div class="process__title"><span class="pno">{escape(self.plan.labels.get(b.id, "مسیر"))}</span>
  <span>{inline(d["title"])}</span>{src_chips(b.sources, self.show_sources)}</div>
  {rail_svg}
  <div class="dual__lanes">
    <div class="lane lane--fwd"><div class="lane__head" style="--lane:{cf}"><svg class="lane__tri" viewBox="0 0 10 10"><polygon points="10,1 10,9 2,5"/></svg> {inline(fwd["title"])}</div>{self._steps(fwd["steps"])}</div>
    <div class="lane lane--bwd"><div class="lane__head" style="--lane:{cb}">{inline(bwd["title"])} <svg class="lane__tri" viewBox="0 0 10 10"><polygon points="0,1 0,9 8,5"/></svg></div>{self._steps(bwd["steps"])}</div>
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

    def b_summary_box(self, b: Block) -> str:
        return (f'<div class="summarybox" data-bid="{escape(b.id)}"><h3>{inline(b.data["title"])}</h3>'
                f'<p>{inline(b.data["text"])}</p>{src_chips(b.sources, self.show_sources)}</div>')

    def b_team_note(self, b: Block) -> str:
        return (f'<div class="teamnote" data-bid="{escape(b.id)}"><span class="tn-t">یادداشت عضو تیم — '
                f'{inline(b.data["title"])}</span></div>')
