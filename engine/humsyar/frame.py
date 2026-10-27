"""
قاب موضوعی دور صفحات هامزیار — لایهٔ رویی (overlay) برداری با کد SVG.

چرا overlay جدا؟ در چاپ Chromium جای‌گذاری `position: fixed` برای مبلمان صفحه
قابل اعتماد نبود (در آزمایش به پایین صفحه می‌چسبید). پس قاب یک PDF تک‌صفحه‌ای
مستقل با حاشیهٔ صفر رندر و با PyMuPDF روی همهٔ صفحات (جز کاور) مهر می‌شود؛
شمارهٔ صفحه هم در همان مرحله داخل کپسول وسط خط پایین قاب می‌نشیند.

هندسه (mm): قاب در ۶mm از لبه، خط دوتایی ظریف (≤۰٫۸pt)، نقوش گوشه ≤۱۱mm،
متن محتوا با حاشیهٔ ۱۴mm هرگز زیر نقوش نمی‌رود.
تم‌ها در FRAME_THEMES ثبت می‌شوند؛ `none` یعنی بدون قاب.
"""
from __future__ import annotations

import math
import random
from html import escape

from .model import Session
from .planner import fa_num

FRAME_INSET_MM = 6.0
# ناحیهٔ امن محتوا برای تست QA (mm): چپ، بالا، راست، پایین
SAFE_RECT_MM = (12.0, 12.0, 198.0, 285.0)
CAPSULE_CY_MM = 291.0  # مرکز کپسول شماره روی خط پایین قاب

_BRAND = "#0B7A6E"
_DEEP = "#0B3050"
_SOFT = "#7FB3A8"


def _corner_dendrite(seed: int) -> str:
    """نقش دندریتی یک گوشه در مختصات محلی (مبدأ گوشه، جهت رشد به داخل: پایین-چپ).

    با transform برای چهار گوشه آینه می‌شود. برد کل نقش ≤ ۱۱mm.
    """
    rng = random.Random(seed)
    parts: list[str] = []

    def branch(x: float, y: float, ang: float, length: float, w: float, depth: int) -> None:
        if depth == 0 or length < 0.8:
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="0.42" fill="{_BRAND}" opacity="0.55"/>')
            return
        x2 = x + math.cos(ang) * length
        y2 = y + math.sin(ang) * length
        qx = x + math.cos(ang + 0.22) * length * 0.55
        qy = y + math.sin(ang + 0.22) * length * 0.55
        parts.append(f'<path d="M {x:.1f} {y:.1f} Q {qx:.1f} {qy:.1f} {x2:.1f} {y2:.1f}" '
                     f'fill="none" stroke="{_BRAND}" stroke-width="{w:.2f}" '
                     f'stroke-linecap="round" opacity="0.5"/>')
        for _ in range(2):
            branch(x2, y2, ang + rng.uniform(-0.55, 0.55),
                   length * rng.uniform(0.58, 0.72), w * 0.66, depth - 1)

    # جهت پایه: قطری به داخل صفحه (در دستگاه صفحه با y رو به پایین: چپ+پایین)
    branch(0, 0, math.radians(135), 4.6, 0.34, 3)
    branch(0, 0, math.radians(112), 3.6, 0.26, 3)
    branch(0, 0, math.radians(160), 3.4, 0.26, 3)
    return "".join(parts)


def _est_text_w(text: str, size_mm: float) -> float:
    return len(text) * size_mm * 0.52


