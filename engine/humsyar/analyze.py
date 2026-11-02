"""
تحلیل‌گر محتوای علمی (Semantic Content Analyzer) — راند ۴.

هدف: پیش از هر تصمیم چیدمان، «ماهیت» هر بخش از روی ترکیب بلوک‌های ساختاریافته
شناخته شود و به یک ساختار دادهٔ قابل‌استفاده برای موتور (نه متن آزاد) تبدیل شود:
پروفایل بخش (ترکیب، حجم متن، تراکم عدد/اصطلاح لاتین، شکل‌ها، جدول‌ها، روابط)
+ کهن‌الگوی ارائه (توضیحی، مقایسه‌ای، طبقه‌بندی، فرایندی، شکل‌محور، …)
+ امتیاز پیچیدگی.

اصول:
- قطعی و قاعده‌محور است؛ هیچ محتوای علمی ساخته یا تفسیر نمی‌شود. نوع معنایی هر
  بلوک همان نوع ساختاری آن در مدل است و کهن‌الگو از «ترکیب» بلوک‌ها نتیجه می‌شود.
- خروجی برای امتیازدهی چیدمان (scoring)، کنترل تنوع و گزارش تصمیم‌ها مصرف می‌شود.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .model import Block, Session, Topic

_EN_RE = re.compile(r"[A-Za-z]{2,}")
_NUM_RE = re.compile(r"[0-9۰-۹]+(?:[.٫][0-9۰-۹]+)?")

ARCHETYPES = ("explanatory", "comparison", "classification", "process",
              "figure_centric", "definition_led", "summary", "mixed")


@dataclass
class SectionProfile:
    topic_id: str
    section_id: str            # شناسهٔ بلوک section یا «intro» برای پیش‌درآمد مبحث
    title: str
    block_ids: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    text_chars: int = 0
    numeric_tokens: int = 0
    en_tokens: int = 0
    figures: list[dict[str, Any]] = field(default_factory=list)
    tables: list[dict[str, Any]] = field(default_factory=list)
    callout_kinds: list[str] = field(default_factory=list)
    has_process: bool = False
    has_tree: bool = False
    has_summary: bool = False
    archetype: str = "mixed"
    complexity: float = 0.0
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic_id, "section": self.section_id, "title": self.title,
            "blocks": self.block_ids, "counts": self.counts,
            "text_chars": self.text_chars, "numeric_tokens": self.numeric_tokens,
            "en_tokens": self.en_tokens, "figures": self.figures, "tables": self.tables,
            "callout_kinds": self.callout_kinds, "has_process": self.has_process,
            "has_tree": self.has_tree, "archetype": self.archetype,
            "complexity": round(self.complexity, 2), "reasons": self.reasons,
        }


def section_spans(topic: Topic) -> list[tuple[Block | None, list[Block]]]:
    """بلوک‌های یک مبحث را به بازه‌های بخشی تقسیم می‌کند.

    هر بازه با یک بلوک section شروع می‌شود؛ بلوک‌های پیش از نخستین section
    بازهٔ «پیش‌درآمد» با سربرگ None هستند. ترتیب معنایی هرگز عوض نمی‌شود.
    """
    spans: list[tuple[Block | None, list[Block]]] = []
    head: Block | None = None
    cur: list[Block] = []
    for b in topic.blocks:
        if b.type == "section":
            if cur or head is not None:
                spans.append((head, cur))
            head, cur = b, [b]
        else:
            cur.append(b)
    if cur or head is not None:
        spans.append((head, cur))
    return spans


def _profile_span(topic_id: str, head: Block | None, blocks: list[Block]) -> SectionProfile:
    p = SectionProfile(
        topic_id=topic_id,
        section_id=head.id if head else "intro",
        title=str(head.data.get("title", "")) if head else "پیش‌درآمد مبحث",
        block_ids=[b.id for b in blocks],
    )
    for b in blocks:
        p.counts[b.type] = p.counts.get(b.type, 0) + 1
        text = " ".join(f for f in b.text_fragments()
                        if not f.endswith((".png", ".jpg", ".jpeg")))
        if b.type in ("paragraph", "callout"):
            p.text_chars += len(text)
        p.numeric_tokens += len(_NUM_RE.findall(text))
        p.en_tokens += len(_EN_RE.findall(text))
        if b.type == "figure":
            p.figures.append({
                "id": b.id,
                "labels": len(b.data.get("labels", [])),
                "has_side_text": bool(b.data.get("side_text")),
                "explicit_layout": str(b.data.get("layout", "auto")),
            })
        elif b.type == "table":
            p.tables.append({
                "id": b.id, "rows": len(b.data.get("rows", [])),
                "cols": len(b.data.get("headers", [])),
                "row_header": bool(b.data.get("row_header")),
            })
        elif b.type == "callout":
            p.callout_kinds.append(str(b.data.get("kind", "")))
        elif b.type in ("process", "dual_process"):
            p.has_process = True
        elif b.type == "tree":
            p.has_tree = True
        elif b.type == "summary_box":
            p.has_summary = True
    p.archetype, p.reasons = classify_section(p)
    p.complexity = _complexity(p)
    return p


def classify_section(p: SectionProfile) -> tuple[str, list[str]]:
    """کهن‌الگوی ارائهٔ بخش از روی ترکیب بلوک‌ها (قواعد قطعی و قابل ممیزی)."""
    reasons: list[str] = []
    comparison_tables = [t for t in p.tables if t["cols"] >= 3 or t["row_header"]]
    if p.has_tree:
        reasons.append("نمودار درختی/طبقه‌بندی در بخش هست")
        return "classification", reasons
    if p.has_process:
        reasons.append("بلوک فرایند/مسیر مرحله‌ای در بخش هست")
        return "process", reasons
    if comparison_tables and sum(t["rows"] for t in comparison_tables) >= 4:
        reasons.append("جدول مقایسه‌ای چندستونه با ردیف کافی")
        return "comparison", reasons
    if p.has_summary and p.counts.get("paragraph", 0) <= 2:
        reasons.append("بخش حول جمع‌بندی می‌چرخد")
        return "summary", reasons
    if len(p.figures) >= 2 or (len(p.figures) == 1 and p.text_chars < 900):
        reasons.append(f"{len(p.figures)} شکل در برابر {p.text_chars} نویسه متن؛ ارائه شکل‌محور")
        return "figure_centric", reasons
    if "definition" in p.callout_kinds and p.counts.get("paragraph", 0) <= 2:
        reasons.append("کادر تعریف اصطلاح با متن کوتاه")
        return "definition_led", reasons
    if p.text_chars >= 2000 and not p.figures and not p.tables:
        reasons.append("متن توضیحی بلند بدون شکل/جدول؛ صفحهٔ آرام متنی")
        return "explanatory", reasons
    reasons.append("ترکیب متنوع بلوک‌ها بدون محور غالب")
    return "mixed", reasons


def _complexity(p: SectionProfile) -> float:
    """پیچیدگی نسبی ۰..۱ — ابتکاریِ قابل‌تنظیم، مستند و قطعی (نه قضاوت علمی)."""
    relations = (1 if p.has_process else 0) + (1 if p.has_tree else 0) + len(p.tables)
    return round(min(1.0,
                     0.35 * min(p.text_chars / 3000, 1.0)
                     + 0.25 * min(relations / 3, 1.0)
                     + 0.20 * min(len(p.figures) / 3, 1.0)
                     + 0.20 * min(p.en_tokens / 25, 1.0)), 3)


def analyze_session(session: Session) -> list[SectionProfile]:
    """پروفایل همهٔ بخش‌های جلسه (مباحث + بخش پایانی) به ترتیب سند."""
    out: list[SectionProfile] = []
    for t in session.topics:
        for head, blocks in section_spans(t):
            if blocks:
                out.append(_profile_span(t.id, head, blocks))
    if session.closing:
        fake = Topic(id="closing", number=0, title="جمع‌بندی", blocks=list(session.closing))
        for head, blocks in section_spans(fake):
            if blocks:
                out.append(_profile_span("closing", head, blocks))
    return out


def archetype_of_block(profiles: list[SectionProfile], block_id: str) -> str:
    for p in profiles:
        if block_id in p.block_ids:
            return p.archetype
    return "mixed"
