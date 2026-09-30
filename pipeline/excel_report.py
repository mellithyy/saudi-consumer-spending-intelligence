"""Build the Excel management report: one printable page that follows a Year cell.

Stage 5 of the pipeline (the Excel report, beside the Power BI dashboard).
Input:  data/powerbi/*.parquet (run pipeline/export.py first)
Output: reports/excel/saudi_spending_report.xlsx

The workbook is a working Excel file, not a picture of numbers. The Data sheet holds every row; the Calc sheet
works out each figure with ordinary Excel formulas (SUMIFS, MAXIFS, INDEX/MATCH); the Report sheet only shows
them. A manager picks a year in one cell and the whole page, the tables and the chart follow it.
The figures match the dashboard's: growth compares only the week numbers found in both years, and an average
payment is total spent divided by total payments.
"""
from pathlib import Path

import duckdb
from openpyxl import Workbook
from openpyxl.cell.rich_text import CellRichText, TextBlock
from openpyxl.cell.text import InlineFont
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.chart.data_source import AxDataSource, NumDataSource, NumRef, StrRef
from openpyxl.formatting.rule import DataBarRule, FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.table import Table, TableStyleInfo

PROJECT_FOLDER = Path(__file__).resolve().parent.parent
EXPORT_FOLDER = PROJECT_FOLDER / "data" / "powerbi"
OUTPUT = PROJECT_FOLDER / "reports" / "excel" / "saudi_spending_report.xlsx"

YEARS = [2022, 2023, 2024, 2025]  # 2021 is left out: its year before, 2020, starts in May, mid-pandemic
DEFAULT_YEAR = 2025

# The dashboard's colours, so the two reports look like one family
INK, INK2, MUTED = "13161B", "4F5966", "646E7B"
BORDER, CANVAS = "E3E7EC", "F4F6F8"
WEEK_COLOURS = {"Normal": "C9D1DA", "Part Ramadan": "5FB48C", "Full Ramadan": "16825D", "Eid": "D98A1E"}
YEAR_BEFORE = "6B7684"
FONT = "Segoe UI"
# growth: a sign always shown, falls in red. The true minus sign (−) is escaped with a backslash, because
# Excel only shows a few characters (+ - $ and so on) as they are inside a number format.
PLUS = '+0.0%;[Red]\\−0.0%;0.0%'

# One row per week per series, the three levels stacked, with the week labels the dashboard uses.
DATA_QUERY = """
    WITH rows AS (
        SELECT 'National' AS level, 'Saudi Arabia' AS name, date_key, value_k_sar, transactions_k
        FROM '{folder}/fact_national.parquet'
        UNION ALL
        SELECT 'City', c.city, f.date_key, f.value_k_sar, f.transactions_k
        FROM '{folder}/fact_city.parquet' AS f JOIN '{folder}/dim_city.parquet' AS c USING (city_key)
        UNION ALL
        SELECT 'Sector', s.sector, f.date_key, f.value_k_sar, f.transactions_k
        FROM '{folder}/fact_sector.parquet' AS f JOIN '{folder}/dim_sector.parquet' AS s USING (sector_key)
    )
    SELECT d.week_start, d.year, d.week_of_year, r.level, r.name, r.value_k_sar, r.transactions_k,
           d.week_type, coalesce(d.phase, '') AS phase, coalesce(d.ramadan_phase, '') AS ramadan_phase,
           d.ramadan_year,
           -- one text key per row, so a formula can find a week with a single MATCH
           r.level || '|' || r.name || '|' || d.year || '|' || d.week_of_year AS key
    FROM rows AS r JOIN '{folder}/dim_date.parquet' AS d USING (date_key)
    ORDER BY CASE r.level WHEN 'National' THEN 1 WHEN 'City' THEN 2 ELSE 3 END, r.name, d.week_start
"""
DATA_COLUMNS = [  # (header on the Data sheet, defined name the formulas use, column width, number format)
    ("Week start", "WeekStart", 12, "d mmm yyyy"),
    ("Year", "Year", 7, "0"),
    ("Week", "Week", 7, "0"),
    ("Level", "Level", 10, "@"),
    ("Name", "Name", 22, "@"),
    ("Spent (thousand SAR)", "Spent", 20, "#,##0"),
    ("Payments (thousand)", "Payments", 19, "#,##0"),
    ("Week type", "WeekType", 13, "@"),
    ("Phase", "Phase", 30, "@"),
    ("Ramadan phase", "RamadanPhase", 16, "@"),
    ("Ramadan year", "RamadanYear", 14, "0"),
    ("Key", "Key", 38, "@"),
]


def font(size=10, bold=False, colour=INK, italic=False):
    return Font(name=FONT, size=size, bold=bold, color=colour, italic=italic)


def fill(colour):
    return PatternFill("solid", start_color=colour, end_color=colour)


THIN = Side(style="thin", color=BORDER)
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
LINE_UNDER = Border(bottom=Side(style="thin", color=INK2))


