#!/usr/bin/env python3
"""ممیزی خودکار PDF نهایی هامزیار (مرحلهٔ ۰) — فقط گزارش، بدون تغییر در خروجی.

معیارها: فضای خالی هر صفحه، خانواده‌های hue در هر صفحه (بدون پیکسل‌های داخل
تصاویر)، رنگ‌های وکتوری خارج از توکن‌ها، نشت تگ زبان، سه‌نقطهٔ بریدگی،
متن دولایهٔ جلد، صفحهٔ بی‌شماره، نوار تیرهٔ لبهٔ تصاویر منبع، dpi مؤثر.

اجرا:
  .venv/bin/python tools/audit_pdf.py [pdf] [--out output/_audit] [--compare baseline.json]
خروجی: audit.json + contact_sheet.png در پوشهٔ خروجی.
"""
from __future__ import annotations

import argparse
import colorsys
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))

import pymupdf  # noqa: E402

MM = 72 / 25.4
ZONE_TOP_MM = 16.0      # زیر هدر
ZONE_BOTTOM_MM = 283.0  # بالای فوتر (A4: 297-14)


def _content_bottom_mm(page: pymupdf.Page) -> float:
    # فقط داخل ستون متن (۱۰ تا ۲۰۰ میلی‌متر) و ناحیهٔ محتوا؛ تب کناری، فوتر
    # و تزئینات قاب جزو محتوا نیستند.
    bottom = 0.0
    for bl in page.get_text("dict")["blocks"]:
        if bl.get("type") == 0 and bl.get("lines"):
            x0, _, x1, y1 = (v / MM for v in bl["bbox"])
            if y1 <= ZONE_BOTTOM_MM and x0 >= 8 and x1 <= 202:
                bottom = max(bottom, y1)
    for img in page.get_images(full=True):
        for r in page.get_image_rects(img[0]):
            y1 = r.y1 / MM
            if y1 <= ZONE_BOTTOM_MM and r.x0 / MM >= 8 and r.x1 / MM <= 202:
                bottom = max(bottom, y1)
    for dr in page.get_drawings():
        r = dr["rect"]
        # قاب صفحه/خطوط عمودی تمام‌قد و پس‌زمینهٔ تمام‌صفحه محتوا نیست
        if r.height > page.rect.height * 0.8:
            continue
        if r.width > page.rect.width * 0.9 and r.height > page.rect.height * 0.5:
            continue
        y1 = r.y1 / MM
        if y1 <= ZONE_BOTTOM_MM and r.x0 / MM >= 8 and r.x1 / MM <= 202:
            bottom = max(bottom, y1)
    return bottom


def _hue_families(page: pymupdf.Page) -> dict[str, float]:
    """سهم هر بازهٔ hue از پیکسل‌های اشباع‌شدهٔ صفحه (خارج از مستطیل تصاویر)."""
    mat = pymupdf.Matrix(0.5, 0.5)
    pix = page.get_pixmap(matrix=mat)
    img_rects = []
    for img in page.get_images(full=True):
        for r in page.get_image_rects(img[0]):
            img_rects.append((r.x0 * 0.5, r.y0 * 0.5, r.x1 * 0.5, r.y1 * 0.5))
    w, h, n = pix.width, pix.height, pix.n
    samples = pix.samples
    bins: dict[int, int] = {}
    sat_total = 0
    step = 3
    for y in range(0, h, step):
        row = y * w * n
        for x in range(0, w, step):
            if any(rx0 <= x <= rx1 and ry0 <= y <= ry1 for rx0, ry0, rx1, ry1 in img_rects):
                continue
            i = row + x * n
            r, g, b = samples[i] / 255, samples[i + 1] / 255, samples[i + 2] / 255
            hh, ss, vv = colorsys.rgb_to_hsv(r, g, b)
            if ss > 0.25 and 0.15 < vv < 0.97:
                sat_total += 1
                key = int(hh * 12) % 12
                bins[key] = bins.get(key, 0) + 1
    if not sat_total:
        return {}
    names = ["قرمز", "نارنجی", "زردنارنجی", "زرد", "سبززرد", "سبز", "فیروزه‌ای",
             "سبزآبی", "آبی", "نیلی", "بنفش", "سرخابی"]
    return {names[k]: round(100 * v / sat_total, 2)
            for k, v in sorted(bins.items()) if v / sat_total > 0.003}


