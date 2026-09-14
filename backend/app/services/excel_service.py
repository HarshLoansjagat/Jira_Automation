"""
Excel report generator using openpyxl.
Reproduces the EXACT reference image format for DC-AI Sprint Report.

Reference layout:
  Row 1  : Title (merged A:H, dark navy)
  Row 2  : empty
  Row 3  : Day-1 Fixed Scope (SP) | value
  Row 4  : Sprint Start | value
  Row 5  : empty
  Row 6  : Section 1 header (merged A:H, mid-blue)
  Row 7  : Column headers (Date | Update | Current Scope SP | Completed SP |
                           Scope Change SP | Completion % | Daily Movement | "")
  Row 8  : Morning row
  Row 9  : EOD row
  Row 10 : empty
  Row 11 : empty
  Row 12 : empty
  Row 13 : Section 2 header (merged A:H, mid-blue)
  Row 14 : Column headers (Developer | Morning Assigned SP | Morning Completed SP |
                           Morning % | EOD Assigned SP | EOD Completed SP | EOD % | Movement)
  Row 15+ : Developer rows (fixed order)
  Last   : Total Development Team (green)
"""
from __future__ import annotations

import logging
import os
from typing import List, Optional

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from app.calculations.engine import SprintCalculationResult
from app.calculations.morning_eod import SprintMovementResult
from app.calculations.qa import QAResult
from app.config import settings

logger = logging.getLogger(__name__)

# ── Exact colour palette from reference image ────────────────────────────────
DARK_NAVY   = "1F3864"   # title bar / column header bg  → white text
MID_BLUE    = "2E75B6"   # section header bg             → white text bold
LIGHT_BLUE  = "DEEAF1"   # developer row alternating tint
TOTAL_GREEN = "E2EFDA"   # Total Development Team row    → black bold
WHITE       = "FFFFFF"
BLACK       = "000000"
HEADER_BG   = "1F3864"   # same as DARK_NAVY


# ── Style helpers ────────────────────────────────────────────────────────────

def _font(bold=False, color=WHITE, size=11, italic=False):
    return Font(bold=bold, color=color, size=size, name="Calibri", italic=italic)


def _fill(hex_color: str) -> PatternFill:
    return PatternFill(fill_type="solid", fgColor=hex_color)


def _thin_border() -> Border:
    thin = Side(style="thin", color="AAAAAA")
    return Border(left=thin, right=thin, top=thin, bottom=thin)


def _center(wrap=False) -> Alignment:
    return Alignment(horizontal="center", vertical="center", wrap_text=wrap)


def _left(wrap=False) -> Alignment:
    return Alignment(horizontal="left", vertical="center", wrap_text=wrap)


def _right(wrap=False) -> Alignment:
    return Alignment(horizontal="right", vertical="center", wrap_text=wrap)


