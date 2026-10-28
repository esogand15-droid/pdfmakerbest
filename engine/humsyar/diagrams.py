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


def _wrap(text: str, max_chars: int, max_lines: int = 2) -> list[str]:
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
    if len(lines) > max_lines:  # بدون برش متن: خطوط اضافه در خط آخر ادغام می‌شوند
        lines = lines[: max_lines - 1] + [" ".join(lines[max_lines - 1:])]
    return lines


DEFAULT_STYLE = {
    "fs_label": FS_LABEL, "fs_note": FS_NOTE, "gap_x": GAP_X, "gap_y": GAP_Y,
    "pad_x": PAD_X, "node_h": NODE_H, "max_w": 215,
    "wrap_label": 26, "wrap_note": 30, "wrap_by_depth": {}, "wrap_note_by_depth": {},
    "char_w": CHAR_W, "lh_label": 1.28, "lh_note": 1.32, "pad_y": 9,
    "max_label_lines": 2, "max_note_lines": 2,
}


def _style(style: dict[str, Any] | None) -> dict[str, Any]:
    st = dict(DEFAULT_STYLE)
    if style:
        st.update(style)
    return st


def _prepare(node: dict[str, Any], depth: int = 0,
             st: dict[str, Any] | None = None) -> dict[str, Any]:
    st = _style(st) if st is None or depth == 0 else st
    wrap_l = st["wrap_by_depth"].get(depth, st["wrap_label"])
    label_lines = _wrap(node["label"], wrap_l, st["max_label_lines"])
    wrap_n = st["wrap_note_by_depth"].get(depth, st["wrap_note"])
    note_lines = (_wrap(node["note"], wrap_n, st["max_note_lines"])
                  if node.get("note") else [])
    w = max([len(l) * st["fs_label"] * st["char_w"] for l in label_lines]
            + [len(l) * st["fs_note"] * st["char_w"] for l in note_lines]
            + [st.get("min_w", 44)]) + 2 * st["pad_x"]
    lh_l, lh_n = st["fs_label"] * st["lh_label"], st["fs_note"] * st["lh_note"]
    h = max(st["node_h"], st["pad_y"] + len(label_lines) * lh_l + len(note_lines) * lh_n)
    children = [_prepare(c, depth + 1, st) for c in node.get("children", [])]
    sub_h = sum(c["sub_h"] for c in children) + st["gap_y"] * max(0, len(children) - 1)
    return {
        "label_lines": label_lines, "note_lines": note_lines,
        "alert": bool(node.get("alert")), "w": min(w, st["max_w"]), "h": h,
        "children": children, "depth": depth, "st": st,
        "sub_h": max(h, sub_h),
    }


def _columns(tree: dict[str, Any], st: dict[str, Any]):
    col_w: dict[int, float] = {}

    def scan(n: dict[str, Any]) -> None:
        col_w[n["depth"]] = max(col_w.get(n["depth"], 0), n["w"])
        for c in n["children"]:
            scan(c)

    scan(tree)
    col_x: dict[int, float] = {}
    x = 0.0
    for d in range(max(col_w), -1, -1):
        col_x[d] = x
        x += col_w[d] + st["gap_x"]
    return col_w, col_x, x - st["gap_x"]


# سبک درخت تمام‌صفحه: واحدها pt در مقیاس چاپ (عرض صفحهٔ متن ۵۱۶pt).
# مؤثر در چاپ: برچسب ≈۸٫۶pt و یادداشت ≈۷٫۹pt — بالاتر از کف خوانایی ۷٫۵pt.
PAGE_STYLE = {
    "fs_label": 9.4, "fs_note": 8.6, "gap_x": 10, "gap_y": 2.0, "pad_x": 5.5,
    "pad_y": 5, "node_h": 16, "max_w": 150, "min_w": 34, "wrap_label": 16,
    "wrap_note": 22, "char_w": 0.46,
    "wrap_by_depth": {0: 9, 1: 22, 2: 23, 3: 18, 4: 16, 5: 15},
    "wrap_note_by_depth": {3: 22, 4: 22, 5: 22},
    "lh_label": 1.18, "lh_note": 1.24, "max_label_lines": 3, "max_note_lines": 4,
}


def measure_tree(root: dict[str, Any], style: dict[str, Any] | None = None):
    """ابعاد (عرض، ارتفاع) درخت با سبک داده‌شده — برای کنترل جاگیری در صفحه."""
    st = _style(style)
    tree = _prepare(root, 0, st)
    _cw, _cx, total_w = _columns(tree, st)
    return total_w, tree["sub_h"]


def tree_svg(root: dict[str, Any], color_for=None,
             style: dict[str, Any] | None = None) -> str:
    st = _style(style)
    tree = _prepare(root, 0, st)
    col_w, col_x, total_w = _columns(tree, st)
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
            child_top += c["sub_h"] + st["gap_y"]
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
        lh_l, lh_n = st["fs_label"] * st["lh_label"], st["fs_note"] * st["lh_note"]
        lines_h = len(n["label_lines"]) * lh_l + len(n["note_lines"]) * lh_n
        ty = cy - lines_h / 2
        for l in n["label_lines"]:
            ty += lh_l
            parts.append(f'<text x="{nx + n["w"] / 2:.0f}" y="{ty - lh_l * 0.22:.0f}" '
                         f'class="tree-label">{escape(l)}</text>')
        for l in n["note_lines"]:
            ty += lh_n
            parts.append(f'<text x="{nx + n["w"] / 2:.0f}" y="{ty - lh_n * 0.24:.0f}" '
                         f'class="tree-note">{escape(l)}</text>')
        parts.append("</g>")
        return cy

    place(tree, 0)
    return (
        f'<svg class="tree-svg" viewBox="0 0 {total_w:.0f} {total_h:.0f}" '
        f'style="--tl-fs:{st["fs_label"]}px;--tn-fs:{st["fs_note"]}px" '
        f'xmlns="http://www.w3.org/2000/svg" role="img">{"".join(parts)}</svg>'
    )


