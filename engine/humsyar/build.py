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
from .model import Session, load_session, normalize_text, validate
from .packing import measure_blocks, pack
from .planner import Plan, fa_num, plan_session
from .qa import render_pages_png, run_qa
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
    return "\n".join(faces)


def _render_pdf(html: str, out_pdf: Path, work: Path, session: Session,
                *, margin: dict, tag: str) -> None:
    html_path = work / f"{tag}.html"
    html_path.write_text(html, encoding="utf-8")
    cfg = {
        "margin": margin, "headerFooter": False,
        "fontFile": str(REPO_ROOT / "assets" / "fonts" / "Vazirmatn-Regular.ttf"),
    }
    cfg_path = work / f"render_config_{tag}.json"
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run(
        ["node", str(ENGINE_DIR / "render.mjs"), str(html_path), str(out_pdf), str(cfg_path)],
        cwd=ENGINE_DIR, capture_output=True, text=True, timeout=600)
    if proc.returncode != 0 or "RENDER_OK" not in proc.stdout:
        raise RuntimeError(f"رندر PDF ({tag}) ناموفق بود:\n{proc.stdout}\n{proc.stderr}")


def _find_heading_pages(pdf_path: Path, plan: Plan) -> dict[str, int]:
    """شمارهٔ صفحهٔ هر سرفصل در PDF بدنه (بدون کاور) با جست‌وجوی ترتیبی نرمال‌شده."""
    import pymupdf
    doc = pymupdf.open(str(pdf_path))
    pages_norm = [normalize_text(p.get_text()) for p in doc]
    found: dict[str, int] = {}
    start = 1  # صفحهٔ اول بدنه فهرست است؛ محتوا از صفحهٔ دوم بدنه شروع می‌شود
    for _lvl, display, anchor in plan.headings:
        parts = display.split(": ", 1)
        seg = parts[-1]
        fa_words = [w for w in display.split() if any("؀" <= ch <= "ۿ" for ch in w)]
        cands = [normalize_text(seg)[:40],
                 normalize_text(parts[0]) if len(parts) > 1 else "",
                 normalize_text(" ".join(seg.split()[:3])),
                 normalize_text(max(fa_words, key=len)) if fa_words else ""]
        for key_n in cands:
            if not key_n:
                continue
            hit = next((i for i in range(start, len(pages_norm)) if key_n in pages_norm[i]), None)
            if hit is not None:
                found[anchor] = hit + 1
                start = hit
                break
    return found


def _optimize_figures(session: Session, work: Path) -> None:
    """نسخهٔ نمایشی سبک از تصاویر برای PDF کم‌حجم؛ اصل تصویر در assets دست‌نخورده می‌ماند."""
    try:
        from PIL import Image
    except ImportError:
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


def _stamp_furniture(doc, frame_pdf: Path | None) -> None:
    """مهر قاب روی همهٔ صفحات جز کاور + کپسول شمارهٔ صفحه با ارقام فارسی.

    انتخاب طراحی (راند ۲): کپسول فقط عدد صفحه را دارد — تمیزتر از «صفحهٔ X از Y»
    و با خط قاب یکپارچه‌تر است. کاور شمرده می‌شود ولی شماره نمی‌خورد.
    """
    import pymupdf
    overlay = pymupdf.open(str(frame_pdf)) if frame_pdf else None
    font = pymupdf.Font(fontfile=str(REPO_ROOT / "assets" / "fonts" / "Vazirmatn-Bold.ttf"))
    for i in range(1, doc.page_count):
        page = doc[i]
        if overlay is not None:
            page.show_pdf_page(page.rect, overlay, 0)
            cx, cy = 105 * MM, CAPSULE_CY_MM * MM
            r = pymupdf.Rect(cx - 8 * MM, cy - 2.6 * MM, cx + 8 * MM, cy + 2.6 * MM)
            page.draw_rect(r, color=(0.043, 0.43, 0.42), fill=(1, 1, 1), width=0.7, radius=0.5)
            txt = fa_num(i + 1)
            tw = pymupdf.TextWriter(page.rect)
            tw.append((cx - font.text_length(txt, fontsize=9) / 2, cy + 3.2),
                      txt, font=font, fontsize=9)
            tw.write_text(page, color=(0.027, 0.31, 0.36))


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
    doc.save(str(tmp), garbage=3, deflate=True)
    tmp.replace(pdf_path)
    return links


