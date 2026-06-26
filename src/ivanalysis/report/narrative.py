"""Investment-viability narrative report (spec section 5).

Structured like a credit/equity analyst's note and ending in a clear
viable / conditional / not-viable call. Every claim is backed by a computed
number from the engine; nothing is asserted without a figure (spec section 8).
The verdict is rule-based and transparent -- the scoring is shown, not hidden.
"""

from __future__ import annotations

from typing import Optional

from ..metrics import run_ratios
from ..metrics.common import MetricResult
from ..model import Company

DISCLAIMER = (
    "> **Disclaimer.** This is educational analysis, **not investment, tax, or "
    "legal advice.** Figures derive from the inputs and cited sources shown; "
    "consult a licensed advisor before acting."
)


def _by_name(results: list[MetricResult]) -> dict[str, MetricResult]:
    return {r.name: r for r in results}


def _trend(company: Company, name: str) -> Optional[float]:
    """CAGR-ish first-to-last change for a named ratio, or None."""
    series = []
    for i in range(len(company.periods)):
        for r in run_ratios(company, i):
            if r.name == name and r.value is not None:
                series.append(r.value)
    if len(series) >= 2 and series[0] not in (0, None):
        return series[-1] - series[0]
    return None


def score_viability(company: Company) -> dict:
    """Transparent rubric across profitability, leverage, liquidity, growth.

    Returns dict with ``points``, ``max``, ``verdict`` and ``drivers``."""
    latest = run_ratios(company, len(company.periods) - 1)
    m = _by_name(latest)
    drivers: list[str] = []
    points = 0
    checks = 0

    def check(metric_name: str, ok: bool, msg_good: str, msg_bad: str):
        nonlocal points, checks
        r = m.get(metric_name)
        if r is None or r.value is None:
            return
        checks += 1
        if ok:
            points += 1
            drivers.append(f"[+] {msg_good} ({r.name} = {r.display()})")
        else:
            drivers.append(f"[-] {msg_bad} ({r.name} = {r.display()})")

    def v(name):
        r = m.get(name)
        return r.value if r and r.value is not None else None

    # Profitability
    check("Net Profit Margin", (v("Net Profit Margin") or -1) >= 0.05,
          "Profitable at the bottom line", "Thin or negative net margin")
    check("Return on Equity (ROE)", (v("Return on Equity (ROE)") or -1) >= 0.10,
          "Generates solid returns on equity", "Sub-par return on equity")
    # Liquidity
    check("Current Ratio", (v("Current Ratio") or 0) >= 1.0,
          "Covers near-term obligations", "Current liabilities exceed current assets")
    # Leverage
    check("Debt Ratio", (v("Debt Ratio") or 1) <= 0.7,
          "Moderate balance-sheet leverage", "Highly leveraged balance sheet")
    tie = v("Times Interest Earned")
    check("Times Interest Earned", tie is None or tie >= 3.0,
          "Comfortably services interest", "Interest coverage is tight")
    # Growth in profitability
    roe_trend = _trend(company, "Return on Equity (ROE)")
    if roe_trend is not None:
        checks += 1
        if roe_trend >= 0:
            points += 1
            drivers.append(f"[+] ROE trend improving ({roe_trend * 100:+.1f} pts over period)")
        else:
            drivers.append(f"[-] ROE trend deteriorating ({roe_trend * 100:+.1f} pts over period)")

    ratio = points / checks if checks else 0.0
    if ratio >= 0.7:
        verdict = "VIABLE"
    elif ratio >= 0.45:
        verdict = "CONDITIONAL"
    else:
        verdict = "NOT VIABLE"
    return {"points": points, "max": checks, "ratio": ratio,
            "verdict": verdict, "drivers": drivers}


def _ratio_table(company: Company, names: list[str]) -> str:
    periods = company.periods
    header = "| Metric | " + " | ".join(p.label for p in periods) + " | Read |"
    sep = "|" + "---|" * (len(periods) + 2)
    rows = [header, sep]
    per_period = [_by_name(run_ratios(company, i)) for i in range(len(periods))]
    for name in names:
        cells = []
        read = ""
        for i in range(len(periods)):
            r = per_period[i].get(name)
            cells.append(r.display() if r else "n/a")
            if i == len(periods) - 1 and r:
                read = r.interpretation
        rows.append(f"| {name} | " + " | ".join(cells) + f" | {read} |")
    return "\n".join(rows)


