"""
خوانندهٔ منبع واحد رنگ‌های برند برای کد پایتون + مشتق‌سازی نقش‌محور رنگ مبحث.

توکن‌ها فقط در `engine/themes/brand.css` تعریف شده‌اند؛ این ماژول همان فایل
را می‌خواند (شامل حل زنجیرهٔ var()) تا کاور، قاب، نوار پیشرفت (PyMuPDF) و
SVGهای تولیدی دقیقاً از همان مقادیر استفاده کنند. هیچ فهرست رنگ دومی در کد
ساخته نمی‌شود؛ رنگ مبحث از «شمارهٔ مبحث» می‌آید (نقش)، هرگز از محتوا.
"""
from __future__ import annotations

import colorsys
import re
from functools import lru_cache
from pathlib import Path

BRAND_CSS = Path(__file__).resolve().parent.parent / "themes" / "brand.css"

_DECL_RE = re.compile(r"--([A-Za-z0-9-]+):\s*([^;]+);")
_HEX_FULL = re.compile(r"^#[0-9A-Fa-f]{6}$|^#[0-9A-Fa-f]{3}$")
_VAR_RE = re.compile(r"^var\(\s*--([A-Za-z0-9-]+)\s*\)$")


@lru_cache(maxsize=1)
def tokens() -> dict[str, str]:
    """نام توکن ← مقدار HEX؛ ارجاع‌های var() به‌صورت بازگشتی حل می‌شوند."""
    text = BRAND_CSS.read_text(encoding="utf-8")
    raw: dict[str, str] = {n: v.strip() for n, v in _DECL_RE.findall(text)}

    def resolve(name: str, seen: frozenset) -> str | None:
        if name in seen or name not in raw:
            return None
        v = raw[name]
        if _HEX_FULL.match(v):
            v = v.upper()
            return "#" + "".join(ch * 2 for ch in v[1:]) if len(v) == 4 else v
        m = _VAR_RE.match(v)
        if m:
            return resolve(m.group(1), seen | {name})
        return None

    out: dict[str, str] = {}
    for name in raw:
        r = resolve(name, frozenset())
        if r:
            out[name] = r
    return out


def hex_of(name: str) -> str:
    """مقدار HEX یک توکن؛ نام ناشناخته خطای صریح می‌دهد (رنگ حدسی ممنوع)."""
    return tokens()[name]


def _rgb01(hexv: str) -> tuple[float, float, float]:
    return tuple(int(hexv[i:i + 2], 16) / 255 for i in (1, 3, 5))  # type: ignore[return-value]


def rgb_of(name: str) -> tuple[float, float, float]:
    """سه‌تایی RGB در بازهٔ ۰..۱ برای PyMuPDF."""
    return _rgb01(hex_of(name))


def rgb_of_hex(hexv: str) -> tuple[float, float, float]:
    return _rgb01(hexv)


def rgba_of(name: str, alpha: float) -> str:
    """رشتهٔ rgba() برای CSS تولیدی (مثلاً هاله‌های کاور)."""
    r, g, b = (round(c * 255) for c in _rgb01(hex_of(name)))
    return f"rgba({r},{g},{b},{alpha:g})"


def brand_css_text() -> str:
    """متن کامل brand.css برای تزریق به سندهای HTML کاور/قاب."""
    return BRAND_CSS.read_text(encoding="utf-8")


# ---------------------------------------------------------------- مشتق‌سازی HSL
def _lum(hexv: str) -> float:
    def f(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = _rgb01(hexv)
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _to_hex(r: float, g: float, b: float) -> str:
    return "#%02X%02X%02X" % tuple(round(c * 255) for c in (r, g, b))


def mix_hex(c1: str, c2: str, p: float) -> str:
    """ترکیب خطی دو رنگ: p سهم رنگ اول."""
    a, b = _rgb01(c1), _rgb01(c2)
    return _to_hex(*[a[i] * p + b[i] * (1 - p) for i in range(3)])


def derive_deep(hexv: str, bg: str, ratio: float = 4.6) -> str:
    """تیره‌کردن HSL تا رسیدن به کنتراست هدف روی پس‌زمینه — مشتق خودکار رنگ."""
    r, g, b = _rgb01(hexv)
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    while l > 0.02 and contrast(_to_hex(*colorsys.hls_to_rgb(h, l, s)), bg) < ratio:
        l -= 0.01
    return _to_hex(*colorsys.hls_to_rgb(h, l, s))


# ---------------------------------------------------------------- رنگ مبحث
CHAPTER_COUNT = 8


def chapter_accent(number: int) -> str:
    """رنگ مبحث فقط از شمارهٔ آن: accent[(number-1) mod 8]."""
    return hex_of(f"chapter-{((int(number) - 1) % CHAPTER_COUNT) + 1}")


def chapter_vars(number: int) -> dict[str, str]:
    """متغیرهای CSS یک مبحث: پایه، متن امن روی روشن، پس‌زمینهٔ هدر (متن سفید)، نرم."""
    base = chapter_accent(number)
    paper = hex_of("paper")
    return {
        "--chapter-accent": base,
        "--chapter-deep": derive_deep(base, paper, 4.6),
        "--chapter-header": derive_deep(base, "#FFFFFF", 4.55),
        "--chapter-soft": mix_hex(base, paper, 0.10),
    }


def chapter_style(number: int) -> str:
    """رشتهٔ style آماده برای wrapper مبحث."""
    return ";".join(f"{k}:{v}" for k, v in chapter_vars(number).items())
