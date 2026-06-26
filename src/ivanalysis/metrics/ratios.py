"""Liquidity, activity, leverage, profitability and DuPont (spec 4.1-4.5).

Each function takes a ``Ctx`` (company bound to a period) and returns a
``MetricResult`` carrying the number and the live Excel formula.
"""

from __future__ import annotations

from .common import Ctx, MetricResult, avg, sadd, sdiv, smul, ssub

DAYS = 365


# ---------------------------------------------------------------------------
# 4.1 Liquidity
# ---------------------------------------------------------------------------
def current_ratio(c: Ctx) -> MetricResult:
    return MetricResult(
        "Current Ratio", "Liquidity",
        sdiv(c.val("current_assets"), c.val("current_liabilities")),
        f"={c.ref('current_assets')}/{c.ref('current_liabilities')}",
        "Current assets per $1 of current liabilities; >1 covers near-term bills.",
        "x", healthy=lambda v: v >= 1.0,
    )


def quick_ratio(c: Ctx) -> MetricResult:
    numer = ssub(c.val("current_assets"), c.val("inventory"))
    return MetricResult(
        "Quick (Acid-Test) Ratio", "Liquidity",
        sdiv(numer, c.val("current_liabilities")),
        f"=({c.ref('current_assets')}-{c.ref('inventory')})/{c.ref('current_liabilities')}",
        "Liquidity excluding inventory; >1 is conservative coverage.",
        "x", healthy=lambda v: v >= 0.9,
    )


def net_working_capital(c: Ctx) -> MetricResult:
    return MetricResult(
        "Net Working Capital", "Liquidity",
        ssub(c.val("current_assets"), c.val("current_liabilities")),
        f"={c.ref('current_assets')}-{c.ref('current_liabilities')}",
        "Current assets minus current liabilities; the operating cushion.",
        "$", healthy=lambda v: v >= 0,
    )


def nwc_to_total_assets(c: Ctx) -> MetricResult:
    nwc = ssub(c.val("current_assets"), c.val("current_liabilities"))
    return MetricResult(
        "NWC-to-Total-Assets", "Liquidity",
        sdiv(nwc, c.val("total_assets")),
        f"=({c.ref('current_assets')}-{c.ref('current_liabilities')})/{c.ref('total_assets')}",
        "Share of assets funded as working-capital cushion.",
        "%",
    )


# ---------------------------------------------------------------------------
# 4.2 Activity / Efficiency  (averages use prior period when available)
# ---------------------------------------------------------------------------
def inventory_turnover(c: Ctx) -> MetricResult:
    avg_inv = avg(c.val("inventory"), c.val("inventory", -1))
    if c.has_prior and c.val("inventory", -1) is not None:
        denom = f"AVERAGE({c.ref('inventory')},{c.ref('inventory', -1)})"
    else:
        denom = c.ref("inventory")
    return MetricResult(
        "Inventory Turnover", "Activity",
        sdiv(c.val("cogs"), avg_inv),
        f"={c.ref('cogs')}/{denom}",
        "Times inventory sold per year; higher = leaner stock.",
        "x", healthy=lambda v: v > 0,
    )


def days_sales_inventory(c: Ctx) -> MetricResult:
    turns = sdiv(c.val("cogs"), avg(c.val("inventory"), c.val("inventory", -1)))
    if c.has_prior and c.val("inventory", -1) is not None:
        denom = f"AVERAGE({c.ref('inventory')},{c.ref('inventory', -1)})"
    else:
        denom = c.ref("inventory")
    return MetricResult(
        "Days Sales in Inventory", "Activity",
        sdiv(DAYS, turns),
        f"={DAYS}/({c.ref('cogs')}/{denom})",
        "Days of inventory on hand; lower = faster conversion to cash.",
        "days",
    )


def collection_period(c: Ctx) -> MetricResult:
    # DSO = AR / (Credit Sales / 365). Credit sales default to total revenue.
    daily_sales = sdiv(c.val("revenue"), DAYS)
    return MetricResult(
        "Collection Period (DSO)", "Activity",
        sdiv(c.val("accounts_receivable"), daily_sales),
        f"={c.ref('accounts_receivable')}/({c.ref('revenue')}/{DAYS})",
        "Average days to collect receivables; lower is better.",
        "days",
    )