import re as _re

_FA_D = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def _fa(v) -> str:
    return str(v).translate(_FA_D)


def _clean(text: str) -> str:
    """حذف نشانه‌گذاری درون‌خطی برای برچسب گره (متن علمی دست‌نخورده می‌ماند)."""
    t = _re.sub(r"\[\[term:(.+?)\|(.+?)\]\]", r"\1", str(text))
    t = _re.sub(r"\[\[num:(.+?)\]\]", r"\1", t)
    t = _re.sub(r"\[en:([^\]]+)\]", r"\1", t)
    return " ".join(t.replace("**", "").split())


def _norm_key(t: str) -> str:
    return _clean(t).replace(" ", "").replace("\u200c", "")


def _tree_labels(node: dict[str, Any], acc: set) -> set:
    acc.add(_norm_key(str(node.get("label", ""))))
    for c in node.get("children", []) or []:
        _tree_labels(c, acc)
    return acc


def _section_node(section, blocks, grafted: list[dict[str, Any]],
                  graft_labels: set | None = None) -> dict[str, Any]:
    children: list[dict[str, Any]] = []
    if graft_labels is None:
        graft_labels = set()
        for g in grafted:
            _tree_labels(g, graft_labels)
    for sb in blocks:
        d = sb.data
        if sb.type == "table":
            rows = [_clean(r[0]) for r in d.get("rows", []) if r and str(r[0]).strip()]
            if graft_labels and rows:
                hit = sum(1 for r in rows
                          if any(_norm_key(r) in g or g in _norm_key(r) for g in graft_labels))
                if hit >= max(1, round(0.7 * len(rows))):
                    continue  # همان طبقه‌بندی در درخت پیوندی هست؛ تکرار نمی‌شود
            node: dict[str, Any] = {"label": _clean(d.get("title", "جدول"))}
            if 3 <= len(rows) <= 4:      # طبقه‌بندی کوچک: هر ردیف یک شاخه
                node["children"] = [{"label": r} for r in rows]
            elif 0 < len(rows) <= 2:     # دو حالت: در یادداشت گره
                node["note"] = " · ".join(rows)
            # جدول بزرگ: فقط عنوان در درخت؛ ردیف‌ها در خود جدول و نقشهٔ مرور کامل‌اند
            children.append(node)
        elif sb.type == "dual_process":
            lanes = []
            for key in ("forward", "backward"):
                lane = d.get(key) or {}
                if lane.get("title"):
                    heads = [str(st.get("head", "")) if isinstance(st, dict) else str(st)
                             for st in lane.get("steps", [])]
                    lanes.append((_clean(lane["title"]), [h for h in heads if h]))
            node = {"label": _clean(d.get("title", "فرایند")), "children": []}
            same_steps = len(lanes) == 2 and lanes[0][1] == lanes[1][1] and lanes[0][1]
            if same_steps:  # گام‌های دو جهت یکی است؛ یک‌بار در والد می‌آید
                node["note"] = " · ".join(lanes[0][1])
                node["children"] = [{"label": t} for t, _h in lanes]
            else:
                node["children"] = [{"label": t, "note": " · ".join(h)}
                                    for t, h in lanes]
            children.append(node)
        elif sb.type == "tree" and d.get("root"):
            children.append(d["root"])
    children.extend(grafted)
    return {"label": _clean(section.data.get("title", "")), "children": children}


def session_tree(session, root_label: str, root_note: str = "") -> dict[str, Any]:
    """درخت جامع جلسه فقط از ساختار و عبارات خود محتوا ساخته می‌شود:
    ریشه ← مبحث ← بخش ← (جدول/فرایند/درخت تألیفی) + اصطلاحات کلیدی هر مبحث.
    درخت‌های تألیفیِ بخش پایانی با attach_to به بخش مربوط پیوند می‌خورند."""
    grafts: dict[str, list] = {}
    loose: list = []
    for b in session.closing:
        if b.type == "tree" and b.data.get("root"):
            tgt = b.data.get("attach_to")
            if tgt:
                grafts.setdefault(str(tgt), []).append(b.data["root"])
            else:
                loose.append(b.data["root"])
    topics: list[dict[str, Any]] = []
    for t in session.topics:
        groups: list[tuple[Any, list]] = []
        for b in t.blocks:
            if b.type == "section":
                groups.append((b, []))
            elif groups:
                groups[-1][1].append(b)
        topic_grafts = grafts.get(t.id, [])
        all_graft_labels: set = set()
        for g in topic_grafts:
            _tree_labels(g, all_graft_labels)
        for sec, _b in groups:
            for g in grafts.get(sec.id, []):
                _tree_labels(g, all_graft_labels)
        # درخت پیوندیِ سطح مبحث اول می‌آید: نمای کلی طبقه‌بندی، بعد جزئیات بخش‌ها
        children = list(topic_grafts) + [
            _section_node(sec, blks, grafts.get(sec.id, []), all_graft_labels)
            for sec, blks in groups]
        topics.append({"label": f"مبحث {_fa(t.number)}: {_clean(t.title)}",
                       "children": children})
    # پیوندی که هدفش پیدا نشود هرگز گم نمی‌شود: در سطح ریشه می‌آید
    known = {t.id for t in session.topics}
    for t in session.topics:
        known |= {b.id for b in t.blocks if b.type == "section"}
    for tgt, roots in grafts.items():
        if tgt not in known:
            loose.extend(roots)
    return {"label": root_label, "note": root_note,
            "children": topics + loose}
