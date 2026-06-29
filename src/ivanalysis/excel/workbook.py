"""Live-formula Excel workbook builder (spec section 6).

Hard requirement: computed metrics are written as *cell formulas referencing
named input cells*, never pasted static values. Change any Inputs/Assumptions
cell and the whole report recalculates -- it is a working model.

Sheets: Inputs, Assumptions, Ratios, Valuation, CapBudget, Charts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import absolute_coordinate, get_column_letter, quote_sheetname
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.page import PageMargins

from ..metrics import run_ratios
from ..model import BALANCE_FIELDS, CASHFLOW_FIELDS, INCOME_FIELDS, Company, excel_name

# -- styles -----------------------------------------------------------------
TITLE = Font(bold=True, size=14, color="1F4E78")
H2 = Font(bold=True, size=11, color="FFFFFF")
HDR_FILL = PatternFill("solid", fgColor="1F4E78")
SECTION_FILL = PatternFill("solid", fgColor="D9E1F2")
GOOD_FILL = PatternFill("solid", fgColor="C6EFCE")
BAD_FILL = PatternFill("solid", fgColor="FFC7CE")
MUTED = Font(italic=True, size=9, color="808080")
BOLD = Font(bold=True)
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
DISCLAIMER = (
    "Educational analysis only -- NOT investment, tax, or legal advice. "
    "Consult a licensed advisor before acting. Every figure ties to an input "
    "cell or cited SEC filing; missing inputs are excluded, never invented."
)


class WorkbookBuilder:
    def __init__(self, company: Company):
        self.company = company.normalize()
        self.wb = Workbook()
        self.cell_map: dict[tuple[str, str], str] = {}  # (attr, period) -> abs ref
        self.assumption_refs: dict[str, str] = {}

    # -- helpers ------------------------------------------------------------
    def _define(self, name: str, sheet: str, coord: str) -> str:
        ref = f"{quote_sheetname(sheet)}!{absolute_coordinate(coord)}"
        # Replace any pre-existing name (idempotent rebuilds).
        if name in self.wb.defined_names:
            del self.wb.defined_names[name]
        self.wb.defined_names.add(DefinedName(name, attr_text=ref))
        return ref

    @staticmethod
    def _disclaimer_row(ws, row: int, span: int = 6) -> None:
        ws.cell(row=row, column=1, value=DISCLAIMER).font = MUTED
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=span)

    @staticmethod
    def _setup_print(ws, title_row: int = 3) -> None:
        """Print-friendly page setup: landscape, fit-to-width, repeating header row."""
        ws.page_setup.orientation = "landscape"
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.page_margins = PageMargins(left=0.4, right=0.4, top=0.5, bottom=0.5,
                                       header=0.3, footer=0.3)
        ws.print_area = f"A1:{get_column_letter(ws.max_column)}{ws.max_row}"
        ws.print_title_rows = f"{title_row}:{title_row}"
        ws.oddFooter.center.text = "&P of &N"

    # ======================================================================
    def build(self) -> Workbook:
        self._sheet_inputs()
        self._sheet_assumptions()
        self._sheet_ratios()
        self._sheet_valuation()
        self._sheet_capbudget()
        self._sheet_charts()
        return self.wb

    def save(self, path: str | Path) -> Path:
        self.build()
        path = Path(path)
        self.wb.save(path)
        return path

    # ----------------------------------------------------------------- Inputs
    def _sheet_inputs(self) -> None:
        ws = self.wb.active
        ws.title = "Inputs"
        periods = self.company.periods
        ws.cell(row=1, column=1, value=f"{self.company.name} -- Raw Inputs").font = TITLE
        ws.column_dimensions["A"].width = 34
        for j in range(len(periods)):
            ws.column_dimensions[get_column_letter(2 + j)].width = 16

        # header
        hr = 3
        ws.cell(row=hr, column=1, value="Line item ($, except per-share)")
        for j, p in enumerate(periods):
            c = ws.cell(row=hr, column=2 + j, value=p.label)
            c.font = H2
            c.fill = HDR_FILL
            c.alignment = Alignment(horizontal="center")
        ws.cell(row=hr, column=1).font = H2
        ws.cell(row=hr, column=1).fill = HDR_FILL

        self._inputs_rowmap: dict[str, int] = {}
        row = hr + 1
        for section, group in (
            ("Income Statement", INCOME_FIELDS),
            ("Balance Sheet", BALANCE_FIELDS),
            ("Cash Flow", CASHFLOW_FIELDS),
        ):
            sc = ws.cell(row=row, column=1, value=section)
            sc.font = BOLD
            sc.fill = SECTION_FILL
            ws.merge_cells(start_row=row, start_column=1, end_row=row,
                           end_column=1 + len(periods))
            row += 1
            for attr, _label, _stmt, name in group:
                ws.cell(row=row, column=1, value=name)
                self._inputs_rowmap[attr] = row
                for j, p in enumerate(periods):
                    coord = f"{get_column_letter(2 + j)}{row}"
                    val = getattr(p, attr)
                    cell = ws.cell(row=row, column=2 + j)
                    if val is not None:
                        cell.value = val
                        cell.number_format = "#,##0"
                        cell.border = BORDER
                        ref = self._define(excel_name(attr, p.label), "Inputs", coord)
                        self.cell_map[(attr, p.label)] = ref
                row += 1
            row += 1

        row += 1
        ws.cell(row=row, column=1, value="Sources:").font = BOLD
        for j, p in enumerate(periods):
            ws.cell(row=row, column=2 + j, value=p.source).font = MUTED
        self._disclaimer_row(ws, row + 2, span=1 + len(periods))
        self._setup_print(ws, title_row=hr)

    # ------------------------------------------------------------ Assumptions
    def _sheet_assumptions(self) -> None:
        ws = self.wb.create_sheet("Assumptions")
        ws.column_dimensions["A"].width = 34
        ws.column_dimensions["B"].width = 16
        ws.column_dimensions["C"].width = 50
        ws.cell(row=1, column=1, value="Market & Policy Assumptions (editable)").font = TITLE
        for col, head in ((1, "Assumption"), (2, "Value"), (3, "Notes")):
            c = ws.cell(row=3, column=col, value=head)
            c.font = H2
            c.fill = HDR_FILL

        notes = {
            "risk_free_rate": "Rf -- 10Y Treasury or user input (decimal)",
            "market_return": "E(Rm) -- expected market return (decimal)",
            "beta": "Equity beta",
            "tax_rate": "T -- marginal tax rate (decimal)",
            "dividend_growth_g": "g -- dividend growth (decimal, < required return)",
            "required_return_k": "k -- required return / WACC override (decimal)",
            "flotation_cost": "f -- flotation cost (decimal)",
            "cost_of_debt_pretax": "Pre-tax cost of debt / YTM (decimal)",
            "price_per_share": "Current market price per share",
            "book_value_per_share": "Book value per share",
            "dividend_per_share": "Annual dividend per share (D0)",
            "shares_outstanding": "Shares outstanding",
            "weight_debt": "Capital-structure weight of debt (optional)",
            "weight_preferred": "Weight of preferred (optional)",
            "weight_equity": "Weight of equity (optional)",
        }
        row = 4
        for attr, (named, value) in self.company.assumptions.as_named_cells().items():
            ws.cell(row=row, column=1, value=attr.replace("_", " ").title())
            cell = ws.cell(row=row, column=2)
            if value is not None:
                cell.value = value
            cell.border = BORDER
            cell.fill = PatternFill("solid", fgColor="FFF2CC")  # editable=yellow
            self.assumption_refs[attr] = self._define(
                named, "Assumptions", f"B{row}")
            ws.cell(row=row, column=3, value=notes.get(attr, "")).font = MUTED
            row += 1
        self._disclaimer_row(ws, row + 1, span=3)
        self._setup_print(ws, title_row=3)

    # ---------------------------------------------------------------- Ratios
    def _sheet_ratios(self) -> None:
        ws = self.wb.create_sheet("Ratios")
        periods = self.company.periods
        ws.column_dimensions["A"].width = 30
        ws.column_dimensions["B"].width = 14
        for j in range(len(periods)):
            ws.column_dimensions[get_column_letter(3 + j)].width = 13
        fcol = 3 + len(periods)
        icol = fcol + 1
        ws.column_dimensions[get_column_letter(fcol)].width = 46
        ws.column_dimensions[get_column_letter(icol)].width = 60

        ws.cell(row=1, column=1, value="Ratio Analysis -- live formulas (sec 4.1-4.5)").font = TITLE

        hr = 3
        ws.cell(row=hr, column=1, value="Metric").font = H2
        ws.cell(row=hr, column=1).fill = HDR_FILL
        ws.cell(row=hr, column=2, value="Category").font = H2
        ws.cell(row=hr, column=2).fill = HDR_FILL
        for j, p in enumerate(periods):
            c = ws.cell(row=hr, column=3 + j, value=p.label)
            c.font = H2
            c.fill = HDR_FILL
            c.alignment = Alignment(horizontal="center")
        ws.cell(row=hr, column=fcol, value="Excel formula (latest period)").font = H2
        ws.cell(row=hr, column=fcol).fill = HDR_FILL
        ws.cell(row=hr, column=icol, value="Interpretation").font = H2
        ws.cell(row=hr, column=icol).fill = HDR_FILL

        # Pre-compute each period's metric list.
        per_period = [run_ratios(self.company, i) for i in range(len(periods))]
        n_metrics = len(per_period[0]) if per_period else 0

        row = hr + 1
        for m in range(n_metrics):
            latest = per_period[-1][m]
            ws.cell(row=row, column=1, value=latest.name)
            ws.cell(row=row, column=2, value=latest.category).font = MUTED
            for j in range(len(periods)):
                res = per_period[j][m]
                cell = ws.cell(row=row, column=3 + j)
                if res.value is not None:
                    cell.value = res.formula  # LIVE formula
                    cell.number_format = _fmt(res.unit)
                    if res.healthy is not None:
                        cell.fill = GOOD_FILL if res.healthy(res.value) else BAD_FILL
                else:
                    cell.value = "n/a"
                    cell.font = MUTED
                cell.alignment = Alignment(horizontal="center")
            ws.cell(row=row, column=fcol, value=latest.formula[1:]).font = MUTED  # text, drop '='
            ws.cell(row=row, column=icol, value=latest.interpretation).font = MUTED
            row += 1

        ws.cell(row=row + 1, column=1,
                value="Green = healthy, red = weak (vs. generic thresholds; "
                      "fills reflect loaded data).").font = MUTED
        self._disclaimer_row(ws, row + 3, span=icol)
        self._ratios_rowmap = {per_period[-1][m].name: hr + 1 + m for m in range(n_metrics)}
        self._setup_print(ws, title_row=hr)

    # ------------------------------------------------------------- Valuation
    def _sheet_valuation(self) -> None:
        ws = self.wb.create_sheet("Valuation")
        ws.column_dimensions["A"].width = 38
        for col in "BCDEFGH":
            ws.column_dimensions[col].width = 14
        a = self.assumption_refs
        latest = self.company.periods[-1]
        ws.cell(row=1, column=1, value="Valuation -- WACC / DCF / Gordon / Multiples").font = TITLE

        # --- Cost of capital block ---
        r = 3
        ws.cell(row=r, column=1, value="Cost of Capital").font = H2
        ws.cell(row=r, column=1).fill = HDR_FILL
        r += 1

        def kv(label, formula, fmt="0.00%", note=""):
            nonlocal r
            ws.cell(row=r, column=1, value=label)
            c = ws.cell(row=r, column=2)
            c.value = formula
            c.number_format = fmt
            c.border = BORDER
            if note:
                ws.cell(row=r, column=3, value=note).font = MUTED
            here = f"B{r}"
            r += 1
            return here

        kd_cell = kv("After-tax cost of debt k_d",
                     f"=(1-{a['tax_rate']})*{a['cost_of_debt_pretax']}",
                     note="(1 - T) x pre-tax YTM")
        ke_cell = kv("Cost of equity k_e (CAPM)",
                     f"={a['risk_free_rate']}+{a['beta']}*({a['market_return']}-{a['risk_free_rate']})",
                     note="Rf + beta x (E(Rm) - Rf)")
        kp_cell = kv("Cost of preferred k_p",
                     f"=IF({a['price_per_share']}=0,0,"
                     f"{a['dividend_per_share']}/({a['price_per_share']}*(1-{a['flotation_cost']})))",
                     note="D_p / (P_p (1 - f))  [proxy]")

        # Weights: use overrides if present else derive from latest balance sheet.
        ltd = self.cell_map.get(("long_term_debt", latest.label))
        teq = self.cell_map.get(("total_equity", latest.label))
        if ltd and teq:
            wd = f"=IF(({ltd}+{teq})=0,0,{ltd}/({ltd}+{teq}))"
            we = f"=IF(({ltd}+{teq})=0,0,{teq}/({ltd}+{teq}))"
        else:
            wd = f"={a['weight_debt']}"
            we = f"={a['weight_equity']}"
        wd_cell = kv("Weight of debt W_d", wd, note="Market/structure weight")
        we_cell = kv("Weight of equity W_e", we)
        wacc_cell = kv(
            "WACC", f"={wd_cell}*{kd_cell}+{we_cell}*{ke_cell}",
            note="W_d k_d + W_e k_e")
        self._wacc_cell = f"Valuation!{wacc_cell}"

        # --- DCF (illustrative FCF projection) ---
        r += 1
        ws.cell(row=r, column=1, value="Discounted Cash Flow (illustrative)").font = H2
        ws.cell(row=r, column=1).fill = HDR_FILL
        r += 1
        cfo = self.cell_map.get(("cfo", latest.label))
        capex = self.cell_map.get(("capex", latest.label))
        base_row = r
        ws.cell(row=r, column=1, value="Base free cash flow (CFO - CapEx)")
        if cfo and capex:
            ws.cell(row=r, column=2, value=f"={cfo}-{capex}").number_format = "#,##0"
        else:
            ws.cell(row=r, column=2, value=0).number_format = "#,##0"
        ws.cell(row=r, column=3, value="From latest cash-flow statement").font = MUTED
        r += 1
        ws.cell(row=r, column=1, value="Projection growth g (Assumptions)")
        ws.cell(row=r, column=2, value=f"={a['dividend_growth_g']}").number_format = "0.00%"
        g_cell = f"B{r}"
        r += 1

        proj_header = r
        ws.cell(row=r, column=1, value="Year")
        for yr in range(1, 6):
            ws.cell(row=r, column=1 + yr, value=yr).font = BOLD
        ws.cell(row=r, column=7, value="Terminal").font = BOLD
        r += 1
        ws.cell(row=r, column=1, value="Projected FCF")
        prev = f"B{base_row}"
        fcf_row = r
        for yr in range(1, 6):
            col = get_column_letter(1 + yr)
            ws.cell(row=r, column=1 + yr,
                    value=f"={prev}*(1+{g_cell})").number_format = "#,##0"
            prev = f"{col}{r}"
        # Terminal value via Gordon at WACC on year-5 FCF.
        tv_col = get_column_letter(7)
        last_fcf = f"{get_column_letter(6)}{fcf_row}"
        ws.cell(row=r, column=7,
                value=f"=IF(({wacc_cell}-{g_cell})<=0,0,{last_fcf}*(1+{g_cell})/({wacc_cell}-{g_cell}))"
                ).number_format = "#,##0"
        r += 1
        # PV of explicit FCF + PV of terminal.
        npv_range = f"C{fcf_row}:G{fcf_row}"  # years 1-5 in C..G
        ws.cell(row=r, column=1, value="PV of explicit FCF (yrs 1-5)")
        ws.cell(row=r, column=2,
                value=f"=NPV({wacc_cell},C{fcf_row}:{get_column_letter(6)}{fcf_row})"
                ).number_format = "#,##0"
        pv_explicit = f"B{r}"
        r += 1
        ws.cell(row=r, column=1, value="PV of terminal value")
        ws.cell(row=r, column=2,
                value=f"={tv_col}{fcf_row}/((1+{wacc_cell})^5)").number_format = "#,##0"
        pv_tv = f"B{r}"
        r += 1
        ws.cell(row=r, column=1, value="Enterprise value (DCF)").font = BOLD
        ws.cell(row=r, column=2, value=f"={pv_explicit}+{pv_tv}").number_format = "#,##0"
        ev_cell = f"B{r}"
        r += 1
        # Intrinsic value per share & gap vs market.
        shares = self.cell_map.get(("diluted_shares", latest.label)) or a["shares_outstanding"]
        ws.cell(row=r, column=1, value="Intrinsic value per share (EV/shares)")
        ws.cell(row=r, column=2,
                value=f"=IF({shares}=0,0,{ev_cell}/{shares})").number_format = "#,##0.00"
        iv_cell = f"B{r}"
        r += 1
        ws.cell(row=r, column=1, value="Market price per share")
        ws.cell(row=r, column=2, value=f"={a['price_per_share']}").number_format = "#,##0.00"
        r += 1
        ws.cell(row=r, column=1, value="Upside / (downside) vs market").font = BOLD
        ws.cell(row=r, column=2,
                value=f"=IF({a['price_per_share']}=0,0,{iv_cell}/{a['price_per_share']}-1)"
                ).number_format = "0.0%"
        self._intrinsic_cell = f"Valuation!{iv_cell}"

        # --- Gordon growth & multiples cross-checks ---
        r += 2
        ws.cell(row=r, column=1, value="Cross-checks").font = H2
        ws.cell(row=r, column=1).fill = HDR_FILL
        r += 1
        ws.cell(row=r, column=1, value="Gordon-growth value = D0(1+g)/(k_e - g)")
        ws.cell(row=r, column=2,
                value=f"=IF(({ke_cell}-{g_cell})<=0,0,"
                      f"{a['dividend_per_share']}*(1+{g_cell})/({ke_cell}-{g_cell}))"
                ).number_format = "#,##0.00"
        r += 1
        eps_ref = self.cell_map.get(("eps", latest.label))
        if eps_ref:
            ws.cell(row=r, column=1, value="Multiples value = EPS x assumed P/E (15x)")
            ws.cell(row=r, column=2, value=f"={eps_ref}*15").number_format = "#,##0.00"
            r += 1
        self._disclaimer_row(ws, r + 1, span=7)
        self._setup_print(ws, title_row=1)

    # -------------------------------------------------------------- CapBudget
    def _sheet_capbudget(self) -> None:
        ws = self.wb.create_sheet("CapBudget")
        ws.column_dimensions["A"].width = 34
        for col in "BCDEFGH":
            ws.column_dimensions[col].width = 13
        ws.cell(row=1, column=1,
                value="Capital Budgeting -- editable project (sec 4.7)").font = TITLE
        ws.cell(row=2, column=1,
                value="Edit the cash flows; NPV / IRR / PI / payback recalc live.").font = MUTED

        # required return k pulled from WACC if available else assumption k.
        k_cell = "Assumptions!" + self.assumption_refs["required_return_k"].split("!")[-1]
        ws.cell(row=4, column=1, value="Required return k (uses WACC if set)")
        ws.cell(row=4, column=2,
                value=f"=IF({self._wacc_cell}>0,{self._wacc_cell},{k_cell})"
                ).number_format = "0.00%"
        kref = "B4"

        hr = 6
        ws.cell(row=hr, column=1, value="Year")
        years = list(range(0, 6))
        for j, y in enumerate(years):
            c = ws.cell(row=hr, column=2 + j, value=y)
            c.font = H2
            c.fill = HDR_FILL
            c.alignment = Alignment(horizontal="center")
        # Net cash flow row -- seeded with an illustrative project the user edits.
        ncf_row = hr + 1
        ws.cell(row=ncf_row, column=1, value="Net cash flow (NCF)").font = BOLD
        seed = [-100000, 30000, 35000, 40000, 30000, 25000]
        for j, v in enumerate(seed):
            cell = ws.cell(row=ncf_row, column=2 + j, value=v)
            cell.number_format = "#,##0"
            cell.border = BORDER
            cell.fill = PatternFill("solid", fgColor="FFF2CC")
        cf0 = f"B{ncf_row}"
        cf1_5 = f"C{ncf_row}:G{ncf_row}"

        # cumulative row for payback visual
        cum_row = ncf_row + 1
        ws.cell(row=cum_row, column=1, value="Cumulative cash flow")
        ws.cell(row=cum_row, column=2, value=f"={cf0}").number_format = "#,##0"
        for j in range(1, 6):
            prev = get_column_letter(1 + j)
            cur = get_column_letter(2 + j)
            ws.cell(row=cum_row, column=2 + j,
                    value=f"={prev}{cum_row}+{cur}{ncf_row}").number_format = "#,##0"

        r = cum_row + 2
        def metric(label, formula, fmt="#,##0.00", note=""):
            nonlocal r
            ws.cell(row=r, column=1, value=label)
            c = ws.cell(row=r, column=2, value=formula)
            c.number_format = fmt
            c.font = BOLD
            c.border = BORDER
            if note:
                ws.cell(row=r, column=4, value=note).font = MUTED
            cellref = f"B{r}"
            r += 1
            return cellref

        npv_cell = metric("NPV", f"={cf0}+NPV({kref},{cf1_5})", "#,##0",
                          "= -outlay + PV(future NCF)")
        irr_cell = metric("IRR", f"=IRR(B{ncf_row}:G{ncf_row})", "0.00%")
        pi_cell = metric("Profitability Index (PI)",
                         f"=IF({cf0}=0,0,NPV({kref},{cf1_5})/-{cf0})", "0.000",
                         "PV future / initial outlay")
        # Payback via cumulative crossing
        metric("Payback (yrs, approx)",
               f"=MATCH(TRUE,INDEX(C{cum_row}:G{cum_row}>=0,0),0)", "0.0",
               "First year cumulative >= 0")
        # ARR = avg annual NCF (yrs1-5) / avg book value (0.5 x outlay)
        metric("Accounting Rate of Return (ARR)",
               f"=AVERAGE({cf1_5})/(-{cf0}/2)", "0.00%",
               "avg income / avg book value")

        r += 1
        ws.cell(row=r, column=1, value="Decision rules").font = H2
        ws.cell(row=r, column=1).fill = HDR_FILL
        r += 1
        ws.cell(row=r, column=1, value="NPV rule (>0 accept)")
        ws.cell(row=r, column=2, value=f'=IF({npv_cell}>0,"ACCEPT","REJECT")')
        r += 1
        ws.cell(row=r, column=1, value="IRR rule (>k accept)")
        ws.cell(row=r, column=2, value=f'=IF({irr_cell}>{kref},"ACCEPT","REJECT")')
        r += 1
        ws.cell(row=r, column=1, value="PI rule (>1 accept)")
        ws.cell(row=r, column=2, value=f'=IF({pi_cell}>1,"ACCEPT","REJECT")')
        r += 1

        # NPV profile table for the chart sheet.
        self._npv_profile_anchor = (ncf_row, cf0, cf1_5, kref)
        r += 1
        ws.cell(row=r, column=1, value="NPV profile (for chart)").font = BOLD
        r += 1
        prof_hdr = r
        ws.cell(row=r, column=1, value="Discount rate")
        ws.cell(row=r, column=2, value="NPV")
        r += 1
        self._npv_profile_range = None
        first = r
        for pct in range(0, 31, 5):
            rate = pct / 100.0
            ws.cell(row=r, column=1, value=rate).number_format = "0%"
            ws.cell(row=r, column=2,
                    value=f"={cf0}+NPV(A{r},{cf1_5})").number_format = "#,##0"
            r += 1
        self._npv_profile_range = (prof_hdr, first, r - 1)
        self._disclaimer_row(ws, r + 1, span=7)
        self._setup_print(ws, title_row=4)

    # ----------------------------------------------------------------- Charts
    def _sheet_charts(self) -> None:
        ws = self.wb.create_sheet("Charts")
        ws.cell(row=1, column=1, value="Charts").font = TITLE
        periods = self.company.periods
        n = len(periods)

        def _labelled(chart) -> None:
            chart.dataLabels = DataLabelList(showVal=True, numFmt="#,##0.00")
            for s in chart.series:
                s.dLbls = DataLabelList(showVal=True, numFmt="#,##0.00")

        # 1) Ratio trends (ROE, Net margin, Current ratio) from Ratios sheet.
        rmap = getattr(self, "_ratios_rowmap", {})
        wanted = ["Return on Equity (ROE)", "Net Profit Margin", "Current Ratio"]
        rows = [rmap[w] for w in wanted if w in rmap]
        if rows and n >= 2:
            chart = LineChart()
            chart.title = "Key ratio trends"
            chart.style = 12
            chart.height = 8
            chart.width = 16
            chart.y_axis.title = "Ratio value"
            chart.x_axis.title = "Period"
            cats = Reference(self.wb["Ratios"], min_col=3, max_col=2 + n, min_row=3, max_row=3)
            for rr in rows:
                ref = Reference(self.wb["Ratios"], min_col=3, max_col=2 + n,
                                min_row=rr, max_row=rr)
                chart.add_data(ref, from_rows=True, titles_from_data=False)
            chart.set_categories(cats)
            ws.add_chart(chart, "A3")

        # 2) Revenue & net income trend (Inputs sheet), side-by-side with (1).
        imap = getattr(self, "_inputs_rowmap", {})
        if n >= 2 and "revenue" in imap and "net_income" in imap:
            inc_chart = LineChart()
            inc_chart.title = "Revenue & net income trend"
            inc_chart.style = 12
            inc_chart.height = 8
            inc_chart.width = 16
            inc_chart.y_axis.title = "$"
            inc_chart.x_axis.title = "Period"
            inputs_ws = self.wb["Inputs"]
            cats = Reference(inputs_ws, min_col=2, max_col=1 + n, min_row=3, max_row=3)
            for attr in ("revenue", "net_income"):
                ref = Reference(inputs_ws, min_col=2, max_col=1 + n,
                                min_row=imap[attr], max_row=imap[attr])
                inc_chart.add_data(ref, from_rows=True, titles_from_data=False)
            inc_chart.set_categories(cats)
            ws.add_chart(inc_chart, "K3")

        # 3) Capital structure: long-term debt vs equity, per period.
        if n >= 1 and "long_term_debt" in imap and "total_equity" in imap:
            cap_chart = BarChart()
            cap_chart.type = "col"
            cap_chart.grouping = "clustered"
            cap_chart.title = "Capital structure: debt vs equity"
            cap_chart.height = 8
            cap_chart.width = 16
            cap_chart.y_axis.title = "$"
            inputs_ws = self.wb["Inputs"]
            cats = Reference(inputs_ws, min_col=2, max_col=1 + n, min_row=3, max_row=3)
            for attr in ("long_term_debt", "total_equity"):
                ref = Reference(inputs_ws, min_col=2, max_col=1 + n,
                                min_row=imap[attr], max_row=imap[attr])
                cap_chart.add_data(ref, from_rows=True, titles_from_data=False)
            cap_chart.set_categories(cats)
            _labelled(cap_chart)
            ws.add_chart(cap_chart, "A22")

        # 4) Intrinsic vs market value bar.
        ws.cell(row=41, column=1, value="Intrinsic vs Market (per share)").font = BOLD
        ws.cell(row=42, column=1, value="Intrinsic")
        ws.cell(row=42, column=2, value=f"={self._intrinsic_cell}").number_format = "#,##0.00"
        ws.cell(row=43, column=1, value="Market")
        price_ref = "Assumptions!" + self.assumption_refs["price_per_share"].split("!")[-1]
        ws.cell(row=43, column=2, value=f"={price_ref}").number_format = "#,##0.00"
        ws.cell(row=44, column=1,
                value="Note: \"Market\" shows $0.00 until Price / Share is entered "
                      "on the Assumptions sheet.").font = MUTED
        bar = BarChart()
        bar.title = "Intrinsic vs market value/share"
        bar.height = 7
        bar.width = 12
        bar.y_axis.title = "$/share"
        bar_data = Reference(ws, min_col=2, min_row=42, max_row=43)
        bar_cats = Reference(ws, min_col=1, min_row=42, max_row=43)
        bar.add_data(bar_data, titles_from_data=False)
        bar.set_categories(bar_cats)
        _labelled(bar)
        ws.add_chart(bar, "K22")

        # 5) NPV profile line chart from CapBudget.
        if getattr(self, "_npv_profile_range", None):
            hdr, first, last = self._npv_profile_range
            cb = self.wb["CapBudget"]
            npv_chart = LineChart()
            npv_chart.title = "NPV profile (NPV vs discount rate)"
            npv_chart.height = 8
            npv_chart.width = 14
            npv_chart.x_axis.title = "Discount rate"
            npv_chart.y_axis.title = "NPV ($)"
            data = Reference(cb, min_col=2, min_row=hdr, max_row=last)
            cats = Reference(cb, min_col=1, min_row=first, max_row=last)
            npv_chart.add_data(data, titles_from_data=True)
            npv_chart.set_categories(cats)
            _labelled(npv_chart)
            ws.add_chart(npv_chart, "A60")

        self._disclaimer_row(ws, 78, span=6)
        self._setup_print(ws, title_row=1)


def _fmt(unit: str) -> str:
    return {
        "%": "0.00%",
        "x": "0.00",
        "days": "0.0",
        "$": "#,##0",
    }.get(unit, "0.0000")


def build_workbook(company: Company, path: str | Path) -> Path:
    """Convenience entry point used by the CLI and the MCP-style API."""
    return WorkbookBuilder(company).save(path)
