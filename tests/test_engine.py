"""تست‌های موتور هامزیار — اجرا: pytest tests/ (از ریشهٔ مخزن، با venv فعال)."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))

from humsyar.diagrams import tree_svg                      # noqa: E402
from humsyar.model import load_session, normalize_text, validate  # noqa: E402
from humsyar.planner import plan_session                  # noqa: E402
from humsyar.typeset import Typesetter, inline            # noqa: E402

PILOT = ROOT / "content" / "session01_pilot.yaml"
PILOT_PDF = ROOT / "output" / "neuroanat_s01_pilot_final.pdf"

# حقایق کنترلی جلسهٔ ۱ (از پرامپت پروژه، بخش تست‌ها) — نباید هرگز در خروجی گم/عوض شوند
CONTROL_FACTS = ["۶۰ قطعهٔ بین‌گره‌ای", "بیش از ۴۰۰", "۱۰۰ تا ۴۰۰",
                 "یک به یک", "یک به چند", "GFAP", "Kinesin", "Dynein", "ده برابر"]


@pytest.fixture(scope="module")
def session():
    return load_session(str(PILOT))


def test_pilot_model_valid(session):
    assert validate(session) == []


def test_validation_catches_duplicate_figure(session):
    import copy
    s2 = copy.deepcopy(session)
    figs = [b for b in s2.all_blocks() if b.type == "figure"]
    figs[1].data["file"] = figs[0].data["file"]
    errs = validate(s2)
    assert any("بیش از یک‌بار" in e for e in errs)


def test_conflict_block_preserved(session):
    conflicts = [b for b in session.all_blocks() if b.status == "unresolved_conflict"]
    assert len(conflicts) >= 1
    txt = conflicts[0].data["text"]
    assert "۴۰۰" in txt and "۱۰۰ تا ۴۰۰" in txt  # هر دو نقل می‌مانند


def test_planner_numbering_and_editions(session):
    import copy
    s_final = plan_session(copy.deepcopy(session), "final", ROOT)
    assert s_final.labels["s01t4-f1"].startswith("شکل ۴-")
    assert s_final.labels["s01t6-tb1"].startswith("جدول ۶-")
    assert not any(b.type == "team_note" for b in s_final.session.all_blocks())
    s_wb = plan_session(copy.deepcopy(session), "workbook", ROOT)
    assert any(b.type == "team_note" for b in s_wb.session.all_blocks())


def test_inline_bidi_markup():
    html = inline("متن [[term:تپهٔ آکسونی|Axon Hillock]] و [en:Na+/K+-ATPase] و **مهم**")
    assert "<bdi" in html and "Axon Hillock" in html and "<strong>مهم</strong>" in html


def test_tree_svg_from_data():
    svg = tree_svg({"label": "ریشه", "children": [
        {"label": "شاخهٔ الف", "children": [{"label": "برگ"}]},
        {"label": "شاخهٔ ب", "alert": True}]})
    assert svg.startswith("<svg") and "ریشه" in svg and "tree-node--alert" in svg


def test_typeset_is_deterministic(session):
    import copy
    p1 = plan_session(copy.deepcopy(session), "final", ROOT)
    p2 = plan_session(copy.deepcopy(session), "final", ROOT)
    h1 = Typesetter(p1).document("/*css*/")
    h2 = Typesetter(p2).document("/*css*/")
    assert h1 == h2  # ورودی یکسان ← خروجی ساختاری یکسان


@pytest.mark.skipif(not PILOT_PDF.exists(), reason="PDF پایلوت هنوز ساخته نشده؛ اول build بزنید")
def test_built_pdf_qa_and_facts(session):
    import json
    from humsyar.qa import run_qa
    _rep = json.loads((ROOT / "output" / "build_report.json").read_text(encoding="utf-8"))
    _sheet = set((_rep.get("ultra_sheet") or {}).get("pages_in_book") or [])
    qa = run_qa(session, PILOT_PDF, CONTROL_FACTS, sheet_pages=_sheet)
    assert qa["ok"], qa["errors"]
    assert qa["figures_pdf"] == qa["figures_model"] == 11
    assert qa["min_font_pt"] >= 7.0
    import pymupdf
    doc = pymupdf.open(str(PILOT_PDF))
    assert len(doc.get_toc()) >= 10  # نشانک‌های PDF
    full = normalize_text(" ".join(p.get_text() for p in doc))
    for cell in ["Slow", "Intermediate", "Fast"]:
        assert cell in full


def test_normalize_lam_alef_and_diacritics():
    assert normalize_text("معمولاً لاله") == normalize_text("معموًال الله".replace("الله", "لاله"))
