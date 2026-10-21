"""Write the analysis to a formula-driven Excel workbook.

The DCF sheet contains live formulas pointing at named input cells, so changing an input
in Excel re-values the company exactly as the Python model would. Reverse-DCF and
sensitivity results are written as values (they come from many model runs).
Conventions: blue font = hard-coded input, black = formula.
"""
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName

from .pipeline import Analysis

BLUE = Font(color="0000CC")
BOLD = Font(bold=True)
TITLE = Font(bold=True, size=14)
HEADER_FILL = PatternFill("solid", fgColor="DDE4EE")
KEY_FILL = PatternFill("solid", fgColor="FFF2CC")
TOP_BORDER = Border(top=Side(style="thin"))

USD_M = '#,##0.0,,;(#,##0.0,,);"-"'   # display raw dollars in millions
USD = '$#,##0.00'
PCT = '0.0%'
NUM = '#,##0.00'
SHARES_M = '#,##0.0,,'

# (name, label, attribute on Analysis, number format, is_input)
BASE_INPUTS = [
    ("Price", "Share price", "base.price", USD, True),
    ("Shares", "Shares outstanding (millions)", "base.shares", SHARES_M, True),
    ("Revenue_0", "Base-period revenue ($M)", "base.revenue", USD_M, True),
    ("Cash", "Cash + short-term investments ($M)", "base.cash", USD_M, True),
    ("Debt", "Debt ($M)", "base.debt", USD_M, True),
    ("Leases", "Operating lease liabilities ($M)", "base.lease_liabilities", USD_M, True),
]
ASSUMPTION_INPUTS = [
    ("Growth_Y1", "Revenue growth, year 1", "growth_year1", PCT),
    ("Growth_Start", "Revenue growth, start of fade line", "growth_start", PCT),
    ("Terminal_Growth", "Terminal growth (final year & beyond)", "terminal_growth", PCT),
    ("Margin_Start", "EBIT margin, starting", "margin_start", PCT),
    ("Margin_Target", "EBIT margin, target", "margin_target", PCT),
    ("Margin_Fade", "Years to reach target margin", "margin_fade_years", "0"),
    ("Tax_Rate", "Tax rate", "tax_rate", PCT),
    ("DA_Pct", "D&A % of revenue", "d_and_a_pct_revenue", PCT),
    ("Capex_Pct", "Capex % of revenue", "capex_pct_revenue", PCT),
    ("NWC_Pct", "Net working capital % of revenue", "nwc_pct_revenue", PCT),
    ("Risk_Free", "Risk-free rate (10Y UST)", "risk_free", PCT),
    ("Beta", "Beta (Blume-adjusted)", "beta", NUM),
    ("ERP", "Equity risk premium", "equity_risk_premium", PCT),
    ("Kd_Pre", "Pre-tax cost of debt", "pre_tax_cost_of_debt", PCT),
    ("Mid_Year", "Mid-year convention (1 = yes)", "mid_year_convention", "0"),
    ("Leases_As_Debt", "Treat leases as debt (1 = yes)", "leases_as_debt", "0"),
]


def _get(obj, dotted: str):
    for part in dotted.split("."):
        obj = getattr(obj, part)
    return obj


def _name(wb: Workbook, name: str, sheet: str, cell: str) -> None:
    col, row = cell.rstrip("0123456789"), cell[len(cell.rstrip("0123456789")):]
    wb.defined_names[name] = DefinedName(name, attr_text=f"'{sheet}'!${col}${row}")


