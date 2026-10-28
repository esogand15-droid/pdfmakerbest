"""
ارکستراتور ساخت (راند ۲):
مدل ← اعتبارسنجی ← پلان ← اندازه‌گیری ارتفاع بلوک‌ها در مرورگر ← بسته‌بندی فضا
← حروف‌چینی و رندر بدنه ← شمارهٔ واقعی صفحات فهرست (با آفست کاور) ← رندر نهایی
← کاور تمام‌صفحه + قاب موضوعی + کپسول شمارهٔ صفحه ← نشانک و پیوندهای فهرست ← QA.

شماره‌گذاری صفحات: کاور صفحهٔ ۱ شمرده می‌شود ولی شماره نمی‌خورد؛ فهرست صفحهٔ ۲ است.
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from . import __version__
from .brand import load_brand
from .cover import cover_html
from .frame import CAPSULE_CY_MM, frame_html
import os as _os
from .palette import brand_css_text, hex_of, rgb_of, rgb_of_hex, session_vars
from .model import Session, load_session, normalize_text, validate
from .packing import measure_blocks, pack
from .planner import Plan, fa_num, plan_session
from .qa import render_pages_png, run_qa
from .revision import coverage_report
from .typeset import Typesetter

ENGINE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = ENGINE_DIR.parent
BODY_MARGIN = {"top": "14mm", "bottom": "13mm", "left": "14mm", "right": "14mm"}
ZERO_MARGIN = {"top": "0mm", "bottom": "0mm", "left": "0mm", "right": "0mm"}
MM = 72 / 25.4


def _font_css() -> str:
    fdir = REPO_ROOT / "assets" / "fonts"
    faces = []
    for name, weight in [("Vazirmatn-Regular", 400), ("Vazirmatn-Medium", 500),
                         ("Vazirmatn-Bold", 700), ("Vazirmatn-Light", 300)]:
        p = fdir / f"{name}.ttf"
        if p.exists():
            faces.append(
                f'@font-face{{font-family:Vazirmatn;src:url(file://{p});font-weight:{weight}}}')
    # فونت لاتین Inter (جفت وزیرمتن): برای اصطلاحات و متن انگلیسی
    for name, weight, style in [("Inter-Regular", 400, "normal"), ("Inter-Italic", 400, "italic"),
                                ("Inter-Medium", 500, "normal"), ("Inter-SemiBold", 600, "normal"),
                                ("Inter-Bold", 700, "normal")]:
        p = fdir / f"{name}.woff2"
        if p.exists():
            faces.append(
                f'@font-face{{font-family:Inter;src:url(file://{p}) format("woff2");'
                f'font-weight:{weight};font-style:{style}}}')
    return "\n".join(faces)


def _render_pdf(html: str, out_pdf: Path, work: Path, session: Session,
                *, margin: dict, tag: str, omit_background: bool = False) -> None:
    html_path = work / f"{tag}.html"
    html_path.write_text(html, encoding="utf-8")
    cfg = {
        "margin": margin, "headerFooter": False, "omitBackground": omit_background,
        "fontFile": str(REPO_ROOT / "assets" / "fonts" / "Vazirmatn-Regular.ttf"),
    }
    cfg_path = work / f"render_config_{tag}.json"
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run(
        ["node", str(ENGINE_DIR / "render.mjs"), str(html_path.resolve()),
         str(Path(out_pdf).resolve()), str(cfg_path.resolve())],
        cwd=ENGINE_DIR, capture_output=True, text=True, timeout=600)
    if proc.returncode != 0 or "RENDER_OK" not in proc.stdout:
        raise RuntimeError(f"رندر PDF ({tag}) ناموفق بود:\n{proc.stdout}\n{proc.stderr}")


def _body_end_index(pages_norm: list[str], start: int) -> int:
    """نخستین صفحهٔ پسامطلب (نقشهٔ مرور/درخت/واژه‌نامه): جست‌وجوی عنوان‌های بدنه
    نباید به آن‌سو برود، چون آن صفحات عنوان بخش‌ها را عیناً تکرار می‌کنند."""
    end = len(pages_norm)
    for probe in ("نقشهٔ جامع مرور", "نمودار درختی جامع جلسه", "واژه‌نامهٔ فارسی"):
        pn = normalize_text(probe)
        hit = next((i for i in range(start, len(pages_norm)) if pn in pages_norm[i]), None)
        if hit is not None:
            end = min(end, hit)
    return end


def _find_heading_pages(pdf_path: Path, plan: Plan, start: int = 1) -> dict[str, int]:
    """شمارهٔ صفحهٔ هر سرفصل در PDF بدنه (بدون کاور) با جست‌وجوی ترتیبی نرمال‌شده."""
    import pymupdf
    doc = pymupdf.open(str(pdf_path))
    pages_norm = [normalize_text(p.get_text()) for p in doc]
    found: dict[str, int] = {}
    end = _body_end_index(pages_norm, start)
    # start: نخستین اندیس صفحهٔ محتوا (بدنه: ۱ بعد از فهرست؛ نهایی: ۲ بعد از کاور+فهرست)
    for _lvl, display, anchor in plan.headings:
        parts = display.split(": ", 1)
        seg = parts[-1]
        fa_words = [w for w in display.split() if any("؀" <= ch <= "ۿ" for ch in w)]
        strong = normalize_text(" ".join(fa_words[:4]))
        cands = [normalize_text(seg)[:40],
                 strong if len(strong) >= 14 else "",
                 normalize_text(parts[0]) if len(parts) > 1 and len(normalize_text(parts[0])) >= 12 else "",
                 normalize_text(" ".join(seg.split()[:3])),
                 normalize_text(max(fa_words, key=len)) if fa_words else ""]
        for key_n in cands:
            if not key_n:
                continue
            hit = next((i for i in range(start, min(end + 1, len(pages_norm)))
                        if key_n in pages_norm[i]), None)
            if hit is not None:
                found[anchor] = hit + 1
                start = hit
                break
    return found


def _find_block_pages(pdf_path: Path, session: Session, plan: Plan) -> dict[str, int]:
    """شمارهٔ صفحهٔ هر شکل/جدول در PDF بدنه (جست‌وجوی ترتیبی نرمال‌شده روی عنوان)."""
    import pymupdf
    doc = pymupdf.open(str(pdf_path))
    pages_norm = [normalize_text(p.get_text()) for p in doc]
    found: dict[str, int] = {}
    start = 1  # بعد از صفحهٔ فهرست
    end = _body_end_index(pages_norm, start)
    for b in session.all_blocks():
        if b.type not in ("figure", "table"):
            continue
        title = str(b.data.get("title_fa") or b.data.get("title") or "")
        if not title:
            continue
        cands = [normalize_text(title)[:40],
                 normalize_text(" ".join(title.split()[:3]))]
        for key_n in cands:
            if not key_n:
                continue
            hit = next((i for i in range(start, min(end + 1, len(pages_norm)))
                        if key_n in pages_norm[i]), None)
            if hit is not None:
                found[b.id] = hit + 1
                start = hit
                break
    return found


def _page_topics(session: Session, plan: Plan,
                 toc_pages: dict[str, int], total_pages: int) -> dict[int, dict]:
    """برای هر صفحهٔ نهایی: مبحث جاری (شماره، عنوان کوتاه، ترتیب در نقشهٔ جلسه)."""
    smap = {int(m["number"]): (i, str(m["title"]))
            for i, m in enumerate(session.session_map or [])}
    starts: list[tuple[int, dict]] = []
    topics_by_id = {t.id: t for t in session.topics}
    for lvl, _disp, anchor in plan.headings:
        t = topics_by_id.get(anchor)
        if t is not None and anchor in toc_pages:
            order, short = smap.get(t.number, (len(starts), t.title))
            starts.append((toc_pages[anchor],
                           {"number": t.number, "short": short, "order": order}))
    starts.sort(key=lambda x: x[0])  # فقط بر اساس صفحه؛ دیکشنری‌ها مقایسه نمی‌شوند
    out: dict[int, dict] = {}
    cur: dict = {}
    si = 0
    for pg in range(2, total_pages + 1):
        while si < len(starts) and starts[si][0] <= pg:
            cur = starts[si][1]
            si += 1
        out[pg] = cur
    return out


def _optimize_figures(session: Session, work: Path) -> None:
    """نسخهٔ نمایشی سبک از تصاویر برای PDF کم‌حجم؛ اصل تصویر در assets دست‌نخورده می‌ماند."""
    try:
        from PIL import Image
    except ImportError:
        print('هشدار: Pillow نصب نیست؛ بهینه‌سازی تصویر رد شد (PDF پرحجم می‌شود)')
        return
    fig_dir = work / "fig"
    fig_dir.mkdir(parents=True, exist_ok=True)
    for b in session.all_blocks():
        if b.type != "figure":
            continue
        src = REPO_ROOT / str(b.data["file"])
        if not src.exists():
            continue
        dst = fig_dir / (src.stem + ".jpg")
        im = Image.open(src).convert("RGB")
        if im.width > 1500:
            im = im.resize((1500, round(im.height * 1500 / im.width)), Image.LANCZOS)
        im.save(dst, quality=82, optimize=True)
        b.data["_opt_file"] = str(dst.relative_to(REPO_ROOT))


def _stamp_furniture(doc, frame_pdfs, page_topics: dict | None = None,
                     session_number: int = 1) -> None:
    """مهر قاب روی همهٔ صفحات جز کاور + کپسول شمارهٔ صفحه با ارقام فارسی.

    انتخاب طراحی (راند ۲): کپسول فقط عدد صفحه را دارد — تمیزتر از «صفحهٔ X از Y»
    و با خط قاب یکپارچه‌تر است. کاور شمرده می‌شود ولی شماره نمی‌خورد.
    """
    import pymupdf
    overlays = {}
    if isinstance(frame_pdfs, dict):
        overlays = {k: pymupdf.open(str(v)) for k, v in frame_pdfs.items() if v}
    elif frame_pdfs:
        overlays = {"_single": pymupdf.open(str(frame_pdfs))}
    font = pymupdf.Font(fontfile=str(REPO_ROOT / "assets" / "fonts" / "Vazirmatn-Bold.ttf"))
    total = doc.page_count
    for i in range(1, total):
        page = doc[i]
        pg_no = i + 1
        info = (page_topics or {}).get(pg_no, {})
        # زبانه همیشه سمت راست است (لبه‌ای که دانشجو جزوهٔ چاپی را از آن ورق می‌زند)
        key = info.get("number")
        overlay = overlays.get(key) or overlays.get("_single")
        if overlay is not None:
            page.show_pdf_page(page.rect, overlay, 0)
            # نوار پیشرفت مطالعه: از راست پر می‌شود (جهت خواندن فارسی) و در چاپ
            # سیاه‌وسفید هم با قاب تیره + پُری تیره + شیار سفید قابل تشخیص است.
            # فوتر دو ردیفه (راند ۱۳): ردیف ۱ نوار پیشرفت تمام‌عرض محتوا با
            # رنگ جلسه (از راست پر می‌شود)؛ ردیف ۲ روی خط پایین قاب است:
            # راست برند، چپ عنوان مجموعه، وسط دقیقاً کپسول (در قاب/همین‌جا).
            _sv = session_vars(int(session_number))
            _acc = rgb_of_hex(_sv["--session-accent"])
            _acc_h = rgb_of_hex(_sv["--session-header"])
            frac = i / max(1, total - 1)
            tx0, tx1, ty, th = 14 * MM, 196 * MM, 286.6 * MM, 1.0 * MM
            page.draw_rect(pymupdf.Rect(tx0, ty, tx1, ty + th),
                           color=None, fill=rgb_of("line-warm"), radius=0.5)
            fw = (tx1 - tx0) * frac
            if fw > 0.6 * MM:
                page.draw_rect(pymupdf.Rect(tx1 - fw, ty, tx1, ty + th),
                               color=None, fill=_acc, radius=0.5)
            cx, cy = 105 * MM, CAPSULE_CY_MM * MM
            r = pymupdf.Rect(cx - 8 * MM, cy - 2.6 * MM, cx + 8 * MM, cy + 2.6 * MM)
            page.draw_rect(r, color=_acc_h, fill=_acc_h, width=0.7, radius=0.5)
            txt = fa_num(i + 1)
            tw = pymupdf.TextWriter(page.rect)
            tw.append((cx - font.text_length(txt, fontsize=9) / 2, cy + 3.2),
                      txt, font=font, fontsize=9)
            tw.write_text(page, color=(1, 1, 1))


def _stamp_toc_links(doc, toc_pages: dict[str, int],
                     toc_link_rects: list[dict]) -> int:
    """پیوندهای داخلی فهرست از مختصات واقعی اندازه‌گیری‌شده در مرورگر ساخته می‌شوند."""
    import pymupdf
    if doc.page_count < 2 or not toc_link_rects:
        return 0
    page = doc[1]
    for link in list(page.get_links()):
        try:
            page.delete_link(link)
        except Exception:
            break
    made = 0
    for lr in toc_link_rects:
        anchor = str(lr.get("href", "")).lstrip("#")
        if anchor not in toc_pages:
            continue
        rect = pymupdf.Rect((14 + lr["x"]) * MM, (14 + lr["y"]) * MM,
                             (14 + lr["x"] + lr["w"]) * MM, (14 + lr["y"] + lr["h"]) * MM)
        page.insert_link({
            "kind": pymupdf.LINK_GOTO, "from": rect,
            "page": toc_pages[anchor] - 1, "to": pymupdf.Point(40, 40),
        })
        made += 1
    return made


def _add_bookmarks(pdf_path: Path, plan: Plan, toc_pages: dict[str, int],
                   brand: dict[str, str], toc_link_rects: list[dict]) -> int:
    import pymupdf
    doc = pymupdf.open(str(pdf_path))
    toc = []
    prev = 0
    for lvl, display, anchor in plan.headings:
        if anchor not in toc_pages:
            continue
        lvl = max(1, min(lvl, prev + 1))
        toc.append([lvl, display, toc_pages[anchor]])
        prev = lvl
    if toc:
        doc.set_toc(toc)
    s = plan.session
    doc.set_metadata({
        "title": f"{s.course} — جلسهٔ {s.session_number}: {s.title} | {brand['en']}",
        "author": brand["en"],
        "subject": f"جزوهٔ {s.course}، جلسهٔ {s.session_number} از {s.session_total} — {brand['fa']}",
        "creator": f"{brand['en']} PDF Engine {__version__}",
        "producer": f"{brand['en']} PDF Engine {__version__}",
    })
    links = _stamp_toc_links(doc, toc_pages, toc_link_rects)
    tmp = pdf_path.with_suffix(".tmp.pdf")
    doc.save(str(tmp), garbage=4, deflate=True)
    tmp.replace(pdf_path)
    return links


def build(content_path: str, *, edition: str = "final", theme: str = "a",
          show_sources: bool = True, print_theme: bool = False,
          bw_theme: bool = False, out_dir: str = "output",
          control_facts: list[str] | None = None) -> dict:
    t0 = time.time()
    session = load_session(content_path)
    errors = validate(session)
    if errors:
        raise ValueError("مدل محتوا نامعتبر است:\n" + "\n".join(f"- {e}" for e in errors))
    brand = load_brand(REPO_ROOT)

    out = Path(out_dir).resolve()
    work = out / "_work"
    work.mkdir(parents=True, exist_ok=True)
    # مدیریت خطای صریح: تصویر گمشده یعنی توقف فوری با نام بلوک، نه PDF ناقص
    missing_figs = [f"{b.id} ← {b.data.get('file')}" for b in session.all_blocks()
                    if b.type == "figure"
                    and not (REPO_ROOT / str(b.data.get("file", ""))).exists()]
    if missing_figs:
        raise FileNotFoundError(
            "فایل تصویر برای بلوک(های) زیر پیدا نشد؛ ساخت متوقف شد: "
            + "؛ ".join(missing_figs))
    _optimize_figures(session, work)
    plan = plan_session(session, edition, REPO_ROOT)
    if not brand.get("logo_uri"):
        plan.warn("فایل لوگوی رسمی برند پیدا نشد؛ کاور و سربرگ با برند تایپوگرافیک ساخته می‌شوند "
                  f"(مسیر مورد انتظار: {brand.get('logo')})")

    font_css = _font_css()
    brand_css = brand_css_text()
    css = font_css + "\n" + brand_css + "\n" + (ENGINE_DIR / "themes" / "humsyar.css").read_text(encoding="utf-8")
    assets_uri = f"file://{REPO_ROOT}/"
    pdf_path = out / f"{session.id}_{edition}{'_bw' if bw_theme else '_print' if print_theme else ''}.pdf"
    body_pdf = work / "body.pdf"

    # گذر اندازه‌گیری + بسته‌بندی فضا (look-ahead)
    ts = Typesetter(plan, show_sources=show_sources, assets_uri=assets_uri, brand=brand,
                      print_theme=print_theme, bw_theme=bw_theme)
    html_a = ts.document(css, theme)
    html_a_path = work / "measure.html"
    html_a_path.write_text(html_a, encoding="utf-8")
    heights, toc_link_rects, table_meta = measure_blocks(html_a_path, work, ENGINE_DIR)
    pack(session, plan, heights, table_meta)

    # رندر بدنه و یافتن شمارهٔ واقعی صفحات (با آفست +۱ برای کاور)
    ts_b = Typesetter(plan, show_sources=show_sources, assets_uri=assets_uri, brand=brand,
                      print_theme=print_theme, bw_theme=bw_theme)
    _render_pdf(ts_b.document(css, theme), body_pdf, work, session,
                margin=BODY_MARGIN, tag="body1")
    # حلقهٔ بازرسی بصری: Render → Inspect → Repair → Render Again (حداکثر دو دور)؛
    # اصلاح رانش شبیه‌سازی (feedback) یکی از خانواده‌های اصلاح همین حلقه است.
    from .inspect import inspect_body, repair_body
    from .packing import feedback_adjust
    inspection_rounds: list[dict] = []
    for fb_round in (1, 2):
        findings = inspect_body(body_pdf, session, plan)
        actions = repair_body(findings, session, plan, body_pdf)
        actions += feedback_adjust(session, body_pdf, plan, heights)
        inspection_rounds.append({"round": fb_round, "findings": findings, "repairs": actions})
        if not actions:
            break
        ts_fb = Typesetter(plan, show_sources=show_sources, assets_uri=assets_uri, brand=brand,
                      print_theme=print_theme, bw_theme=bw_theme)
        _render_pdf(ts_fb.document(css, theme), body_pdf, work, session,
                    margin=BODY_MARGIN, tag=f"body1fb{fb_round}")
    inspection_final = inspect_body(body_pdf, session, plan)
    toc_pages = {k: v + 1 for k, v in _find_heading_pages(body_pdf, plan).items()}
    fig_pages = {k: v + 1 for k, v in _find_block_pages(body_pdf, session, plan).items()}

    ts_c = Typesetter(plan, show_sources=show_sources, toc_pages=toc_pages,
                      fig_pages=fig_pages, print_theme=print_theme, bw_theme=bw_theme,
                      assets_uri=assets_uri, brand=brand)
    html_final = ts_c.document(css, theme)
    (out / f"{session.id}_{edition}.html").write_text(html_final, encoding="utf-8")
    _render_pdf(html_final, body_pdf, work, session, margin=BODY_MARGIN, tag="body2")

    # کاور تمام‌صفحه + قاب موضوعی
    cover_pdf = work / "cover.pdf"
    _cover_light = print_theme or _os.environ.get("BRAND_COVER", "").lower() == "light"
    _render_pdf(cover_html(session, brand, font_css + "\n" + brand_css, light=_cover_light),
                cover_pdf, work, session,
                margin=ZERO_MARGIN, tag="cover")
    # واریانت قاب به‌ازای (مبحث جاری، زوج/فرد) برای زبانهٔ انگشت‌نما + نوار پیشرفت
    import pymupdf as _pm
    _bd = _pm.open(str(body_pdf))
    page_topics = _page_topics(session, plan, toc_pages, _bd.page_count + 1)
    _bd.close()
    frame_pdfs: dict = {}
    needed = {page_topics.get(pg, {}).get("number"): page_topics.get(pg, {})
              for pg in range(2, max(page_topics, default=2) + 1)}
    _color_cfg = (plan.layout_cfg or {}).get("color_system", {}) or {}
    _paper_hex = "#FFFFFF" if (print_theme or _color_cfg.get("paper") == "white") else hex_of("paper")
    for tnum, info in needed.items():
        fdoc = frame_html(session, brand, font_css + "\n" + brand_css,
                          topic_number=tnum, topic_short=info.get("short", ""),
                          topic_order=info.get("order", 0),
                          accent_mode=str(_color_cfg.get("chapter_accent_mode", "off")),
                          paper_hex=_paper_hex,
                          side="right")  # همیشه لبهٔ راست: سمت ورق‌زدن دانشجو
        if fdoc is None:
            frame_pdfs = {}
            break
        fp = work / f"frame_{tnum}.pdf"
        _render_pdf(fdoc, fp, work, session, margin=ZERO_MARGIN, tag=f"frame_{tnum}",
                    omit_background=True)
        frame_pdfs[tnum] = fp

    # ادغام: کاور + بدنه، مهر قاب و شماره‌ها
    import pymupdf
    final = pymupdf.open(str(cover_pdf))
    final.insert_pdf(pymupdf.open(str(body_pdf)))
    _stamp_furniture(final, frame_pdfs, page_topics,
                     session_number=session.session_number)
    # garbage=4 جریان‌های فونت تکراریِ واریانت‌های قاب را یکی می‌کند (۵٫۳→۲٫۵MB)
    final.save(str(pdf_path), garbage=4, deflate=True)
    final.close()
    toc_links = _add_bookmarks(pdf_path, plan, toc_pages, brand, toc_link_rects)

    # بازبینی نهایی شماره‌های فهرست روی خود PDF نهایی (پس از ادغام کاور)
    verify = _find_heading_pages(pdf_path, plan, start=2)
    toc_mismatch = {k: (toc_pages.get(k), v) for k, v in verify.items()
                    if toc_pages.get(k) not in (None, v)}
    if toc_mismatch:
        plan.log(f"[بازبینی فهرست] ناهمخوانی شمارهٔ صفحه در فهرست: {toc_mismatch}")

    qa = run_qa(session, pdf_path, control_facts)
    # یافته‌های بازرسی بصری که خودکار اصلاح نشدند به QA می‌روند (بدنه +۱ = نهایی با کاور)
    qa["inspection_findings"] = inspection_final
    leftover = [f for f in inspection_final if f["severity"] == "warn"]
    if leftover:
        qa["warnings"] = list(qa.get("warnings", [])) + [
            f"بازرسی بصری: صفحهٔ {f['page'] + 1} — {f['detail']} (علت محتمل: {f['cause']})"
            for f in leftover]
    qa["toc_verified"] = not toc_mismatch
    if toc_mismatch:
        qa["warnings"] = list(qa.get("warnings", [])) + [
            f"شمارهٔ صفحهٔ فهرست با PDF نهایی نمی‌خواند: {toc_mismatch}"]
    qa["toc_links"] = toc_links
    renders = render_pages_png(pdf_path, out / "pages")

    report = {
        "engine": __version__, "session": session.id, "edition": edition, "theme": theme,
        "pdf": str(pdf_path), "build_seconds": round(time.time() - t0, 1),
        "toc_pages_found": toc_pages, "toc_links": toc_links,
        "planner_decisions": plan.decisions, "planner_warnings": plan.warnings,
        "content_analysis": [p.to_dict() for p in plan.analysis],
        "coverage": coverage_report(session),
        "layout_decisions": plan.layout_decisions,
        "page_signatures": [{k: v for k, v in s.items() if k != "blocks"}
                             for s in plan.page_signatures],
        "inspection": {"rounds": inspection_rounds, "final_findings": inspection_final},
        "qa": qa, "renders": [str(r) for r in renders],
    }
    (out / "build_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "review_report.md").write_text(_review_md(session, plan, qa), encoding="utf-8")
    return report


def _review_md(session: Session, plan: Plan, qa: dict) -> str:
    fill = qa.get("fill_per_page") or []
    lines = [
        f"# گزارش بازبینی — {session.course}، جلسهٔ {session.session_number} ({plan.edition})",
        "",
        "این گزارش جای «برگه‌های تحویل» جزوهٔ مادر را در فرایند نهایی می‌گیرد: "
        "هر ابهام علمی اینجاست، نه حدس‌زده‌شده در متن.",
        "",
        f"- صفحات PDF: {qa['pages']} (کاور + فهرست + بدنه) · میانگین نویسه/صفحه: {qa['avg_chars_per_page']}",
        f"- میانگین پُری صفحات محتوایی: {qa.get('fill_avg_pct', '—')}٪ · "
        f"پُری هر صفحه: {fill}",
        f"- تصاویر: مدل {qa['figures_model']} / PDF {qa['figures_pdf']} · "
        f"کمترین فونت: {qa['min_font_pt']}pt · پیوندهای فهرست: {qa.get('toc_links', '—')}",
        f"- نتیجهٔ QA خودکار: {'✅ قبول' if qa['ok'] else '❌ دارای خطا'}",
        "",
        "## موارد نیازمند بازبینی انسانی",
    ]
    lines += [f"- {it}" for it in qa["review_items"]] or ["- (موردی ثبت نشده)"]
    lines += ["", "## هشدارهای موتور چیدمان (کیفیت تصویر و …)"]
    lines += [f"- {w}" for w in plan.warnings] or ["- (هشداری نیست)"]
    lines += ["", "## خطاها/هشدارهای QA"]
    lines += [f"- ❌ {e}" for e in qa["errors"]]
    lines += [f"- ⚠️ {w}" for w in qa["warnings"]]
    if not qa["errors"] and not qa["warnings"]:
        lines.append("- (موردی نیست)")
    lines += ["", "## تصمیم‌های چیدمان و بسته‌بندی (خلاصه)"]
    lines += [f"- {d}" for d in plan.decisions]
    return "\n".join(lines) + "\n"
