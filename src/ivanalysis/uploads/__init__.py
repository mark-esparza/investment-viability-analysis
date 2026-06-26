"""Private / small-business ingestion (spec section 2.2).

There is no public API that returns a specific business's financials or tax
returns, so this data comes from user uploads / manual entry only. This module
normalizes that input into the same section-3 model the EDGAR path produces.

Two paths:
  * ``company_from_dict`` / ``company_from_json`` -- structured manual entry.
  * ``parse_document`` / ``company_from_documents`` -- PDF/image + tax-form
    extraction via pdfplumber (OCR fallback for scans). The extractor returns
    data for review; it never feeds a calculation directly.

Whichever path is used, ``confirm_grid`` MUST be shown and accepted before the
numbers feed any calculation (spec section 8: tax-form parsing is user-confirmed).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from ..model import ALL_FIELDS, FIELD_LABEL, Assumptions, Company, FinancialPeriod

_VALID_ATTRS = {attr for attr, *_ in ALL_FIELDS}


def company_from_dict(data: dict) -> Company:
    """Build a Company from a plain dict (see ``samples/`` for the shape)."""
    company = Company(
        name=data.get("name", "Private Company"),
        ticker=data.get("ticker"),
        mode="private",
        description=data.get("description", ""),
    )
    for pdata in data.get("periods", []):
        period = FinancialPeriod(
            label=pdata["label"],
            fiscal_year=pdata.get("fiscal_year"),
            currency=pdata.get("currency", "USD"),
            source=pdata.get("source", "User upload"),
        )
        for key, value in pdata.items():
            if key in _VALID_ATTRS and value is not None:
                setattr(period, key, float(value))
        company.periods.append(period)

    adata = data.get("assumptions", {})
    company.assumptions = Assumptions(**{
        k: v for k, v in adata.items() if k in Assumptions().__dict__
    })
    return company.normalize()


def company_from_json(path: str | Path) -> Company:
    return company_from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def confirm_grid(company: Company) -> str:
    """Render the review-and-correct grid the user must accept before compute.

    Returns a printable table of every mapped line item per period. The caller
    is responsible for obtaining explicit confirmation."""
    lines = [f"CONFIRMATION GRID -- {company.name} ({company.mode} mode)",
             "Review every mapped value. Correct anything wrong BEFORE analysis.",
             ""]
    header = ["Line item"] + [p.label for p in company.periods]
    widths = [28] + [14] * len(company.periods)
    lines.append(_row(header, widths))
    lines.append(_row(["-" * (w - 1) for w in widths], widths))
    for attr, _label, _stmt, name in ALL_FIELDS:
        vals = []
        present = False
        for p in company.periods:
            v = getattr(p, attr)
            if v is None:
                vals.append("n/a")
            else:
                vals.append(f"{v:,.0f}")
                present = True
        if present:
            lines.append(_row([name] + vals, widths))
    lines.append("")
    lines.append("Confirm these figures are correct before computing metrics.")
    return "\n".join(lines)


def parse_document(path: str | Path, name: str = "Uploaded Company") -> dict:
    """Extract a single statement / tax-form PDF into a company dict (unconfirmed).

    Handles income statement, balance sheet, cash-flow statement and tax forms
    (1120 / 1120-S / 1065 / Schedule C). The result MUST be reviewed via
    ``confirm_grid`` before it reaches a calculation -- no extracted number is
    silently trusted (spec section 8)."""
    from .parse import parse_statements
    return parse_statements([path], name=name)


def company_from_documents(paths, name: str = "Uploaded Company") -> Company:
    """Parse and merge one or more statement PDFs into a (still-unconfirmed)
    Company. Show ``confirm_grid`` and obtain user sign-off before computing."""
    from .parse import parse_statements
    if isinstance(paths, (str, Path)):
        paths = [paths]
    return company_from_dict(parse_statements(paths, name=name))


def _row(cells, widths) -> str:
    return "".join(str(c).ljust(w) for c, w in zip(cells, widths))


__all__ = [
    "company_from_dict", "company_from_json", "confirm_grid",
    "parse_document", "company_from_documents",
]