def generate_report(company: Company) -> str:
    company = company.normalize()
    if not company.periods:
        return "# Report\n\nNo periods available to analyze."

    s = score_viability(company)
    latest = company.periods[-1]
    m = _by_name(run_ratios(company, len(company.periods) - 1))
    out: list[str] = []

    # 1. Executive summary
    out.append(f"# Investment-Viability Report — {company.name}")
    if company.ticker:
        out.append(f"*Ticker {company.ticker} · CIK {company.cik or 'n/a'} · "
                   f"{company.mode}-company mode · periods "
                   f"{company.periods[0].label}–{latest.label}*")
    out.append("")
    out.append(DISCLAIMER)
    out.append("")
    out.append("## 1. Executive Summary")
    out.append(f"**Verdict: {s['verdict']}** "
               f"(passed {s['points']} of {s['max']} viability checks).")
    out.append("")
    out.append("Key drivers:")
    for d in s["drivers"][:6]:
        out.append(f"- {d}")
    out.append("")

    # 2. Company overview
    out.append("## 2. Company Overview")
    out.append(company.description or
               f"{company.name} is analyzed across {len(company.periods)} reporting "
               f"periods. Scale (latest): revenue {_disp(latest.revenue)}, "
               f"total assets {_disp(latest.total_assets)}, "
               f"equity {_disp(latest.total_equity)}.")
    out.append("")

    # 3. Accounting policy notes
    out.append("## 3. Accounting Policy Notes")
    basis = "US GAAP (SEC XBRL facts)" if company.mode == "public" else "user-supplied statements"
    out.append(f"- Basis of preparation: {basis}.")
    out.append("- Inventory method, consolidation and revenue-recognition policies "
               "affect comparability with peers; verify against filing footnotes "
               "before cross-company conclusions.")
    out.append(f"- Source provenance: {latest.source or 'n/a'}.")
    out.append("")

    # 4. Ratio analysis
    out.append("## 4. Ratio Analysis (3-year trend)")
    out.append("### Liquidity & Activity")
    out.append(_ratio_table(company, [
        "Current Ratio", "Quick (Acid-Test) Ratio", "Net Working Capital",
        "Inventory Turnover", "Collection Period (DSO)", "Total Asset Turnover"]))
    out.append("")
    out.append("### Leverage & Profitability")
    out.append(_ratio_table(company, [
        "Debt Ratio", "Times Interest Earned", "Equity Multiplier",
        "Gross Profit Margin", "Net Profit Margin", "Return on Assets (ROA)",
        "Return on Equity (ROE)"]))
    out.append("")

    # 5. DuPont
    out.append("## 5. DuPont Decomposition")
    dp = m.get("ROE (DuPont 3-step)")
    npm, tat, em = m.get("Net Profit Margin"), m.get("Total Asset Turnover"), m.get("Equity Multiplier")
    if dp and dp.value is not None:
        out.append(f"ROE of **{dp.display()}** decomposes into net margin "
                   f"{_md(npm)} × asset turnover {_md(tat)} × equity multiplier "
                   f"{_md(em)}. This isolates whether returns are driven by "
                   f"operating profitability, asset efficiency, or leverage.")
    else:
        out.append("DuPont decomposition unavailable (missing inputs).")
    out.append("")

    # 6. Valuation
    out.append("## 6. Valuation")
    out.append("DCF (WACC-discounted), Gordon-growth and a multiples cross-check "
               "are built live in the **Valuation** sheet of the workbook; the "
               "intrinsic-value vs. market-price gap and upside/(downside) update "
               "with any assumption change. Supply Rf, E(Rm), beta, price and "
               "dividend on the Assumptions sheet to activate them.")
    pe = m.get("Price/Earnings (P/E)")
    mb = m.get("Market-to-Book")
    if pe and pe.value is not None:
        out.append(f"- Market multiples: P/E {pe.display()}, "
                   f"Market-to-Book {_md(mb)}.")
    out.append("")

    # 7. Capital budgeting
    out.append("## 7. Capital-Budgeting View")
    out.append("For an expansion/acquisition scenario, the **CapBudget** sheet "
               "computes NPV, IRR, PI, payback and ARR from editable project cash "
               "flows, with accept/reject flags driven by the required return "
               "(NPV>0, IRR>k, PI>1). Replace the seeded cash flows with the "
               "project under review.")
    out.append("")

    # 8. Risk
    out.append("## 8. Risk Assessment")
    a = company.assumptions
    if a.beta is not None and a.risk_free_rate is not None and a.market_return is not None:
        req = a.risk_free_rate + a.beta * (a.market_return - a.risk_free_rate)
        roe_v = m.get("Return on Equity (ROE)")
        out.append(f"- CAPM required return = Rf + β(E(Rm)−Rf) = "
                   f"{a.risk_free_rate*100:.1f}% + {a.beta:.2f}×"
                   f"({a.market_return*100:.1f}%−{a.risk_free_rate*100:.1f}%) = "
                   f"**{req*100:.2f}%**.")
        if roe_v and roe_v.value is not None:
            gap = roe_v.value - req
            verdict_word = "exceeds" if gap >= 0 else "falls short of"
            out.append(f"- Delivered ROE ({roe_v.display()}) {verdict_word} the "
                       f"CAPM hurdle by {gap*100:+.1f} pts.")
    else:
        out.append("- Provide beta, Rf and E(Rm) on the Assumptions sheet to "
                   "compute the CAPM required return and compare it to delivered ROE.")
    out.append("")

    # 9. Conclusion
    out.append("## 9. Investment-Viability Conclusion")
    out.append(f"**{company.name} is assessed {s['verdict']}.** "
               f"The call synthesizes margin of safety, leverage risk, growth "
               f"quality and return generation:")
    for d in s["drivers"]:
        out.append(f"- {d}")
    out.append("")
    out.append(f"_Score: {s['points']}/{s['max']} checks passed "
               f"({s['ratio']*100:.0f}%). Thresholds: ≥70% viable, "
               f"45–69% conditional, <45% not viable._")
    out.append("")
    out.append(DISCLAIMER)
    return "\n".join(out)


def _disp(v: Optional[float]) -> str:
    return f"${v:,.0f}" if v is not None else "n/a"


def _md(r: Optional[MetricResult]) -> str:
    return r.display() if r and r.value is not None else "n/a"
