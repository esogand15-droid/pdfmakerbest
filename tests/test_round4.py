"""تست‌های راند ۴: موتور صفحه‌آرایی تطبیقی محتوامحور.

اثبات‌های کلیدی: تحلیل معنایی قطعی، امتیازدهی کاندید با فیلترهای سخت،
«محتوای یکسان ← دو چیدمان متفاوتِ موجه بر اساس بافت»، حساسیت به وزن‌های کانفیگ،
کنترلر تنوع، و حلقهٔ بازرسی/اصلاح روی PDF واقعی.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))

from humsyar.analyze import analyze_session  # noqa: E402
from humsyar.build import build  # noqa: E402
from humsyar.model import load_session  # noqa: E402
from humsyar.planner import plan_session  # noqa: E402
from humsyar.scoring import load_layout_config, score_process_variant  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
OUT = ROOT / "tests" / "_out"


# ── تحلیل‌گر معنایی ──────────────────────────────────────────
def test_analyzer_archetypes_on_fixture():
    s = load_session(str(FIX / "adaptive.yaml"))
    arch = {p.section_id: p.archetype for p in analyze_session(s)}
    assert arch["fa-s1"] == "process"
    assert arch["fa-s3"] == "explanatory"
    assert arch["fa-s4"] == "comparison"


def test_analyzer_on_real_pilot_content():
    s = load_session(str(ROOT / "content" / "session01_pilot.yaml"))
    arch = {p.section_id: p.archetype for p in analyze_session(s)}
    assert arch["s01t4-s2"] == "comparison"      # جدول آکسون/دندریت
    assert arch["s01t4-s3"] == "process"          # انتقال آکسونی
    assert arch["s01t6-s1"] == "comparison"       # جدول شش سلول
    assert arch["closing"] if "closing" in arch else arch["intro"]


# ── اثبات مرکزی: محتوای یکسان، دو چیدمان متفاوت بر اساس بافت ──
def test_same_process_content_two_justified_layouts():
    s = load_session(str(FIX / "adaptive.yaml"))
    plan = plan_session(s, "final", ROOT)
    by_id = {b.id: b for b in s.all_blocks()}
    v1, v2 = by_id["fa-pr1"].data["_variant"], by_id["fa-pr2"].data["_variant"]
    assert {v1, v2} == {"vertical", "strip"}, (v1, v2)
    # هر دو تصمیم با امتیاز کاندیدها در حافظهٔ طراحی ثبت شده‌اند
    dec = {d["block"]: d for d in plan.layout_decisions if d["kind"] == "process"}
    assert dec["fa-pr1"]["chosen"] == v1 and dec["fa-pr2"]["chosen"] == v2
    assert all(len(d["candidates"]) == 2 for d in dec.values())


def test_diversity_weight_zero_removes_variation():
    cfg = load_layout_config(ROOT)
    cfg["preferences"]["diversity_strength"] = 0.0
    s = load_session(str(FIX / "adaptive.yaml"))
    plan_session(s, "final", ROOT, layout_cfg=cfg)
    by_id = {b.id: b for b in s.all_blocks()}
    assert by_id["fa-pr1"].data["_variant"] == by_id["fa-pr2"].data["_variant"] == "vertical"


def test_scorer_hard_filters_beat_weights():
    """درخواست صریح داده و نبود متن لنگر با هیچ وزنی دور زده نمی‌شود."""
    s = load_session(str(ROOT / "content" / "session01_pilot.yaml"))
    plan = plan_session(s, "final", ROOT)
    by_id = {b.id: b for b in s.all_blocks()}
    assert by_id["s01t6-f7"].data["_layout"] == "side"        # صریح در داده + side_text
    assert len(by_id["s01t6-f7"].data["_candidates"]) == 1   # کاندید دیگری ساخته نشده
    # شکل عمودی بدون متن لنگر هرگز side نمی‌شود
    assert all(b.data["_layout"] != "side" for b in s.all_blocks()
               if b.type == "figure" and not b.data.get("side_text"))


def test_process_scorer_is_deterministic():
    cfg = load_layout_config(ROOT)
    a = score_process_variant("strip", steps=3, prev_variant="vertical", cfg=cfg)
    b = score_process_variant("strip", steps=3, prev_variant="vertical", cfg=cfg)
    assert a == b and 0 < a["total"] < 1


# ── کنترلر تنوع (واحدی، با کاندید ساخته‌شده) ─────────────────
def test_diversity_controller_swaps_within_epsilon():
    from humsyar.packing import _Item, _diversify
    s = load_session(str(ROOT / "content" / "session01_pilot.yaml"))
    plan = plan_session(s, "final", ROOT)
    fig = next(b for b in s.all_blocks() if b.id == "s01t6-f2")
    # کاندید تقریباً هم‌امتیاز می‌سازیم تا شرط اپسیلون برقرار شود
    cur = dict(fig.data["_candidates"][0])
    alt = dict(fig.data["_candidates"][1])
    alt["score"] = dict(alt["score"], total=cur["score"]["total"] - 0.02)
    alt["img_h_mm"] = cur["img_h_mm"]
    fig.data["_candidates"] = [cur, alt]
    items, page_of = [], {}
    # سه صفحهٔ متوالی با امضای یکسان: هر صفحه پاراگراف+شکل با ارتفاع برابر؛
    # شکل صفحهٔ میانی همان هدف تعویض است
    paras = [b for b in s.all_blocks() if b.type == "paragraph"][:3]
    other_figs = [b for b in s.all_blocks() if b.type == "figure" and b.id != fig.id][:2]
    for i, pb in enumerate(paras, 1):
        items.append(_Item(pb.id, 120.0, pb, "t"))
        page_of[pb.id] = i
    for i, fb in enumerate([other_figs[0], fig, other_figs[1]], 1):
        items.append(_Item(fb.id, 80.0, fb, "t"))
        page_of[fb.id] = i
    before = fig.data["_layout"]
    notes: list[str] = []
    _diversify(s, plan, items, page_of, notes.append)
    assert fig.data["_layout"] == alt["layout"] != before
    assert any(d["kind"] == "diversity_swap" for d in plan.layout_decisions)


# ── بازرسی بصری: واحد اصلاح + بیلد کامل ─────────────────────
def test_repair_orphan_heading_sets_break_before():
    from humsyar.inspect import repair_body
    s = load_session(str(FIX / "adaptive.yaml"))
    plan = plan_session(s, "final", ROOT)
    sec = next(b for b in s.all_blocks() if b.id == "fa-s3")
    findings = [{"page": 3, "type": "orphan_heading", "severity": "warn",
                 "detail": "x", "cause": "y", "block": "fa-s3"}]
    actions = repair_body(findings, s, plan, Path("/nonexistent.pdf"))
    assert sec.data.get("_break_before") is True
    assert actions and "fa-s3" in actions[0]


@pytest.fixture(scope="module")
def rep_adaptive():
    return build(str(FIX / "adaptive.yaml"), edition="final", out_dir=str(OUT / "adaptive"))


def test_adaptive_build_report_and_strip_rendered(rep_adaptive):
    assert rep_adaptive["qa"]["ok"], rep_adaptive["qa"]["errors"]
    assert rep_adaptive["content_analysis"]
    assert rep_adaptive["layout_decisions"]
    assert "inspection" in rep_adaptive and "final_findings" in rep_adaptive["inspection"]
    html = (OUT / "adaptive" / "fixture_adaptive_final.html").read_text(encoding="utf-8")
    assert "process--strip" in html           # گونهٔ افقی واقعاً رندر شده
    assert "secpan--airy" in html             # ریتم تنفسی بخش توضیحی اعمال شده


def test_monotony_fixture_signatures_recorded():
    rep = build(str(FIX / "monotony.yaml"), edition="final", out_dir=str(OUT / "monotony"))
    assert rep["qa"]["ok"], rep["qa"]["errors"]
    sigs = rep["page_signatures"]
    assert len(sigs) >= 3 and all("signature" in s for s in sigs)
    rep2 = build(str(FIX / "monotony.yaml"), edition="final", out_dir=str(OUT / "monotony2"))
    assert [s["signature"] for s in rep2["page_signatures"]] == [s["signature"] for s in sigs]


def test_pilot_decisions_logged_and_content_preserved():
    import json
    rep = json.loads((ROOT / "output" / "build_report.json").read_text(encoding="utf-8"))
    assert rep["qa"]["ok"]
    fig_decisions = [d for d in rep["layout_decisions"] if d["kind"] == "figure"]
    assert len(fig_decisions) == 11
    assert all("candidates" in d and d["candidates"] for d in fig_decisions)
    assert rep["content_analysis"][0]["archetype"]