def fixed_asset_turnover(c: Ctx) -> MetricResult:
    return MetricResult(
        "Fixed Asset Turnover", "Activity",
        sdiv(c.val("revenue"), c.val("net_fixed_assets")),
        f"={c.ref('revenue')}/{c.ref('net_fixed_assets')}",
        "Sales generated per $1 of net fixed assets.",
        "x",
    )


def total_asset_turnover(c: Ctx) -> MetricResult:
    return MetricResult(
        "Total Asset Turnover", "Activity",
        sdiv(c.val("revenue"), c.val("total_assets")),
        f"={c.ref('revenue')}/{c.ref('total_assets')}",
        "Sales generated per $1 of total assets.",
        "x",
    )


# ---------------------------------------------------------------------------
# 4.3 Leverage / Solvency
# ---------------------------------------------------------------------------
def debt_ratio(c: Ctx) -> MetricResult:
    return MetricResult(
        "Debt Ratio", "Leverage",
        sdiv(c.val("total_liabilities"), c.val("total_assets")),
        f"={c.ref('total_liabilities')}/{c.ref('total_assets')}",
        "Share of assets financed by liabilities; lower = less risk.",
        "%", healthy=lambda v: v <= 0.7,
    )


def debt_to_equity(c: Ctx) -> MetricResult:
    return MetricResult(
        "Debt-to-Equity (LT)", "Leverage",
        sdiv(c.val("long_term_debt"), c.val("total_equity")),
        f"={c.ref('long_term_debt')}/{c.ref('total_equity')}",
        "Long-term debt per $1 of equity.",
        "x", healthy=lambda v: v <= 2.0,
    )


def total_debt_to_equity(c: Ctx) -> MetricResult:
    return MetricResult(
        "Total Debt-to-Equity", "Leverage",
        sdiv(c.val("total_liabilities"), c.val("total_equity")),
        f"={c.ref('total_liabilities')}/{c.ref('total_equity')}",
        "All liabilities per $1 of equity.",
        "x", healthy=lambda v: v <= 3.0,
    )


def times_interest_earned(c: Ctx) -> MetricResult:
    return MetricResult(
        "Times Interest Earned", "Leverage",
        sdiv(c.val("ebit"), c.val("interest_expense")),
        f"={c.ref('ebit')}/{c.ref('interest_expense')}",
        "EBIT coverage of interest; >3 is comfortable.",
        "x", healthy=lambda v: v >= 3.0,
    )


def cash_coverage(c: Ctx) -> MetricResult:
    numer = sadd(c.val("ebit"), c.val("depreciation"))
    return MetricResult(
        "Cash Coverage", "Leverage",
        sdiv(numer, c.val("interest_expense")),
        f"=({c.ref('ebit')}+{c.ref('depreciation')})/{c.ref('interest_expense')}",
        "Interest coverage adding back non-cash depreciation.",
        "x", healthy=lambda v: v >= 3.5,
    )


def fixed_charge_coverage(c: Ctx) -> MetricResult:
    numer = sadd(c.val("ebit"), c.val("lease_payments"))
    denom = sadd(c.val("interest_expense"), c.val("lease_payments"))
    return MetricResult(
        "Fixed Charge Coverage", "Leverage",
        sdiv(numer, denom),
        f"=({c.ref('ebit')}+{c.ref('lease_payments')})/"
        f"({c.ref('interest_expense')}+{c.ref('lease_payments')})",
        "Coverage of interest + lease obligations.",
        "x", healthy=lambda v: v >= 1.5,
    )


def equity_multiplier(c: Ctx) -> MetricResult:
    return MetricResult(
        "Equity Multiplier", "Leverage",
        sdiv(c.val("total_assets"), c.val("total_equity")),
        f"={c.ref('total_assets')}/{c.ref('total_equity')}",
        "Assets per $1 of equity; the leverage factor in DuPont.",
        "x",
    )


# ---------------------------------------------------------------------------
# 4.4 Profitability
# ---------------------------------------------------------------------------
def gross_margin(c: Ctx) -> MetricResult:
    return MetricResult(
        "Gross Profit Margin", "Profitability",
        sdiv(c.val("gross_profit"), c.val("revenue")),
        f"={c.ref('gross_profit')}/{c.ref('revenue')}",
        "Gross profit per $1 of sales.",
        "%", healthy=lambda v: v >= 0.20,
    )


def net_margin(c: Ctx) -> MetricResult:
    return MetricResult(
        "Net Profit Margin", "Profitability",
        sdiv(c.val("net_income"), c.val("revenue")),
        f"={c.ref('net_income')}/{c.ref('revenue')}",
        "Bottom-line profit per $1 of sales.",
        "%", healthy=lambda v: v >= 0.05,
    )


