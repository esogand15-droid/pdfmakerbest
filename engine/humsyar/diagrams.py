"""
ساخت نمودار درختی طبقه‌بندی به صورت SVG از روی دادهٔ ساختاریافته.

چرا SVG با متن واقعی؟ چون در PDF قابل جست‌وجو می‌ماند و در هر مقیاسی تیز چاپ می‌شود.
جهت خواندن فارسی: ریشه در راست، هر سطح یک ستون به چپ. خطوط اتصال منحنی ملایم.

قرارداد داده:
  node = {"label": str, "note": str?, "alert": bool?, "children": [node...]}
«alert» برای استثناها (مثلاً میکروگلیا با منشأ متفاوت) — با حاشیهٔ نقطه‌چین و برچسب.
"""
from __future__ import annotations

from html import escape
from typing import Any

# هندسه (واحد: px در viewBox؛ با CSS به عرض صفحه مقیاس می‌شود)
FS_LABEL = 12.5      # اندازهٔ فونت برچسب در SVG
FS_NOTE = 10.5
NODE_H = 34
GAP_Y = 10
GAP_X = 34           # فاصلهٔ افقی بین ستون‌ها (جای خط اتصال)
CHAR_W = 0.52        # ضریب تخمین عرض نویسهٔ فارسی نسبت به اندازهٔ فونت
PAD_X = 10


def _est_width(text: str, fs: float) -> float:
    return len(text) * fs * CHAR_W


def _wrap(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > max_chars and cur:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines[:2]  # حداکثر دو خط در گره؛ جزئیات بیشتر جای در جدول/متن است


def _prepare(node: dict[str, Any], depth: int = 0) -> dict[str, Any]:
    label_lines = _wrap(node["label"], 26)
    note_lines = _wrap(node["note"], 30) if node.get("note") else []
    w = max([_est_width(l, FS_LABEL) for l in label_lines]
            + [_est_width(l, FS_NOTE) for l in note_lines] + [60]) + 2 * PAD_X
    h = max(NODE_H, 12 + len(label_lines) * 16 + len(note_lines) * 14)
    children = [_prepare(c, depth + 1) for c in node.get("children", [])]
    sub_h = sum(c["sub_h"] for c in children) + GAP_Y * max(0, len(children) - 1)
    return {
        "label_lines": label_lines, "note_lines": note_lines,
        "alert": bool(node.get("alert")), "w": min(w, 215), "h": h,
        "children": children, "depth": depth,
        "sub_h": max(h, sub_h),
    }


def tree_svg(root: dict[str, Any], color_for=None) -> str:
    tree = _prepare(root)
    # عرض هر ستون = عریض‌ترین گرهٔ آن عمق
    col_w: dict[int, float] = {}

    def scan(n: dict[str, Any]) -> None:
        col_w[n["depth"]] = max(col_w.get(n["depth"], 0), n["w"])
        for c in n["children"]:
            scan(c)

    scan(tree)
    max_depth = max(col_w)
    # موقعیت x ستون‌ها از راست (ریشه) به چپ
    col_x: dict[int, float] = {}
    x = 0.0
    for d in range(max_depth, -1, -1):
        col_x[d] = x
        x += col_w[d] + GAP_X
    total_w = x - GAP_X
    total_h = tree["sub_h"]

    parts: list[str] = []

    def place(n: dict[str, Any], top: float) -> float:
        """برگرداندن y مرکز گره؛ رسم گره و فرزندان از بالا."""
        cy = top + n["sub_h"] / 2
        nx = col_x[n["depth"]] + (col_w[n["depth"]] - n["w"])  # چسبیده به راست ستون
        ny = cy - n["h"] / 2
        n["_x"], n["_cy"] = nx, cy
        child_top = top
        for c in n["children"]:
            ccy = place(c, child_top)
            child_top += c["sub_h"] + GAP_Y
            # خط منحنی از لبهٔ چپ والد به لبهٔ راست فرزند
            x1, x2 = nx, c["_x"] + c["w"]
            mx = (x1 + x2) / 2
            _cc = color_for(c) if color_for else None
            _ls = f' style="stroke:{_cc}"' if _cc else ""
            parts.append(
                f'<path d="M {x1:.0f} {cy:.0f} C {mx:.0f} {cy:.0f}, {mx:.0f} {ccy:.0f}, '
                f'{x2:.0f} {ccy:.0f}" class="tree-link"{_ls}/>'
            )
        # خود گره
        cls = "tree-node tree-node--alert" if n["alert"] else "tree-node"
        if n["depth"] == 0:
            cls += " tree-node--root"
        _nc = color_for(n) if color_for else None
        _rs = f' style="stroke:{_nc}"' if _nc else ""
        parts.append(
            f'<g class="{cls}"><rect x="{nx:.0f}" y="{ny:.0f}" width="{n["w"]:.0f}" '
            f'height="{n["h"]:.0f}" rx="8"{_rs}/>'
        )
        lines_h = len(n["label_lines"]) * 16 + len(n["note_lines"]) * 14
        ty = cy - lines_h / 2
        for l in n["label_lines"]:
            ty += 13
            parts.append(f'<text x="{nx + n["w"] / 2:.0f}" y="{ty:.0f}" '
                         f'class="tree-label">{escape(l)}</text>')
            ty += 3
        for l in n["note_lines"]:
            ty += 11
            parts.append(f'<text x="{nx + n["w"] / 2:.0f}" y="{ty:.0f}" '
                         f'class="tree-note">{escape(l)}</text>')
            ty += 3
        parts.append("</g>")
        return cy

    place(tree, 0)
    return (
        f'<svg class="tree-svg" viewBox="0 0 {total_w:.0f} {total_h:.0f}" '
        f'xmlns="http://www.w3.org/2000/svg" role="img">{"".join(parts)}</svg>'
    )
