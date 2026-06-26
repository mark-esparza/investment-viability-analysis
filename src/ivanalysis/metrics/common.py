"""Shared primitives for the equation engine (spec section 4).

Design contract (spec section 7): every metric takes the section-3 data model
and returns BOTH the numeric result and the Excel formula string that should be
written into the workbook. The formula references named ranges so the workbook
recalculates when inputs change -- it is a working model, not a static dump.

``Ctx`` binds a company + a period index and exposes two parallel accessors:
  - ``val(attr, offset)``  -> the Python number (for computation & tests)
  - ``ref(attr, offset)``  -> the Excel named range (for the formula string)
Keeping them parallel guarantees the number and the formula describe the same
cells, so the workbook is auditable against the report.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from ..model import Company, FinancialPeriod, _assumption_name, excel_name

NA = "n/a"


@dataclass
class MetricResult:
    name: str
    category: str
    value: Optional[float]
    formula: str  # Excel formula text, e.g. "=CurrentAssets_FY24/CurrentLiab_FY24"
    interpretation: str = ""
    unit: str = ""  # "", "x", "%", "$", "days", "ratio"
    # Optional health rule for conditional formatting: a callable(value)->bool,
    # True == healthy. None means "no opinion".
    healthy: Optional[Callable[[float], bool]] = None

    @property
    def available(self) -> bool:
        return self.value is not None

    def display(self) -> str:
        if self.value is None:
            return NA
        if self.unit == "%":
            return f"{self.value * 100:.2f}%"
        if self.unit == "x":
            return f"{self.value:.2f}x"
        if self.unit == "days":
            return f"{self.value:.1f} days"
        if self.unit == "$":
            return f"{self.value:,.0f}"
        return f"{self.value:,.4f}"


class Ctx:
    """A company bound to one period index ``i`` (0 == oldest)."""

    def __init__(self, company: Company, i: int):
        self.company = company
        self.i = i
        self.periods = company.periods
        self.p: FinancialPeriod = company.periods[i]
        self.a = company.assumptions

    # -- value accessors (numbers) ------------------------------------------
    def val(self, attr: str, offset: int = 0) -> Optional[float]:
        idx = self.i + offset
        if idx < 0 or idx >= len(self.periods):
            return None
        return getattr(self.periods[idx], attr)

    def aval(self, attr: str) -> Optional[float]:
        return getattr(self.a, attr)

    # -- reference accessors (Excel named ranges) ---------------------------
    def ref(self, attr: str, offset: int = 0) -> Optional[str]:
        idx = self.i + offset
        if idx < 0 or idx >= len(self.periods):
            return None
        return excel_name(attr, self.periods[idx].label)

    def aref(self, attr: str) -> str:
        return _assumption_name(attr)

    @property
    def has_prior(self) -> bool:
        return self.i > 0


# ---------------------------------------------------------------------------
# Safe arithmetic -- divide-by-zero and missing inputs return None, never raise
# (spec section 8: "no interest -> TIE = n/a, not error").
# ---------------------------------------------------------------------------
def sdiv(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None or b == 0:
        return None
    return a / b


def ssub(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None:
        return None
    return a - b


def sadd(*vals) -> Optional[float]:
    if any(v is None for v in vals):
        return None
    return sum(vals)


def smul(*vals) -> Optional[float]:
    if any(v is None for v in vals):
        return None
    out = 1.0
    for v in vals:
        out *= v
    return out


def avg(a: Optional[float], b: Optional[float]) -> Optional[float]:
    """Average of two periods; if only one is present, fall back to it so a
    company with a single year still produces a turnover ratio."""
    if a is not None and b is not None:
        return (a + b) / 2.0
    return a if a is not None else b
