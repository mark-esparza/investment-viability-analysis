# Investment-Viability Analysis

Ingests a company's financials — from **SEC EDGAR** (public companies) or
**user-supplied statements** (private / small business) — computes the standard
library of finance ratios, valuation, and capital-budgeting metrics, and answers
one question: **is this business a viable investment, and why?**

Output is two artifacts:

1. A **live-formula Excel workbook** — every metric is a cell formula referencing
   named input cells, so changing any input recalculates the whole model.
2. A **narrative report** (Markdown) structured like a credit/equity analyst's
   note, ending in a clear **viable / conditional / not-viable** verdict with the
   supporting numbers.

> **Educational analysis only — not investment, tax, or legal advice.** Every
> figure ties back to an input cell or a cited SEC filing; missing inputs are
> excluded, never invented. This disclaimer is repeated in every report and
> every workbook sheet.

---

## Web application

A FastAPI backend serves a single-page UI (the backend is required because SEC
EDGAR has no browser CORS). Analyze a public ticker or upload statement PDFs,
review the extracted figures in an editable grid, see the verdict + metrics +
full report inline, and download the live-formula workbook.

```bash
pip install -e ".[web,uploads]"        # fastapi, uvicorn, markdown, pdfplumber, ...
export IVA_SEC_USER_AGENT="InvestmentViability/1.0 you@example.com"
python -m ivanalysis.webapp            # -> http://127.0.0.1:8000
```

Endpoints: `POST /api/ticker`, `POST /api/parse` (upload), `POST /api/analyze`
(confirmed), `GET /api/download/{token}`.

## Quick start (CLI)

```bash
pip install -r requirements.txt        # requests + openpyxl (+ pytest)

# Public company (live SEC EDGAR). Set a descriptive User-Agent (SEC requires it).
export IVA_SEC_USER_AGENT="InvestmentViability/1.0 you@example.com"
PYTHONPATH=src python -m ivanalysis ticker WMT --years 4 --out out

# Private / small business (manual figures via JSON; shows a confirmation grid).
PYTHONPATH=src python -m ivanalysis upload samples/smallbiz.json --out out

# Private / small business from PDF statements or tax forms:
#   1) extract -> review -> correct, then 2) compute.
PYTHONPATH=src python -m ivanalysis parse samples/riverside_statements.pdf --name "Riverside" --out out
PYTHONPATH=src python -m ivanalysis upload out/Riverside_extracted.json --out out

# Re-run a public name from cache without hitting EDGAR again:
PYTHONPATH=src python -m ivanalysis ticker WMT --offline --out out
```

The `parse` step never computes: it extracts figures to `<name>_extracted.json`
and prints the confirmation grid. You review/correct the JSON (and add an
`assumptions` block) before running `upload` — no extracted number is trusted
blindly (spec §8).

Each run writes `out/<name>.xlsx` and `out/<name>_report.md`. Pre-generated
samples for a public company (Walmart) and a small business live in
[`examples/`](examples/).

---

## How it maps to the spec

| Spec section | Where |
|---|---|
| 2.1 SEC EDGAR (User-Agent, ≤10 req/s, disk cache, no-CORS backend) | [`edgar/client.py`](src/ivanalysis/edgar/client.py) |
| XBRL tag-alias table | [`edgar/tags.py`](src/ivanalysis/edgar/tags.py) |
| 2.2 Uploads + tax forms, user-confirmed before compute | [`uploads/__init__.py`](src/ivanalysis/uploads/__init__.py) |
| 3 Canonical data model | [`model.py`](src/ivanalysis/model.py) |
| 4.1–4.5 Ratios + DuPont (value **and** live Excel formula) | [`metrics/ratios.py`](src/ivanalysis/metrics/ratios.py) |
| 4.6–4.11 TVM, capital budgeting, CAPM, valuation, cost of capital, leverage | [`metrics/finance_math.py`](src/ivanalysis/metrics/finance_math.py) |
| 5 Narrative report + verdict | [`report/narrative.py`](src/ivanalysis/report/narrative.py) |
| 6 Live-formula workbook (Inputs/Assumptions/Ratios/Valuation/CapBudget/Charts) | [`excel/workbook.py`](src/ivanalysis/excel/workbook.py) |
| 7 CLI runner | [`cli.py`](src/ivanalysis/cli.py) |
| 8 Guardrails (disclaimer, sources, n/a not error, throttle) | throughout |

