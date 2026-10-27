"""تست‌های راند ۷ — نقشهٔ جامع مرور: تجزیهٔ بی‌اتلاف، ماتریس پوشش، رندر.

اصل اثبات: اتصال دوبارهٔ گزاره‌های هر پاراگراف باید عین متن پاراگراف شود
(هیچ واژه‌ای در تجزیه گم یا بازنویسی نشده است) و هر گزاره یک گرهٔ نقشه دارد.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))

from humsyar.model import load_session, normalize_text
from humsyar.planner import plan_session
from humsyar.revision import assign_coverage, coverage_report, extract_items
from humsyar.typeset import Typesetter

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "content" / "session01_pilot.yaml"


def _session():
    return load_session(str(PILOT))


# ------------------------------------------------------------ بی‌اتلافی تجزیه
def test_paragraph_decomposition_is_lossless():
    s = _session()
    items = extract_items(s)
    by_block: dict[str, list[str]] = {}
    for it in items:
        by_block.setdefault(it.block_id, []).append(it.text)
    for b in s.all_blocks():
        if b.type != "paragraph":
            continue
        joined = normalize_text(" ".join(by_block.get(b.id, [])))
        assert joined == normalize_text(b.data["text"]), b.id


def test_every_table_row_and_label_extracted():
    s = _session()
    items = extract_items(s)
    row_items = [i for i in items if i.kind == "table_row"]
    total_rows = sum(len(b.data["rows"]) for b in s.all_blocks() if b.type == "table")
    assert len(row_items) == total_rows
    # هر سلول باید در متن گزارهٔ ردیفش پیدا شود
    for b in s.all_blocks():
        if b.type != "table":
            continue
        mine = [i.text for i in row_items if i.block_id == b.id]
        for row, txt in zip(b.data["rows"], mine):
            for cell in row:
                assert normalize_text(str(cell)) in normalize_text(txt)
    terms = {(i.text) for i in items if i.kind == "terminology"}
    for b in s.all_blocks():
        if b.type == "figure":
            for lb in b.data.get("labels", []) or []:
                assert str(lb["fa"]) in terms


def test_extraction_is_deterministic():
    s = _session()
    a = [(i.id, i.kind, i.text) for i in extract_items(s)]
    b = [(i.id, i.kind, i.text) for i in extract_items(s)]
    assert a == b and len({x[0] for x in a}) == len(a)  # شناسه‌ها یکتا و پایدار


# ------------------------------------------------------------------ پوشش
def test_coverage_matrix_complete_and_honest():
    s = _session()
    rep = coverage_report(s)
    assert rep["complete"] is True
    assert rep["unassigned"] == []
    n_figs = sum(1 for b in s.all_blocks() if b.type == "figure")
    # تنها موارد unresolved جزئیات درون تصویرها هستند — نه حذف بی‌صدا
    assert len(rep["unresolved"]) == n_figs
    assert rep["by_status"]["covered"] == rep["total_items"] - n_figs
    # بلوک‌های مشتق (tldr/tree) صریح از جهان پوشش کنار گذاشته شده‌اند
    assert any("tl" in x for x in rep["excluded_derived_blocks"])
    assert any("tree" in x for x in rep["excluded_derived_blocks"])
    m = assign_coverage(s)
    assert all(v["node"] for v in m.values())


def test_kind_rules_are_conservative():
    s = _session()
    items = extract_items(s)
    exc = [i for i in items if i.kind == "exception"]
    assert exc and all(("استثنا" in i.text or "به‌جز" in i.text or "به جز" in i.text
                        or i.block_id.startswith("s01t")) for i in exc)
    conf = [i for i in items if i.kind == "source_conflict"]
    assert len(conf) == 1 and "۴۰۰" in conf[0].text and conf[0].has_number
    steps = [i for i in items if i.kind == "process"]
    assert steps and all(i.meta.get("step_no") for i in steps)


# -------------------------------------------------------------------- رندر
def test_revision_map_renders_verbatim_items():
    s = _session()
    plan = plan_session(s, "final", ROOT)
    ts = Typesetter(plan, toc_pages={}, fig_pages={})
    html = ts.revision_map()
    assert "نقشهٔ جامع مرور" in html
    assert "rev__panel" in html
    # یک جملهٔ واقعی متن باید عیناً در نقشه باشد
    p1 = [b for b in s.all_blocks() if b.id == "s01t4-p1"][0]
    first = p1.data["text"].split(".")[0].replace("**", "")
    plain_html = __import__("re").sub(r"<[^>]+>", " ", html)
    assert normalize_text(first)[:40] in normalize_text(plain_html)
    # ارجاع جزئیات درون تصویر
    assert "جزئیات درون تصویر را سرِ خود شکل مرور کنید" in html


def test_revision_map_config_gate():
    s = _session()
    plan = plan_session(s, "final", ROOT)
    plan.layout_cfg = dict(plan.layout_cfg or {})
    plan.layout_cfg["revision_map"] = {"enabled": False}
    assert Typesetter(plan).revision_map() == ""


def test_qa_reports_coverage_on_built_pdf():
    pdf = ROOT / "output" / "neuroanat_s01_pilot_final.pdf"
    if not pdf.exists():
        return
    import json
    rep = json.loads((ROOT / "output" / "build_report.json").read_text(encoding="utf-8"))
    cov = rep.get("coverage") or rep["qa"].get("coverage")
    assert cov and cov["complete"] is True and cov["total_items"] > 100
