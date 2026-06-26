"""PDF statement extraction (spec section 2.2, acceptance criterion 2).

Generates a digital (text-based) multi-year statement PDF with reportlab, then
parses it back through the real pdfplumber pipeline and checks the mapped values.
"""

import pytest

from ivanalysis.metrics import run_ratios
from ivanalysis.uploads import company_from_documents, confirm_grid
from ivanalysis.uploads.parse import parse_statements

reportlab = pytest.importorskip("reportlab")
pytest.importorskip("pdfplumber")


STATEMENT_LINES = [
    "Riverside Coffee Roasters LLC",
    "Consolidated Financial Statements",
    "(in thousands)",
    "                                          2024        2023",
    "Net sales                                1,950       1,680",
    "Cost of goods sold                         765         680",
    "Gross profit                             1,185       1,000",
    "Operating expenses                         930         805",
    "Depreciation and amortization               52          48",
    "Operating income                           203         147",
    "Interest expense                            31          30",
    "Income before income taxes                 172         117",
    "Net income                                 172         117",
    "",
    "Cash and cash equivalents                  130          85",
    "Accounts receivable                         48          42",
    "Inventories                                 95          82",
    "Total current assets                       285         220",
    "Property and equipment, net                470         440",
    "Total assets                               755         660",
    "Accounts payable                            80          72",
    "Total current liabilities                  110         100",
    "Long-term debt                             265         285",
    "Total liabilities                          375         385",
    "Total stockholders equity                  380         275",
    "",
    "Net cash provided by operating activities  205         158",
    "Net cash used in investing activities      (82)        (68)",
    "Net cash used in financing activities      (78)        (65)",
    "Capital expenditures                       (82)        (68)",
    "Net increase in cash                        45          25",
]


def _make_pdf(path):
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=letter)
    c.setFont("Courier", 9)
    y = 740
    for line in STATEMENT_LINES:
        c.drawString(40, y, line)
        y -= 14
    c.save()


@pytest.fixture
def statement_pdf(tmp_path):
    p = tmp_path / "statements.pdf"
    _make_pdf(p)
    return p


def test_parse_extracts_two_periods(statement_pdf):
    data = parse_statements([statement_pdf], name="Riverside")
    labels = [p["label"] for p in data["periods"]]
    assert labels == ["FY23", "FY24"]  # sorted oldest -> newest

    fy24 = next(p for p in data["periods"] if p["label"] == "FY24")
    # "in thousands" scale applied
    assert fy24["revenue"] == 1_950_000
    assert fy24["cogs"] == 765_000
    assert fy24["net_income"] == 172_000
    assert fy24["total_assets"] == 755_000
    assert fy24["total_equity"] == 380_000
    assert fy24["long_term_debt"] == 265_000
    assert fy24["cfo"] == 205_000
    # parenthesized values parse as negative
    assert fy24["cfi"] == -82_000
    assert fy24["capex"] == -82_000

    fy23 = next(p for p in data["periods"] if p["label"] == "FY23")
    assert fy23["revenue"] == 1_680_000
    assert fy23["total_assets"] == 660_000


def test_parsed_company_computes_metrics(statement_pdf):
    company = company_from_documents([statement_pdf], name="Riverside")
    assert len(company.periods) == 2
    m = {r.name: r for r in run_ratios(company, len(company.periods) - 1)}
    # current ratio FY24 = 285 / 110
    assert abs(m["Current Ratio"].value - 285_000 / 110_000) < 1e-6
    assert abs(m["Net Profit Margin"].value - 172_000 / 1_950_000) < 1e-6
    # confirmation grid renders the mapped values for user sign-off
    grid = confirm_grid(company)
    assert "CONFIRMATION GRID" in grid
    assert "Net Income" in grid


def test_scanned_pdf_without_ocr_raises_clear_error(tmp_path):
    """An image-only PDF (no text layer) should raise a clear, actionable error
    rather than silently producing nothing -- unless OCR libs are installed."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    p = tmp_path / "blank_scan.pdf"
    c = canvas.Canvas(str(p), pagesize=letter)
    c.save()  # no text drawn -> no extractable text layer

    from ivanalysis.uploads.parse import extract_text
    try:
        text = extract_text(p)
        assert text.strip() == ""  # OCR present but nothing to read
    except NotImplementedError as exc:
        assert "OCR" in str(exc)