### The metric contract (spec 7)
Every ratio function takes the section-3 model and returns **both** the number
and the Excel formula string referencing named cells — guaranteeing the report
and the workbook describe the same calculation:

```python
def current_ratio(c: Ctx) -> MetricResult:
    return MetricResult("Current Ratio", "Liquidity",
        sdiv(c.val("current_assets"), c.val("current_liabilities")),   # number
        f"={c.ref('current_assets')}/{c.ref('current_liabilities')}")  # live formula
```

---

## Excel workbook (live model)

- **Inputs** — every raw line item per period in named cells (`Sales_FY24`, …).
- **Assumptions** — Rf, E(Rm), β, T, g, k, flotation … editable (yellow).
- **Ratios** — §4.1–4.5 as live formulas + plain-text formula + interpretation;
  healthy/weak conditional fills.
- **Valuation** — cost-of-capital block → WACC, an illustrative DCF, Gordon-growth
  and a multiples cross-check, with intrinsic-vs-market gap.
- **CapBudget** — editable project cash flows → `=NPV`, `=IRR`, PI, payback, ARR
  and accept/reject flags; plus an NPV-profile table.
- **Charts** — ratio trends, intrinsic-vs-market, NPV profile.

Change any Inputs/Assumptions cell and Excel recalculates everything downstream.

---

## Tests

```bash
python -m pytest -q
```

- `tests/test_finance_math.py` — validates every §4.6–4.12 formula against
  canonical textbook values (TVM, NPV/IRR/PI/payback, CAPM, bond/Gordon, WACC,
  DOL/DFL/DCL, break-even), plus safe divide-by-zero / no-sign-change behavior.
- `tests/test_ratios_and_excel.py` — ratio correctness, the DuPont identity
  reconciling to direct ROE, "missing input → n/a not error", and that the
  generated `.xlsx` actually contains **live formulas** with resolvable named
  ranges (acceptance criterion 4).

> Note on the reference guides: the BarCharts QuickStudy *Finance* PDF is a
> laminated guide with a non-standard font encoding and does not extract to
> machine-readable text, so formulas are validated **numerically** against the
> canonical examples above rather than by text-diffing the guide.

---

## Project layout

```
src/ivanalysis/
  model.py            # §3 canonical data model + field registry + named-range map
  metrics/
    common.py         # Ctx / MetricResult contract, safe arithmetic
    ratios.py         # §4.1–4.5 (value + live formula)
    finance_math.py   # §4.6–4.12 pure textbook math
  edgar/
    client.py         # rate-limited, cached, User-Agent'd EDGAR client
    tags.py           # XBRL tag-alias table
    ingest.py         # CompanyFacts -> model (with provenance)
  uploads/            # private/SMB: JSON entry, confirm grid, PDF/tax-form parsing
  excel/workbook.py   # live-formula .xlsx builder
  report/narrative.py # analyst-style report + viability scoring
  webapp/             # FastAPI backend + single-page web UI
  cli.py              # ticker / upload / parse commands
samples/smallbiz.json # worked private-company example
tests/                # unit + integration tests
```

## Document parsing (wired)
- `uploads/parse.py` extracts **digital** statement/tax-form PDFs (income
  statement, balance sheet, cash flow; 1120 / 1120-S / 1065 / Schedule C) with
  pdfplumber — no external binaries. It handles multi-year columns, `(parens)`
  negatives, and "in thousands/millions" scaling via a label-synonym table.
- **Scanned/image-only** PDFs fall back to OCR (`pytesseract` + `pdf2image`)
  *if installed*; otherwise a clear, actionable error is raised rather than
  guessing. Either way, extraction routes through the confirmation grid before
  any calculation.

## Not yet wired (clean seams)
- OCR binaries (Tesseract + Poppler) for scanned documents — the fallback code
  path exists; only the system binaries are optional.
- An MCP server exposing `analyze_ticker` / `analyze_uploads` / `build_workbook`
  (the functions already exist as the public API in `ivanalysis/__init__.py`).
```
