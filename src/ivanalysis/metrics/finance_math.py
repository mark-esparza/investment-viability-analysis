"""Pure financial mathematics (spec 4.6-4.11).

These are stateless textbook formulas operating on plain numbers, so they can be
unit-tested against known examples (acceptance criterion 3). The Excel writer
renders the same relationships with native ``=NPV/=IRR/=PV/=FV`` functions.

Conventions: rates are decimals (0.10 == 10%); ``n`` is periods; cash-flow lists
are ordered from t=0. Everything degrades to ``None`` on undefined input rather
than raising.
"""

from __future__ import annotations

import math
from typing import Optional, Sequence

Num = Optional[float]


# ===========================================================================
# 4.6 Time Value of Money
# ===========================================================================
def pv_single(fv: float, r: float, n: float, m: int = 1) -> float:
    """Present value of a single sum, compounded ``m`` times per period."""
    return fv / (1 + r / m) ** (m * n)


def pv_continuous(fv: float, r: float, n: float) -> float:
    return fv * math.exp(-r * n)


def fv_single(pv: float, r: float, n: float, m: int = 1) -> float:
    return pv * (1 + r / m) ** (m * n)


def fv_continuous(pv: float, r: float, n: float) -> float:
    return pv * math.exp(r * n)


def pv_annuity(pmt: float, r: float, n: float, due: bool = False) -> float:
    if r == 0:
        base = pmt * n
    else:
        base = pmt * (1 - (1 + r) ** -n) / r
    return base * (1 + r) if due else base


def fv_annuity(pmt: float, r: float, n: float, due: bool = False) -> float:
    if r == 0:
        base = pmt * n
    else:
        base = pmt * ((1 + r) ** n - 1) / r
    return base * (1 + r) if due else base


def pv_perpetuity(pmt: float, r: float) -> Num:
    if r == 0:
        return None
    return pmt / r


def ear(nominal: float, m: int) -> float:
    """Effective annual rate from a nominal rate compounded m times (=EFFECT)."""
    return (1 + nominal / m) ** m - 1


def apr(rate_per_period: float, periods_per_year: int) -> float:
    return rate_per_period * periods_per_year


# ===========================================================================
# 4.7 Capital Budgeting
# ===========================================================================
def operating_cash_flow(revenues: float, costs: float, dep: float, tax: float) -> float:
    """OCF = (Revenues - Costs)(1 - T) + T * Depreciation."""
    return (revenues - costs) * (1 - tax) + tax * dep


def net_cash_flow(ocf: float, delta_nwc: float, delta_capex: float) -> float:
    return ocf - delta_nwc - delta_capex


def npv(rate: float, cashflows: Sequence[float]) -> float:
    """NPV with cashflows[0] at t=0 (typically the negative outlay)."""
    return sum(cf / (1 + rate) ** t for t, cf in enumerate(cashflows))


def irr(cashflows: Sequence[float], guess: float = 0.1) -> Num:
    """Internal rate of return via bisection on a sign change, then refine.
    Returns None when no rate in (-0.999, 10) zeroes the NPV."""
    lo, hi = -0.999, 10.0
    f_lo = npv(lo, cashflows)
    f_hi = npv(hi, cashflows)
    if f_lo == 0:
        return lo
    if f_hi == 0:
        return hi
    if (f_lo > 0) == (f_hi > 0):
        return None  # no sign change -> no real IRR in range
    for _ in range(200):
        mid = (lo + hi) / 2
        f_mid = npv(mid, cashflows)
        if abs(f_mid) < 1e-9:
            return mid
        if (f_mid > 0) == (f_lo > 0):
            lo, f_lo = mid, f_mid
        else:
            hi = mid
    return (lo + hi) / 2


def profitability_index(rate: float, cashflows: Sequence[float]) -> Num:
    """PI = PV of future inflows / initial outlay. cashflows[0] is the outlay
    (negative)."""
    outlay = -cashflows[0]
    if outlay == 0:
        return None
    pv_future = sum(cf / (1 + rate) ** t for t, cf in enumerate(cashflows) if t > 0)
    return pv_future / outlay


def payback_period(cashflows: Sequence[float]) -> Num:
    """Years to recover the initial outlay, with fractional interpolation."""
    outlay = -cashflows[0]
    if outlay <= 0:
        return None
    cumulative = 0.0
    for t in range(1, len(cashflows)):
        prev = cumulative
        cumulative += cashflows[t]
        if cumulative >= outlay:
            shortfall = outlay - prev
            return (t - 1) + shortfall / cashflows[t] if cashflows[t] else float(t)
    return None  # never recovered


def accounting_rate_of_return(avg_income: float, avg_book_value: float) -> Num:
    if avg_book_value == 0:
        return None
    return avg_income / avg_book_value


def capital_budget_decision(npv_v: Num, irr_v: Num, pi_v: Num, k: float) -> dict:
    """Accept/reject per spec 4.7 rules."""
    return {
        "npv": "ACCEPT" if (npv_v is not None and npv_v > 0)
        else "REJECT" if npv_v is not None else "n/a",
        "irr": "ACCEPT" if (irr_v is not None and irr_v > k)
        else "REJECT" if irr_v is not None else "n/a",
        "pi": "ACCEPT" if (pi_v is not None and pi_v > 1)
        else "REJECT" if pi_v is not None else "n/a",
    }


# ===========================================================================
# 4.8 Risk & Return / CAPM
# ===========================================================================
def expected_return(probs: Sequence[float], returns: Sequence[float]) -> float:
    return sum(p * r for p, r in zip(probs, returns))


