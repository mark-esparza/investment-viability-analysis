"""SEC EDGAR ingestion (spec section 2.1)."""

from .client import EdgarClient
from .ingest import analyze_ticker, build_company_from_facts

__all__ = ["EdgarClient", "analyze_ticker", "build_company_from_facts"]
