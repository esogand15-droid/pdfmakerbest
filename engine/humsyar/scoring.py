"""
امتیازدهی کاندیدهای چیدمان (Layout Candidate Scorer) — راند ۴.

برای هر شکل/فرایند، چند کاندید معتبر ساخته و با یک تابع امتیاز قطعی و قابل‌تنظیم
سنجیده می‌شود. محدودیت‌های سخت (سقف ارتفاع، کف خوانایی برچسب، نیاز side به متن
لنگر، درخواست صریح داده) پیش از امتیازدهی به‌صورت فیلتر اعمال می‌شوند و هیچ وزنی
نمی‌تواند آن‌ها را دور بزند. همهٔ کاندیدها و امتیازها در گزارش تصمیم‌ها ثبت می‌شوند
تا هر انتخاب قابل ممیزی باشد.

وزن‌ها و قرابت کهن‌الگوها از config/layout.yaml خوانده می‌شوند (حافظهٔ طراحی)؛
نبود فایل یعنی پیش‌فرض‌های همین ماژول.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_DEFAULT_WEIGHTS = {
    "content_fit": 0.30, "aspect_fit": 0.20, "readability": 0.20,
    "density": 0.10, "diversity": 0.10, "continuity": 0.05, "print_safety": 0.05,
}
_DEFAULT_PREFS = {"diversity_strength": 0.7, "diversity_epsilon": 0.06,
                  "prefer_calm_text_pages": True}
_DEFAULT_AFFINITY: dict[str, dict[str, float]] = {
    "figure_centric": {"full": 0.85, "sidecap": 0.80, "side": 0.70},
    "comparison": {"full": 0.80, "sidecap": 0.65, "side": 0.55},
    "process": {"full": 0.80, "sidecap": 0.70, "side": 0.75},
    "explanatory": {"full": 0.60, "sidecap": 0.85, "side": 0.90},
    "classification": {"full": 0.75, "sidecap": 0.75, "side": 0.70},
    "definition_led": {"full": 0.70, "sidecap": 0.80, "side": 0.75},
    "summary": {"full": 0.75, "sidecap": 0.75, "side": 0.70},
    "mixed": {"full": 0.75, "sidecap": 0.75, "side": 0.70},
}


def load_layout_config(repo_root: Path) -> dict[str, Any]:
    cfg: dict[str, Any] = {
        "weights": dict(_DEFAULT_WEIGHTS),
        "preferences": dict(_DEFAULT_PREFS),
        "affinity": {k: dict(v) for k, v in _DEFAULT_AFFINITY.items()},
    }
    p = repo_root / "config" / "layout.yaml"
    if p.exists():
        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        if isinstance(raw.get("weights"), dict):
            cfg["weights"].update({k: float(v) for k, v in raw["weights"].items()})
        if isinstance(raw.get("preferences"), dict):
            cfg["preferences"].update(raw["preferences"])
        if isinstance(raw.get("affinity"), dict):
            for k, v in raw["affinity"].items():
                if isinstance(v, dict):
                    cfg["affinity"].setdefault(k, {}).update(
                        {kk: float(vv) for kk, vv in v.items()})
    return cfg


def aspect_fit(layout: str, aspect_wh: float, h_over_w: float) -> float:
    """تناسب نسبت ابعاد تصویر با نوع چیدمان (۰..۱)."""
    if aspect_wh >= 1.3:      # عریض
        return {"full": 1.0, "sidecap": 0.35, "side": 0.50}[layout]
    if h_over_w >= 0.8:       # عمودی/مربعی
        return {"full": 0.55, "sidecap": 1.0, "side": 0.95}[layout]
    return {"full": 0.80, "sidecap": 0.80, "side": 0.70}[layout]


def score_figure_candidate(cand: dict[str, Any], *, archetype: str,
                           aspect_wh: float, h_over_w: float,
                           prev_layout: str | None, cfg: dict[str, Any]) -> dict[str, float]:
    """اجزای امتیاز یک کاندید شکل؛ cand باید disp_mm/img_h_mm/eff_dpi داشته باشد."""
    layout = cand["layout"]
    aff = cfg["affinity"].get(archetype, cfg["affinity"]["mixed"])
    strength = float(cfg["preferences"].get("diversity_strength", 0.7))
    parts = {
        "content_fit": float(aff.get(layout, 0.7)),
        "aspect_fit": aspect_fit(layout, aspect_wh, h_over_w),
        "readability": round(0.6 * min(1.0, cand["eff_dpi"] / 180.0)
                             + 0.4 * min(1.0, cand["disp_mm"] / 130.0), 3),
        "density": round(1.0 - min(1.0, cand["img_h_mm"] / 240.0), 3),
        "diversity": 1.0 if layout != prev_layout else round(1.0 - 0.55 * strength, 3),
        "continuity": {"side": 1.0, "sidecap": 0.85, "full": 0.70}[layout],
        "print_safety": round(1.0 - max(0.0, cand["img_h_mm"] - 100.0) / 300.0, 3),
    }
    w = cfg["weights"]
    total = sum(float(w.get(k, 0.0)) * v for k, v in parts.items())
    return {"total": round(total, 4), **{k: round(v, 3) for k, v in parts.items()}}


def score_process_variant(variant: str, *, steps: int, prev_variant: str | None,
                          cfg: dict[str, Any]) -> dict[str, float]:
    """امتیاز گونهٔ نمایش فرایند: نوار افقی در برابر گام‌های عمودی."""
    strength = float(cfg["preferences"].get("diversity_strength", 0.7))
    if variant == "strip":
        parts = {"content_fit": 0.80, "density": 0.95, "readability": 0.80,
                 "continuity": 0.85}
    else:
        parts = {"content_fit": 0.85, "density": round(1.0 - min(1.0, steps / 9.0), 3),
                 "readability": 0.90, "continuity": 0.80}
    parts["diversity"] = 1.0 if variant != prev_variant else round(1.0 - 0.55 * strength, 3)
    w = cfg["weights"]
    total = (float(w.get("content_fit", 0.3)) * parts["content_fit"]
             + float(w.get("density", 0.1)) * parts["density"]
             + float(w.get("readability", 0.2)) * parts["readability"]
             + float(w.get("continuity", 0.05)) * parts["continuity"]
             + float(w.get("diversity", 0.1)) * parts["diversity"])
    return {"total": round(total, 4), **{k: round(v, 3) for k, v in parts.items()}}