def name_range(wb, name, ref):
    wb.defined_names[name] = DefinedName(name, attr_text=ref)


def read_data():
    folder = EXPORT_FOLDER.as_posix()
    if not (EXPORT_FOLDER / "fact_national.parquet").exists():
        raise FileNotFoundError(f"{EXPORT_FOLDER} has no export. Run python pipeline/export.py first.")
    rows = duckdb.sql(DATA_QUERY.format(folder=folder)).fetchall()
    cities = [r[0] for r in duckdb.sql(f"SELECT city FROM '{folder}/dim_city.parquet' ORDER BY city").fetchall()]
    sectors = [r[0] for r in duckdb.sql(f"SELECT sector FROM '{folder}/dim_sector.parquet' ORDER BY sector").fetchall()]
    return rows, cities, sectors


def data_sheet(wb, rows):
    ws = wb.create_sheet("Data")
    ws.append([c[0] for c in DATA_COLUMNS])
    for row in rows:
        ws.append(list(row))
    last = len(rows) + 1
    for i, (header, name, width, number_format) in enumerate(DATA_COLUMNS):
        letter = ws.cell(row=1, column=i + 1).column_letter
        ws.column_dimensions[letter].width = width
        for cell in ws[letter][1:]:
            cell.number_format = number_format
        # Readable formulas: SUMIFS(Spent, Level, "City", ...) instead of SUMIFS(Data!$F$2:$F$7831, ...)
        name_range(wb, name, f"Data!${letter}$2:${letter}${last}")
    table = Table(displayName="Spending", ref=f"A1:{ws.cell(row=1, column=len(DATA_COLUMNS)).column_letter}{last}")
    table.tableStyleInfo = TableStyleInfo(name="TableStyleLight1", showRowStripes=True)
    ws.add_table(table)
    ws.freeze_panes = "A2"
    return last - 1


