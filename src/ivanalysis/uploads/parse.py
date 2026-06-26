"""Statement & tax-form extraction for the private/SMB path (spec section 2.2).

Text-based (digital) PDFs are parsed with pdfplumber -- no external binaries.
Scanned PDFs fall back to OCR (pytesseract + pdf2image) *if installed*; if not,
a clear error is raised rather than guessing. Extraction NEVER feeds a
calculation directly: callers route the result through ``confirm_grid`` and the
user reviews/corrects every value first (spec section 8).

Coverage today:
  * Single- or multi-column income statement / balance sheet / cash-flow PDFs
    whose lines read "<label> ... <number> [<number> ...]".
  * Tax forms (1120 / 1120-S / 1065 / Schedule C) via the same label synonyms.
Layout-heavy or image-only statements may need manual correction in the grid --
that is the point of the confirmation step.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

# Ordered most-specific -> most-general. First matching rule wins per line, and
# an attribute is only filled once (the canonical top line), so a later
# "total assets" never overwrites an earlier "total current assets".
LABEL_RULES: list[tuple[str, list[str]]] = [
    # --- cash-flow (before the generic "cash" balance rule) ---
    ("cfo", ["net cash provided by operating", "net cash used in operating",
             "cash flows from operating", "net cash from operating",
             "cash provided by operating", "operating activities"]),
    ("cfi", ["net cash provided by investing", "net cash used in investing",
             "cash flows from investing", "net cash from investing",
             "investing activities"]),
    ("cff", ["net cash provided by financing", "net cash used in financing",
             "cash flows from financing", "net cash from financing",
             "financing activities"]),
    ("net_change_cash", ["net increase in cash", "net decrease in cash",
                         "net change in cash", "net increase decrease in cash"]),
    ("capex", ["capital expenditures", "purchases of property",
               "payments for property", "purchase of property and equipment",
               "additions to property"]),
    ("lease_payments", ["operating lease payments", "principal payments on finance",
                        "lease payments"]),
    ("delta_nwc", ["change in net working capital", "changes in working capital"]),
    # --- income statement ---
    ("cogs", ["cost of goods sold", "cost of sales", "cost of revenue",
              "cost of products sold", "cost of goods and services"]),
    ("gross_profit", ["gross profit", "gross margin"]),
    ("operating_expenses", ["total operating expenses", "operating expenses",
                            "selling general and administrative",
                            "selling, general", "operating costs and expenses"]),
    ("depreciation", ["depreciation and amortization", "depreciation & amortization",
                      "depreciation"]),
    ("ebit", ["operating income", "income from operations", "operating profit",
              "earnings before interest and taxes"]),
    ("interest_expense", ["interest expense", "interest and debt expense"]),
    ("ebt", ["income before income taxes", "income before provision for income",
             "income before taxes", "pretax income", "earnings before taxes",
             "taxable income"]),
    ("taxes", ["provision for income taxes", "income tax expense",
               "income tax provision", "income taxes", "total tax"]),
    ("preferred_dividends", ["preferred dividends", "dividends on preferred"]),
    ("net_income", ["net income", "net earnings", "net loss", "consolidated net income"]),
    ("diluted_shares", ["diluted weighted average shares",
                        "weighted average diluted shares",
                        "weighted-average diluted shares", "diluted shares"]),
    ("eps", ["diluted earnings per share", "earnings per share - diluted",
             "diluted eps", "earnings per share"]),
    ("revenue", ["total revenue", "net revenue", "total net sales", "net sales",
                 "total income", "gross receipts or sales", "gross receipts",
                 "revenues", "sales", "total revenues"]),
    # --- balance sheet ---
    ("marketable_securities", ["marketable securities", "short-term investments",
                               "short term investments"]),
    ("accounts_receivable", ["accounts receivable", "trade receivables",
                             "receivables, net", "net receivables"]),
    ("inventory", ["inventories", "merchandise inventories", "inventory"]),
    ("other_current_assets", ["other current assets", "prepaid expenses and other"]),
    ("current_assets", ["total current assets"]),
    ("net_fixed_assets", ["property and equipment, net", "property, plant and equipment, net",
                          "net property and equipment", "property plant and equipment net",
                          "net fixed assets", "property and equipment"]),
    ("total_assets", ["total assets"]),
    ("accounts_payable", ["accounts payable"]),
    ("other_current_liabilities", ["other current liabilities",
                                   "accrued liabilities", "accrued expenses"]),
    ("current_liabilities", ["total current liabilities"]),
    ("long_term_debt", ["long-term debt", "long term debt"]),
    ("total_liabilities", ["total liabilities"]),
    ("preferred_equity", ["preferred stock"]),
    ("total_equity", ["total stockholders equity", "total shareholders equity",
                      "total stockholders' equity", "total shareholders' equity",
                      "total equity", "stockholders equity", "shareholders equity",
                      "owners equity", "members equity", "partners capital"]),
    ("cash", ["cash and cash equivalents", "cash and equivalents", "cash"]),
]

_SCALE = [
    (re.compile(r"in\s+billions", re.I), 1_000_000_000),
    (re.compile(r"in\s+millions", re.I), 1_000_000),
    (re.compile(r"in\s+thousands", re.I), 1_000),
]
_NUM_TOKEN = re.compile(r"\(?-?\$?\s?[\d][\d,]*(?:\.\d+)?\)?")
_YEAR = re.compile(r"\b(?:FY\s?)?(19|20)\d{2}\b", re.I)


def _normalize(label: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", label.lower()).strip()


def _to_number(token: str) -> Optional[float]:
    t = token.strip()
    if not any(ch.isdigit() for ch in t):
        return None
    neg = t.startswith("(") and t.endswith(")")
    t = t.replace("(", "").replace(")", "").replace("$", "").replace(",", "").strip()
    try:
        v = float(t)
    except ValueError:
        return None
    return -v if neg else v


def _detect_scale(text: str) -> int:
    for rx, mult in _SCALE:
        if rx.search(text):
            return mult
    return 1


def _detect_periods(lines: list[str]) -> list[str]:
    """Find the column header row of fiscal years, return labels like FY24."""
    for line in lines:
        years = re.findall(r"\b(19|20)(\d{2})\b", line)
        # require >=2 distinct year tokens on one line to call it a header
        if len(years) >= 2:
            labels = [f"FY{yy}" for _cc, yy in years]
            # de-dup preserving order
            seen, out = set(), []
            for lab in labels:
                if lab not in seen:
                    seen.add(lab)
                    out.append(lab)
            return out
    return []


def _split_label_numbers(line: str) -> tuple[str, list[float]]:
    tokens = _NUM_TOKEN.findall(line)
    nums = [n for n in (_to_number(t) for t in tokens) if n is not None]
    # label = text before the first numeric token
    m = _NUM_TOKEN.search(line)
    label = line[: m.start()] if m else line
    return label.strip(), nums


def extract_text(path: str | Path) -> str:
    """Best-effort text extraction. pdfplumber for digital PDFs; OCR fallback for
    scans only if pytesseract + pdf2image are installed."""
    import pdfplumber

    path = Path(path)
    text_parts: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text_parts.append(page.extract_text() or "")
    text = "\n".join(text_parts)
    if text.strip():
        return text
    return _ocr_fallback(path)


def _ocr_fallback(path: Path) -> str:
    try:
        import pdf2image
        import pytesseract
    except ImportError as exc:
        raise NotImplementedError(
            f"'{path.name}' has no extractable text (likely a scan). OCR fallback "
            "needs 'pytesseract' + 'pdf2image' and the Tesseract/Poppler binaries. "
            "Install them, or transcribe the figures into a JSON for the upload "
            "command."
        ) from exc
    images = pdf2image.convert_from_path(str(path))
    return "\n".join(pytesseract.image_to_string(im) for im in images)


def parse_statement_text(text: str) -> dict:
    """Map raw statement text to {periods:[{label, <attrs>}...]}."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    scale = _detect_scale(text)
    periods = _detect_periods(lines) or ["FY?"]
    # one bucket of attr->value per detected period column
    buckets: list[dict] = [{} for _ in periods]

    for line in lines:
        norm = _normalize(line)
        if not norm:
            continue
        label, nums = _split_label_numbers(line)
        if not nums:
            continue
        norm_label = _normalize(label)
        if not norm_label:
            continue
        for attr, patterns in LABEL_RULES:
            if any(p in norm_label for p in patterns):
                # positional map of numbers -> period columns
                for i in range(min(len(periods), len(nums))):
                    if attr not in buckets[i]:  # first occurrence wins
                        buckets[i][attr] = nums[i] * scale
                break

    out_periods = []
    for label, bucket in zip(periods, buckets):
        if bucket:
            fy = None
            m = re.search(r"(\d{2})$", label)
            if m:
                fy = 2000 + int(m.group(1))
            out_periods.append({"label": label, "fiscal_year": fy, **bucket})
    return {"periods": out_periods, "_scale": scale}


def parse_statements(paths: list[str | Path], name: str = "Uploaded Company") -> dict:
    """Parse one or more statement/tax PDFs and merge into a company dict ready
    for ``company_from_dict`` -- AFTER the user confirms via the grid."""
    merged: dict[str, dict] = {}  # period label -> attrs
    sources: dict[str, list[str]] = {}
    for path in paths:
        text = extract_text(path)
        parsed = parse_statement_text(text)
        for p in parsed["periods"]:
            label = p["label"]
            bucket = merged.setdefault(label, {"label": label,
                                               "fiscal_year": p.get("fiscal_year")})
            for k, v in p.items():
                if k in ("label", "fiscal_year"):
                    continue
                bucket.setdefault(k, v)
            sources.setdefault(label, []).append(Path(path).name)

    periods = []
    for label, bucket in merged.items():
        bucket["source"] = "Upload: " + ", ".join(sorted(set(sources.get(label, []))))
        periods.append(bucket)
    periods.sort(key=lambda b: (b.get("fiscal_year") or 0, b["label"]))
    return {"name": name, "mode": "private", "periods": periods}
