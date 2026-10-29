"""مرحلهٔ ۰+۱ بازخورد کاربر (رنگ و نشانه‌ها):
- ساختار پایه (تب، سربرگ جدول، نشان شکل/جدول، شمارهٔ مبحث، چک‌باکس) = رنگ جلسه.
- نشانه‌های معنایی راهنما (کادرها + آیکن‌ها) رنگ خانوادهٔ خودشان را نگه می‌دارند.
- نقطهٔ کنار تیتر بخش همیشه sun؛ جهت‌های جریان دوطرفه از دو توکن عمومی می‌آیند
  و خط/عنوان/دایره در هر مسیر هم‌رنگ‌اند.
- بسته‌بندی فشرده و کارت آغاز مبحث جمع‌وجور (از دور قبل) سر جایشان هستند.
ابزار ممیزی مرحلهٔ ۰: tools/audit_pdf.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "engine" / "themes" / "humsyar.css").read_text(encoding="utf-8")
BRAND = (ROOT / "engine" / "themes" / "brand.css").read_text(encoding="utf-8")
TYPESET = (ROOT / "engine" / "humsyar" / "typeset.py").read_text(encoding="utf-8")
PACKING = (ROOT / "engine" / "humsyar" / "packing.py").read_text(encoding="utf-8")

SES = "var(--session-header,var(--brand-deep))"


def test_structure_uses_session_color():
    # نشان شکل/جدول/فرایند، حباب شمارهٔ مبحث، تب فعال نوار پیشرفت، نقشهٔ جلسه
    assert f".fig__cap .fno{{\n  display:inline-block; background:{SES}" in CSS
    assert f"background:{SES}; color:#fff; font-size:8pt; font-weight:700;" in CSS  # .tno
    assert "table.tbl th{\n  background:var(--session-header" in CSS
    assert "td.rowh{ font-weight:700; color:var(--session-deep" in CSS
    assert f".process__title .pno{{ background:{SES}" in CSS
    assert f"flex:0 0 auto; background:{SES}" in CSS  # .topic-num
    assert f".pstrip__c--cur{{ background:{SES}" in CSS
    assert ".pstrip__c--done b{ background:var(--session-accent" in CSS
    assert "border:1.2pt solid var(--session-accent" in CSS  # جای تیک اهداف
    # fam6 دیگر روی هیچ سطح ساختاری نیست؛ فقط خانوادهٔ معنایی و راهنما
    for sel in (".fno", ".tno", ".pno", "table.tbl th", ".topic-num",
                ".pstrip__c--cur", ".session-map li.in .n", ".section .sno"):
        chunk = CSS[CSS.index(sel):CSS.index(sel) + 260]
        assert "fam6" not in chunk, sel


def test_semantic_marks_keep_family_colors():
    # کادرها: نوار آغازین و عنوان با رنگ خانواده (از R12/R13) دست‌نخورده
    assert ".callout--key{ color:var(--ink); border-inline-start-color:var(--fam2); }" in CSS
    assert ".callout--conflict .callout__head{ color:var(--c-conflict); }" in CSS
    # آیکن کنار تیترها دیگر سبز برند خنثی‌کننده ندارد؛ رنگ از icon_color_css می‌آید
    assert ".h-ic .ic{ color:var(--brand)" not in CSS
    assert ".src b{ color:var(--fam1-deep)" in CSS  # چیپ منبع = نشانهٔ خانوادهٔ ۱
    # کارت آغاز مبحث: متن برچسب‌ها جلسه، قلاب آیکن خانواده سر جاست
    assert ".topic-card .why b{ color:var(--session-deep" in CSS
    assert "tc-obj" in TYPESET and "tc-pre" in TYPESET and "tc-term" in TYPESET


def test_section_dot_is_always_sun():
    assert "--sun: #FFB627;" in BRAND
    assert "border-radius:50%; background:var(--sun);" in CSS  # .section::before
    assert CSS.count(".section::before") == 1  # یک قانون واحد برای کل جزوه


def test_direction_tokens_and_lane_consistency():
    assert "--dir-forward: #0F5E63;" in BRAND
    assert "--dir-reverse: #B84A12;" in BRAND
    assert 'cf = hex_of("dir-forward")' in TYPESET
    assert 'cb = hex_of("dir-reverse")' in TYPESET
    # --lane روی خود مسیر است تا عنوان، خط ستون و دایره‌ها هم‌رنگ شوند
    assert 'class="lane lane--fwd" style="--lane:{cf}"' in TYPESET
    assert 'class="lane lane--bwd" style="--lane:{cb}"' in TYPESET
    assert ".lane__head{ color:var(--lane" in CSS
    assert ".lane .step .n{ background:var(--lane" in CSS
    assert ".lane .steps::before{ border-color:var(--lane" in CSS
    assert ".lane--fwd .lane__head{ color:var(--brand)" not in CSS
    assert ".lane--bwd .step .n{ background:var(--accent)" not in CSS


def test_no_off_token_hex_in_booklet_css():
    """نسخهٔ سبک linter مرحلهٔ ۱: هیچ hex مستقیمی در CSS جزوه جز توکن‌های brand نیست."""
    tokens = {h.upper() for h in re.findall(r"#[0-9A-Fa-f]{6}\b", BRAND)}
    tokens |= {"#FFFFFF", "#FFF"}
    used = {h.upper() for h in re.findall(r"#[0-9A-Fa-f]{6}\b", CSS)}
    assert used <= tokens, used - tokens


def test_audit_tool_exists_and_baseline_kept():
    assert (ROOT / "tools" / "audit_pdf.py").exists()


def test_topic_card_is_compact():
    assert "--fs-h-topic:14.5pt" in CSS
    assert "font-size:8.3pt; line-height:1.55" in CSS  # .topic-card
    assert ".objlist li{ position:relative; padding-right:14pt; margin:1.2pt 0; }" in CSS


def test_feedback_audits_forced_breaks():
    assert "حسابرسی شکست" in PACKING
    assert 'b.data.pop("_break_before", None)' in PACKING
    assert "blank < 32.0" in PACKING and "adjusted >= 8" in PACKING


def test_final_pdf_fill_is_dense():
    report = json.loads((ROOT / "output" / "build_report.json").read_text(encoding="utf-8"))
    assert report["theme"] == "a" and report["qa"]["ok"]
    fills = [f for f in report["qa"]["fill_per_page"] if f is not None]
    assert sum(fills) / len(fills) >= 88
    assert min(fills[:-4]) >= 65  # بدترین صفحهٔ بدنه، بدون جمع‌بندی/شیت/واژه‌نامه
