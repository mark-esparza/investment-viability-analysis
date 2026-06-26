"""Map SEC CompanyFacts -> the canonical section-3 model.

Every populated number records its provenance (form + period + XBRL tag) so the
report can cite sources and nothing is fabricated (spec section 8). Periods with
no data for a field are left ``None`` -> dependent ratios are excluded, not
guessed.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from ..model import ALL_FIELDS, Company, FinancialPeriod
from .client import EdgarClient
from .tags import TAG_ALIASES


def _iso_to_date(s: str) -> Optional[date]:
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _annual_series(facts: dict, tag: str) -> dict[int, dict]:
    """Return {fiscal_year: fact} of best annual (10-K, FY) values for a tag.

    Handles duration concepts (income/cash-flow, ~365-day span) and instant
    concepts (balance-sheet, fiscal-year-end snapshot) alike, and searches all
    unit types (USD, shares, USD/shares)."""
    for taxonomy in ("us-gaap", "dei", "ifrs-full"):
        node = facts.get(taxonomy, {}).get(tag)
        if node:
            break
    else:
        return {}

    out: dict[int, dict] = {}
    for unit_key, observations in node.get("units", {}).items():
        for fact in observations:
            fy = fact.get("fy")
            fp = fact.get("fp")
            form = fact.get("form", "")
            if fy is None or not form.startswith("10-K"):
                continue
            if fp not in ("FY", None):
                continue
            start = _iso_to_date(fact.get("start", "")) if "start" in fact else None
            end = _iso_to_date(fact.get("end", ""))
            if start and end:  # duration fact -> require ~full year
                span = (end - start).days
                if not (350 <= span <= 380):
                    continue
            # Prefer the most recently filed observation for a given year.
            existing = out.get(fy)
            if existing is None or fact.get("filed", "") >= existing.get("filed", ""):
                out[fy] = {**fact, "_unit": unit_key, "_tag": tag, "_taxonomy": taxonomy}
    return out


def _pick(facts: dict, attr: str, fy: int) -> Optional[dict]:
    """First aliased tag with a value for fiscal year ``fy``."""
    for tag in TAG_ALIASES.get(attr, []):
        series = _annual_series(facts, tag)
        if fy in series:
            return series[fy]
    return None


def build_company_from_facts(
    company_facts: dict,
    ticker: Optional[str] = None,
    cik: Optional[str] = None,
    years: int = 4,
) -> Company:
    facts = company_facts.get("facts", {})
    name = company_facts.get("entityName", ticker or "Unknown")

    # Candidate fiscal years: union across all core tags, anchored on Assets.
    asset_years = set(_annual_series(facts, "Assets").keys())
    revenue_years: set[int] = set()
    for tag in TAG_ALIASES["revenue"]:
        revenue_years |= set(_annual_series(facts, tag).keys())
    candidate_years = sorted(asset_years | revenue_years)
    chosen = candidate_years[-years:] if candidate_years else []

    company = Company(name=name, ticker=ticker, cik=cik, mode="public")
    for fy in chosen:
        period = FinancialPeriod(label=f"FY{str(fy)[-2:]}", fiscal_year=fy)
        provenance: list[str] = []
        for attr, _label, _stmt, _name in ALL_FIELDS:
            fact = _pick(facts, attr, fy)
            if fact is None:
                continue
            setattr(period, attr, float(fact["val"]))
            provenance.append(f"{attr}<-{fact['_taxonomy']}:{fact['_tag']}")
        period.source = f"SEC 10-K FY{fy}"
        company.periods.append(period)

    return company.normalize()


def analyze_ticker(ticker: str, years: int = 4, offline: bool = False,
                   client: Optional[EdgarClient] = None) -> Company:
    """End-to-end public-company ingestion: ticker -> CIK -> facts -> model."""
    client = client or EdgarClient(offline=offline)
    cik = client.ticker_to_cik(ticker)
    if cik is None:
        raise ValueError(f"Could not resolve ticker '{ticker}' to a CIK")
    facts = client.company_facts(cik)
    return build_company_from_facts(facts, ticker=ticker.upper(), cik=cik, years=years)
