"""Command-line interface (spec section 7: CLI runner; EDGAR has no CORS).

Examples:
    python -m ivanalysis ticker WMT --years 4 --out out/WMT
    python -m ivanalysis upload samples/smallbiz.json --out out/smallbiz
    python -m ivanalysis ticker AAPL --offline    # use cached EDGAR data only
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .edgar import EdgarClient, analyze_ticker
from .excel import build_workbook
from .report import generate_report
from .uploads import company_from_dict, company_from_json, confirm_grid


def _emit(company, outdir: Path, confirm: bool) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    if confirm:
        print(confirm_grid(company))
        print()
    xlsx = build_workbook(company, outdir / f"{_slug(company)}.xlsx")
    report = generate_report(company)
    md = outdir / f"{_slug(company)}_report.md"
    md.write_text(report, encoding="utf-8")
    print(f"Workbook : {xlsx}")
    print(f"Report   : {md}")
    print()
    # Echo the verdict line for quick CLI feedback.
    for line in report.splitlines():
        if line.startswith("**Verdict:"):
            print(line.replace("**", ""))
            break


def _slug(company) -> str:
    base = company.ticker or company.name
    return "".join(ch for ch in base if ch.isalnum()) or "company"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="ivanalysis", description="Investment-viability analysis")
    sub = parser.add_subparsers(dest="cmd", required=True)

    pt = sub.add_parser("ticker", help="Analyze a public company by ticker (SEC EDGAR)")
    pt.add_argument("ticker")
    pt.add_argument("--years", type=int, default=4)
    pt.add_argument("--offline", action="store_true", help="use cached EDGAR data only")
    pt.add_argument("--out", default="out")

    pu = sub.add_parser("upload", help="Analyze a private company from a JSON file")
    pu.add_argument("path")
    pu.add_argument("--out", default="out")
    pu.add_argument("--no-confirm", action="store_true",
                    help="skip the confirmation grid (not recommended)")

    pp = sub.add_parser(
        "parse", help="Extract statement/tax-form PDFs to a reviewable JSON "
                      "(does NOT compute -- review, correct, then run 'upload')")
    pp.add_argument("paths", nargs="+", help="one or more statement/tax-form PDFs")
    pp.add_argument("--name", default="Uploaded Company")
    pp.add_argument("--out", default="out")

    args = parser.parse_args(argv)
    try:
        if args.cmd == "ticker":
            client = EdgarClient(offline=args.offline)
            company = analyze_ticker(args.ticker, years=args.years,
                                     offline=args.offline, client=client)
            if not company.periods:
                print(f"No usable periods found for {args.ticker}.", file=sys.stderr)
                return 2
            _emit(company, Path(args.out), confirm=False)
        elif args.cmd == "upload":
            company = company_from_json(args.path)
            _emit(company, Path(args.out), confirm=not args.no_confirm)
        elif args.cmd == "parse":
            from .uploads.parse import parse_statements
            parsed = parse_statements(args.paths, name=args.name)
            company = company_from_dict(parsed)
            print(confirm_grid(company))
            print()
            outdir = Path(args.out)
            outdir.mkdir(parents=True, exist_ok=True)
            slug = _slug(company)
            jpath = outdir / f"{slug}_extracted.json"
            jpath.write_text(json.dumps(parsed, indent=2), encoding="utf-8")
            print(f"Extracted figures written to: {jpath}")
            print("REVIEW and CORRECT this file (extraction is not trusted "
                  "blindly), add Assumptions, then run:")
            print(f"    python -m ivanalysis upload {jpath}")
    except Exception as exc:  # surface a clean message, not a traceback
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
