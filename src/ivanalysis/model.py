"""Canonical internal data model (spec section 3).

Both ingestion modes -- SEC EDGAR (public companies) and parsed user uploads
(private / small business) -- normalize into these structures before any metric
is computed. Keeping a single schema is what lets the same equation engine and
the same Excel contract serve both modes.

Every monetary field is ``Optional[float]``: ``None`` means "not available"
rather than zero, so dependent ratios can be excluded honestly (spec section 8).
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Optional


# ---------------------------------------------------------------------------
# Field registry -- single source of truth shared by the model, the Excel
# Inputs sheet, and the formula builder. (attr, excel_label, statement, label)
#   excel_label -> used to build named ranges like ``Sales_FY24``
# ---------------------------------------------------------------------------
INCOME_FIELDS = [
    ("revenue", "Sales", "Income Statement", "Revenue (Sales)"),
    ("cogs", "COGS", "Income Statement", "Cost of Goods Sold"),
    ("gross_profit", "GrossProfit", "Income Statement", "Gross Profit"),
    ("operating_expenses", "OpEx", "Income Statement", "Operating / Admin Expenses"),
    ("depreciation", "Depreciation", "Income Statement", "Depreciation & Amortization"),
    ("ebit", "EBIT", "Income Statement", "EBIT (Operating Income)"),
    ("interest_expense", "Interest", "Income Statement", "Interest Expense"),
    ("ebt", "EBT", "Income Statement", "Earnings Before Tax"),
    ("taxes", "Taxes", "Income Statement", "Income Taxes"),
    ("net_income", "NetIncome", "Income Statement", "Net Income"),
    ("preferred_dividends", "PrefDiv", "Income Statement", "Preferred Dividends"),
    ("diluted_shares", "DilutedShares", "Income Statement", "Diluted Shares Outstanding"),
    ("eps", "EPS", "Income Statement", "Earnings per Share (diluted)"),
]

BALANCE_FIELDS = [
    ("cash", "Cash", "Balance Sheet", "Cash & Equivalents"),
    ("marketable_securities", "Marketable", "Balance Sheet", "Marketable Securities"),
    ("accounts_receivable", "AR", "Balance Sheet", "Accounts Receivable"),
    ("inventory", "Inventory", "Balance Sheet", "Inventory"),
    ("other_current_assets", "OtherCA", "Balance Sheet", "Other Current Assets"),
    ("current_assets", "CurrentAssets", "Balance Sheet", "Total Current Assets"),
    ("net_fixed_assets", "NetFixedAssets", "Balance Sheet", "Net Fixed Assets"),
    ("total_assets", "TotalAssets", "Balance Sheet", "Total Assets"),
    ("accounts_payable", "AP", "Balance Sheet", "Accounts Payable"),
    ("other_current_liabilities", "OtherCL", "Balance Sheet", "Other Current Liabilities"),
    ("current_liabilities", "CurrentLiab", "Balance Sheet", "Total Current Liabilities"),
    ("long_term_debt", "LongTermDebt", "Balance Sheet", "Long-Term Debt"),
    ("total_liabilities", "TotalLiab", "Balance Sheet", "Total Liabilities"),
    ("preferred_equity", "PrefEquity", "Balance Sheet", "Preferred Equity"),
    ("common_equity", "CommonEquity", "Balance Sheet", "Common Equity"),
    ("total_equity", "TotalEquity", "Balance Sheet", "Total Equity"),
]

CASHFLOW_FIELDS = [
    ("cfo", "CFO", "Cash Flow", "Cash Flow from Operations"),
    ("cfi", "CFI", "Cash Flow", "Cash Flow from Investing"),
    ("cff", "CFF", "Cash Flow", "Cash Flow from Financing"),
    ("net_change_cash", "NetChangeCash", "Cash Flow", "Net Change in Cash"),
    ("lease_payments", "LeasePayments", "Cash Flow", "Lease Payments"),
    ("capex", "CapEx", "Cash Flow", "Capital Expenditures"),
    ("delta_nwc", "DeltaNWC", "Cash Flow", "Change in Net Working Capital"),
]

ALL_FIELDS = INCOME_FIELDS + BALANCE_FIELDS + CASHFLOW_FIELDS

# attr -> excel_label lookup
EXCEL_LABEL = {attr: label for attr, label, _stmt, _name in ALL_FIELDS}
FIELD_LABEL = {attr: name for attr, _label, _stmt, name in ALL_FIELDS}


def excel_name(attr: str, period_label: str) -> str:
    """Named-range identifier for a model field in a given period, e.g.
    ``Sales_FY24``. Periods are sanitized to valid range characters."""
    safe_period = period_label.replace("-", "_").replace(" ", "_")
    return f"{EXCEL_LABEL[attr]}_{safe_period}"


@dataclass
class FinancialPeriod:
    """One reporting period (fiscal year or quarter) across all statements."""

    label: str  # e.g. "FY24"
    fiscal_year: Optional[int] = None
    currency: str = "USD"
    source: str = ""  # provenance, e.g. "SEC 10-K FY2024" or "Upload: IS.pdf"

    # Income statement
    revenue: Optional[float] = None
    cogs: Optional[float] = None
    gross_profit: Optional[float] = None
    operating_expenses: Optional[float] = None
    depreciation: Optional[float] = None
    ebit: Optional[float] = None
    interest_expense: Optional[float] = None
    ebt: Optional[float] = None
    taxes: Optional[float] = None
    net_income: Optional[float] = None
    preferred_dividends: Optional[float] = None
    diluted_shares: Optional[float] = None
    eps: Optional[float] = None

    # Balance sheet
    cash: Optional[float] = None
    marketable_securities: Optional[float] = None
    accounts_receivable: Optional[float] = None
    inventory: Optional[float] = None
    other_current_assets: Optional[float] = None
    current_assets: Optional[float] = None
    net_fixed_assets: Optional[float] = None
    total_assets: Optional[float] = None
    accounts_payable: Optional[float] = None
    other_current_liabilities: Optional[float] = None
    current_liabilities: Optional[float] = None
    long_term_debt: Optional[float] = None
    total_liabilities: Optional[float] = None
    preferred_equity: Optional[float] = None
    common_equity: Optional[float] = None
    total_equity: Optional[float] = None

    # Cash flow
    cfo: Optional[float] = None
    cfi: Optional[float] = None
    cff: Optional[float] = None
    net_change_cash: Optional[float] = None
    lease_payments: Optional[float] = None
    capex: Optional[float] = None
    delta_nwc: Optional[float] = None

    def derive_missing(self) -> None:
        """Fill obvious identities when a component is missing but its parts are
        present. Conservative: never overwrites a value that already exists."""
        if self.gross_profit is None and _have(self.revenue, self.cogs):
            self.gross_profit = self.revenue - self.cogs
        if self.ebt is None and _have(self.ebit, self.interest_expense):
            self.ebt = self.ebit - self.interest_expense
        if self.net_income is None and _have(self.ebt, self.taxes):
            self.net_income = self.ebt - self.taxes
        if self.total_equity is None and _have(self.common_equity, self.preferred_equity):
            self.total_equity = self.common_equity + self.preferred_equity
        # Many large filers tag Assets and StockholdersEquity but no single
        # Liabilities element; recover it from the accounting identity rather
        # than dropping every leverage ratio.
        if self.total_liabilities is None and _have(self.total_assets, self.total_equity):
            self.total_liabilities = self.total_assets - self.total_equity
        if self.eps is None and _have(self.net_income, self.diluted_shares) and self.diluted_shares:
            common_earn = self.net_income - (self.preferred_dividends or 0.0)
            self.eps = common_earn / self.diluted_shares


@dataclass
class Assumptions:
    """Market inputs and policy assumptions (spec section 3, last bullet).

    All overridable; never hardcode these into calculations (spec section 2.3)."""

    price_per_share: Optional[float] = None
    shares_outstanding: Optional[float] = None
    book_value_per_share: Optional[float] = None
    dividend_per_share: Optional[float] = None
    dividend_growth_g: Optional[float] = None  # g
    risk_free_rate: Optional[float] = None  # Rf
    market_return: Optional[float] = None  # E(Rm)
    beta: Optional[float] = None
    required_return_k: Optional[float] = None  # k / WACC override
    tax_rate: Optional[float] = None  # T
    flotation_cost: Optional[float] = 0.0  # f
    # Capital structure weights (for WACC); default to nothing => derived
    weight_debt: Optional[float] = None
    weight_preferred: Optional[float] = None
    weight_equity: Optional[float] = None
    cost_of_debt_pretax: Optional[float] = None  # before-tax yield to maturity

    def as_named_cells(self) -> dict:
        """attr -> (named_range, value) for the Assumptions sheet."""
        out = {}
        for f in fields(self):
            out[f.name] = (_assumption_name(f.name), getattr(self, f.name))
        return out


# Assumption named ranges use a fixed map so formulas read clearly.
_ASSUMPTION_NAMES = {
    "price_per_share": "Price",
    "shares_outstanding": "SharesOut",
    "book_value_per_share": "BookValuePS",
    "dividend_per_share": "DPS",
    "dividend_growth_g": "GrowthG",
    "risk_free_rate": "Rf",
    "market_return": "MarketReturn",
    "beta": "Beta",
    "required_return_k": "RequiredReturnK",
    "tax_rate": "TaxRate",
    "flotation_cost": "Flotation",
    "weight_debt": "WeightDebt",
    "weight_preferred": "WeightPref",
    "weight_equity": "WeightEquity",
    "cost_of_debt_pretax": "CostDebtPretax",
}


def _assumption_name(attr: str) -> str:
    return _ASSUMPTION_NAMES.get(attr, attr)


@dataclass
class Company:
    """Top-level container. ``periods`` are ordered oldest -> newest so index
    arithmetic (prior-period averages, growth) is well defined."""

    name: str
    ticker: Optional[str] = None
    cik: Optional[str] = None
    mode: str = "public"  # "public" | "private"
    description: str = ""
    periods: list[FinancialPeriod] = field(default_factory=list)
    assumptions: Assumptions = field(default_factory=Assumptions)

    def sorted_periods(self) -> list[FinancialPeriod]:
        return sorted(
            self.periods,
            key=lambda p: (p.fiscal_year if p.fiscal_year is not None else 0, p.label),
        )

    def normalize(self) -> "Company":
        self.periods = self.sorted_periods()
        for p in self.periods:
            p.derive_missing()
        return self


def _have(*vals) -> bool:
    return all(v is not None for v in vals)