def _inputs_sheet(wb: Workbook, x: Analysis) -> None:
    ws = wb.active
    ws.title = "Inputs"
    ws["A1"] = f"{x.company} ({x.ticker}) - DCF inputs"
    ws["A1"].font = TITLE
    ws["A2"] = (f"Base period {x.base.label} (ended {x.base.period_end:%d %b %Y}). "
                f"Market data as of {x.market.as_of}. "
                "Blue = input (edit freely); black = formula.")
    row = 4
    ws.cell(row, 1, "Market & balance sheet").font = BOLD
    row += 1
    for name, label, attr, fmt, _ in BASE_INPUTS:
        ws.cell(row, 1, label)
        c = ws.cell(row, 2, float(_get(x, attr)))
        c.number_format, c.font = fmt, BLUE
        _name(wb, name, "Inputs", f"B{row}")
        row += 1

    row += 1
    ws.cell(row, 1, "Assumptions").font = BOLD
    row += 1
    for name, label, attr, fmt in ASSUMPTION_INPUTS:
        value = getattr(x.assumptions, attr)
        if value is None and attr == "growth_year1":
            value = x.assumptions.growth_start  # no override: year 1 sits on the fade line
        ws.cell(row, 1, label)
        c = ws.cell(row, 2, int(value) if isinstance(value, bool) else value)
        c.number_format, c.font = fmt, BLUE
        _name(wb, name, "Inputs", f"B{row}")
        row += 1
    ws.cell(row, 1, "Forecast years (structural: rebuild workbook to change)")
    ws.cell(row, 2, x.assumptions.forecast_years)
    _name(wb, "N_Years", "Inputs", f"B{row}")
    row += 2

    ws.cell(row, 1, "Discount rate").font = BOLD
    row += 1
    formulas = [
        ("Cost_Of_Equity", "Cost of equity (CAPM)", "=Risk_Free+Beta*ERP", PCT),
        ("Equity_MV", "Market value of equity ($M)", "=Price*Shares", USD_M),
        ("Debt_For_WACC", "Debt used in WACC ($M)", "=Debt+Leases*Leases_As_Debt", USD_M),
        ("WACC_Computed", "WACC (computed)",
         "=(Equity_MV*Cost_Of_Equity+Debt_For_WACC*Kd_Pre*(1-Tax_Rate))/(Equity_MV+Debt_For_WACC)", PCT),
    ]
    for name, label, f, fmt in formulas:
        ws.cell(row, 1, label)
        ws.cell(row, 2, f).number_format = fmt
        _name(wb, name, "Inputs", f"B{row}")
        row += 1
    ws.cell(row, 1, "WACC override (leave blank to use computed)")
    ws.cell(row, 2).font = BLUE
    ws.cell(row, 2).number_format = PCT
    if x.assumptions.wacc_override is not None:
        ws.cell(row, 2, x.assumptions.wacc_override)
    _name(wb, "WACC_Override", "Inputs", f"B{row}")
    row += 1
    ws.cell(row, 1, "WACC used").font = BOLD
    c = ws.cell(row, 2, '=IF(WACC_Override="",WACC_Computed,WACC_Override)')
    c.number_format, c.font, c.fill = PCT, BOLD, KEY_FILL
    _name(wb, "WACC", "Inputs", f"B{row}")
    row += 1
    ws.cell(row, 1, "Net debt ($M)")
    ws.cell(row, 2, "=Debt_For_WACC-Cash").number_format = USD_M
    _name(wb, "Net_Debt", "Inputs", f"B{row}")

    ws.column_dimensions["A"].width = 52
    ws.column_dimensions["B"].width = 16


