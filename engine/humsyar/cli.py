"""رابط خط فرمان موتور هامزیار.

مثال‌ها:
  python -m humsyar.cli build ../../content/session01_pilot.yaml --edition final
  python -m humsyar.cli build ../../content/session01_pilot.yaml --edition workbook --theme b
  python -m humsyar.cli extract ../../HumsYar_NeuroAnat_Jalase1.pdf --out ../../audit/extract2
"""
from __future__ import annotations

import argparse
import json
import sys


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="humsyar", description="موتور جزوه‌ساز هامزیار")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="ساخت PDF نهایی از فایل محتوای جلسه")
    b.add_argument("content")
    b.add_argument("--edition", choices=["final", "workbook"], default="final")
    b.add_argument("--theme", choices=["a", "b"], default="a")
    b.add_argument("--out", default="output")
    b.add_argument("--no-sources", action="store_true", help="پنهان‌کردن برچسب‌های منبع")

    e = sub.add_parser("extract", help="استخراج متن/تصویر از جزوهٔ مادر PDF")
    e.add_argument("pdf")
    e.add_argument("--out", required=True)

    args = ap.parse_args(argv)

    if args.cmd == "build":
        from .build import build
        report = build(args.content, edition=args.edition, theme=args.theme,
                       show_sources=not args.no_sources, out_dir=args.out)
        qa = report["qa"]
        print(f"PDF: {report['pdf']} ({qa['pages']} صفحه، {report['build_seconds']}s)")
        print(f"QA: {'✅ قبول' if qa['ok'] else '❌ خطا'} · هشدار چیدمان: {len(report['planner_warnings'])}")
        for e_ in qa["errors"]:
            print(f"  ❌ {e_}")
        return 0 if qa["ok"] else 2

    if args.cmd == "extract":
        from .extract import extract_mother
        info = extract_mother(args.pdf, args.out)
        print(json.dumps(info, ensure_ascii=False, indent=1))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