def _token_hexes(root: Path) -> set[str]:
    hexes = {"#FFFFFF", "#000000"}
    brand = (root / "engine" / "themes" / "brand.css").read_text(encoding="utf-8")
    hexes |= {h.upper() for h in re.findall(r"#[0-9A-Fa-f]{6}\b", brand)}
    try:
        from humsyar.palette import session_vars
        for s in range(1, 14):
            for v in session_vars(s).values():
                if isinstance(v, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", v):
                    hexes.add(v.upper())
    except Exception:
        pass
    return hexes


def _used_vector_colors(doc: pymupdf.Document) -> dict[str, int]:
    counts: dict[str, int] = {}
    def add(rgb) -> None:
        if rgb is None:
            return
        if isinstance(rgb, int):
            hexv = f"#{rgb:06X}"
        else:
            hexv = "#" + "".join(f"{round(c * 255):02X}" for c in rgb[:3])
        counts[hexv] = counts.get(hexv, 0) + 1
    for page in doc:
        for bl in page.get_text("dict")["blocks"]:
            for ln in bl.get("lines", []):
                for sp in ln.get("spans", []):
                    add(sp.get("color"))
        for dr in page.get_drawings():
            add(dr.get("fill"))
            add(dr.get("color"))
    return counts


def _image_edge_and_dpi(doc: pymupdf.Document) -> list[dict]:
    out: list[dict] = []
    seen: set[int] = set()
    for pno, page in enumerate(doc):
        for img in page.get_images(full=True):
            xref = img[0]
            rects = page.get_image_rects(xref)
            if not rects:
                continue
            r = rects[0]
            try:
                pix = pymupdf.Pixmap(doc, xref)
            except Exception:
                continue
            if pix.n > 4:  # CMYK و مانند آن
                pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
            w_px, h_px = pix.width, pix.height
            dpi = w_px / (r.width / 72) if r.width else 0
            entry: dict = {"page": pno + 1, "xref": xref,
                           "px": [w_px, h_px], "dpi": round(dpi)}
            if xref not in seen and h_px >= 20:
                seen.add(xref)
                n, samples = pix.n, pix.samples
                def row_mean(y: int) -> float:
                    base = y * w_px * n
                    vals = [samples[base + x * n] * 0.299 + samples[base + x * n + 1] * 0.587
                            + samples[base + x * n + 2] * 0.114
                            for x in range(0, w_px, max(1, w_px // 40))]
                    return sum(vals) / len(vals)
                band = max(2, int(h_px * 0.03))
                tops = [row_mean(y) for y in range(band)]
                bots = [row_mean(y) for y in range(h_px - band, h_px)]
                top = sum(tops) / band
                bot = sum(bots) / band
                mid = row_mean(h_px // 2)
                def _sd(v: list[float], m: float) -> float:
                    return (sum((x - m) ** 2 for x in v) / len(v)) ** 0.5
                entry["edge_lum"] = {"top": round(top), "bottom": round(bot), "mid": round(mid)}
                entry["dark_edge"] = bool(
                    (bot < 60 and _sd(bots, bot) < 25)
                    or (top < 60 and _sd(tops, top) < 25)
                    or bot < mid - 100)
            out.append(entry)
    return out


def _contact_sheet(doc: pymupdf.Document, path: Path, cols: int = 4) -> None:
    from PIL import Image
    thumbs = []
    for page in doc:
        pix = page.get_pixmap(matrix=pymupdf.Matrix(0.32, 0.32))
        thumbs.append(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
    tw, th = thumbs[0].size
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tw + (cols + 1) * 6, rows * th + (rows + 1) * 6), (60, 60, 60))
    for i, im in enumerate(thumbs):
        x = 6 + (i % cols) * (tw + 6)
        y = 6 + (i // cols) * (th + 6)
        sheet.paste(im, (x, y))
    sheet.save(path)


def audit(pdf: Path, root: Path) -> dict:
    doc = pymupdf.open(str(pdf))
    leak_re = re.compile(r"[a-z]{2}:[A-Za-z][A-Za-z]{0,20}")
    pages: list[dict] = []
    leaks: list[dict] = []
    ellipsis_pages: list[int] = []
    no_number: list[int] = []
    for i, page in enumerate(doc):
        bottom = _content_bottom_mm(page)
        blank = max(0.0, ZONE_BOTTOM_MM - bottom)
        fill = (min(bottom, ZONE_BOTTOM_MM) - ZONE_TOP_MM) / (ZONE_BOTTOM_MM - ZONE_TOP_MM)
        text = page.get_text()
        for m in leak_re.finditer(text):
            leaks.append({"page": i + 1, "text": m.group(0)})
        if "…" in text:
            ellipsis_pages.append(i + 1)
        h = page.rect.height
        foot = page.get_text("text", clip=pymupdf.Rect(0, h - 14 * MM, page.rect.width, h))
        if not re.search(r"[0-9۰-۹]", foot):
            no_number.append(i + 1)
        fams = _hue_families(page)
        pages.append({
            "page": i + 1,
            "fill_pct": round(100 * max(0.0, min(1.0, fill))),
            "blank_mm": round(blank, 1),
            "hue_families": fams,
            "hue_family_count": len(fams),
        })
    used = _used_vector_colors(doc)
    tokens = _token_hexes(root)
    off_token = {h: c for h, c in sorted(used.items(), key=lambda kv: -kv[1])
                 if h.upper() not in tokens}
    cover_lines = [ln.strip() for ln in doc[0].get_text().splitlines() if ln.strip()]
    dup_lines = sorted({ln for ln in cover_lines if cover_lines.count(ln) > 1})
    images = _image_edge_and_dpi(doc)
    report = {
        "pdf": str(pdf),
        "pages": len(doc),
        "per_page": pages,
        "mean_fill_pct": round(sum(p["fill_pct"] for p in pages) / max(1, len(pages)), 1),
        "pages_over_25pct_blank": [p["page"] for p in pages if p["fill_pct"] < 75],
        "pages_over_3_hue_families": [p["page"] for p in pages if p["hue_family_count"] > 3],
        "off_token_colors": off_token,
        "tag_leaks": leaks,
        "ellipsis_pages": ellipsis_pages,
        "pages_without_number": no_number,
        "cover_duplicate_lines": dup_lines,
        "dark_edge_images": [e for e in images if e.get("dark_edge")],
        "low_dpi_images": [e for e in images if e.get("dpi", 999) < 150],
    }
    _contact_sheet(doc, _OUT / "contact_sheet.png")
    doc.close()
    return report


_OUT = Path("output/_audit")


def main() -> None:
    ap = argparse.ArgumentParser(description="ممیزی خودکار PDF نهایی هامزیار")
    ap.add_argument("pdf", nargs="?", default="output/HumsYar_Final.pdf")
    ap.add_argument("--out", default="output/_audit")
    ap.add_argument("--compare", default=None, help="مسیر JSON ممیزی قبلی برای مقایسه")
    args = ap.parse_args()
    global _OUT
    _OUT = Path(args.out)
    _OUT.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[1]
    report = audit(Path(args.pdf), root)
    (_OUT / "audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
    print(f"صفحات: {report['pages']} | میانگین پُری: {report['mean_fill_pct']}٪")
    print("صفحات با بیش از ۲۵٪ فضای خالی:", report["pages_over_25pct_blank"])
    print("صفحات با بیش از ۳ خانوادهٔ hue:", report["pages_over_3_hue_families"])
    print("رنگ خارج از توکن:", len(report["off_token_colors"]))
    print("نشت تگ:", report["tag_leaks"])
    print("صفحات دارای … :", report["ellipsis_pages"])
    print("صفحات بی‌شماره:", report["pages_without_number"])
    print("خطوط تکراری جلد:", report["cover_duplicate_lines"])
    print("تصاویر نامزد لبهٔ تیره:", [(e["page"], e["xref"]) for e in report["dark_edge_images"]])
    print("تصاویر زیر 150dpi:", [(e["page"], e["dpi"]) for e in report["low_dpi_images"]])
    if args.compare:
        old = json.loads(Path(args.compare).read_text(encoding="utf-8"))
        print("--- مقایسه با ممیزی قبلی ---")
        for k in ("pages", "mean_fill_pct", "pages_over_25pct_blank",
                  "pages_over_3_hue_families", "tag_leaks", "ellipsis_pages",
                  "pages_without_number"):
            print(f"{k}: {old.get(k)} -> {report.get(k)}")
        print("off_token:", len(old.get("off_token_colors", {})), "->",
              len(report["off_token_colors"]))
        print("dark_edge:", len(old.get("dark_edge_images", [])), "->",
              len(report["dark_edge_images"]))


if __name__ == "__main__":
    main()
