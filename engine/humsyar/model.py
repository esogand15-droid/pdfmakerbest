"""
مدل محتوای ساختاریافتهٔ HumsYar — لایهٔ دادهٔ موتور.

اصول (از پرامپت پروژه):
- محتوا از ارائه (HTML/CSS) جداست. هر بلوک شناسهٔ پایدار دارد.
- هر بلوک وضعیت بازبینی علمی دارد: extracted / editorial / needs_review /
  approved / unresolved_conflict
- ارجاع منبع (کتاب + صفحه) روی بلوک‌ها حفظ می‌شود تا خروجی قابل‌ردیابی باشد.
- نوع بلوک جدید = یک کلاس جدید + ثبت در BLOCK_TYPES؛ موتور بازنویسی نمی‌شود.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import yaml

REVIEW_STATUSES = {"extracted", "editorial", "needs_review", "approved", "unresolved_conflict"}
CALLOUT_KINDS = {"key", "clinical", "warning", "bridge", "conflict", "exam"}
FIGURE_LAYOUTS = {"auto", "side", "full"}


@dataclass
class Source:
    """ارجاع به منبع علمی؛ مثلاً کتاب «اسنل» صفحهٔ ۱۰۸."""
    book: str
    pages: str = ""
    figure: str = ""  # شمارهٔ شکل در کتاب، اگر هست

    def label(self) -> str:
        parts = [self.book]
        if self.figure:
            parts.append(f"شکل {self.figure}")
        if self.pages:
            parts.append(f"ص {self.pages}")
        return "، ".join(parts)


@dataclass
class Block:
    id: str
    type: str
    status: str = "needs_review"
    sources: list[Source] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)

    def text_fragments(self) -> list[str]:
        """همهٔ رشته‌های متنی بلوک؛ برای تست پوشش محتوا در PDF نهایی."""
        out: list[str] = []

        skip = {"file", "layout", "quality_flags"}

        def walk(v: Any) -> None:
            if isinstance(v, str):
                out.append(v)
            elif isinstance(v, list):
                for item in v:
                    walk(item)
            elif isinstance(v, dict):
                for k, item in v.items():
                    if k in skip or str(k).startswith("_"):
                        continue
                    walk(item)

        walk(self.data)
        return out


@dataclass
class Topic:
    id: str
    number: int
    title: str
    why: str = ""
    objectives: list[str] = field(default_factory=list)
    prereq_required: list[str] = field(default_factory=list)
    prereq_suggested: list[str] = field(default_factory=list)
    key_terms: list[dict[str, str]] = field(default_factory=list)  # {fa, en}
    mother_pages: str = ""  # بازهٔ صفحات در جزوهٔ مادر
    blocks: list[Block] = field(default_factory=list)
    status: str = "needs_review"


@dataclass
class Session:
    id: str
    course: str
    title: str
    session_number: int
    session_total: int
    subtitle: str = ""
    version: str = "۰٫۱"
    cover_motif: str = "histology-neuron-glia"  # نقش کاور؛ برای هر جلسه در پیکربندی محتوا
    frame_theme: str = "anatomy-nervous"        # تم قاب موضوعی صفحات (none = بدون قاب)
    draft: bool = False                          # در حالت پیش‌نویس روی کاور برچسب پایلوت می‌آید
    note: str = ""  # یادداشت شفافیت (مثلاً «پایلوت»)
    session_map: list[dict[str, Any]] = field(default_factory=list)  # همهٔ مباحث جلسه
    topics: list[Topic] = field(default_factory=list)
    closing: list[Block] = field(default_factory=list)  # جمع‌بندی/درخت/چک‌لیست پایانی

    def all_blocks(self) -> list[Block]:
        blocks: list[Block] = []
        for t in self.topics:
            blocks.extend(t.blocks)
        blocks.extend(self.closing)
        return blocks


# ---------------------------------------------------------------- بارگذاری YAML

def _source(raw: dict[str, Any]) -> Source:
    return Source(book=str(raw.get("book", "")), pages=str(raw.get("pages", "")),
                  figure=str(raw.get("figure", "")))


def _block(raw: dict[str, Any]) -> Block:
    known = {"id", "type", "status", "sources"}
    return Block(
        id=str(raw.get("id", "")),
        type=str(raw.get("type", "")),
        status=str(raw.get("status", "needs_review")),
        sources=[_source(s) for s in raw.get("sources", [])],
        data={k: v for k, v in raw.items() if k not in known},
    )


def load_session(path: str) -> Session:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    topics = []
    for t in raw.get("topics", []):
        topics.append(Topic(
            id=str(t["id"]), number=int(t["number"]), title=str(t["title"]),
            why=str(t.get("why", "")), objectives=list(t.get("objectives", [])),
            prereq_required=list(t.get("prereq_required", [])),
            prereq_suggested=list(t.get("prereq_suggested", [])),
            key_terms=list(t.get("key_terms", [])),
            mother_pages=str(t.get("mother_pages", "")),
            status=str(t.get("status", "needs_review")),
            blocks=[_block(b) for b in t.get("blocks", [])],
        ))
    return Session(
        id=str(raw["id"]), course=str(raw["course"]), title=str(raw["title"]),
        session_number=int(raw["session_number"]), session_total=int(raw["session_total"]),
        subtitle=str(raw.get("subtitle", "")), version=str(raw.get("version", "۰٫۱")),
        cover_motif=str(raw.get("cover_motif", "histology-neuron-glia")),
        frame_theme=str(raw.get("frame_theme", "anatomy-nervous")),
        draft=bool(raw.get("draft", False)),
        note=str(raw.get("note", "")), session_map=list(raw.get("session_map", [])),
        topics=topics, closing=[_block(b) for b in raw.get("closing", [])],
    )


# ---------------------------------------------------------------- اعتبارسنجی

BLOCK_TYPES = {
    "section", "paragraph", "callout", "table", "figure", "process",
    "dual_process", "tree", "checklist", "summary_box", "team_note",
}

_REQUIRED: dict[str, list[str]] = {
    "section": ["title"],
    "paragraph": ["text"],
    "callout": ["kind", "title", "text"],
    "table": ["title", "headers", "rows"],
    "figure": ["file", "title_fa", "explain_fa"],
    "process": ["title", "steps"],
    "dual_process": ["title", "forward", "backward"],
    "tree": ["title", "root"],
    "checklist": ["title", "items"],
    "summary_box": ["title", "text"],
    "team_note": ["title"],
}


def validate(session: Session) -> list[str]:
    """خطاها (رشته) برگردانده می‌شوند؛ لیست خالی یعنی مدل سالم است."""
    errors: list[str] = []
    seen_ids: set[str] = set()
    seen_figures: dict[str, str] = {}

    def check_block(b: Block, where: str) -> None:
        if not b.id:
            errors.append(f"{where}: بلوک بدون شناسه")
        elif b.id in seen_ids:
            errors.append(f"{where}: شناسهٔ تکراری «{b.id}»")
        seen_ids.add(b.id)
        if b.type not in BLOCK_TYPES:
            errors.append(f"{where}/{b.id}: نوع بلوک ناشناخته «{b.type}»")
            return
        if b.status not in REVIEW_STATUSES:
            errors.append(f"{where}/{b.id}: وضعیت بازبینی نامعتبر «{b.status}»")
        for req in _REQUIRED[b.type]:
            if req not in b.data or b.data[req] in ("", None, []):
                errors.append(f"{where}/{b.id}: فیلد اجباری «{req}» خالی است")
        if b.type == "callout" and b.data.get("kind") not in CALLOUT_KINDS:
            errors.append(f"{where}/{b.id}: نوع کادر نامعتبر «{b.data.get('kind')}»")
        if b.type == "figure":
            f = str(b.data.get("file", ""))
            if f in seen_figures:
                errors.append(f"{where}/{b.id}: تصویر «{f}» بیش از یک‌بار استفاده شده "
                              f"(قبلاً در {seen_figures[f]})؛ هر تصویر دقیقاً یک‌بار")
            seen_figures[f] = b.id
            if b.data.get("layout", "auto") not in FIGURE_LAYOUTS:
                errors.append(f"{where}/{b.id}: چیدمان تصویر نامعتبر")
        if b.type == "table":
            n = len(b.data.get("headers", []))
            for i, row in enumerate(b.data.get("rows", [])):
                if len(row) != n:
                    errors.append(f"{where}/{b.id}: ردیف {i+1} جدول {len(row)} سلول دارد، سرستون {n}تا")
        if b.status == "unresolved_conflict" and not b.sources:
            errors.append(f"{where}/{b.id}: بلوک اختلاف منابع باید ارجاع داشته باشد")

    if not session.topics:
        errors.append("سند هیچ مبحثی ندارد")
    for t in session.topics:
        if t.status not in REVIEW_STATUSES:
            errors.append(f"مبحث {t.id}: وضعیت نامعتبر")
        for term in t.key_terms:
            # معادل لاتین فقط وقتی مجاز است که در خود منبع آمده باشد؛
            # نبودش خطا نیست (اختراع املای لاتین ممنوع است)، فقط فارسی چاپ می‌شود.
            if not term.get("fa"):
                errors.append(f"مبحث {t.id}: اصطلاح بدون معادل فارسی: {term}")
        for b in t.blocks:
            check_block(b, t.id)
    for b in session.closing:
        check_block(b, "closing")
    return errors


# ---------------------------------------------------------------- نرمال‌سازی متن

_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")


def normalize_text(s: str) -> str:
    """نرمال‌سازی برای مقایسهٔ متن مدل با متن استخراج‌شده از PDF.

    تفاوت‌های مجاز رندر (نیم‌فاصله، فاصله، ارقام) حذف می‌شوند؛ خود کلمات نه.
    """
    import unicodedata
    s = unicodedata.normalize("NFKC", s)
    # اعراب (تنوین، همزهٔ روی ه و…) در استخراج PDF گاه جابه‌جا برمی‌گردند؛ برای مقایسه حذفشان می‌کنیم.
    s = re.sub(r"[ً-ٰ]", "", s)
    s = s.translate(_PERSIAN_DIGITS)
    s = s.replace("‌", "").replace("‏", "").replace("‎", "")
    s = s.replace("ي", "ی").replace("ك", "ک").replace("ة", "ه")
    # لیگاتور «لا» در استخراج PDF گاهی با ترتیب معکوس (ال) برمی‌گردد؛
    # برای مقایسهٔ دوطرفه هر دو را به یک صورت متعارف می‌بریم.
    s = s.replace("لا", "ال").replace("لآ", "ال")
    s = re.sub(r"\[\[term:([^\]|]+)\|([^\]]+)\]\]", r"\1 (\2)", s)  # نشانه‌گذاری اصطلاح
    s = re.sub(r"\[en:([^\]]+)\]", r"\1", s)  # عبارت لاتین ایزوله
    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)  # بولد
    s = re.sub(r"\s+", "", s)
    return s
