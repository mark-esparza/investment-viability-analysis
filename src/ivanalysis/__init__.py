"""Investment-Viability Analysis.

Ingests company financials from SEC EDGAR (public companies) or user uploads
(private / small business), computes the full finance equation library, and
emits a live-formula Excel workbook plus a narrative viability report.

Public API (also the intended MCP tool surface):
    analyze_ticker(ticker)        -> Company           (public mode)
    company_from_json(path)       -> Company           (private mode)
    build_workbook(company, path) -> Path              (live .xlsx)
    generate_report(company)      -> str               (markdown report)
"""

from .edgar import analyze_ticker
from .excel import build_workbook
from .model import Assumptions, Company, FinancialPeriod
from .report import generate_report, score_viability
from .uploads import company_from_dict, company_from_json

__version__ = "0.1.0"

__all__ = [
    "analyze_ticker", "build_workbook", "generate_report", "score_viability",
    "company_from_dict", "company_from_json",
    "Company", "FinancialPeriod", "Assumptions",
]