def calc_sheet(wb, cities, sectors):
    """Every figure of the report, worked out in one place. Report cells only point here."""
    ws = wb.create_sheet("Calc")
    ws.column_dimensions["A"].width = 44
    for letter in "BCDEFGHIJKLMNOP":
        ws.column_dimensions[letter].width = 14
    ws["A1"] = "Calculations for the Report sheet. Every cell here is a formula over the Data sheet."
    ws["A1"].font = font(11, bold=True)

    same_weeks = 'Week, ">="&CommonFrom, Week, "<="&CommonTo'
    scalars = [  # (defined name, label, formula, number format)
        ("PrevYear", "Year before", "=SelYear-1", "0"),
        ("FirstWeekY", "First week number of the year", '=_xlfn.MINIFS(Week, Level, "National", Year, SelYear)', "0"),
        ("LastWeekY", "Last week number of the year", '=_xlfn.MAXIFS(Week, Level, "National", Year, SelYear)', "0"),
        ("FirstWeekP", "First week number of the year before", '=_xlfn.MINIFS(Week, Level, "National", Year, PrevYear)', "0"),
        ("LastWeekP", "Last week number of the year before", '=_xlfn.MAXIFS(Week, Level, "National", Year, PrevYear)', "0"),
        # Growth is fair only on weeks found in both years: 2025 has weeks 1 to 27 so far, 2023 has a week 53.
        ("CommonFrom", "Same weeks: from week", "=MAX(FirstWeekY, FirstWeekP)", "0"),
        ("CommonTo", "Same weeks: to week", "=MIN(LastWeekY, LastWeekP)", "0"),
        ("WeeksY", "Weeks in the year", '=COUNTIFS(Level, "National", Year, SelYear)', "0"),
        ("DateFrom", "First day", '=_xlfn.MINIFS(WeekStart, Level, "National", Year, SelYear)', "d mmm yyyy"),
        ("DateTo", "Last day", '=_xlfn.MAXIFS(WeekStart, Level, "National", Year, SelYear)+6', "d mmm yyyy"),
        ("NatSpent", "National spent, thousand SAR", '=SUMIFS(Spent, Level, "National", Year, SelYear)', "#,##0"),
        ("NatPay", "National payments, thousand", '=SUMIFS(Payments, Level, "National", Year, SelYear)', "#,##0"),
        ("NatSpentSame", "National spent on the same weeks", f'=SUMIFS(Spent, Level, "National", Year, SelYear, {same_weeks})', "#,##0"),
        ("NatSpentPrev", "National spent, same weeks a year before", f'=SUMIFS(Spent, Level, "National", Year, PrevYear, {same_weeks})', "#,##0"),
        ("NatPaySame", "National payments on the same weeks", f'=SUMIFS(Payments, Level, "National", Year, SelYear, {same_weeks})', "#,##0"),
        ("NatPayPrev", "National payments, same weeks a year before", f'=SUMIFS(Payments, Level, "National", Year, PrevYear, {same_weeks})', "#,##0"),
        ("NatGrowth", "Spending growth, same weeks", "=NatSpentSame/NatSpentPrev-1", PLUS),
        # An average payment is total spent / total payments, never an average of weekly averages.
        ("NatAvgPay", "Average payment, SAR", "=NatSpent/NatPay", "0.0"),
        ("NatAvgPaySame", "Average payment on the same weeks, SAR", "=NatSpentSame/NatPaySame", "0.0"),
        ("NatAvgPayPrev", "Average payment a year before, SAR", "=NatSpentPrev/NatPayPrev", "0.0"),
        ("NatAvgPayChange", "Change in the average payment", "=NatAvgPaySame/NatAvgPayPrev-1", PLUS),
        ("BiggestWeek", "Biggest week, thousand SAR", '=_xlfn.MAXIFS(Spent, Level, "National", Year, SelYear)', "#,##0"),
        ("BiggestRow", "Its row in the weekly table below", "=MATCH(BiggestWeek, WeeklySpent, 0)", "0"),
        ("BiggestDate", "Its first day", "=INDEX(WeeklyDate, BiggestRow)", "d mmm yyyy"),
        ("BiggestPhase", "What that week was", "=INDEX(WeeklyPhase, BiggestRow)", "@"),
        # Ramadan of the chosen year. The 8 weeks before Ramadan 2025 start in December 2024, so they carry
        # ramadan_year 2025, not the calendar year.
        ("RamBefore", "Ramadan: average week of the 8 weeks before, thousand SAR",
         '=AVERAGEIFS(Spent, Level, "National", RamadanYear, SelYear, RamadanPhase, "8 weeks before")', "#,##0"),
        ("RamLast", "Ramadan: last full week, thousand SAR",
         '=SUMIFS(Spent, Level, "National", RamadanYear, SelYear, RamadanPhase, "Last full week")', "#,##0"),
        ("RamEid", "Ramadan: Eid al-Fitr week, thousand SAR",
         '=SUMIFS(Spent, Level, "National", RamadanYear, SelYear, RamadanPhase, "Eid week")', "#,##0"),
        ("RamLift", "Last full week against the 8 weeks before", "=RamLast/RamBefore-1", PLUS),
        ("RamEidDrop", "Eid week against the last full week", "=RamEid/RamLast-1", PLUS),
    ]
    for i, (name, label, formula, number_format) in enumerate(scalars, start=3):
        ws.cell(row=i, column=1, value=label).font = font(10, colour=INK2)
        cell = ws.cell(row=i, column=2, value=formula)
        cell.number_format = number_format
        name_range(wb, name, f"Calc!$B${i}")

    # Weekly table: one row per week number, for the chart and the biggest-week note
    top = len(scalars) + 5
    heads = ["Week", "First day", "Key", "Spent, thousand SAR", "Week type", "Phase", "Label",
             "Normal", "Part Ramadan", "Full Ramadan", "Eid", "Same week, year before"]
    ws.cell(row=top - 1, column=1, value="Weekly, the chosen year (bn SAR in the chart columns)").font = font(11, bold=True)
    for j, head in enumerate(heads, start=1):
        c = ws.cell(row=top, column=j, value=head)
        c.font = font(10, bold=True)
    first, last = top + 1, top + 53
    for n in range(1, 54):
        r = top + n
        ws.cell(row=r, column=1, value=n)
        has = f'COUNTIFS(Level, "National", Year, SelYear, Week, A{r})'
        ws.cell(row=r, column=2, value=f'=IF({has}=0, "", _xlfn.MINIFS(WeekStart, Level, "National", Year, SelYear, Week, A{r}))').number_format = "d mmm yyyy"
        ws.cell(row=r, column=3, value=f'="National|Saudi Arabia|"&SelYear&"|"&A{r}')
        ws.cell(row=r, column=4, value=f'=IF(B{r}="", "", SUMIFS(Spent, Level, "National", Year, SelYear, Week, A{r}))').number_format = "#,##0"
        # &"" keeps an empty Data cell as empty text: a formula that reads an empty cell gets 0 otherwise
        ws.cell(row=r, column=5, value=f'=IF(B{r}="", "", INDEX(WeekType, MATCH(C{r}, Key, 0))&"")')
        ws.cell(row=r, column=6, value=f'=IF(B{r}="", "", INDEX(Phase, MATCH(C{r}, Key, 0))&"")')
        # axis label: the month's name on its first week (days 1 to 7), blank on the others
        ws.cell(row=r, column=7, value=f'=IF(B{r}="", "", IF(DAY(B{r})<=7, TEXT(B{r}, "mmm"), ""))')
        # One column per week type: a chart colours each column by type, so every week keeps its colour
        # whatever year is picked. #N/A (not 0) leaves no bar and no label.
        for k, week_type in enumerate(["Normal", "Part Ramadan", "Full Ramadan", "Eid"]):
            ws.cell(row=r, column=8 + k, value=f'=IF(E{r}="{week_type}", D{r}/1000000, NA())').number_format = "0.00"
        before = f'COUNTIFS(Level, "National", Year, PrevYear, Week, A{r})'
        ws.cell(row=r, column=12, value=f'=IF(OR(B{r}="", {before}=0), NA(), SUMIFS(Spent, Level, "National", Year, PrevYear, Week, A{r})/1000000)').number_format = "0.00"
    name_range(wb, "WeeklySpent", f"Calc!$D${first}:$D${last}")
    name_range(wb, "WeeklyDate", f"Calc!$B${first}:$B${last}")
    name_range(wb, "WeeklyPhase", f"Calc!$F${first}:$F${last}")
    # Chart ranges that stop at the year's last week (weeks run 1, 2, 3 ... with no gaps from 2021 on)
    for name, col in [("ChartLabels", "G"), ("ChartNormal", "H"), ("ChartPart", "I"), ("ChartFull", "J"),
                      ("ChartEid", "K"), ("ChartBefore", "L")]:
        ws.defined_names[name] = DefinedName(
            name, attr_text=f"Calc!${col}${first}:INDEX(Calc!${col}${first}:${col}${last}, WeeksY)")

    # Cities and sectors: one row each, in name order; the Report sorts them with LARGE + INDEX/MATCH
    def block(top_row, title, level, names, columns):
        ws.cell(row=top_row - 1, column=1, value=title).font = font(11, bold=True)
        for j, (head, _, _) in enumerate(columns, start=1):
            ws.cell(row=top_row, column=j, value=head).font = font(10, bold=True)
        for i, item in enumerate(names, start=1):
            r = top_row + i
            ws.cell(row=r, column=1, value=item)
            for j, (_, formula, number_format) in enumerate(columns[1:], start=2):
                c = ws.cell(row=r, column=j, value="=" + formula.format(r=r, level=level))
                c.number_format = number_format
        return top_row + 1, top_row + len(names)

    same = 'Week, ">="&CommonFrom, Week, "<="&CommonTo'
    base = '"{level}", Name, $A{r}'
    city_cols = [
        ("City", None, None),
        ("Spent", f'SUMIFS(Spent, Level, {base}, Year, SelYear)', "#,##0"),                       # B
        ("Payments", f'SUMIFS(Payments, Level, {base}, Year, SelYear)', "#,##0"),                 # C
        ("Spent, same weeks", f'SUMIFS(Spent, Level, {base}, Year, SelYear, {same})', "#,##0"),   # D
        ("Year before", f'SUMIFS(Spent, Level, {base}, Year, PrevYear, {same})', "#,##0"),        # E
        ("Growth", "D{r}/E{r}-1", PLUS),                                                          # F
        ("Share of national", "B{r}/NatSpent", "0.0%"),                                            # G
        ("Average payment", "B{r}/C{r}", "0.0"),                                                   # H
        # Sort key: growth plus a tiny row number, so two equal values never tie in MATCH
        ("Sort key", "F{r}+ROW()/1000000000", "0.000000"),                                         # I
        ("Ramadan: 8 weeks before", f'AVERAGEIFS(Spent, Level, {base}, RamadanYear, SelYear, RamadanPhase, "8 weeks before")', "#,##0"),  # J
        ("Ramadan: last full week", f'SUMIFS(Spent, Level, {base}, RamadanYear, SelYear, RamadanPhase, "Last full week")', "#,##0"),      # K
        ("Ramadan lift", "K{r}/J{r}-1", PLUS),                                                    # L
    ]
    c_top = last + 4
    c_first, c_last = block(c_top, "Cities", "City", cities, city_cols)
    sector_cols = city_cols[:6] + [
        ("Payments, same weeks", f'SUMIFS(Payments, Level, {base}, Year, SelYear, {same})', "#,##0"),   # G
        ("Payments, year before", f'SUMIFS(Payments, Level, {base}, Year, PrevYear, {same})', "#,##0"),  # H
        ("Payments growth", "G{r}/H{r}-1", PLUS),                                                        # I
        ("Average payment", "B{r}/C{r}", "0.0"),                                                         # J
        ("Average payment change", "(D{r}/G{r})/(E{r}/H{r})-1", PLUS),                                  # K
        ("Sort key", "B{r}+ROW()/1000000000", "#,##0"),                                                  # L
        ("Ramadan: 8 weeks before", f'AVERAGEIFS(Spent, Level, {base}, RamadanYear, SelYear, RamadanPhase, "8 weeks before")', "#,##0"),  # M
        ("Ramadan: last full week", f'SUMIFS(Spent, Level, {base}, RamadanYear, SelYear, RamadanPhase, "Last full week")', "#,##0"),      # N
        ("Ramadan lift", "N{r}/M{r}-1", PLUS),                                                           # O
        ("Lift sort key", "O{r}+ROW()/1000000000", "0.000000"),                                          # P
    ]
    sector_cols[0] = ("Sector", None, None)
    s_top = c_last + 4
    s_first, s_last = block(s_top, "Sectors", "Sector", sectors, sector_cols)
    for name, col, a, b in [("CityName", "A", c_first, c_last), ("CitySpent", "B", c_first, c_last),
                            ("CityGrowth", "F", c_first, c_last), ("CityShare", "G", c_first, c_last),
                            ("CityAvgPay", "H", c_first, c_last), ("CityKey", "I", c_first, c_last),
                            ("SectorName", "A", s_first, s_last), ("SectorSpent", "B", s_first, s_last),
                            ("SectorGrowth", "F", s_first, s_last), ("SectorPayGrowth", "I", s_first, s_last),
                            ("SectorAvgPay", "J", s_first, s_last), ("SectorAvgPayChange", "K", s_first, s_last),
                            ("SectorKey", "L", s_first, s_last), ("SectorLift", "O", s_first, s_last),
                            ("SectorLiftKey", "P", s_first, s_last)]:
        name_range(wb, name, f"Calc!${col}${a}:${col}${b}")
    for row in ws.iter_rows(min_row=3, max_row=s_last):
        for cell in row:
            if cell.font == Font():  # not styled yet
                cell.font = font(10)
    return first, last