def _dcf_sheet(wb: Workbook, x: Analysis) -> None:
    ws = wb.create_sheet("DCF")
    n = x.assumptions.forecast_years
    ws["A1"] = f"{x.ticker} discounted cash flow ($M except per share)"
    ws["A1"].font = TITLE

    first_col = 2
    cols = [get_column_letter(first_col + i) for i in range(n)]
    ws.cell(3, 1, "Fiscal year").font = BOLD
    ws.cell(4, 1, "Year #")
    for i, col in enumerate(cols):
        ws[f"{col}3"] = x.result.projection.columns[i]
        ws[f"{col}3"].font, ws[f"{col}3"].fill = BOLD, HEADER_FILL
        ws[f"{col}4"] = i + 1

    lines = [  # (row, label, formula template using {c}=column, {p}=previous column, fmt)
        (5, "Revenue growth", "=IF({c}4=1,Growth_Y1,Growth_Start+(Terminal_Growth-Growth_Start)*({c}4-1)/(N_Years-1))", PCT),
        (6, "Revenue", None, USD_M),
        (7, "EBIT margin", "=Margin_Start+(Margin_Target-Margin_Start)*MIN({c}4/Margin_Fade,1)", PCT),
        (8, "EBIT", "={c}6*{c}7", USD_M),
        (9, "Taxes", "={c}8*Tax_Rate", USD_M),
        (10, "NOPAT", "={c}8-{c}9", USD_M),
        (11, "+ D&A", "={c}6*DA_Pct", USD_M),
        (12, "- Capex", "={c}6*Capex_Pct", USD_M),
        (13, "Net working capital", "={c}6*NWC_Pct", USD_M),
        (14, "- Change in NWC", None, USD_M),
        (15, "Free cash flow to firm", "={c}10+{c}11-{c}12-{c}14", USD_M),
        (16, "Discount period", "={c}4-0.5*Mid_Year", "0.0"),
        (17, "Discount factor", "=1/(1+WACC)^{c}16", "0.000"),
        (18, "PV of FCFF", "={c}15*{c}17", USD_M),
    ]
    for row, label, template, fmt in lines:
        ws.cell(row, 1, label)
        for i, col in enumerate(cols):
            prev = cols[i - 1] if i else None
            if row == 6:
                f = f"=Revenue_0*(1+{col}5)" if i == 0 else f"={prev}6*(1+{col}5)"
            elif row == 14:
                f = f"={col}13-Revenue_0*NWC_Pct" if i == 0 else f"={col}13-{prev}13"
            else:
                f = template.format(c=col, p=prev)
            ws[f"{col}{row}"] = f
            ws[f"{col}{row}"].number_format = fmt
    for row in (15, 18):
        ws.cell(row, 1).font = BOLD
        for col in cols:
            ws[f"{col}{row}"].font, ws[f"{col}{row}"].border = BOLD, TOP_BORDER

    last = cols[-1]
    summary = [
        ("Sum of PV of FCFF", f"=SUM({cols[0]}18:{last}18)", USD_M, "PV_FCFF"),
        ("Terminal value (Gordon growth)", f"={last}15*(1+Terminal_Growth)/(WACC-Terminal_Growth)", USD_M, "TV"),
        ("PV of terminal value", "=TV/(1+WACC)^N_Years", USD_M, "PV_TV"),
        ("Enterprise value", "=PV_FCFF+PV_TV", USD_M, "EV"),
        ("Less: net debt", "=Net_Debt", USD_M, None),
        ("Equity value", "=EV-Net_Debt", USD_M, "Equity_Value"),
        ("Value per share", "=Equity_Value/Shares", USD, "Value_Per_Share"),
        ("Current price", "=Price", USD, None),
        ("Upside / (downside)", "=Value_Per_Share/Price-1", PCT, None),
        ("Terminal value % of EV", "=PV_TV/EV", PCT, None),
        ("Implied EV / base-period EBIT", f"=EV/(Revenue_0*Margin_Start)", '0.0"x"', None),
    ]
    row = 21
    ws.cell(row - 1, 1, "Valuation").font = BOLD
    for label, f, fmt, name in summary:
        ws.cell(row, 1, label)
        c = ws.cell(row, 2, f)
        c.number_format = fmt
        if name:
            _name(wb, name, "DCF", f"B{row}")
        if label in ("Value per share", "Enterprise value", "Equity value"):
            ws.cell(row, 1).font = c.font = BOLD
        if label == "Value per share":
            c.fill = KEY_FILL
        row += 1

    ws.column_dimensions["A"].width = 32
    for col in cols:
        ws.column_dimensions[col].width = 12
    ws.freeze_panes = "B4"


def _historicals_sheet(wb: Workbook, x: Analysis) -> None:
    ws = wb.create_sheet("Historicals")
    ws["A1"] = f"{x.ticker} historical financials (SEC 10-K XBRL; $M)"
    ws["A1"].font = TITLE
    ratio_rows = {"revenue_growth", "gross_margin", "ebit_margin", "effective_tax_rate",
                  "d_and_a_pct_revenue", "capex_pct_revenue", "nwc_pct_revenue",
                  "sbc_pct_revenue", "roic"}
    table = x.hist.copy()
    if x.latest.attrs["label"].startswith("TTM"):
        table[x.latest.attrs["label"]] = x.latest.reindex(table.index)
    ws.cell(3, 1, "Fiscal year").font = BOLD
    for j, fy in enumerate(table.columns, start=2):
        c = ws.cell(3, j, fy if isinstance(fy, str) else int(fy))
        c.font, c.fill = BOLD, HEADER_FILL
    for i, item in enumerate(table.index, start=4):
        ws.cell(i, 1, item.replace("_", " "))
        for j, v in enumerate(table.loc[item], start=2):
            if v == v:  # skip NaN
                c = ws.cell(i, j, float(v))
                c.number_format = PCT if item in ratio_rows else (
                    SHARES_M if item == "diluted_shares" else USD_M)
    ws.column_dimensions["A"].width = 34
    ws.freeze_panes = "B4"