def build(content_path: str, *, edition: str = "final", theme: str = "a",
          show_sources: bool = True, out_dir: str = "output",
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
    _optimize_figures(session, work)
    plan = plan_session(session, edition, REPO_ROOT)

    font_css = _font_css()
    css = font_css + "\n" + (ENGINE_DIR / "themes" / "humsyar.css").read_text(encoding="utf-8")
    assets_uri = f"file://{REPO_ROOT}/"
    pdf_path = out / f"{session.id}_{edition}.pdf"
    body_pdf = work / "body.pdf"

    # گذر اندازه‌گیری + بسته‌بندی فضا (look-ahead)
    ts = Typesetter(plan, show_sources=show_sources, assets_uri=assets_uri, brand=brand)
    html_a = ts.document(css, theme)
    html_a_path = work / "measure.html"
    html_a_path.write_text(html_a, encoding="utf-8")
    heights, toc_link_rects = measure_blocks(html_a_path, work, ENGINE_DIR)
    pack(session, plan, heights)

    # رندر بدنه و یافتن شمارهٔ واقعی صفحات (با آفست +۱ برای کاور)
    ts_b = Typesetter(plan, show_sources=show_sources, assets_uri=assets_uri, brand=brand)
    _render_pdf(ts_b.document(css, theme), body_pdf, work, session,
                margin=BODY_MARGIN, tag="body1")
    toc_pages = {k: v + 1 for k, v in _find_heading_pages(body_pdf, plan).items()}

    ts_c = Typesetter(plan, show_sources=show_sources, toc_pages=toc_pages,
                      assets_uri=assets_uri, brand=brand)
    html_final = ts_c.document(css, theme)
    (out / f"{session.id}_{edition}.html").write_text(html_final, encoding="utf-8")
    _render_pdf(html_final, body_pdf, work, session, margin=BODY_MARGIN, tag="body2")

    # کاور تمام‌صفحه + قاب موضوعی
    cover_pdf = work / "cover.pdf"
    _render_pdf(cover_html(session, brand, font_css), cover_pdf, work, session,
                margin=ZERO_MARGIN, tag="cover")
    frame_doc = frame_html(session, brand, font_css)
    frame_pdf = work / "frame.pdf"
    if frame_doc is not None:
        _render_pdf(frame_doc, frame_pdf, work, session, margin=ZERO_MARGIN, tag="frame")
    else:
        frame_pdf = None  # type: ignore[assignment]

    # ادغام: کاور + بدنه، مهر قاب و شماره‌ها
    import pymupdf
    final = pymupdf.open(str(cover_pdf))
    final.insert_pdf(pymupdf.open(str(body_pdf)))
    _stamp_furniture(final, frame_pdf)
    final.save(str(pdf_path), garbage=3, deflate=True)
    final.close()
    toc_links = _add_bookmarks(pdf_path, plan, toc_pages, brand, toc_link_rects)

    qa = run_qa(session, pdf_path, control_facts)
    qa["toc_links"] = toc_links
    renders = render_pages_png(pdf_path, out / "pages")

    report = {
        "engine": __version__, "session": session.id, "edition": edition, "theme": theme,
        "pdf": str(pdf_path), "build_seconds": round(time.time() - t0, 1),
        "toc_pages_found": toc_pages, "toc_links": toc_links,
        "planner_decisions": plan.decisions, "planner_warnings": plan.warnings,
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
