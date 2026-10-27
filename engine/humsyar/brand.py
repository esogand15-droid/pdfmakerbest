"""ثابت مرکزی برند هامزیار — تنها منبع نام برند در موتور (config/brand.yaml)."""
from __future__ import annotations

from pathlib import Path

import yaml

_DEFAULTS = {"fa": "هامزیار", "en": "HumsYar", "tagline_fa": "علوم پایهٔ پزشکی",
             "series_fa": "جزوهٔ علوم پایهٔ پزشکی", "latin_line": "HumsYar · Medical Notes"}


def load_brand(repo_root: Path) -> dict[str, str]:
    p = repo_root / "config" / "brand.yaml"
    brand = dict(_DEFAULTS)
    if p.exists():
        brand.update({k: str(v) for k, v in (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).items()})
    return brand