def report_sheet(wb, weekly_first, weekly_last, n_cities, n_sectors):
    ws = wb["Report"]
    ws.sheet_view.showGridLines = False
    widths = {"A": 2, "B": 22, "C": 12, "D": 12, "E": 12, "F": 12, "G": 3,
              "H": 24, "I": 11, "J": 11, "K": 11, "L": 11, "M": 11, "N": 2}
    for letter, width in widths.items():
        ws.column_dimensions[letter].width = width

    def put(ref, value, f=None, number_format=None, align=None):
        c = ws[ref]
        c.value = value
        c.font = f or font(10)
        if number_format:
            c.number_format = number_format
        if align:
            c.alignment = align
        return c

    left, right = Alignment(horizontal="left", vertical="center"), Alignment(horizontal="right", vertical="center")
    wrap = Alignment(horizontal="left", vertical="top", wrap_text=True)

    put("B1", "Card spending in Saudi Arabia", font(20, bold=True))
    put("B2", "Management summary for planning teams in banks, shops and malls. Weekly data to 12 Jul 2025. "
              "Source: SAMA, via the KAPSARC data portal.", font(9, colour=MUTED))
    ws.row_dimensions[1].height = 32

    # The one input cell. Everything on the page follows it.
    put("B4", "Year (pick one)", font(10, bold=True), align=left)
    year = put("C4", DEFAULT_YEAR, font(12, bold=True), "0", Alignment(horizontal="center", vertical="center"))
    year.fill = fill("FFF4D6")
    year.border = Border(left=Side(style="thin", color="D98A1E"), right=Side(style="thin", color="D98A1E"),
                         top=Side(style="thin", color="D98A1E"), bottom=Side(style="thin", color="D98A1E"))
    choice = DataValidation(type="list", formula1='"' + ",".join(map(str, YEARS)) + '"', allow_blank=False,
                            showErrorMessage=True, errorTitle="Year", error="Pick a year from 2022 to 2025.")
    ws.add_data_validation(choice)
    choice.add("C4")
    name_range(wb, "SelYear", "Report!$C$4")
    put("D4", '="Growth compares weeks "&CommonFrom&" to "&CommonTo&" of "&SelYear&" with the same weeks of "&PrevYear&"."',
        font(9, colour=INK2), align=left)

    # Four headline numbers
    kpis = [
        ("B", "C", "Spent (bn SAR)", "=NatSpent/1000000", "#,##0.00",
         '=WeeksY&" weeks, "&IF(YEAR(DateFrom)=YEAR(DateTo), TEXT(DateFrom, "d mmm"), TEXT(DateFrom, "d mmm yyyy"))&" to "&TEXT(DateTo, "d mmm yyyy")'),
        ("D", "F", "Growth on the same weeks a year before", "=NatGrowth", '+0.0%;\\−0.0%;0.0%',
         '="From "&TEXT(NatSpentPrev/1000000, "#,##0.00")&" bn SAR in "&PrevYear'),
        ("H", "I", "Average payment (SAR)", "=NatAvgPay", "0.0",
         '=TEXT(NatAvgPayChange, "+0.0%;\\−0.0%")&", from "&TEXT(NatAvgPayPrev, "0.0")&" SAR in "&PrevYear'),
        ("J", "M", "Biggest week (bn SAR)", "=BiggestWeek/1000000", "#,##0.00",
         '=TEXT(BiggestDate, "d mmm")&IF(BiggestPhase="", "", ", "&BiggestPhase)'),
    ]
    for a, b, label, value, number_format, note in kpis:
        for r in (6, 7, 8):
            ws.merge_cells(f"{a}{r}:{b}{r}")
        put(f"{a}6", label, font(9, colour=INK2), align=left)
        put(f"{a}7", value, font(22), number_format, left)
        put(f"{a}8", note, font(9, colour=MUTED), align=left)
        cols = range(ws[f"{a}6"].column, ws[f"{b}6"].column + 1)
        for r in (6, 7, 8):
            for col in cols:
                c = ws.cell(row=r, column=col)
                c.fill = fill("FFFFFF")
                c.border = Border(left=THIN if col == cols[0] else None, right=THIN if col == cols[-1] else None,
                                  top=THIN if r == 6 else None, bottom=THIN if r == 8 else None)
    ws.row_dimensions[7].height = 34

    # Weekly chart (left) and the Ramadan box (right)
    put("B10", "Weekly spending, billion SAR", font(12, bold=True))
    put("B11", '="Columns: "&SelYear&", by week type. Dashed line: the same week of "&PrevYear&"."',
        font(9, colour=INK2))
    # The legend is text in a cell: Excel's own legend took space from a small chart and covered the axis.
    parts = []
    for week_type in ["Normal", "Part Ramadan", "Full Ramadan", "Eid"]:
        parts += [TextBlock(InlineFont(rFont=FONT, sz=9, color=WEEK_COLOURS[week_type]), "■ "),
                  TextBlock(InlineFont(rFont=FONT, sz=9, color=INK2), f"{week_type}    ")]
    parts += [TextBlock(InlineFont(rFont=FONT, sz=9, color=YEAR_BEFORE), "- - "),
              TextBlock(InlineFont(rFont=FONT, sz=9, color=INK2), "Year before")]
    ws["B12"] = CellRichText(*parts)
    calc_ws = wb["Calc"]
    bars = BarChart()
    bars.type, bars.grouping, bars.overlap, bars.gapWidth = "col", "stacked", 100, 40
    series_names = ["ChartNormal", "ChartPart", "ChartFull", "ChartEid"]
    for k, week_type in enumerate(["Normal", "Part Ramadan", "Full Ramadan", "Eid"]):
        bars.add_data(Reference(calc_ws, min_col=8 + k, min_row=weekly_first - 1, max_row=weekly_last), titles_from_data=True)
        s = bars.series[-1]
        s.graphicalProperties.solidFill = WEEK_COLOURS[week_type]
        s.graphicalProperties.line.noFill = True
    line = LineChart()
    line.add_data(Reference(calc_ws, min_col=12, min_row=weekly_first - 1, max_row=weekly_last), titles_from_data=True)
    s = line.series[0]
    s.graphicalProperties.line.solidFill = YEAR_BEFORE
    s.graphicalProperties.line.dashStyle = "dash"
    s.graphicalProperties.line.width = 19050  # 1.5 pt, in EMU
    s.smooth = False
    s.marker.symbol = "none"
    # The series point at names that grow and shrink with the year (27 weeks for 2025, 53 for 2023), so the
    # chart has no empty weeks at the end of a part year. The names are defined on the Calc sheet.
    for s, name in zip(list(bars.series) + [line.series[0]], series_names + ["ChartBefore"]):
        s.val = NumDataSource(numRef=NumRef(f=f"Calc!{name}"))
        s.cat = AxDataSource(strRef=StrRef(f="Calc!ChartLabels"))
    bars += line
    bars.legend = None
    bars.y_axis.numFmt = "0"
    bars.y_axis.majorGridlines = None
    bars.x_axis.tickLblSkip = 1  # the labels are month names on each month's first week, blank on the others
    bars.x_axis.tickMarkSkip = 1
    bars.x_axis.delete = False  # openpyxl 3.1 hides axes unless told
    bars.y_axis.delete = False
    # cm; columns B to F are about 515 px (13.6 cm) wide, so the chart stays clear of the Ramadan box in H
    bars.height, bars.width = 8.0, 13.4
    ws.add_chart(bars, "B13")

    put("H10", "Ramadan and Eid, national", font(12, bold=True))
    put("H11", '="Ramadan "&SelYear&". The 8 weeks before it can start in the year before."', font(9, colour=INK2))
    put("K13", "bn SAR", font(9, colour=INK2), align=right)
    put("L13", "Change", font(9, colour=INK2), align=right)
    rows = [("Average week, the 8 weeks before Ramadan", "=RamBefore/1000000", None),
            ("Last full week of Ramadan", "=RamLast/1000000", "=RamLift"),
            ("Eid al-Fitr week", "=RamEid/1000000", "=RamEidDrop")]
    for i, (label, value, change) in enumerate(rows, start=14):
        ws.merge_cells(f"H{i}:J{i}")
        put(f"H{i}", label, font(10), align=left)
        put(f"K{i}", value, font(10, bold=True), "#,##0.00", right)
        if change:
            put(f"L{i}", change, font(10, bold=True), PLUS, right)
    put("H17", "Changes: the last full week against the 8 weeks before; the Eid week against the last full week.",
        font(8, colour=MUTED))
    put("H19", "Biggest rise in the last full week, by sector", font(10, bold=True))
    for k in range(1, 4):
        r = 19 + k
        ws.merge_cells(f"H{r}:J{r}")
        put(f"H{r}", f"=INDEX(SectorName, MATCH(LARGE(SectorLiftKey, {k}), SectorLiftKey, 0))", align=left)
        put(f"K{r}", f"=INDEX(SectorLift, MATCH(LARGE(SectorLiftKey, {k}), SectorLiftKey, 0))", font(10, bold=True), PLUS, right)
    put("H23", "Biggest fall", font(10, bold=True))
    ws.merge_cells("H24:J24")
    put("H24", "=INDEX(SectorName, MATCH(SMALL(SectorLiftKey, 1), SectorLiftKey, 0))", align=left)
    put("K24", "=INDEX(SectorLift, MATCH(SMALL(SectorLiftKey, 1), SectorLiftKey, 0))", font(10, bold=True), PLUS, right)
    ws.merge_cells("H26:M28")
    put("H26", "What to plan: stock, staff and offers ready for the last full week of Ramadan, above all in clothing "
               "and jewelry. The Eid week itself is quieter: in every year from 2021 to 2025 it fell against the week before.",
        font(9, colour=INK), align=wrap)

    # Cities, ranked by growth (left)
    put("B30", "Cities, ranked by growth", font(12, bold=True))
    put("B31", '="Growth on the same weeks a year before. National "&TEXT(NatGrowth, "+0.0%;\\−0.0%")&". Khobar and Dammam in bold."',
        font(9, colour=INK2))
    heads = [("B", "City", left), ("C", "Spent (bn SAR)", right), ("D", "Growth", right),
             ("E", "Share", right), ("F", "Avg payment", right)]
    for col, head, al in heads:
        c = put(f"{col}33", head, font(9, bold=True, colour=INK2), align=al)
        c.border = LINE_UNDER
    pick = "MATCH(LARGE(CityKey, {k}), CityKey, 0)"
    for k in range(1, n_cities + 1):
        r = 33 + k
        put(f"B{r}", f"=INDEX(CityName, {pick.format(k=k)})", align=left)
        put(f"C{r}", f"=INDEX(CitySpent, {pick.format(k=k)})/1000000", number_format="#,##0.00", align=right)
        put(f"D{r}", f"=INDEX(CityGrowth, {pick.format(k=k)})", number_format=PLUS, align=right)
        put(f"E{r}", f"=INDEX(CityShare, {pick.format(k=k)})", number_format="0.0%", align=right)
        put(f"F{r}", f"=INDEX(CityAvgPay, {pick.format(k=k)})", number_format="#,##0.0", align=right)
    city_rows = f"B34:F{33 + n_cities}"
    ws.conditional_formatting.add(city_rows, FormulaRule(formula=['OR($B34="Khobar",$B34="Dammam")'],
                                                         font=Font(name=FONT, bold=True, color=INK)))
    ws.conditional_formatting.add(f"C34:C{33 + n_cities}", DataBarRule(start_type="num", start_value=0, end_type="max",
                                                                       color="C9D1DA", showValue=True))

    # Sectors, largest first (right)
    put("H30", "Sectors, largest first", font(12, bold=True))
    put("H31", "Growth on the same weeks a year before. Change: of the average payment.", font(9, colour=INK2))
    heads = [("H", "Sector", left), ("I", "Spent (bn)", right), ("J", "Spending", right), ("K", "Payments", right),
             ("L", "Avg payment", right), ("M", "Change", right)]
    for col, head, al in heads:
        c = put(f"{col}33", head, font(9, bold=True, colour=INK2), align=al)
        c.border = LINE_UNDER
    pick = "MATCH(LARGE(SectorKey, {k}), SectorKey, 0)"
    for k in range(1, n_sectors + 1):
        r = 33 + k
        put(f"H{r}", f"=INDEX(SectorName, {pick.format(k=k)})", align=left)
        put(f"I{r}", f"=INDEX(SectorSpent, {pick.format(k=k)})/1000000", number_format="#,##0.00", align=right)
        put(f"J{r}", f"=INDEX(SectorGrowth, {pick.format(k=k)})", number_format=PLUS, align=right)
        put(f"K{r}", f"=INDEX(SectorPayGrowth, {pick.format(k=k)})", number_format=PLUS, align=right)
        put(f"L{r}", f"=INDEX(SectorAvgPay, {pick.format(k=k)})", number_format="#,##0.0", align=right)
        put(f"M{r}", f"=INDEX(SectorAvgPayChange, {pick.format(k=k)})", number_format=PLUS, align=right)
    total = 34 + n_sectors
    for col, value, number_format in [("H", "All sectors", None), ("I", "=NatSpent/1000000", "#,##0.00"),
                                      ("J", "=NatGrowth", PLUS), ("K", "=NatPaySame/NatPayPrev-1", PLUS),
                                      ("L", "=NatAvgPay", "0.0"), ("M", "=NatAvgPayChange", PLUS)]:
        c = put(f"{col}{total}", value, font(10, bold=True), number_format, left if col == "H" else right)
        c.border = Border(top=Side(style="thin", color=INK2))
    ws.conditional_formatting.add(f"I34:I{33 + n_sectors}", DataBarRule(start_type="num", start_value=0, end_type="max",
                                                                        color="C9D1DA", showValue=True))

    # Notes under the cities
    notes = ("Spending: the value of card payments at shop terminals, in Saudi riyals. It leaves out cash and online "
             "shopping, and its growth mixes real spending, prices and the move from cash to cards.\n"
             "Same weeks: each week against the week with the same number a year before; weeks found in only one "
             "of the two years are left out, so a part year is compared with the same part.\n"
             "Average payment: total spent divided by the number of payments.\n"
             "The source gives sectors for the whole country only, never inside one city. \"Other cities\" holds "
             "every city it does not name.")
    top_notes = 35 + n_cities
    ws.merge_cells(f"B{top_notes}:F{top_notes + 9}")
    put(f"B{top_notes}", notes, font(8, colour=MUTED), align=wrap)

    # One landscape A4 page
    ws.print_area = f"A1:N{max(total, top_notes + 9) + 1}"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 1
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_options.horizontalCentered = True
    ws.page_margins.left = ws.page_margins.right = 0.4
    ws.page_margins.top = ws.page_margins.bottom = 0.5


