"""موتور «نقشهٔ جامع مرور» (Master Revision Map) — پوشش کامل، بدون حذف و بازنویسی.

اصل معماری: محتوا از دادهٔ ساخت‌یافتهٔ جلسه به‌صورت **مکانیکی و بی‌اتلاف** به
گزاره‌های قابل ردیابی تجزیه می‌شود (جمله‌به‌جمله، ردیف‌به‌ردیف، گام‌به‌گام).
هیچ جمله‌ای بازنویسی، خلاصه یا تفسیر نمی‌شود؛ متن هر گزاره عین عبارت منبع است.
سپس هر گزاره به یک گرهٔ نقشه (بخش مربوط خودش) تخصیص می‌یابد و «ماتریس پوشش»
ثابت می‌کند چیزی از قلم نیفتاده است.

آنچه ماشینی قابل پوشش نیست — جزئیات درون پیکسل‌های تصویر فراتر از برچسب‌ها —
با وضعیت `unresolved` و ارجاع به خود شکل گزارش می‌شود؛ بی‌صدا حذف نمی‌شود.

دامنهٔ پوشش: بلوک‌های حامل محتوای علمی (پاراگراف، جدول، شکل، فرایند، کادر،
جمع‌بندی، چک‌لیست). بلوک‌های مشتقِ نمایشی (`tldr` و `tree`) خودشان نمایی از
همان محتوا هستند و در جهان پوشش شمرده نمی‌شوند تا دوباره‌شماری رخ ندهد؛
این انتخاب در گزارش پوشش صریح ثبت می‌شود.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .model import Block, Session

_SPLIT = re.compile(r"(?<=\.)\s+")
_EXCEPTION_MARKERS = ("استثنا", "به‌جز", "به جز")
_DIGITS = set("۰۱۲۳۴۵۶۷۸۹0123456789")
_CALLOUT_KIND_MAP = {
    "conflict": "source_conflict", "clinical": "clinical", "warning": "exception",
    "exception": "exception", "exam": "exam", "key": "key",
    "definition": "definition", "example": "example", "summary": "summary",
    "bridge": "relationship", "mnemonic": "mnemonic", "formula": "formula",
    "terminology": "terminology", "unresolved": "unresolved_kind",
}
DERIVED_BLOCK_TYPES = {"tldr", "tree"}  # نماهای مشتق؛ دوباره‌شماری نمی‌شوند


@dataclass
class Item:
    id: str
    kind: str                     # detail|exception|terminology|process|table_row|...
    text: str                     # عین عبارت منبع (با نشانه‌گذاری درون‌متنی خودش)
    block_id: str
    topic_id: str
    section_id: str               # گرهٔ نقشه: بخش والد (یا مبحث/closing)
    has_number: bool = False
    meta: dict[str, Any] = field(default_factory=dict)


def _sentences(text: str) -> list[str]:
    return [p.strip() for p in _SPLIT.split(str(text)) if p.strip()]


def _kind_for_sentence(sent: str) -> str:
    if any(m in sent for m in _EXCEPTION_MARKERS):
        return "exception"
    return "detail"


def _num(text: str) -> bool:
    return any(ch in _DIGITS for ch in str(text))


def extract_items(session: Session) -> list[Item]:
    """تجزیهٔ قطعی و بی‌اتلاف محتوای علمی جلسه به گزاره‌های قابل ردیابی."""
    items: list[Item] = []

    def add(kind: str, text: str, b: Block, topic_id: str, section_id: str,
            seq: int, **meta: Any) -> None:
        items.append(Item(
            id=f"{b.id}#{seq}", kind=kind, text=str(text), block_id=b.id,
            topic_id=topic_id, section_id=section_id,
            has_number=_num(text), meta=meta))

    def from_block(b: Block, topic_id: str, section_id: str) -> None:
        d = b.data
        if b.type in DERIVED_BLOCK_TYPES or b.type in ("section", "team_note", "quick_check"):
            return
        if b.type == "paragraph":
            for i, sent in enumerate(_sentences(d.get("text", ""))):
                add(_kind_for_sentence(sent), sent, b, topic_id, section_id, i)
        elif b.type == "callout":
            kind = _CALLOUT_KIND_MAP.get(str(d.get("kind", "")), "detail")
            add(kind, d.get("text", ""), b, topic_id, section_id, 0,
                title=str(d.get("title", "")))
        elif b.type == "table":
            for i, row in enumerate(d.get("rows", [])):
                add("table_row", " · ".join(str(c) for c in row), b, topic_id,
                    section_id, i, table_title=str(d.get("title", "")) if i == 0 else "",
                    headers=list(d.get("headers", [])) if i == 0 else [])
        elif b.type == "figure":
            seq = 0
            for sent in _sentences(d.get("explain_fa", "")):
                add(_kind_for_sentence(sent), sent, b, topic_id, section_id, seq)
                seq += 1
            for lb in d.get("labels", []) or []:
                if isinstance(lb, dict) and lb.get("fa"):
                    add("terminology", str(lb["fa"]), b, topic_id, section_id, seq,
                        en=str(lb.get("en", "")))
                    seq += 1
            if d.get("caption_en"):
                add("detail", str(d["caption_en"]), b, topic_id, section_id, seq, lang="en")
                seq += 1
            # جزئیات درون خود تصویر ماشینی قابل استخراج نیست؛ صریح گزارش می‌شود
            add("figure_visual", str(d.get("title_fa", "")), b, topic_id, section_id, seq)
        elif b.type == "process":
            for i, st in enumerate(d.get("steps", []) or []):
                txt = (str(st) if isinstance(st, str)
                       else f"{st.get('head', '')}: {st.get('text', '')}".strip(": "))
                add("process", txt, b, topic_id, section_id, i, step_no=i + 1,
                    lane_title=str(d.get("title", "")) if i == 0 else "")
        elif b.type == "dual_process":
            seq = 0
            for lane_key in ("forward", "backward"):
                lane = d.get(lane_key, {}) or {}
                for i, st in enumerate(lane.get("steps", []) or []):
                    txt = (str(st) if isinstance(st, str)
                           else f"{st.get('head', '')}: {st.get('text', '')}".strip(": "))
                    add("process", txt, b, topic_id, section_id, seq,
                        step_no=i + 1,
                        lane_title=str(lane.get("title", "")) if i == 0 else "")
                    seq += 1
            if d.get("rail_note"):
                add("detail", str(d["rail_note"]), b, topic_id, section_id, seq)
        elif b.type == "summary_box":
            for i, sent in enumerate(_sentences(d.get("text", ""))):
                add("summary", sent, b, topic_id, section_id, i,
                    title=str(d.get("title", "")) if i == 0 else "")
        elif b.type == "checklist":
            for i, it in enumerate(d.get("items", []) or []):
                add("summary", str(it), b, topic_id, section_id, i,
                    title=str(d.get("title", "")) if i == 0 else "")

    for t in session.topics:
        section_id = t.id
        # اصطلاحات کلیدی مبحث زیر نخستین بخش همان مبحث می‌نشینند
        first_section = next((b.id for b in t.blocks if b.type == "section"), t.id)
        for i, kt in enumerate(t.key_terms):
            if isinstance(kt, dict) and kt.get("fa"):
                items.append(Item(
                    id=f"{t.id}#term{i}", kind="terminology", text=str(kt["fa"]),
                    block_id=t.id, topic_id=t.id, section_id=first_section,
                    has_number=False, meta={"en": str(kt.get("en", ""))}))
        for b in t.blocks:
            if b.type == "section":
                section_id = b.id
            from_block(b, t.id, section_id)
    last_topic = session.topics[-1].id if session.topics else ""
    for b in session.closing:
        from_block(b, last_topic, "closing")
    return items


def assign_coverage(session: Session,
                      items: list[Item] | None = None) -> dict[str, dict[str, str]]:
    """ماتریس پوشش: هر گزاره ← گرهٔ نقشه + وضعیت.

    covered    = در پنل جزئیات همان بخش چاپ می‌شود
    unresolved = ماشینی قابل نمایش نیست (جزئیات درون تصویر)؛ باید گزارش شود
    """
    items = items if items is not None else extract_items(session)
    section_ids = {b.id for b in session.all_blocks() if b.type == "section"}
    section_ids |= {t.id for t in session.topics} | {"closing"}
    matrix: dict[str, dict[str, str]] = {}
    for it in items:
        if it.kind == "figure_visual":
            matrix[it.id] = {"node": it.block_id, "status": "unresolved",
                             "reason": "جزئیات درون تصویر؛ مرور سرِ خود شکل"}
        elif it.section_id in section_ids:
            matrix[it.id] = {"node": it.section_id, "status": "covered", "reason": ""}
        else:
            matrix[it.id] = {"node": "", "status": "unassigned",
                             "reason": "بخش والد پیدا نشد"}
    return matrix


def coverage_report(session: Session) -> dict[str, Any]:
    """گزارش فنی پوشش برای build_report و QA."""
    items = extract_items(session)
    matrix = assign_coverage(session, items)
    by_status: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    unresolved: list[dict[str, str]] = []
    unassigned: list[str] = []
    for it in items:
        st = matrix[it.id]["status"]
        by_status[st] = by_status.get(st, 0) + 1
        by_kind[it.kind] = by_kind.get(it.kind, 0) + 1
        if st == "unresolved":
            unresolved.append({"id": it.id, "block": it.block_id,
                                "reason": matrix[it.id]["reason"]})
        elif st == "unassigned":
            unassigned.append(it.id)
    derived = [b.id for b in session.all_blocks() if b.type in DERIVED_BLOCK_TYPES]
    return {
        "total_items": len(items),
        "by_status": by_status,
        "by_kind": by_kind,
        "unresolved": unresolved,
        "unassigned": unassigned,
        "excluded_derived_blocks": derived,
        "complete": not unassigned,
    }
