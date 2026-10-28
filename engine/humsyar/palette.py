"""
خوانندهٔ منبع واحد رنگ‌های برند برای کد پایتون.

توکن‌ها فقط در `engine/themes/brand.css` تعریف شده‌اند؛ این ماژول همان فایل
را می‌خواند تا کاور، قاب، نوار پیشرفت (PyMuPDF) و SVGهای تولیدی دقیقاً از
همان مقادیر استفاده کنند. هیچ فهرست رنگ دومی در کد ساخته نمی‌شود.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

BRAND_CSS = Path(__file__).resolve().parent.parent / "themes" / "brand.css"

_HEX_RE = re.compile(r"--([A-Za-z0-9-]+):\s*(#[0-9A-Fa-f]{6}|#[0-9A-Fa-f]{3})\s*;")


@lru_cache(maxsize=1)
def tokens() -> dict[str, str]:
    """نام توکن ← مقدار HEX (فقط توکن‌هایی که مقدارشان رنگ ساده است)."""
    text = BRAND_CSS.read_text(encoding="utf-8")
    out: dict[str, str] = {}
    for name, value in _HEX_RE.findall(text):
        v = value.upper()
        if len(v) == 4:  # #RGB → #RRGGBB
            v = "#" + "".join(ch * 2 for ch in v[1:])
        out[name] = v
    return out


def hex_of(name: str) -> str:
    """مقدار HEX یک توکن؛ نام ناشناخته خطای صریح می‌دهد (رنگ حدسی ممنوع)."""
    return tokens()[name]


def rgb_of(name: str) -> tuple[float, float, float]:
    """سه‌تایی RGB در بازهٔ ۰..۱ برای PyMuPDF."""
    h = hex_of(name)
    return tuple(int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))  # type: ignore[return-value]


def rgba_of(name: str, alpha: float) -> str:
    """رشتهٔ rgba() برای CSS تولیدی (مثلاً هاله‌های کاور)."""
    h = hex_of(name)
    r, g, b = (int(h[i:i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r},{g},{b},{alpha:g})"


def brand_css_text() -> str:
    """متن کامل brand.css برای تزریق به سندهای HTML کاور/قاب."""
    return BRAND_CSS.read_text(encoding="utf-8")
