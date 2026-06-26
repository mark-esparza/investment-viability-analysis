"""Finance equation library (spec section 4).

- ``ratios``        : period-bound ratios returning value + live Excel formula
- ``finance_math``  : stateless textbook math (TVM, capital budgeting, CAPM,
                      valuation, cost of capital, leverage)
- ``common``        : the Ctx / MetricResult contract and safe arithmetic
"""

from . import finance_math, ratios  # noqa: F401
from .common import Ctx, MetricResult
from .ratios import RATIO_METRICS

__all__ = ["Ctx", "MetricResult", "RATIO_METRICS", "ratios", "finance_math", "run_ratios"]


def run_ratios(company, period_index):
    """Compute every section 4.1-4.5 ratio for one period.

    Returns ``list[MetricResult]`` in registry order.
    """
    ctx = Ctx(company, period_index)
    return [metric(ctx) for metric in RATIO_METRICS]
