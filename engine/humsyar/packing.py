"""
بسته‌بندی فضا با look-ahead — پلنر چیدمانِ مرحلهٔ دوم.

روش: ارتفاع واقعی هر بلوک در خود موتور رندر اندازه گرفته می‌شود (measure.mjs)،
بعد صفحه‌بندی در پایتون شبیه‌سازی می‌شود و فقط عملیات مجاز اعمال می‌گردد:
  ۱) کوچک‌کردن تصویر در بازهٔ خوانایی تا در باقیماندهٔ صفحه جا شود؛
  ۲) عقب‌انداختن یک تصویر به اندازهٔ یک بلوک (متن/کادر بعدی جای خالی را پر کند)
     فقط داخل همان بخش و بدون عبور از تیتر؛
  ۳) شکست صفحهٔ تمیز (پیش‌فرض).
تابع هدف: کمینهٔ فضای هدررفته بدون نقض وابستگی معنایی. هر تصمیم لاگ می‌شود.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .model import Block, Session
from .planner import Plan

PAGE_H_MM = 266.0          # ارتفاع مفید شبیه‌سازی (۲۷۰ واقعی منهای حاشیهٔ اطمینان)
MIN_FIG_H_MM = 30.0        # کوچک‌تر از این، تصویر را برای جا شدن خفه نمی‌کنیم
KEEP_TYPES = {"figure", "callout", "process", "dual_process", "tree",
              "checklist", "summary_box", "team_note"}
DEFERRABLE_AFTER = {"paragraph", "callout", "table", "process", "dual_process"}
# پاراگرافی که به شکلِ بعدی اشارهٔ صریح دارد نباید از آن جلو بزند
_FWD_REF_CUES = ("این شکل", "شکل زیر", "این قاب", "این اسلاید", "در تصویر", "این تصویر", "شکل روبه‌رو")


class _Item:
    __slots__ = ("bid", "h", "block", "topic_id", "is_head", "keep")

    def __init__(self, bid: str, h: float, block: Block | None,
                 topic_id: str, is_head: bool = False) -> None:
        self.bid, self.h, self.block = bid, h, block
        self.topic_id, self.is_head = topic_id, is_head
        if block is None or is_head:
            self.keep = True
        elif block.type == "table":
            self.keep = len(block.data.get("rows", [])) <= 5
        else:
            self.keep = block.type in KEEP_TYPES


def measure_blocks(html_path: Path, work: Path,
                   engine_dir: Path) -> tuple[dict[str, float], list[dict]]:
    out = work / "measure.json"
    proc = subprocess.run(
        ["node", str(engine_dir / "measure.mjs"), str(html_path), str(out)],
        cwd=engine_dir, capture_output=True, text=True, timeout=600)
    if proc.returncode != 0 or "MEASURE_OK" not in proc.stdout:
        raise RuntimeError(f"اندازه‌گیری بلوک‌ها ناموفق بود:\n{proc.stdout}\n{proc.stderr}")
    data = json.loads(out.read_text(encoding="utf-8"))
    return {it["bid"]: it["height"] for it in data["blocks"]}, data.get("tocLinks", [])


def _flatten(session: Session, heights: dict[str, float]) -> list[_Item]:
    items: list[_Item] = []
    for t in session.topics:
        items.append(_Item(f"topichead:{t.id}", heights.get(f"topichead:{t.id}", 40.0),
                           None, t.id, is_head=True))
        for b in t.blocks:
            # عضو دوم جفت‌تصویر داخل ارتفاع جفت حساب شده است
            h = 0.0 if b.data.get("_pair_with") else heights.get(b.id, 12.0)
            items.append(_Item(b.id, h, b, t.id, is_head=(b.type == "section")))
    for b in session.closing:
        items.append(_Item(b.id, heights.get(b.id, 12.0), b, "closing",
                           is_head=(b.type == "section")))
    return items


def pack(session: Session, plan: Plan, heights: dict[str, float]) -> list[str]:
    """شبیه‌سازی و اعمال اصلاح‌ها؛ لاگ تصمیم‌ها برگردانده و به plan هم افزوده می‌شود."""
    logs: list[str] = []
    items = _flatten(session, heights)
    # ترتیب جدید بلوک‌ها در هر مبحث (برای اعمال defer)
    order: dict[str, list[Block]] = {t.id: list(t.blocks) for t in session.topics}
    order["closing"] = list(session.closing)

    def note(msg: str) -> None:
        logs.append(msg)
        plan.log(f"[بسته‌بندی] {msg}")

    used = 0.0
    page = 1
    i = 0
    deferred: dict[str, int] = {}
    while i < len(items):
        it = items[i]
        # تیتر باید با دست‌کم بخشی از بلوک بعدی هم‌صفحه بماند
        need = it.h
        if it.is_head and it.block is not None and i + 1 < len(items):
            need += min(items[i + 1].h, 14.0)
        residual = PAGE_H_MM - used
        if need <= residual or used == 0:
            used += it.h
            if used >= PAGE_H_MM:  # بلوکِ قابل‌شکست صفحه را پر کرد
                used = max(0.0, used - PAGE_H_MM)
                page += 1
            i += 1
            continue

        # ——— بلوک جا نمی‌شود؛ عملیات مجاز را امتحان کن ———
        b = it.block
        if (b is not None and b.type == "figure" and b.data.get("_layout") == "full"
                and residual >= MIN_FIG_H_MM + 12):
            # ۱) کوچک‌کردن تصویر برای جا شدن در همین صفحه
            img_h = float(b.data.get("_img_h_mm", it.h))
            cap_h = max(0.0, it.h - img_h)
            target_img_h = residual - cap_h - 3.0
            min_w = float(b.data.get("min_width_mm") or 0)
            w_now = 182.0 * float(b.data.get("_width_pct", 100)) / 100.0
            if target_img_h >= MIN_FIG_H_MM and img_h > 0:
                w_new = w_now * (target_img_h / img_h)
                if w_new >= max(min_w, 55.0):
                    b.data["_width_pct"] = max(30, round(w_new / 182.0 * 100))
                    b.data["_img_h_mm"] = round(target_img_h, 1)
                    note(f"{b.id}: تصویر برای جا شدن در صفحهٔ جاری تا عرض "
                         f"{b.data['_width_pct']}٪ کوچک شد (خوانایی حفظ شده)")
                    used += residual  # صفحه عملاً پر شد
                    used, page = 0.0, page + 1
                    i += 1
                    continue
        if (b is not None and b.type == "figure" and b.data.get("_layout") == "sidecap"
                and residual >= MIN_FIG_H_MM + 12):
            # ۱-ب) کوچک‌کردن تصویرِ کپشن‌کناری برای جا شدن در همین صفحه
            img_h = float(b.data.get("_img_h_mm", it.h))
            if img_h > residual - 3 and img_h > 0:
                from .planner import SIDECAP_COL_MM
                w_now = SIDECAP_COL_MM * float(b.data.get("_width_pct", 100)) / 100.0
                w_new = w_now * ((residual - 3.0) / img_h)
                min_w = float(b.data.get("min_width_mm") or 0)
                if w_new >= max(min_w, 50.0):
                    b.data["_width_pct"] = max(35, round(w_new / SIDECAP_COL_MM * 100))
                    b.data["_img_h_mm"] = round(residual - 3.0, 1)
                    note(f"{b.id}: تصویر کپشن‌کناری برای جا شدن در صفحهٔ جاری کوچک شد")
                    used, page = 0.0, page + 1
                    i += 1
                    continue
        if b is not None and b.type == "figure" and deferred.get(b.id, 0) < 2:
            # ۲) کشیدن بلوک‌های مستقل از پنجرهٔ سه بلوک بعدی به جای خالی همین صفحه (حداکثر دو بار برای هر شکل)
            pulled = False
            for j in range(i + 1, min(i + 4, len(items))):
                nxt = items[j]
                if nxt.topic_id != it.topic_id or nxt.is_head:
                    break
                nb = nxt.block
                if nb is None or nb.type not in DEFERRABLE_AFTER or nxt.h > residual:
                    continue
                txt = str(nb.data.get("text", ""))
                if nb.type == "paragraph" and any(c in txt for c in _FWD_REF_CUES):
                    continue
                lst = order[it.topic_id]
                ia, ib = lst.index(b), lst.index(nb)
                lst.insert(ia, lst.pop(ib))
                items.insert(i, items.pop(j))
                deferred[b.id] = deferred.get(b.id, 0) + 1
                note(f"{b.id}: بلوک «{nxt.bid}» از پنجرهٔ بعدی جلو کشیده شد تا جای خالی "
                     f"انتهای صفحه پر شود (همان بخش، بدون ارجاع پیش‌رو به شکل)")
                pulled = True
                break
            if pulled:
                continue
        # ۳) شکست تمیز صفحه
        used = 0.0
        page += 1

    for t in session.topics:
        t.blocks = order[t.id]
    session.closing = order["closing"]
    note(f"شبیه‌سازی بسته‌بندی: ≈{page} صفحهٔ بدنه")
    return logs