def roa(c: Ctx) -> MetricResult:
    return MetricResult(
        "Return on Assets (ROA)", "Profitability",
        sdiv(c.val("net_income"), c.val("total_assets")),
        f"={c.ref('net_income')}/{c.ref('total_assets')}",
        "Net income per $1 of assets.",
        "%", healthy=lambda v: v >= 0.05,
    )


def roe(c: Ctx) -> MetricResult:
    return MetricResult(
        "Return on Equity (ROE)", "Profitability",
        sdiv(c.val("net_income"), c.val("total_equity")),
        f"={c.ref('net_income')}/{c.ref('total_equity')}",
        "Net income per $1 of equity.",
        "%", healthy=lambda v: v >= 0.10,
    )


def eps(c: Ctx) -> MetricResult:
    # Earnings available to common / diluted shares.
    common_earn = ssub(c.val("net_income"), c.val("preferred_dividends") or 0.0)
    pref = c.val("preferred_dividends")
    pref_term = f"-{c.ref('preferred_dividends')}" if pref else ""
    return MetricResult(
        "Earnings per Share (EPS)", "Profitability",
        sdiv(common_earn, c.val("diluted_shares")),
        f"=({c.ref('net_income')}{pref_term})/{c.ref('diluted_shares')}",
        "Earnings attributable to each common share.",
        "$",
    )


def pe_ratio(c: Ctx) -> MetricResult:
    eps_val = sdiv(
        ssub(c.val("net_income"), c.val("preferred_dividends") or 0.0),
        c.val("diluted_shares"),
    )
    return MetricResult(
        "Price/Earnings (P/E)", "Profitability",
        sdiv(c.aval("price_per_share"), eps_val),
        f"={c.aref('price_per_share')}/{c.ref('eps')}",
        "Price paid per $1 of annual earnings.",
        "x",
    )


def market_to_book(c: Ctx) -> MetricResult:
    return MetricResult(
        "Market-to-Book", "Profitability",
        sdiv(c.aval("price_per_share"), c.aval("book_value_per_share")),
        f"={c.aref('price_per_share')}/{c.aref('book_value_per_share')}",
        "Market price relative to accounting book value per share.",
        "x",
    )


# ---------------------------------------------------------------------------
# 4.5 DuPont decomposition
# ---------------------------------------------------------------------------
def dupont_three_step(c: Ctx) -> MetricResult:
    npm = sdiv(c.val("net_income"), c.val("revenue"))
    tat = sdiv(c.val("revenue"), c.val("total_assets"))
    em = sdiv(c.val("total_assets"), c.val("total_equity"))
    return MetricResult(
        "ROE (DuPont 3-step)", "DuPont",
        smul(npm, tat, em),
        f"=({c.ref('net_income')}/{c.ref('revenue')})"
        f"*({c.ref('revenue')}/{c.ref('total_assets')})"
        f"*({c.ref('total_assets')}/{c.ref('total_equity')})",
        "ROE = Net Margin x Asset Turnover x Equity Multiplier.",
        "%",
    )


def dupont_roa_leverage(c: Ctx) -> MetricResult:
    roa_v = sdiv(c.val("net_income"), c.val("total_assets"))
    de = sdiv(c.val("total_liabilities"), c.val("total_equity"))
    val = None
    if roa_v is not None and de is not None:
        val = roa_v * (1 + de)
    return MetricResult(
        "ROE (ROA x leverage)", "DuPont",
        val,
        f"=({c.ref('net_income')}/{c.ref('total_assets')})"
        f"*(1+{c.ref('total_liabilities')}/{c.ref('total_equity')})",
        "Cross-check: ROE = ROA x (1 + Total Debt/Equity).",
        "%",
    )


# Ordered registry consumed by the engine and the Excel writer.
RATIO_METRICS = [
    current_ratio, quick_ratio, net_working_capital, nwc_to_total_assets,
    inventory_turnover, days_sales_inventory, collection_period,
    fixed_asset_turnover, total_asset_turnover,
    debt_ratio, debt_to_equity, total_debt_to_equity, times_interest_earned,
    cash_coverage, fixed_charge_coverage, equity_multiplier,
    gross_margin, net_margin, roa, roe, eps, pe_ratio, market_to_book,
    dupont_three_step, dupont_roa_leverage,
]