def frame_anatomy_nervous(session: Session, brand: dict[str, str]) -> str:
    corner = _corner_dendrite(seed=session.session_number * 7 + 1)
    # چهار گوشه با آینه‌کردن نقش پایه (مبدأ روی گوشهٔ قاب)
    corners = (
        f'<g transform="translate(204 6)">{corner}</g>'
        f'<g transform="translate(6 6) scale(-1 1)">{corner}</g>'
        f'<g transform="translate(204 291) scale(1 -1)">{corner}</g>'
        f'<g transform="translate(6 291) scale(-1 -1)">{corner}</g>'
    )
    # قطعات میلین روی خط بالا (سمت چپ زبانهٔ سربرگ) + گره‌های رانویه
    myelin = []
    x = 47.0
    for _ in range(5):
        myelin.append(f'<rect x="{x:.1f}" y="5.72" width="7" height="1.75" rx="0.87" '
                      f'fill="{_SOFT}" opacity="0.55"/>')
        x += 7
        myelin.append(f'<circle cx="{x + 1.1:.1f}" cy="6.6" r="0.55" fill="{_BRAND}" opacity="0.6"/>')
        x += 2.2 + 3.4
    tab_text = f"{session.course} — جلسهٔ {fa_num(session.session_number)}"
    tab_w = _est_text_w(tab_text, 3.1) + 7
    tab_x2 = 192.0
    tab_x1 = tab_x2 - tab_w
    foot_r = f"{brand['fa']} · {brand['en']}"
    foot_r_w = _est_text_w(foot_r, 2.9) + 6
    foot_l = brand["series_fa"]
    foot_l_w = _est_text_w(foot_l, 2.9) + 6
    return f'''<svg class="frame-art" viewBox="0 0 210 297" preserveAspectRatio="none"
  xmlns="http://www.w3.org/2000/svg">
  <rect x="6" y="6" width="198" height="285" rx="3.5" fill="none" stroke="{_BRAND}" stroke-width="0.22"/>
  <rect x="7.2" y="7.2" width="195.6" height="282.6" rx="2.8" fill="none" stroke="{_BRAND}" stroke-width="0.11" opacity="0.75"/>
  {corners}
  {"".join(myelin)}
  <!-- زبانهٔ سربرگ روی خط بالا (راست) -->
  <rect x="{tab_x1:.1f}" y="3.9" width="{tab_w:.1f}" height="4.6" fill="white"/>
  <text x="{(tab_x1 + tab_x2) / 2:.1f}" y="7.55" font-size="3.1" font-weight="700"
        fill="{_DEEP}" text-anchor="middle" font-family="Vazirmatn">{escape(tab_text)}</text>
  <!-- برند لاتین سمت مقابل + نشان تک‌رنگ کوچک (اگر دارایی موجود باشد) -->
  <rect x="13" y="3.9" width="34" height="4.6" fill="white"/>
  {f'<image href="{brand["logo_mono_uri"]}" x="13.4" y="3.8" width="5.2" height="5.2" preserveAspectRatio="xMidYMid meet"/>' if brand.get("logo_mono_uri") else ""}
  <text x="{32 if brand.get("logo_mono_uri") else 30}" y="7.5" font-size="2.7" font-weight="700" letter-spacing="0.7"
        fill="{_DEEP}" text-anchor="middle" font-family="DejaVu Sans">{escape(brand['en'])}</text>
  <!-- فوتر روی خط پایین: راست برند، چپ عنوان مجموعه؛ وسط جای کپسول شماره می‌ماند -->
  <rect x="{192 - foot_r_w:.1f}" y="288.9" width="{foot_r_w:.1f}" height="4.4" fill="white"/>
  <text x="{192 - foot_r_w / 2:.1f}" y="292.35" font-size="2.9" font-weight="700"
        fill="{_DEEP}" text-anchor="middle" font-family="Vazirmatn">{escape(foot_r)}</text>
  <rect x="18" y="288.9" width="{foot_l_w:.1f}" height="4.4" fill="white"/>
  <text x="{18 + foot_l_w / 2:.1f}" y="292.35" font-size="2.9"
        fill="{_DEEP}" text-anchor="middle" font-family="Vazirmatn">{escape(foot_l)}</text>
</svg>'''


FRAME_THEMES = {"anatomy-nervous": frame_anatomy_nervous}


def frame_html(session: Session, brand: dict[str, str], font_css: str) -> str | None:
    """سند HTML تک‌صفحه‌ای قاب؛ None یعنی قاب خاموش است."""
    if session.frame_theme == "none":
        return None
    fn = FRAME_THEMES.get(session.frame_theme)
    if fn is None:
        raise ValueError(
            f"تم قاب ناشناخته: «{session.frame_theme}» — تم‌های موجود: {sorted(FRAME_THEMES)} یا none")
    return f"""<!DOCTYPE html><html lang="fa" dir="rtl"><head><meta charset="utf-8">
<style>
{font_css}
@page {{ size: A4; margin: 0; }}
* {{ margin:0; padding:0; }}
.frame-art {{ width:210mm; height:297mm; display:block; }}
</style></head><body>{fn(session, brand)}</body></html>"""
