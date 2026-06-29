"""Best-effort live retrieval of current-market assumption inputs (Rf, beta,
market return, tax rate) from public, no-API-key sources.

Same guardrail as the rest of the app: never invent a number. Each suggested
field carries its source and as-of date so the user can judge it before
accepting; any field that can't be fetched is omitted rather than guessed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import requests

_UA = os.environ.get("IVA_SEC_USER_AGENT", "InvestmentViability/1.0 contact@example.com")
_TIMEOUT = 6

# Damodaran's published implied U.S. equity risk premium is the standard,
# citable reference point for E(Rm) when no live ERP feed is available;
# it's a periodically-updated estimate, not a real-time quote.
_DAMODARAN_ERP = 0.046
_US_FEDERAL_CORPORATE_TAX_RATE = 0.21  # statutory rate under current law (TCJA, 2018-)


@dataclass
class Suggestion:
    field: str
    label: str
    value: float
    source: str
    asof: Optional[str] = None
    note: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "field": self.field, "label": self.label, "value": self.value,
            "source": self.source, "asof": self.asof, "note": self.note,
        }


def fetch_risk_free_rate() -> Optional[Suggestion]:
    """10-Year Treasury Constant Maturity Rate (DGS10), via FRED's public CSV."""
    try:
        r = requests.get(
            "https://fred.stlouisfed.org/graph/fredgraph.csv",
            params={"id": "DGS10"}, timeout=_TIMEOUT,
            headers={"User-Agent": _UA},
        )
        r.raise_for_status()
        rows = [ln.split(",") for ln in r.text.strip().splitlines() if ln.strip()]
        for date, val in reversed(rows[1:]):
            if val not in (".", ""):
                return Suggestion(
                    "risk_free_rate", "Risk-free rate Rf", round(float(val) / 100, 4),
                    "FRED: 10-Year Treasury Constant Maturity Rate (DGS10)", date,
                )
    except Exception:
        pass
    return None


def fetch_market_return(risk_free: Optional[float]) -> Optional[Suggestion]:
    """E(Rm) = Rf + a published implied equity risk premium (Damodaran)."""
    if risk_free is None:
        rf_sugg = fetch_risk_free_rate()
        risk_free = rf_sugg.value if rf_sugg else None
    if risk_free is None:
        return None
    return Suggestion(
        "market_return", "Market return E(Rm)", round(risk_free + _DAMODARAN_ERP, 4),
        "Rf (FRED DGS10) + Damodaran implied U.S. equity risk premium",
        note=f"ERP taken as {_DAMODARAN_ERP:.1%} (Damodaran's periodically-updated "
             "estimate, not a live feed) -- override if you track a different figure.",
    )


def fetch_beta(ticker: str) -> Optional[Suggestion]:
    """Beta from Yahoo Finance's public quoteSummary endpoint (no key required)."""
    if not ticker:
        return None
    try:
        r = requests.get(
            f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker.upper()}",
            params={"modules": "defaultKeyStatistics"}, timeout=_TIMEOUT,
            headers={"User-Agent": _UA},
        )
        r.raise_for_status()
        result = r.json()["quoteSummary"]["result"]
        if not result:
            return None
        beta = result[0]["defaultKeyStatistics"].get("beta", {}).get("raw")
        if beta is None:
            return None
        return Suggestion(
            "beta", "Beta", round(float(beta), 3),
            f"Yahoo Finance defaultKeyStatistics ({ticker.upper()})",
        )
    except Exception:
        return None


def fetch_tax_rate() -> Suggestion:
    """U.S. federal statutory corporate tax rate (current law)."""
    return Suggestion(
        "tax_rate", "Tax rate T", _US_FEDERAL_CORPORATE_TAX_RATE,
        "U.S. federal statutory corporate rate (Tax Cuts and Jobs Act, 2018-)",
        note="Federal only -- add state/local corporate tax if applicable to this company.",
    )


def suggest_assumptions(ticker: Optional[str], is_public: bool) -> list[dict]:
    """Guided retrieval: ticker/public-vs-private context decides which fields
    are even attempted (e.g. beta only makes sense for a public ticker)."""
    out: list[Suggestion] = []

    rf = fetch_risk_free_rate()
    if rf:
        out.append(rf)

    mkt = fetch_market_return(rf.value if rf else None)
    if mkt:
        out.append(mkt)

    if is_public and ticker:
        beta = fetch_beta(ticker)
        if beta:
            out.append(beta)

    out.append(fetch_tax_rate())

    return [s.as_dict() for s in out]
