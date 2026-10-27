"""ثابت مرکزی برند هامزیار — تنها منبع نام و دارایی برند در موتور (config/brand.yaml)."""
from __future__ import annotations

from pathlib import Path

import yaml

_DEFAULTS = {"fa": "هامزیار", "en": "HumsYar", "tagline_fa": "علوم پایهٔ پزشکی",
             "series_fa": "جزوهٔ علوم پایهٔ پزشکی", "latin_line": "HumsYar · Medical Notes",
             "logo": "assets/brand/logo.png", "logo_mono": "assets/brand/logo_mono.png",
             "favicon": "assets/brand/favicon.png"}


def load_brand(repo_root: Path) -> dict[str, str]:
    p = repo_root / "config" / "brand.yaml"
    brand = dict(_DEFAULTS)
    if p.exists():
        brand.update({k: str(v) for k, v in (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).items()})
    # مسیر دارایی‌های لوگو فقط وقتی فایل واقعاً هست به URI تبدیل می‌شود؛
    # نبود فایل یعنی بازگشت به برند تایپوگرافیک (هرگز مسیر جعلی ساخته نمی‌شود).
    for key, uri_key in (("logo", "logo_uri"), ("logo_mono", "logo_mono_uri"),
                         ("favicon", "favicon_uri")):
        f = (repo_root / brand.get(key, "")).resolve()
        brand[uri_key] = f"file://{f}" if brand.get(key) and f.exists() else ""
    return brand
