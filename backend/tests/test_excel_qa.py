from pathlib import Path

from app.calculations.morning_eod import SprintMovementResult
from app.calculations.qa import QAResult, QAStats
from app.calculations.engine import SprintCalculationResult
from app.services.excel_service import ExcelService


def test_excel_appends_qa_section(tmp_path: Path):
    qa = QAResult(stats={"Harshit Raj": QAStats(name="Harshit Raj", assigned_sp=3, completed_sp=2)})
    output = tmp_path / "report.xlsx"
    ExcelService().generate(
        movement=SprintMovementResult(),
        eod_result=SprintCalculationResult(),
        morning_result=None,
        report_date="14/09/2026",
        sprint_label="Sprint 1",
        output_path=str(output),
        qa_result=qa,
    )
    from openpyxl import load_workbook
    worksheet = load_workbook(output, data_only=False).active
    assert worksheet["A23"].value == "3. QA Team Progress"
    assert worksheet["A25"].value == "Harshit Raj"