def variance(probs: Sequence[float], returns: Sequence[float]) -> float:
    er = expected_return(probs, returns)
    return sum(p * (r - er) ** 2 for p, r in zip(probs, returns))


def std_dev(probs: Sequence[float], returns: Sequence[float]) -> float:
    return math.sqrt(variance(probs, returns))


def coefficient_of_variation(probs: Sequence[float], returns: Sequence[float]) -> Num:
    er = expected_return(probs, returns)
    if er == 0:
        return None
    return std_dev(probs, returns) / er


def covariance(probs: Sequence[float], ri: Sequence[float], rj: Sequence[float]) -> float:
    eri = expected_return(probs, ri)
    erj = expected_return(probs, rj)
    return sum(p * (a - eri) * (b - erj) for p, a, b in zip(probs, ri, rj))


def correlation(probs: Sequence[float], ri: Sequence[float], rj: Sequence[float]) -> Num:
    si = std_dev(probs, ri)
    sj = std_dev(probs, rj)
    if si == 0 or sj == 0:
        return None
    return covariance(probs, ri, rj) / (si * sj)


def beta_from_cov(cov_asset_market: float, var_market: float) -> Num:
    if var_market == 0:
        return None
    return cov_asset_market / var_market


def capm(rf: float, beta: float, rm: float) -> float:
    """Required/expected return: E(Ri) = Rf + beta*(E(Rm) - Rf)."""
    return rf + beta * (rm - rf)


def portfolio_return(wi: float, eri: float, wj: float, erj: float) -> float:
    return wi * eri + wj * erj


def portfolio_variance(wi: float, si: float, wj: float, sj: float, cov_ij: float) -> float:
    return wi ** 2 * si ** 2 + wj ** 2 * sj ** 2 + 2 * wi * wj * cov_ij


def sml_slope(rf: float, rm: float) -> float:
    return rm - rf


# ===========================================================================
# 4.9 Valuation
# ===========================================================================
def asset_value(cashflows: Sequence[float], r: float) -> float:
    """Value = sum CFt / (1+r)^t, t starting at 1."""
    return sum(cf / (1 + r) ** (t + 1) for t, cf in enumerate(cashflows))


def bond_value(coupon: float, face: float, r: float, n: int, freq: int = 1) -> float:
    """Annual (freq=1) or semiannual (freq=2) coupon bond."""
    periods = n * freq
    rate = r / freq
    pmt = coupon / freq
    pv_coupons = sum(pmt / (1 + rate) ** t for t in range(1, periods + 1))
    pv_face = face / (1 + rate) ** periods
    return pv_coupons + pv_face


def gordon_growth(d0: float, g: float, rs: float) -> Num:
    """Constant-growth stock value = D0(1+g)/(rs-g). Requires rs > g."""
    if rs <= g:
        return None
    return d0 * (1 + g) / (rs - g)


def preferred_value(d_ps: float, r_ps: float) -> Num:
    if r_ps == 0:
        return None
    return d_ps / r_ps


# ===========================================================================
# 4.10 Cost of Capital
# ===========================================================================
def cost_of_debt_aftertax(pretax: float, tax: float) -> float:
    return (1 - tax) * pretax


def cost_of_preferred(dividend: float, price: float, flotation: float = 0.0) -> Num:
    denom = price * (1 - flotation)
    if denom == 0:
        return None
    return dividend / denom


def cost_of_retained_earnings(d1: float, p0: float, g: float) -> Num:
    if p0 == 0:
        return None
    return d1 / p0 + g


def cost_of_equity_capm(rf: float, beta: float, rm: float) -> float:
    return capm(rf, beta, rm)


def cost_of_new_equity(d1: float, p0: float, g: float, flotation: float) -> Num:
    denom = p0 * (1 - flotation)
    if denom == 0:
        return None
    return d1 / denom + g


def wacc(weights: Sequence[float], costs: Sequence[float]) -> Num:
    """WACC = sum(w_i * k_i). Weights need not be pre-normalized; if they sum to
    a positive number other than 1 they are normalized first."""
    pairs = [(w, k) for w, k in zip(weights, costs) if w is not None and k is not None]
    if not pairs:
        return None
    total_w = sum(w for w, _ in pairs)
    if total_w == 0:
        return None
    return sum(w * k for w, k in pairs) / total_w


# ===========================================================================
# 4.11 Operating / Financial Leverage & Break-even
# ===========================================================================
def breakeven_units(fixed_costs: float, price: float, var_cost: float) -> Num:
    if price - var_cost == 0:
        return None
    return fixed_costs / (price - var_cost)


def degree_operating_leverage(q: float, price: float, var_cost: float, fixed_costs: float) -> Num:
    contribution = q * (price - var_cost)
    denom = contribution - fixed_costs
    if denom == 0:
        return None
    return contribution / denom


def degree_financial_leverage(ebit: float, interest: float) -> Num:
    denom = ebit - interest
    if denom == 0:
        return None
    return ebit / denom


def degree_combined_leverage(dol: Num, dfl: Num) -> Num:
    if dol is None or dfl is None:
        return None
    return dol * dfl


# ===========================================================================
# 4.12 Working capital, dividends, real rate
# ===========================================================================
def cash_conversion_cycle(days_inventory: float, days_receivable: float, days_payable: float) -> float:
    return days_inventory + days_receivable - days_payable


def dividend_payout(dps: float, eps_v: float) -> Num:
    if eps_v == 0:
        return None
    return dps / eps_v


def dividend_yield(annual_dps: float, price: float) -> Num:
    if price == 0:
        return None
    return annual_dps / price


def real_rate(nominal: float, expected_inflation: float) -> float:
    return nominal - expected_inflation
