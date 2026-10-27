"""
ارکستراتور ساخت: مدل ← اعتبارسنجی ← پلان چیدمان ← حروف‌چینی ← رندر Chromium
← (گذر دوم برای شمارهٔ واقعی صفحات در فهرست) ← نشانک PDF ← QA ← گزارش‌ها.
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from . import __version__
from .model import Session, load_session, normalize_text, validate
from .planner import Plan, fa_num, plan_session
from .qa import render_pages_png, run_qa
from .typeset import Typesetter

ENGINE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = ENGINE_DIR.parent


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


def _render_pdf(html: str, out_pdf: Path, work: Path, session: Session) -> None:
    html_path = work / "document.html"
    html_path.write_text(html, encoding="utf-8")
    cfg = {
        "headerRight": f"{session.course} — جلسهٔ {fa_num(session.session_number)}: {session.title}",
        "headerLeft": "HumsYar",
        "footerText": "هامزیار · جزوهٔ علوم پایهٔ پزشکی",
        "fontFile": str(REPO_ROOT / "assets" / "fonts" / "Vazirmatn-Regular.ttf"),
    }
    cfg_path = work / "render_config.json"
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run(
        ["node", str(ENGINE_DIR / "render.mjs"), str(html_path), str(out_pdf), str(cfg_path)],
        cwd=ENGINE_DIR, capture_output=True, text=True, timeout=600)
    if proc.returncode != 0 or "RENDER_OK" not in proc.stdout:
        raise RuntimeError(f"رندر PDF ناموفق بود:\n{proc.stdout}\n{proc.stderr}")


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


def _find_heading_pages(pdf_path: Path, plan: Plan) -> dict[str, int]:
    """شمارهٔ واقعی صفحهٔ هر سرفصل با جست‌وجوی متنی نرمال‌شده در PDF گذر اول."""
    import pymupdf
    doc = pymupdf.open(str(pdf_path))
    pages_norm = [normalize_text(p.get_text()) for p in doc]
    found: dict[str, int] = {}
    start = 1  # صفحهٔ اول کاور/نقشه/فهرست است؛ جست‌وجو از محتوای واقعی و به‌صورت ترتیبی
    for _lvl, display, anchor in plan.headings:
        parts = display.split(": ", 1)
        seg = parts[-1]
        # نامزدها: هر دو بخش عنوان + بلندترین واژهٔ فارسی؛ اولین تطابق برنده است
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


def _add_bookmarks(pdf_path: Path, plan: Plan, toc_pages: dict[str, int]) -> None:
    import pymupdf
    doc = pymupdf.open(str(pdf_path))
    toc = []
    prev = 0
    for lvl, display, anchor in plan.headings:
        if anchor not in toc_pages:
            continue
        lvl = max(1, min(lvl, prev + 1))  # سلسله‌مراتب معتبر برای set_toc
        toc.append([lvl, display, toc_pages[anchor]])
        prev = lvl
    if toc:
        doc.set_toc(toc)
    s = plan.session
    doc.set_metadata({
        "title": f"{s.course} — جلسهٔ {s.session_number}: {s.title} | HumsYar",
        "author": "HumsYar",
        "subject": f"جزوهٔ نهایی {s.course}، جلسهٔ {s.session_number} از {s.session_total}",
        "creator": f"HumsYar PDF Engine {__version__}",
    })
    tmp = pdf_path.with_suffix(".tmp.pdf")
    doc.save(str(tmp), garbage=3, deflate=True)
    tmp.replace(pdf_path)


def build(content_path: str, *, edition: str = "final", theme: str = "a",
          show_sources: bool = True, out_dir: str = "output",
          control_facts: list[str] | None = None) -> dict:
    t0 = time.time()
    session = load_session(content_path)
    errors = validate(session)
    if errors:
        raise ValueError("مدل محتوا نامعتبر است:\n" + "\n".join(f"- {e}" for e in errors))

    out = Path(out_dir).resolve()
    work = out / "_work"
    work.mkdir(parents=True, exist_ok=True)
    plan = plan_session(session, edition, REPO_ROOT)

    _optimize_figures(session, work)

    css = _font_css() + "\n" + (ENGINE_DIR / "themes" / "humsyar.css").read_text(encoding="utf-8")
    assets_uri = f"file://{REPO_ROOT}/"

    # گذر اول: بدون شمارهٔ صفحه؛ برای یافتن جای واقعی سرفصل‌ها
    ts = Typesetter(plan, show_sources=show_sources, assets_uri=assets_uri)
    pdf_path = out / f"{session.id}_{edition}.pdf"
    _render_pdf(ts.document(css, theme), pdf_path, work, session)

    # گذر دوم: فهرست با شمارهٔ واقعی + نشانک‌ها
    toc_pages = _find_heading_pages(pdf_path, plan)
    ts2 = Typesetter(plan, show_sources=show_sources, toc_pages=toc_pages, assets_uri=assets_uri)
    html_final = ts2.document(css, theme)
    (out / f"{session.id}_{edition}.html").write_text(html_final, encoding="utf-8")
    _render_pdf(html_final, pdf_path, work, session)
    _add_bookmarks(pdf_path, plan, toc_pages)

    qa = run_qa(session, pdf_path, control_facts)
    renders = render_pages_png(pdf_path, out / "pages")

    report = {
        "engine": __version__, "session": session.id, "edition": edition, "theme": theme,
        "pdf": str(pdf_path), "build_seconds": round(time.time() - t0, 1),
        "toc_pages_found": toc_pages,
        "planner_decisions": plan.decisions, "planner_warnings": plan.warnings,
        "qa": qa, "renders": [str(r) for r in renders],
    }
    (out / "build_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "review_report.md").write_text(_review_md(session, plan, qa), encoding="utf-8")
    return report


def _review_md(session: Session, plan: Plan, qa: dict) -> str:
    lines = [
        f"# گزارش بازبینی — {session.course}، جلسهٔ {session.session_number} ({plan.edition})",
        "",
        "این گزارش جای «برگه‌های تحویل» جزوهٔ مادر را در فرایند نهایی می‌گیرد: "
        "هر ابهام علمی اینجاست، نه حدس‌زده‌شده در متن.",
        "",
        f"- صفحات PDF: {qa['pages']} · میانگین نویسه/صفحه: {qa['avg_chars_per_page']}",
        f"- تصاویر: مدل {qa['figures_model']} / PDF {qa['figures_pdf']} · "
        f"کمترین فونت: {qa['min_font_pt']}pt",
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
    lines += ["", "## تصمیم‌های چیدمان (خلاصه)"]
    lines += [f"- {d}" for d in plan.decisions]
    return "\n".join(lines) + "\n"
