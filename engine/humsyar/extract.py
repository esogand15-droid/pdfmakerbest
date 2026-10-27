"""
استخراج از جزوهٔ مادر PDF — آداپتور ورودی موتور.

واقعیت فنی جزوهٔ مادر هامزیار: با ReportLab ساخته شده و متن فارسی به صورت
گلیف‌های نمایشی (Arabic Presentation Forms) و با *ترتیب بصری معکوس* ذخیره شده.
پس استخراج خام PyMuPDF برای فارسی برعکس است. این ماژول:
- گلیف‌ها را با NFKC به نویسهٔ استاندارد برمی‌گرداند،
- در سطرهای عمدتاً فارسی ترتیب واژه‌ها را برعکس می‌کند (پیش‌نویس خوانا)،
- تصاویر را با کیفیت اصلی بیرون می‌کشد و DPI مؤثر و پرچم کیفی می‌دهد.

خروجی این مرحله «پیش‌نویس استخراج» است با وضعیت needs_review؛ تبدیل آن به
مدل محتوا (YAML) گام ویرایشی جداست و هر اصلاح واژهٔ لاتین باید در آن گام
با فهرست اصطلاحات و تصویر صفحه تطبیق داده شود. موتور هرگز متن استخراجی را
بدون این عبور، نهایی فرض نمی‌کند.
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

_ARABIC_RE = re.compile(r"[؀-ۿ]")


def _fa_ratio(line: str) -> float:
    letters = [c for c in line if c.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if _ARABIC_RE.match(c)) / len(letters)


def logical_order(text: str) -> str:
    """تبدیل متن بصریِ استخراج‌شده به ترتیب منطقی خوانا (قاعدهٔ اکتشافی؛ نیازمند بازبینی)."""
    text = unicodedata.normalize("NFKC", text)
    out_lines = []
    for line in text.splitlines():
        line = line.strip()
        if _fa_ratio(line) > 0.5 and len(line.split()) > 1:
            line = " ".join(reversed(line.split()))
        out_lines.append(line)
    return "\n".join(out_lines)


def extract_mother(pdf_path: str, out_dir: str) -> dict:
    import pymupdf
    out = Path(out_dir)
    (out / "figures").mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(pdf_path)
    pages_text: list[str] = []
    inventory: list[dict] = []
    for pno, page in enumerate(doc, 1):
        pages_text.append(f"\n\n===== MOTHER PAGE {pno} =====\n"
                          + logical_order(page.get_text("text", sort=True)))
        for img in page.get_images(full=True):
            xref = img[0]
            pix = pymupdf.Pixmap(doc, xref)
            rects = page.get_image_rects(xref)
            disp_w = rects[0].width if rects else 0
            eff_dpi = round(pix.width / (disp_w / 72)) if disp_w else 0
            if pix.n > 4:
                pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
            fname = f"p{pno:02d}_x{xref}.png"
            pix.save(str(out / "figures" / fname))
            flags = []
            if eff_dpi and eff_dpi < 110:
                flags.append(f"low_dpi_{eff_dpi}")
            inventory.append({
                "page": pno, "xref": xref, "file": f"figures/{fname}",
                "width": pix.width, "height": pix.height,
                "eff_dpi_in_mother": eff_dpi, "flags": flags,
            })
    (out / "mother_text_logical.txt").write_text("".join(pages_text), encoding="utf-8")
    (out / "image_inventory.json").write_text(
        json.dumps(inventory, ensure_ascii=False, indent=1), encoding="utf-8")
    return {
        "pages": doc.page_count, "images": len(inventory),
        "out_dir": str(out), "metadata": dict(doc.metadata or {}),
    }