def about_sheet(wb, n_rows):
    ws = wb.create_sheet("About")
    ws.column_dimensions["A"].width = 2
    ws.column_dimensions["B"].width = 26
    ws.column_dimensions["C"].width = 100
    lines = [
        ("About this workbook", None),
        ("", None),
        ("How to use it", "Pick a year in the yellow cell on the Report sheet (2022 to 2025). Every number, table and "
                          "the chart follow it. The Report sheet prints on one landscape A4 page."),
        ("Report", "The page for the manager: four headline numbers, the weekly chart, Ramadan and Eid, cities ranked "
                   "by growth and sectors by size."),
        ("Calc", "Every figure worked out with ordinary formulas (SUMIFS, MAXIFS, AVERAGEIFS, INDEX/MATCH, LARGE). "
                 "The Report sheet only points here, so each number can be traced to one formula."),
        ("Data", f"{n_rows:,} rows: one row per week for the country, each of the 11 cities and each of the 17 "
                 "sectors (10 May 2020 to 12 Jul 2025). Spent is in thousand SAR, payments in thousands."),
        ("", None),
        ("Spending", "The value of card payments at shop terminals, in Saudi riyals."),
        ("Payment", "One card payment at a shop terminal."),
        ("Average payment", "Spending divided by the number of payments."),
        ("Same weeks", "Each week against the week with the same number a year before. Weeks found in only one of "
                       "the two years are left out, so a part year (2025 so far) is compared with the same part."),
        ("Last full week of Ramadan", "The last Sunday-to-Saturday week with all 7 days in Ramadan."),
        ("Week type", "Full Ramadan: all 7 days in Ramadan. Part Ramadan: some of them. Eid: a week that holds an "
                      "Eid day. Normal: no day of Ramadan and no Eid."),
        ("", None),
        ("Source", "SAMA weekly point-of-sale statistics, via the KAPSARC data portal. 270 weeks, 10 May 2020 to "
                   "12 Jul 2025. Ramadan and Eid dates: the Umm al-Qura calendar."),
        ("What it leaves out", "Cash and online shopping. Growth mixes real spending, prices and the move from cash "
                               "to cards."),
        ("Cities and sectors", "The source gives sectors for the whole country only, never inside one city. \"Other "
                               "cities\" holds every city it does not name, including Eastern Province cities such "
                               "as Al-Ahsa and Jubail."),
        ("Built by", "pipeline/excel_report.py in the project repository, from the same files as the Power BI "
                     "dashboard, so the two show the same numbers."),
    ]
    for i, (term, text) in enumerate(lines, start=1):
        a = ws.cell(row=i, column=2, value=term)
        a.font = font(16, bold=True) if i == 1 else font(10, bold=True)
        a.alignment = Alignment(vertical="top")
        if text:
            b = ws.cell(row=i, column=3, value=text)
            b.font = font(10, colour=INK2)
            b.alignment = Alignment(wrap_text=True, vertical="top")
            # Excel does not grow a row to fit wrapped text when it opens a file, so set the height:
            # about 105 characters per line in the 100-wide column, 14 points per line
            ws.row_dimensions[i].height = 14 * (len(text) // 105 + 1) + 2
    ws.sheet_view.showGridLines = False


def main():
    rows, cities, sectors = read_data()
    wb = Workbook()
    wb.active.title = "Report"
    n_rows = data_sheet(wb, rows)
    weekly_first, weekly_last = calc_sheet(wb, cities, sectors)
    report_sheet(wb, weekly_first, weekly_last, len(cities), len(sectors))
    about_sheet(wb, n_rows)
    wb.move_sheet("About", offset=-2)  # Report, About, Data, Calc
    # openpyxl writes formulas without their results; this tells Excel to calculate everything on opening.
    wb.calculation.fullCalcOnLoad = True
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUTPUT)
    print(f"{OUTPUT.relative_to(PROJECT_FOLDER)}: {n_rows:,} data rows, {len(cities)} cities, {len(sectors)} sectors")


if __name__ == "__main__":
    main()
