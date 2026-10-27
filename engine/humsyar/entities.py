"""سیستم رنگ موجودیت‌ها — «رنگ = معنا» (مرحلهٔ ۱ از ارتقای کیفی).

`config/entities.yaml` برای هر موجودیت اصلی (سلول، ساختار، سامانه، جهت فرایند)
یک رنگ ثابت تعریف می‌کند. تطبیق فقط با نام دقیق فارسی/انگلیسی انجام می‌شود —
بدون حدس و بدون تطبیق فازی؛ نامی که در جدول نباشد رنگ نمی‌گیرد.
کاربردها: سربرگ ستون جدول‌های مقایسه‌ای، شاخه‌های درخت طبقه‌بندی، ریل‌های
نمودار فرایند دوجهته و چیپ‌های راهنما. رنگ هرگز تنها حامل معنا نیست؛
همیشه کنار متن/برچسب می‌نشیند تا چاپ سیاه‌وسفید هم خوانا بماند.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "entities.yaml"


@lru_cache(maxsize=4)
def _load(path_str: str) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_name: dict[str, dict[str, Any]] = {}
    by_id: dict[str, dict[str, Any]] = {}
    p = Path(path_str)
    if p.exists():
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        for ent in data.get("entities", []):
            by_id[str(ent["id"])] = ent
            for key in ("fa", "en"):
                for name in ent.get(key, []):
                    by_name[str(name).strip()] = ent
    return by_name, by_id


def entity_for(name: str, config_path: Path | None = None) -> dict[str, Any] | None:
    """موجودیت متناظر با نام دقیق (پس از برش فاصله‌ها) یا None."""
    by_name, _ = _load(str(config_path or CONFIG_PATH))
    return by_name.get(str(name).strip())


def entity_color(name: str, config_path: Path | None = None) -> str | None:
    ent = entity_for(name, config_path)
    return str(ent["color"]) if ent else None


def entity_by_id(eid: str, config_path: Path | None = None) -> dict[str, Any] | None:
    _, by_id = _load(str(config_path or CONFIG_PATH))
    return by_id.get(str(eid))


def entity_css_vars(config_path: Path | None = None) -> str:
    """بلوک متغیرهای CSS برای موجودیت‌ها (تک‌منبع: همین فایل YAML)."""
    _, by_id = _load(str(config_path or CONFIG_PATH))
    decls = "".join(f"--ent-{eid}:{ent['color']};" for eid, ent in by_id.items())
    return f":root{{{decls}}}"
