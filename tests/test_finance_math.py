"""Validate the equation library (spec 4.6-4.11) against textbook numbers.

These canonical cases are the authoritative check on formula correctness
(acceptance criterion 3) -- independent of any reference guide.
"""

import math

from ivanalysis.metrics import finance_math as fm


def approx(a, b, tol=1e-3):
    return abs(a - b) <= tol


# ---- 4.6 Time Value of Money ----
def test_pv_fv_single():
    assert approx(fm.pv_single(1000, 0.10, 5), 620.921, 1e-2)
    assert approx(fm.fv_single(1000, 0.10, 5), 1610.510, 1e-2)


def test_pv_single_compounded():
    # 1000 at 12% compounded monthly for 1 year
    assert approx(fm.pv_single(1000, 0.12, 1, m=12), 1000 / (1 + 0.01) ** 12, 1e-6)


def test_continuous():
    assert approx(fm.fv_continuous(1000, 0.10, 5), 1000 * math.exp(0.5), 1e-6)
    assert approx(fm.pv_continuous(1000, 0.10, 5), 1000 * math.exp(-0.5), 1e-6)


def test_annuities():
    assert approx(fm.pv_annuity(100, 0.10, 5), 379.079, 1e-2)
    assert approx(fm.fv_annuity(100, 0.10, 5), 610.510, 1e-2)
    # annuity due = ordinary x (1+r)
    assert approx(fm.pv_annuity(100, 0.10, 5, due=True),
                  fm.pv_annuity(100, 0.10, 5) * 1.10, 1e-6)


def test_perpetuity_and_rates():
    assert approx(fm.pv_perpetuity(100, 0.10), 1000.0)
    assert approx(fm.ear(0.12, 12), 0.126825, 1e-5)
    assert approx(fm.apr(0.01, 12), 0.12)


# ---- 4.7 Capital Budgeting ----
CF = [-1000, 500, 400, 300, 100]


def test_ocf_and_ncf():
    # (Rev-Costs)(1-T) + T*Dep
    assert approx(fm.operating_cash_flow(1000, 600, 100, 0.30), 310.0)
    assert approx(fm.net_cash_flow(310, 20, 50), 240.0)


def test_npv():
    assert approx(fm.npv(0.10, CF), 78.819, 1e-2)


def test_irr_zeroes_npv():
    r = fm.irr(CF)
    assert r is not None
    assert approx(fm.npv(r, CF), 0.0, 1e-4)


def test_pi_payback_arr():
    pi = fm.profitability_index(0.10, CF)
    assert approx(pi, 1.0788, 1e-3)
    # payback: -1000 +500 +400 -> 900 by yr2, needs 100/300 of yr3
    assert approx(fm.payback_period(CF), 2.333, 1e-2)
    assert approx(fm.accounting_rate_of_return(150, 1000), 0.15)


def test_decision_rules():
    d = fm.capital_budget_decision(fm.npv(0.10, CF), fm.irr(CF),
                                   fm.profitability_index(0.10, CF), 0.10)
    assert d == {"npv": "ACCEPT", "irr": "ACCEPT", "pi": "ACCEPT"}


# ---- 4.8 Risk & Return / CAPM ----
def test_expected_return_variance():
    probs = [0.3, 0.4, 0.3]
    rets = [0.10, 0.15, 0.20]
    er = fm.expected_return(probs, rets)
    assert approx(er, 0.15)
    assert approx(fm.std_dev(probs, rets), math.sqrt(fm.variance(probs, rets)))


def test_capm_and_portfolio():
    assert approx(fm.capm(0.03, 1.2, 0.08), 0.09)
    assert approx(fm.beta_from_cov(0.04, 0.05), 0.8)
    assert approx(fm.portfolio_return(0.6, 0.10, 0.4, 0.05), 0.08)
    var = fm.portfolio_variance(0.6, 0.2, 0.4, 0.1, 0.01)
    assert approx(var, 0.6**2 * 0.04 + 0.4**2 * 0.01 + 2 * 0.6 * 0.4 * 0.01, 1e-9)


def test_correlation_bounds():
    probs = [0.5, 0.5]
    rho = fm.correlation(probs, [0.1, 0.2], [0.2, 0.4])
    assert approx(rho, 1.0, 1e-6)  # perfectly correlated


# ---- 4.9 Valuation ----
def test_bond_and_stock_valuation():
    # 8% annual coupon, par 1000, 5y, yield 10% -> ~924.18
    assert approx(fm.bond_value(80, 1000, 0.10, 5, freq=1), 924.184, 1e-1)
    assert approx(fm.gordon_growth(2.0, 0.05, 0.10), 42.0, 1e-6)
    assert fm.gordon_growth(2.0, 0.12, 0.10) is None  # rs <= g undefined
    assert approx(fm.preferred_value(5, 0.08), 62.5)


# ---- 4.10 Cost of Capital ----
def test_cost_of_capital():
    assert approx(fm.cost_of_debt_aftertax(0.08, 0.21), 0.0632)
    assert approx(fm.cost_of_preferred(5, 50), 0.10)
    assert approx(fm.cost_of_preferred(5, 50, flotation=0.05), 5 / 47.5, 1e-6)
    assert approx(fm.cost_of_retained_earnings(2, 40, 0.05), 0.10)
    assert approx(fm.wacc([0.4, 0.6], [0.05, 0.10]), 0.08)
    # unnormalized weights get normalized
    assert approx(fm.wacc([40, 60], [0.05, 0.10]), 0.08)


# ---- 4.11 Leverage & Break-even ----
def test_leverage_breakeven():
    assert approx(fm.breakeven_units(10000, 50, 30), 500.0)
    assert approx(fm.degree_operating_leverage(1000, 50, 30, 10000), 2.0)
    assert approx(fm.degree_financial_leverage(10000, 2000), 1.25)
    assert approx(fm.degree_combined_leverage(2.0, 1.25), 2.5)


# ---- 4.12 misc ----
def test_working_capital_dividends():
    assert approx(fm.cash_conversion_cycle(40, 30, 25), 45.0)
    assert approx(fm.dividend_payout(1.0, 4.0), 0.25)
    assert approx(fm.dividend_yield(2.0, 40.0), 0.05)
    assert approx(fm.real_rate(0.08, 0.03), 0.05)


# ---- divide-by-zero / missing inputs degrade to None, never raise ----
def test_safe_degradation():
    assert fm.pv_perpetuity(100, 0) is None
    assert fm.gordon_growth(2, 0.10, 0.10) is None
    assert fm.degree_financial_leverage(1000, 1000) is None
    assert fm.irr([1, 2, 3]) is None  # no sign change