class ExcelService:
    """Generates the DC-AI Sprint Report Excel matching the reference image exactly."""

    # Fixed developer order (spec §11)
    DEVELOPER_ORDER: List[str] = [
        "Raj Shinde",
        "Sriniwas Chamreddy",
        "Sunny Shankar",
        "Dinesh Babu",
        "Ayush Srivastava",
    ]

    def generate(
        self,
        movement: SprintMovementResult,
        eod_result: SprintCalculationResult,
        morning_result: Optional[SprintCalculationResult],
        report_date: str,
        sprint_label: str,
        output_path: str,
        day1_fixed_scope: Optional[float] = None,
        sprint_start: Optional[str] = None,
        sprint_end: Optional[str] = None,
        developer_order: Optional[List[str]] = None,
        scenario: str = "EOD",  # "MORNING" | "EOD"
        qa_result: Optional[QAResult] = None,
    ) -> None:
        order = developer_order or self.DEVELOPER_ORDER
        template_path = getattr(settings, "REPORT_TEMPLATE_PATH", "")
        if not template_path:
            downloads = os.path.join(os.path.expanduser("~"), "Downloads")
            candidates = sorted(
                os.path.join(downloads, name)
                for name in os.listdir(downloads)
                if name.lower().startswith("dc_ai_sprint_")
                and name.lower().endswith(".xlsx")
            ) if os.path.isdir(downloads) else []
            template_path = candidates[0] if candidates else ""

        if os.path.exists(template_path):
            wb = load_workbook(template_path)
            ws = wb["Sprint Report"] if "Sprint Report" in wb.sheetnames else wb.active
        else:
            wb = Workbook()
            ws = wb.active
            ws.title = "Sprint Report"
            ws.page_setup.orientation = "landscape"
            ws.page_setup.fitToPage = True
            ws.page_setup.fitToWidth = 1
            ws.page_setup.fitToHeight = 0
            ws.sheet_properties.pageSetUpPr.fitToPage = True

        # Clear the complete report area before writing.  Templates may contain
        # an older copy of the development section; clearing only the data rows
        # leaves that stale heading visible in the generated workbook.
        for merged_range in list(ws.merged_cells.ranges):
            if (
                merged_range.min_col == 1
                and merged_range.max_col == 8
                and merged_range.min_row <= 40
                and merged_range.max_row >= 6
            ):
                ws.unmerge_cells(str(merged_range))
        for r in range(6, max(40, ws.max_row) + 1):
            for c in range(1, 9):
                ws.cell(row=r, column=c).value = None

        # Keep the loaded template layout intact and only populate the data cells.
        ws["A1"] = f"DC-AI {sprint_label} — {'MORNING Snapshot' if scenario == 'MORNING' else 'MORNING vs EOD Report' if (morning_result is not None or scenario == 'MORNING') else 'EOD Report'} | {report_date}"
        ws["A3"] = "Day-1 Fixed Scope (SP)"
        ws["B3"] = day1_fixed_scope if day1_fixed_scope is not None else "N/A"
        ws["A4"] = "Sprint Start"
        ws["B4"] = sprint_start if sprint_start else "N/A"
        ws["A5"] = "Sprint End"
        ws["B5"] = sprint_end if sprint_end else "N/A"

        # Ensure section titles are always present even when a template file is reused.
        ws.merge_cells("A6:H6")
        ws["A6"] = "1. Overall Sprint Progress"
        ws["A6"].font = _font(bold=True, size=12, color=WHITE)
        ws["A6"].fill = _fill(MID_BLUE)
        ws["A6"].alignment = _center()
        ws["A6"].border = _thin_border()

        has_morning = scenario == "MORNING" or morning_result is not None
        _fmt = lambda v: "N/A" if v is None else v

        # Section 1: overall progress rows
        row_idx = 7
        ws.cell(row=row_idx, column=1).value = "Date"
        ws.cell(row=row_idx, column=2).value = "Update"
        ws.cell(row=row_idx, column=3).value = "Current Scope (SP)"
        ws.cell(row=row_idx, column=4).value = "Completed SP"
        ws.cell(row=row_idx, column=5).value = "Scope Change (SP)"
        ws.cell(row=row_idx, column=6).value = "Completion %"
        ws.cell(row=row_idx, column=7).value = "Daily Movement"

        if has_morning:
            row_idx = 8
            ws[f"A{row_idx}"] = report_date
            ws[f"B{row_idx}"] = "Morning"
            ws[f"C{row_idx}"] = _fmt(movement.morning_total_scope)
            ws[f"D{row_idx}"] = _fmt(movement.morning_completed)
            ws[f"E{row_idx}"] = round((movement.morning_total_scope or 0) - (day1_fixed_scope or 0), 2) if day1_fixed_scope else "N/A"
            ws[f"F{row_idx}"] = f'=IFERROR(D{row_idx}/C{row_idx},"N/A")'
            ws[f"F{row_idx}"].number_format = "0.00%"
        else:
            row_idx = 8
            ws[f"A{row_idx}"] = report_date
            ws[f"B{row_idx}"] = "Morning"
            ws[f"C{row_idx}"] = "N/A"
            ws[f"D{row_idx}"] = "N/A"
            ws[f"E{row_idx}"] = "N/A"
            ws[f"F{row_idx}"] = "N/A"

        row_idx = 9
        ws[f"A{row_idx}"] = report_date
        ws[f"B{row_idx}"] = "EOD"
        ws[f"C{row_idx}"] = _fmt(movement.eod_total_scope)
        ws[f"D{row_idx}"] = _fmt(movement.eod_completed)
        ws[f"E{row_idx}"] = round((movement.eod_total_scope or 0) - (day1_fixed_scope or 0), 2) if day1_fixed_scope else "N/A"
        ws[f"F{row_idx}"] = f'=IFERROR(D{row_idx}/C{row_idx},"N/A")'
        ws[f"G{row_idx}"] = f'=IFERROR(F{row_idx}-F{row_idx - 1},"N/A")' if has_morning else "N/A"
        ws[f"F{row_idx}"].number_format = "0.00%"
        ws[f"G{row_idx}"].number_format = "0.00%"

        # Section 2: developer rows
        ws.merge_cells("A13:H13")
        ws["A13"] = "2. Development Team Progress — Morning vs EOD"
        ws["A13"].font = _font(bold=True, size=12, color=WHITE)
        ws["A13"].fill = _fill(MID_BLUE)
        ws["A13"].alignment = _center()
        ws["A13"].border = _thin_border()

        headers = [
            "Developer",
            "Morning Assigned SP",
            "Morning Completed SP",
            "Morning %",
            "EOD Assigned SP",
            "EOD Completed SP",
            "EOD %",
            "Movement",
        ]
        for col_idx, header in enumerate(headers, start=1):
            cell = ws.cell(row=14, column=col_idx)
            cell.value = header
            cell.font = _font(bold=True, color=WHITE, size=11)
            cell.fill = _fill(HEADER_BG)
            cell.alignment = _center(wrap=True)
            cell.border = _thin_border()

        start_row = 15
        for idx, name in enumerate(order, start=start_row):
            mov = movement.developer_movements.get(name)
            if mov is None:
                mov = type('DevPlaceholder', (), {
                    'morning_assigned': 0.0,
                    'morning_completed': 0.0,
                    'morning_pct': 0.0,
                    'eod_assigned': 0.0,
                    'eod_completed': 0.0,
                    'eod_pct': 0.0,
                    'movement_pct': 0.0,
                })()
            ws[f"A{idx}"] = name
            ws[f"B{idx}"] = round(mov.morning_assigned, 2) if has_morning else "N/A"
            ws[f"C{idx}"] = round(mov.morning_completed, 2) if has_morning else "N/A"
            if has_morning:
                ws[f"D{idx}"] = f'=IFERROR(C{idx}/B{idx},"N/A")'
                ws[f"D{idx}"].number_format = "0.00%"
            else:
                ws[f"D{idx}"] = "N/A"
            ws[f"E{idx}"] = round(mov.eod_assigned, 2)
            ws[f"F{idx}"] = round(mov.eod_completed, 2)
            ws[f"G{idx}"] = f'=IFERROR(F{idx}/E{idx},"N/A")'
            ws[f"H{idx}"] = f'=IFERROR(G{idx}-D{idx},"N/A")' if has_morning else "N/A"
            ws[f"G{idx}"].number_format = "0.00%"
            ws[f"H{idx}"].number_format = "0.00%"

        total_row = 20
        ws[f"A{total_row}"] = "Total Development Team"
        ws[f"B{total_row}"] = f"=SUM(B15:B19)" if has_morning else "N/A"
        ws[f"C{total_row}"] = f"=SUM(C15:C19)" if has_morning else "N/A"
        ws[f"D{total_row}"] = f'=IFERROR(C{total_row}/B{total_row},"N/A")' if has_morning else "N/A"
        ws[f"E{total_row}"] = "=SUM(E15:E19)"
        ws[f"F{total_row}"] = "=SUM(F15:F19)"
        ws[f"G{total_row}"] = '=IFERROR(F20/E20,"N/A")'
        ws[f"H{total_row}"] = '=IFERROR(G20-D20,"N/A")'
        for column in ("D", "G", "H"):
            ws[f"{column}{total_row}"].number_format = "0.00%"

        # Section 3 is appended below the established development layout so
        # existing Excel consumers and reference cells remain unchanged.
        qa_row = 23
        ws.merge_cells(f"A{qa_row}:H{qa_row}")
        ws[f"A{qa_row}"] = "3. QA Team Progress"
        ws[f"A{qa_row}"].font = _font(bold=True, size=12, color=WHITE)
        ws[f"A{qa_row}"].fill = _fill(MID_BLUE)
        ws[f"A{qa_row}"].alignment = _center()
        ws[f"A{qa_row}"].border = _thin_border()
        qa_headers = [
            "QA Member", "Morning Assigned QA SP", "Morning Completed QA SP",
            "Morning QA %", "EOD Assigned QA SP", "EOD Completed QA SP",
            "EOD QA %", "Movement",
        ]
        for col_idx, header in enumerate(qa_headers, start=1):
            cell = ws.cell(row=qa_row + 1, column=col_idx)
            cell.value = header
            cell.font = _font(bold=True, color=WHITE, size=10)
            cell.fill = _fill(HEADER_BG)
            cell.alignment = _center(wrap=True)
            cell.border = _thin_border()
        qa_stats = list((qa_result.stats if qa_result else {}).values())
        for index, stats in enumerate(qa_stats, start=qa_row + 2):
            ws.cell(index, 1).value = stats.name
            ws.cell(index, 2).value = "N/A"
            ws.cell(index, 3).value = "N/A"
            ws.cell(index, 4).value = "N/A"
            ws.cell(index, 5).value = round(stats.assigned_sp, 2)
            ws.cell(index, 6).value = round(stats.completed_sp, 2)
            ws.cell(index, 7).value = f'=IFERROR(F{index}/E{index},"N/A")'
            ws.cell(index, 8).value = "N/A"
            ws.cell(index, 7).number_format = "0.00%"
            for column in range(1, 9):
                ws.cell(index, column).border = _thin_border()
                ws.cell(index, column).alignment = _center(wrap=True)
        qa_total_row = qa_row + 2 + len(qa_stats)
        ws.cell(qa_total_row, 1).value = "Total QA Team"
        ws.cell(qa_total_row, 5).value = f"=SUM(E{qa_row + 2}:E{qa_total_row - 1})" if qa_stats else 0
        ws.cell(qa_total_row, 6).value = f"=SUM(F{qa_row + 2}:F{qa_total_row - 1})" if qa_stats else 0
        ws.cell(qa_total_row, 7).value = f'=IFERROR(F{qa_total_row}/E{qa_total_row},"N/A")'
        ws.cell(qa_total_row, 7).number_format = "0.00%"
        for column in range(1, 9):
            cell = ws.cell(qa_total_row, column)
            cell.fill = _fill(TOTAL_GREEN)
            cell.font = _font(bold=True, color=BLACK, size=10)
            cell.border = _thin_border()
            cell.alignment = _center(wrap=True)

        ws.freeze_panes = "A7"
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        # Keep formulas inspectable while asking Excel-compatible viewers to
        # recalculate them when the workbook is opened.
        wb.calculation.fullCalcOnLoad = True
        wb.calculation.forceFullCalc = True
        wb.calculation.calcMode = "auto"
        wb.save(output_path)
        logger.info("Excel saved: %s", output_path)

    # ── Title ─────────────────────────────────────────────────────────────────

    def _write_title(self, ws, row: int, text: str) -> None:
        ws.merge_cells(f"A{row}:H{row}")
        c = ws[f"A{row}"]
        c.value = text
        c.font = _font(bold=True, size=14, color=WHITE)
        c.fill = _fill(DARK_NAVY)
        c.alignment = _center()
        c.border = _thin_border()

    # ── Meta rows (Day-1 / Sprint Start) ──────────────────────────────────────

    def _write_meta_row(self, ws, row: int, label: str, value: str) -> None:
        lc = ws.cell(row=row, column=1)
        lc.value = label
        lc.font = _font(bold=True, color=BLACK, size=11)
        lc.alignment = _left()
        lc.border = _thin_border()

        vc = ws.cell(row=row, column=2)
        vc.value = value
        vc.font = _font(bold=False, color=BLACK, size=11)
        vc.alignment = _left()
        vc.border = _thin_border()

        # Fill remaining columns with border only (no fill — matching reference)
        for col in range(3, 9):
            c = ws.cell(row=row, column=col)
            c.border = _thin_border()

    # ── Section 1: Overall Sprint Progress ───────────────────────────────────

    def _section_overall(
        self,
        ws,
        row: int,
        movement: SprintMovementResult,
        report_date: str,
        has_morning: bool,
        day1_fixed_scope: Optional[float],
        show_eod: bool = True,
    ) -> int:
        # Section header
        ws.merge_cells(f"A{row}:H{row}")
        c = ws[f"A{row}"]
        c.value = "1. Overall Sprint Progress"
        c.font = _font(bold=True, size=12, color=WHITE)
        c.fill = _fill(MID_BLUE)
        c.alignment = _center()
        c.border = _thin_border()
        ws.row_dimensions[row].height = 22
        row += 1

        # Column headers
        headers = [
            "Date",
            "Update",
            "Current Scope (SP)",
            "Completed SP",
            "Scope\nChange (SP)",
            "Completion %",
            "Daily Movement",
            "",
        ]
        self._write_col_headers(ws, row, headers)
        ws.row_dimensions[row].height = 36
        row += 1

        def _sp(val) -> str:
            if val is None:
                return "N/A"
            return round(val, 2)

        def _pct(val) -> str:
            if val is None:
                return "N/A"
            return f"{val:.2f}%"

        # Scope change = Current Scope - Day-1 Fixed Scope (spec §15)
        def _scope_change(current_scope) -> str:
            if day1_fixed_scope is None or day1_fixed_scope == 0:
                return "N/A"
            return round(current_scope - day1_fixed_scope, 2)

        # ── Morning row ──────────────────────────────────────────────────
        if has_morning:
            m_scope_change = _scope_change(movement.morning_total_scope)
            self._write_data_row(ws, row, [
                report_date,
                "Morning",
                _sp(movement.morning_total_scope),
                _sp(movement.morning_completed),
                m_scope_change,
                _pct(movement.morning_pct),
                "",   # Daily movement not shown on morning row
                "",
            ], fill=WHITE)
        else:
            # EOD-only: morning row present but all N/A (template always has 2 rows)
            self._write_data_row(ws, row, [
                report_date, "Morning",
                "N/A", "N/A", "N/A", "N/A", "", "",
            ], fill=WHITE)
        ws.row_dimensions[row].height = 18
        row += 1

        # ── EOD row ──────────────────────────────────────────────────────
        if show_eod:
            eod_scope_change = _scope_change(movement.eod_total_scope)
            daily_mv = f"{movement.daily_movement:+.2f}%" if has_morning else "N/A"
            self._write_data_row(ws, row, [
                report_date,
                "EOD",
                _sp(movement.eod_total_scope),
                _sp(movement.eod_completed),
                eod_scope_change,
                _pct(movement.eod_pct),
                daily_mv,
                "",
            ], fill=WHITE)
        else:
            # Morning-only scenario: EOD row present but all N/A
            self._write_data_row(ws, row, [
                report_date, "EOD",
                "N/A", "N/A", "N/A", "N/A", "N/A", "",
            ], fill=WHITE)
        ws.row_dimensions[row].height = 18
        row += 1

        return row

    # ── Section 2: Development Team Progress ─────────────────────────────────

    def _section_developers(
        self,
        ws,
        row: int,
        movement: SprintMovementResult,
        has_morning: bool,
        order: List[str],
        show_eod: bool = True,
    ) -> int:
        # Section header
        ws.merge_cells(f"A{row}:H{row}")
        c = ws[f"A{row}"]
        c.value = "2. Development Team Progress — Morning vs EOD"
        c.font = _font(bold=True, size=12, color=WHITE)
        c.fill = _fill(MID_BLUE)
        c.alignment = _center()
        c.border = _thin_border()
        ws.row_dimensions[row].height = 22
        row += 1

        # Column headers — matching reference image exactly (wrapped)
        headers = [
            "Developer",
            "Morning\nAssigned SP",
            "Morning\nCompleted SP",
            "Morning %",
            "EOD\nAssigned SP",
            "EOD\nCompleted SP",
            "EOD %",
            "Movement",
        ]
        self._write_col_headers(ws, row, headers)
        ws.row_dimensions[row].height = 40
        row += 1

        # ── Developer rows in fixed order ────────────────────────────────
        # Only show developers in the defined order; extras go to end
        ordered_devs: List[str] = []
        for name in order:
            ordered_devs.append(name)
        for name in movement.developer_movements:
            if name not in ordered_devs:
                ordered_devs.append(name)

        # Totals accumulators
        total_m_assigned = 0.0
        total_m_completed = 0.0
        total_e_assigned = 0.0
        total_e_completed = 0.0

        alt = False
        for dev_name in ordered_devs:
            mov = movement.developer_movements.get(dev_name)
            if mov is None:
                # Developer in order list but no data — show zeros
                from app.calculations.morning_eod import DeveloperMovement
                mov = DeveloperMovement(name=dev_name)

            fill_color = LIGHT_BLUE if alt else WHITE
            alt = not alt

            m_assigned  = mov.morning_assigned  if has_morning else 0.0
            m_completed = mov.morning_completed if has_morning else 0.0
            m_pct       = f"{mov.morning_pct:.2f}%"  if has_morning else "N/A"
            mv_pct      = f"{mov.movement_pct:+.2f}%" if (has_morning and show_eod) else "N/A"

            eod_assigned  = round(mov.eod_assigned,  2) if show_eod else "N/A"
            eod_completed = round(mov.eod_completed, 2) if show_eod else "N/A"
            eod_pct       = f"{mov.eod_pct:.2f}%"       if show_eod else "N/A"

            self._write_data_row(ws, row, [
                dev_name,
                round(m_assigned,  2) if has_morning else "N/A",
                round(m_completed, 2) if has_morning else "N/A",
                m_pct,
                eod_assigned,
                eod_completed,
                eod_pct,
                mv_pct,
            ], fill=fill_color)
            ws.row_dimensions[row].height = 18
            row += 1

            total_m_assigned  += m_assigned
            total_m_completed += m_completed
            total_e_assigned  += mov.eod_assigned
            total_e_completed += mov.eod_completed

        # ── Total Development Team row (green) ───────────────────────────
        # spec §12: total % = sum(completed) / sum(assigned) — NOT average
        total_m_pct = (
            f"{round(total_m_completed / total_m_assigned * 100, 2):.2f}%"
            if (has_morning and total_m_assigned > 0)
            else "N/A"
        )
        if show_eod:
            total_e_pct = (
                f"{round(total_e_completed / total_e_assigned * 100, 2):.2f}%"
                if total_e_assigned > 0 else "0.00%"
            )
            if has_morning and total_m_assigned > 0 and total_e_assigned > 0:
                raw_m = total_m_completed / total_m_assigned * 100
                raw_e = total_e_completed / total_e_assigned * 100
                total_mv = f"{round(raw_e - raw_m, 2):+.2f}%"
            else:
                total_mv = "N/A"
            total_e_assigned_disp  = round(total_e_assigned,  2)
            total_e_completed_disp = round(total_e_completed, 2)
        else:
            total_e_pct            = "N/A"
            total_mv               = "N/A"
            total_e_assigned_disp  = "N/A"
            total_e_completed_disp = "N/A"

        self._write_total_row(ws, row, [
            "Total Development Team",
            round(total_m_assigned,  2) if has_morning else "N/A",
            round(total_m_completed, 2) if has_morning else "N/A",
            total_m_pct,
            total_e_assigned_disp,
            total_e_completed_disp,
            total_e_pct,
            total_mv,
        ])
        ws.row_dimensions[row].height = 20
        row += 1

        return row

    # ── Shared row writers ────────────────────────────────────────────────────

    def _write_col_headers(self, ws, row: int, headers: list) -> None:
        """Dark navy column header row — white bold text, centered with wrap."""
        for col_idx, header in enumerate(headers, start=1):
            c = ws.cell(row=row, column=col_idx)
            c.value = header
            c.font = _font(bold=True, size=10, color=WHITE)
            c.fill = _fill(DARK_NAVY)
            c.alignment = _center(wrap=True)
            c.border = _thin_border()

    def _write_data_row(self, ws, row: int, values: list, fill: str = WHITE) -> None:
        """Standard data row — black text, left-align col A, center rest."""
        for col_idx, val in enumerate(values, start=1):
            c = ws.cell(row=row, column=col_idx)
            c.value = val
            c.font = _font(bold=False, color=BLACK, size=10)
            c.fill = _fill(fill)
            c.border = _thin_border()
            c.alignment = _left() if col_idx == 1 else _center()

    def _write_total_row(self, ws, row: int, values: list) -> None:
        """Green total row — black bold text."""
        for col_idx, val in enumerate(values, start=1):
            c = ws.cell(row=row, column=col_idx)
            c.value = val
            c.font = _font(bold=True, color=BLACK, size=10)
            c.fill = _fill(TOTAL_GREEN)
            c.border = _thin_border()
            c.alignment = _left() if col_idx == 1 else _center()
