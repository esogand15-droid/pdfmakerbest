"""بازخورد کاربر (دور نشانه‌ها و فضای خالی):
۱) نشانه‌های تکرارشونده رنگ و آیکن خانوادهٔ معنایی خودشان را دارند، نه سبز یکدست جلسه.
۲) فضای خالی صفحات کمینه است (بسته‌بندی فعال‌تر + حسابرسی شکست اجباری).
۳) کارت آغاز مبحث فشرده است.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "engine" / "themes" / "humsyar.css").read_text(encoding="utf-8")
TYPESET = (ROOT / "engine" / "humsyar" / "typeset.py").read_text(encoding="utf-8")
PACKING = (ROOT / "engine" / "humsyar" / "packing.py").read_text(encoding="utf-8")


def test_recurring_marks_use_family_colors():
    # نشان شکل/جدول/فرایند، نقطهٔ تیتر بخش، سربرگ جدول: ساختار و ناوبری = fam6
    assert ".fig__cap .fno{\n  display:inline-block; background:var(--fam6-deep)" in CSS
    assert "background:var(--fam6-deep); color:#fff; font-size:8pt; font-weight:700;" in CSS  # .tno
    assert ".process__title .pno{ background:var(--fam6-deep)" in CSS
    assert "border-radius:50%; background:var(--fam6);" in CSS  # .section::before
    assert ".section .sno{ color:var(--fam6-deep)" in CSS
    assert "table.tbl th{\n  background:var(--fam6-deep)" in CSS
    # چیپ منبع: دانش پایه/ارجاع = fam1
    assert ".src b{ color:var(--fam1-deep)" in CSS
    # آیکن کنار تیترها دیگر سبز برند نیست؛ رنگ خانواده از icon_color_css می‌آید
    assert ".h-ic .ic{ color:var(--brand)" not in CSS


def test_topic_card_labels_carry_family_hooks():
    # هر ردیف کارت آغاز مبحث: آیکن + کلاس خانواده (متن‌ها دست‌نخورده‌اند)
    assert "tc-obj" in TYPESET and "tc-pre" in TYPESET and "tc-term" in TYPESET
    assert ".topic-card h3.tc-obj{ color:var(--fam2-deep)" in CSS
    assert ".topic-card h3.tc-pre{ color:var(--fam6-deep)" in CSS
    assert ".topic-card .why b{ color:var(--fam3-deep)" in CSS
    assert ".topic-card__foot .tc-term{ color:var(--fam1-deep)" in CSS
    assert "border:1.2pt solid var(--fam2)" in CSS  # جای تیک اهداف: fam2
    assert ".chip--pre{ background:var(--fam6-soft); border-color:var(--fam6)" in CSS
    # نوار پیشرفت: ناوبری = fam6 (دیگر رنگ جلسه inline نمی‌گیرد)
    assert ".pstrip__c--cur{ background:var(--fam6-deep)" in CSS
    assert 'style="--topic-c:' not in TYPESET.split("def topic")[1].split("def ")[0]


def test_topic_card_is_compact():
    assert "--fs-h-topic:14.5pt" in CSS
    assert "font-size:8.3pt; line-height:1.55" in CSS  # .topic-card
    assert ".objlist li{ position:relative; padding-right:14pt; margin:1.2pt 0; }" in CSS


def test_feedback_audits_forced_breaks():
    # حسابرسی شکست اجباری در برابر رندر واقعی وجود دارد و فقط شکل/جدول سالم را شامل می‌شود
    assert "حسابرسی شکست" in PACKING
    assert 'b.data.pop("_break_before", None)' in PACKING
    assert "blank < 32.0" in PACKING and "adjusted >= 8" in PACKING


def test_final_pdf_fill_is_dense():
    report = json.loads((ROOT / "output" / "build_report.json").read_text(encoding="utf-8"))
    assert report["theme"] == "a" and report["qa"]["ok"]
    fills = [f for f in report["qa"]["fill_per_page"] if f is not None]
    assert sum(fills) / len(fills) >= 88  # میانگین پُری بدنه (پیش از این دور: ۸۳)
    # بدترین صفحهٔ بدنه (به‌جز صفحهٔ جمع‌بندی پایانی که ساختاری است) حداقل ۶۵٪
    body = fills[:-4]  # بدون جمع‌بندی/شیت/واژه‌نامه
    assert min(body) >= 65