def _reverse_sheet(wb: Workbook, x: Analysis) -> None:
    ws = wb.create_sheet("Reverse DCF")
    ws["A1"] = "What is the current price implying?"
    ws["A1"].font = TITLE
    ws["A2"] = ("Each row solves for one input (others held at their base-case values) so that "
                "value per share equals the current price. Solved in Python; values only.")
    headers = ["Input solved for", "Assumed", "Implied by price", "Implied 10Y revenue CAGR"]
    for j, h in enumerate(headers, start=1):
        c = ws.cell(4, j, h)
        c.font, c.fill = BOLD, HEADER_FILL
    labels = {"growth_start": "Revenue growth, start of fade line", "margin_target": "Target EBIT margin"}
    for i, (field, iv) in enumerate(x.implied.items(), start=5):
        ws.cell(i, 1, labels.get(field, field))
        ws.cell(i, 2, iv.assumed).number_format = PCT
        ws.cell(i, 3, iv.implied if iv.implied is not None else "no solution in range").number_format = PCT
        if iv.implied_10y_revenue_cagr is not None:
            ws.cell(i, 4, iv.implied_10y_revenue_cagr).number_format = PCT
    ws.cell(8, 1, f"Price used: ${x.base.price:,.2f} as of {x.market.as_of}")
    for col, w in zip("ABCD", (30, 14, 18, 26)):
        ws.column_dimensions[col].width = w


def _sensitivity_sheet(wb: Workbook, x: Analysis) -> None:
    ws = wb.create_sheet("Sensitivity")
    ws["A1"] = "Sensitivity analysis (value per share)"
    ws["A1"].font = TITLE

    ws["A3"] = "WACC (rows) x terminal growth (columns)"
    ws["A3"].font = BOLD
    for j, g in enumerate(x.grid.columns, start=2):
        c = ws.cell(4, j, g)
        c.number_format, c.font, c.fill = PCT, BOLD, HEADER_FILL
    for i, (w, vals) in enumerate(x.grid.iterrows(), start=5):
        c = ws.cell(i, 1, w)
        c.number_format, c.font, c.fill = PCT, BOLD, HEADER_FILL
        for j, v in enumerate(vals, start=2):
            c = ws.cell(i, j, None if v != v else v)
            c.number_format = USD
            if i == 5 + len(x.grid) // 2 and j == 2 + len(x.grid.columns) // 2:
                c.fill, c.font = KEY_FILL, BOLD

    row = 7 + len(x.grid)
    ws.cell(row, 1, "Tornado: one input shocked at a time").font = BOLD
    row += 1
    for j, h in enumerate(["Input", "Base", "Shock (+/-)", "Value: down", "Value: up", "Swing"], 1):
        c = ws.cell(row, j, h)
        c.font, c.fill = BOLD, HEADER_FILL
    for _, t in x.tornado.iterrows():
        row += 1
        ws.cell(row, 1, t["input"].replace("_override", "").replace("_", " "))
        ws.cell(row, 2, t["base_input"]).number_format = PCT
        ws.cell(row, 3, t["shock"]).number_format = PCT
        for j, k in ((4, "value_low_shock"), (5, "value_high_shock"), (6, "swing")):
            ws.cell(row, j, t[k]).number_format = USD

    row += 2
    ws.cell(row, 1, "Scenarios (mechanical: growth +/-4 pts, margin +/-3 pts)").font = BOLD
    row += 1
    for j, h in enumerate(["Scenario", "Growth yr 1", "Target margin", "Value/share", "vs. price", "Weight"], 1):
        c = ws.cell(row, j, h)
        c.font, c.fill = BOLD, HEADER_FILL
    for name, s in x.scenarios.iterrows():
        row += 1
        ws.cell(row, 1, name)
        for j, (k, fmt) in enumerate((("growth_start", PCT), ("margin_target", PCT),
                                      ("value_per_share", USD), ("upside", PCT), ("weight", PCT)), 2):
            ws.cell(row, j, float(s[k])).number_format = fmt
    row += 1
    ws.cell(row, 1, "Probability-weighted").font = BOLD
    c = ws.cell(row, 4, x.scenarios.attrs["weighted_value"])
    c.number_format, c.font = USD, BOLD

    ws.column_dimensions["A"].width = 40
    for col in "BCDEF":
        ws.column_dimensions[col].width = 14


def write_workbook(x: Analysis, path: Path) -> Path:
    wb = Workbook()
    _inputs_sheet(wb, x)
    _dcf_sheet(wb, x)
    _reverse_sheet(wb, x)
    _sensitivity_sheet(wb, x)
    _historicals_sheet(wb, x)
    for ws in wb.worksheets:
        ws.sheet_view.showGridLines = False
        for row in ws.iter_rows():
            for c in row:
                if c.column > 1:
                    c.alignment = Alignment(horizontal="right")
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path
