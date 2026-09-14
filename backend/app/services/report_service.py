"""
Orchestrates: CSV parse → calculation → Excel generation → DB save.

Three upload scenarios (spec):
  SCENARIO 1 — MORNING only:
    Parse morning CSV → calculate → save MorningSnapshot → generate Excel
    (EOD columns = N/A in Excel)

  SCENARIO 2 — EOD only:
    Parse EOD CSV → calculate → look up saved MorningSnapshot for same sprint+date
    If found → compute movement → Excel with both columns
    If not found → Excel with Morning columns = N/A

  SCENARIO 3 — MORNING + EOD together:
    Parse both → calculate both → compute movement → Excel with both columns
    Also persists/updates the MorningSnapshot for this sprint+date
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from app.calculations.engine import SprintCalculationEngine, SprintCalculationResult
from app.calculations.qa import QACalculationEngine, QAResult
from app.calculations.morning_eod import (
    compute_movement,
    SprintMovementResult,
    DeveloperMovement,
)
from app.config import settings
from app.datasources.csv_source import JiraCSVDataSource, CSVValidationError
from app.models.developer import Developer
from app.models.morning_snapshot import MorningSnapshot
from app.models.report import Report
from app.models.settings_model import AppSetting
from app.models.snapshot import Sprint, Snapshot, IssueSnapshot, DeveloperMetric, QAMetric
from app.services.excel_service import ExcelService

logger = logging.getLogger(__name__)


class ReportService:
    def __init__(self, db: Session):
        self.db = db
        self.csv_source = JiraCSVDataSource()
        self.excel_service = ExcelService()

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def process_upload(
        self,
        file_path: str,
        snapshot_type: str = "EOD",          # "MORNING" | "EOD"
        morning_file_path: Optional[str] = None,  # legacy: both files at once
        report_date: Optional[str] = None,
        day1_fixed_scope: Optional[float] = None,
        sprint_start: Optional[str] = None,
        sprint_end: Optional[str] = None,
        original_filename: Optional[str] = None,
    ) -> dict:
        """
        Entry point for all upload scenarios.
        snapshot_type = "MORNING"  → Scenario 1
        snapshot_type = "EOD"      → Scenario 2 (auto-lookup morning) or
                                     Scenario 3 (morning_file_path supplied)
        """
        if report_date is None:
            report_date = datetime.now().strftime("%d/%m/%Y")

        team = self._get_team()
        completed_statuses = self._get_completed_statuses()
        developer_order = self._get_developer_order()
        engine = SprintCalculationEngine(team, completed_statuses)

        # ── Parse the primary (EOD / morning-only) file ──────────────────
        rows_primary, detected_cols, parse_warnings = self.csv_source.parse(file_path)
        primary_result = engine.calculate(rows_primary, detected_cols)
        primary_qa = QACalculationEngine(self._get_qa_completed_statuses()).calculate(rows_primary, detected_cols)
        sprint_label = primary_result.sprint_name or "Sprint"
        sprint_id = primary_result.sprint_id
        sprint_start = primary_result.sprint_start or sprint_start or self._get_setting_str("sprint_start")
        sprint_end = primary_result.sprint_end or sprint_end or self._get_setting_str("sprint_end")
        sprint_key = self._sprint_key(sprint_label, sprint_id, sprint_start)
        if day1_fixed_scope is None:
            day1_fixed_scope = self._get_sprint_baseline(sprint_key)
        elif day1_fixed_scope >= 0:
            self._save_sprint_baseline(sprint_key, day1_fixed_scope)

        extra_warnings: List[str] = list(parse_warnings)
        self._persist_snapshot(
            sprint_key=self._snapshot_sprint_key(sprint_label, sprint_id, sprint_start),
            sprint_label=sprint_label,
            sprint_id=sprint_id,
            sprint_start=sprint_start,
            sprint_end=sprint_end,
            report_date=report_date,
            snapshot_type=snapshot_type,
            result=primary_result,
            qa_result=primary_qa,
            rows=rows_primary,
            developer_order=developer_order,
            day1_fixed_scope=day1_fixed_scope,
        )

        # ================================================================
        # SCENARIO 1 — MORNING only
        # ================================================================
        if snapshot_type == "MORNING":
            morning_result = primary_result
            eod_result = None

            # Persist the morning snapshot (upsert by sprint + date)
            self._save_morning_snapshot(
                sprint=sprint_label,
                report_date=report_date,
                result=morning_result,
                developer_order=developer_order,
                original_filename=original_filename,
                sprint_id=sprint_id,
                sprint_start=sprint_start,
                sprint_end=sprint_end,
                day1_fixed_scope=day1_fixed_scope,
            )
            extra_warnings.append(
                f"✓ Morning snapshot saved for {sprint_label} on {report_date}. "
                "Upload EOD CSV later today to generate the full Morning vs EOD report."
            )

            movement = _morning_only_movement(
                morning_result, developer_order, day1_fixed_scope
            )

            excel_filename, excel_path = self._excel_path(sprint_label, sprint_id, report_date)
            self.excel_service.generate(
                movement=movement,
                eod_result=morning_result,          # used for story counts / scope
                morning_result=morning_result,       # show morning columns populated
                report_date=report_date,
                sprint_label=sprint_label,
                output_path=excel_path,
                day1_fixed_scope=day1_fixed_scope,
                sprint_start=sprint_start,
                sprint_end=sprint_end,
                developer_order=developer_order,
                scenario="MORNING",
                qa_result=primary_qa,
            )

            report = self._save_report(
                excel_filename=excel_filename,
                excel_path=excel_path,
                sprint_label=sprint_label,
                report_date=report_date,
                snapshot_type="MORNING",
                result=morning_result,
                developer_order=developer_order,
                warnings=morning_result.warnings + extra_warnings,
                completion_percentage=movement.morning_pct,
                sprint_id=sprint_id,
                sprint_start=sprint_start,
                sprint_end=sprint_end,
                day1_fixed_scope=day1_fixed_scope,
            )

            return self._build_response(
                report=report,
                eod_result=morning_result,
                morning_result=morning_result,
                movement=movement,
                extra_warnings=extra_warnings,
                day1_fixed_scope=day1_fixed_scope,
                sprint_start=sprint_start,
                developer_order=developer_order,
                scenario="MORNING",
            )

        # ================================================================
        # SCENARIO 2 & 3 — EOD (with or without morning)
        # ================================================================
        eod_result = primary_result
        morning_result: Optional[SprintCalculationResult] = None
        morning_source = "none"

        # Scenario 3: morning file supplied directly
        if morning_file_path and os.path.exists(morning_file_path):
            rows_morning, _, _ = self.csv_source.parse(morning_file_path)
            morning_result = engine.calculate(rows_morning, detected_cols)
            morning_qa = QACalculationEngine(self._get_qa_completed_statuses()).calculate(rows_morning, detected_cols)
            morning_source = "uploaded"
            self._persist_snapshot(
                sprint_key=self._snapshot_sprint_key(sprint_label, sprint_id, sprint_start),
                sprint_label=sprint_label,
                sprint_id=sprint_id,
                sprint_start=sprint_start,
                sprint_end=sprint_end,
                report_date=report_date,
                snapshot_type="MORNING",
                result=morning_result,
                qa_result=morning_qa,
                rows=rows_morning,
                developer_order=developer_order,
                day1_fixed_scope=day1_fixed_scope,
            )

            # Same-file warning (spec §22)
            if (
                eod_result.total_scope == morning_result.total_scope
                and eod_result.total_completed_sp == morning_result.total_completed_sp
                and eod_result.total_stories == morning_result.total_stories
            ):
                extra_warnings.append(
                    "⚠ Morning and EOD snapshots appear to be the same file. "
                    "Movement may be 0 because both snapshots contain identical data."
                )

            # Persist/update morning snapshot
            self._save_morning_snapshot(
                sprint=sprint_label,
                report_date=report_date,
                result=morning_result,
                developer_order=developer_order,
                original_filename=None,
                sprint_id=sprint_id,
                sprint_start=sprint_start,
                sprint_end=sprint_end,
                day1_fixed_scope=day1_fixed_scope,
            )

        # Scenario 2: auto-lookup saved morning snapshot
        if morning_result is None:
            morning_result = self._load_morning_snapshot(
                sprint=sprint_label,
                report_date=report_date,
                developer_order=developer_order,
            )
            if morning_result is not None:
                morning_source = "saved"
                extra_warnings.append(
                    f"ℹ Automatically matched saved Morning snapshot for "
                    f"{sprint_label} on {report_date}."
                )

        if morning_result is None:
            extra_warnings.append(
                "ℹ No Morning snapshot found for this sprint/date. "
                "Morning columns will show N/A. "
                "Upload Morning CSV first to enable Morning vs EOD comparison."
            )

        movement = compute_movement(
            morning_result,
            eod_result,
            day1_fixed_scope=day1_fixed_scope,
        )

        excel_filename, excel_path = self._excel_path(sprint_label, sprint_id, report_date)
        self.excel_service.generate(
            movement=movement,
            eod_result=eod_result,
            morning_result=morning_result,
            report_date=report_date,
            sprint_label=sprint_label,
            output_path=excel_path,
            day1_fixed_scope=day1_fixed_scope,
            sprint_start=sprint_start,
            sprint_end=sprint_end,
            developer_order=developer_order,
            scenario="EOD",
            qa_result=primary_qa,
        )

        report = self._save_report(
            excel_filename=excel_filename,
            excel_path=excel_path,
            sprint_label=sprint_label,
            report_date=report_date,
            snapshot_type="EOD",
            result=eod_result,
            developer_order=developer_order,
            warnings=eod_result.warnings + extra_warnings,
            completion_percentage=movement.eod_pct,
            sprint_id=sprint_id,
            sprint_start=sprint_start,
            sprint_end=sprint_end,
            day1_fixed_scope=day1_fixed_scope,
        )

        return self._build_response(
            report=report,
            eod_result=eod_result,
            morning_result=morning_result,
            movement=movement,
            extra_warnings=extra_warnings,
            day1_fixed_scope=day1_fixed_scope,
            sprint_start=sprint_start,
            developer_order=developer_order,
            scenario="EOD",
            morning_source=morning_source,
            qa_result=primary_qa,
        )

    def validate_csv(self, file_path: str) -> dict:
        """Validate CSV without generating a report."""
        try:
            rows, detected_cols, warnings = self.csv_source.parse(file_path)
            team = self._get_team()
            completed_statuses = self._get_completed_statuses()
            engine = SprintCalculationEngine(team, completed_statuses)
            result = engine.calculate(rows, detected_cols)
            return {
                "valid": True,
                "total_rows": len(rows),
                "total_stories": result.total_stories,
                "detected_columns": detected_cols,
                "sprint": result.sprint_name,
                "warnings": result.warnings + warnings,
                "summary": {
                    "total_scope": result.total_scope,
                    "completed_sp": result.total_completed_sp,
                    "completion_pct": result.overall_completion_pct,
                },
            }
        except CSVValidationError as exc:
            return {"valid": False, "error": str(exc), "warnings": []}

    def get_morning_snapshots(self) -> list:
        """Return list of saved morning snapshots (for UI display)."""
        rows = (
            self.db.query(MorningSnapshot)
            .order_by(MorningSnapshot.created_at.desc())
            .all()
        )
        return [
            {
                "id": r.id,
                "sprint": r.sprint,
                "report_date": r.report_date,
                "total_scope": r.total_scope,
                "completed_sp": r.completed_sp,
                "completion_pct": r.completion_pct,
                "created_at": r.created_at,
            }
            for r in rows
        ]

    def delete_morning_snapshot(self, snapshot_id: int) -> bool:
        """Delete a saved morning snapshot record by id."""
        snapshot = self.db.query(MorningSnapshot).filter(MorningSnapshot.id == snapshot_id).first()
        if not snapshot:
            return False
        self.db.delete(snapshot)
        self.db.commit()
        return True

    # ------------------------------------------------------------------ #
    #  Morning snapshot persistence                                        #
    # ------------------------------------------------------------------ #

    def _save_morning_snapshot(
        self,
        sprint: str,
        report_date: str,
        result: SprintCalculationResult,
        developer_order: List[str],
        original_filename: Optional[str],
        sprint_id: Optional[str] = None,
        sprint_start: Optional[str] = None,
        sprint_end: Optional[str] = None,
        day1_fixed_scope: Optional[float] = None,
    ) -> MorningSnapshot:
        """Upsert morning snapshot by sprint + report_date."""
        existing = (
            self.db.query(MorningSnapshot)
            .filter_by(sprint=sprint, report_date=report_date)
            .first()
        )
        dev_data = self._dev_data_to_json(result, developer_order)

        if existing:
            existing.total_scope = result.total_scope
            existing.completed_sp = result.total_completed_sp
            existing.completion_pct = result.overall_completion_pct
            existing.developer_data = dev_data
            existing.data_quality_issues = result.data_quality_issues
            existing.sprint_id = sprint_id
            existing.sprint_start = sprint_start
            existing.sprint_end = sprint_end
            existing.day1_fixed_scope = day1_fixed_scope
            if original_filename:
                existing.original_filename = original_filename
            self.db.commit()
            logger.info("Morning snapshot updated: sprint=%s date=%s", sprint, report_date)
            return existing
        else:
            snap = MorningSnapshot(
                sprint=sprint,
                report_date=report_date,
                total_scope=result.total_scope,
                completed_sp=result.total_completed_sp,
                completion_pct=result.overall_completion_pct,
                developer_data=dev_data,
                data_quality_issues=result.data_quality_issues,
                sprint_id=sprint_id,
                sprint_start=sprint_start,
                sprint_end=sprint_end,
                day1_fixed_scope=day1_fixed_scope,
                original_filename=original_filename,
            )
            self.db.add(snap)
            self.db.commit()
            self.db.refresh(snap)
            logger.info("Morning snapshot saved: sprint=%s date=%s", sprint, report_date)
            return snap

    def _load_morning_snapshot(
        self,
        sprint: str,
        report_date: str,
        developer_order: List[str],
    ) -> Optional[SprintCalculationResult]:
        """
        Load a saved morning snapshot and reconstruct a SprintCalculationResult
        so it can be used in compute_movement() exactly like a freshly parsed result.
        """
        snap = (
            self.db.query(MorningSnapshot)
            .filter_by(sprint=sprint, report_date=report_date)
            .first()
        )
        if not snap:
            return None

        from app.calculations.engine import DeveloperStats
        result = SprintCalculationResult()
        result.sprint_name = snap.sprint
        result.total_scope = snap.total_scope
        result.total_completed_sp = snap.completed_sp
        result.total_remaining_sp = round(snap.total_scope - snap.completed_sp, 2)
        result.overall_completion_pct = snap.completion_pct
        result.sprint_id = snap.sprint_id
        result.sprint_start = snap.sprint_start
        result.sprint_end = snap.sprint_end
        result.data_quality_issues = snap.data_quality_issues or []

        dev_data = snap.developer_data or []
        for d in dev_data:
            stats = DeveloperStats(name=d["name"])
            stats.assigned_sp = d.get("assigned_sp", 0.0)
            stats.completed_sp = d.get("completed_sp", 0.0)
            result.developer_stats[d["name"]] = stats

        return result

    # ------------------------------------------------------------------ #
    #  DB helpers                                                          #
    # ------------------------------------------------------------------ #

    def _get_team(self) -> List[str]:
        devs = self.db.query(Developer).filter_by(is_active=True).all()
        return [d.name for d in devs]

    def _get_completed_statuses(self) -> List[str]:
        # Development completion is intentionally fixed to the Jira statuses
        # defined by the report specification.
        return ["Ready for QA", "QA Testing in Progress", "Done/ Live"]

    def _get_qa_completed_statuses(self) -> List[str]:
        return ["Done/ Live", "QA Testing Completed", "QA Done"]

    def _get_developer_order(self) -> List[str]:
        setting = self.db.query(AppSetting).filter_by(key="developer_order").first()
        if setting:
            try:
                return json.loads(setting.value)
            except Exception:
                pass
        return [
            "Raj Shinde", "Sriniwas Chamreddy", "Sunny Shankar",
            "Dinesh Babu", "Ayush Srivastava",
        ]

    def _get_setting_float(self, key: str) -> Optional[float]:
        row = self.db.query(AppSetting).filter_by(key=key).first()
        if not row or row.value in ("null", "", None):
            return None
        try:
            val = json.loads(row.value)
            return float(val) if val is not None else None
        except Exception:
            return None

    def _get_setting_str(self, key: str) -> Optional[str]:
        row = self.db.query(AppSetting).filter_by(key=key).first()
        if not row or row.value in ("null", "", None):
            return None
        try:
            val = json.loads(row.value)
            return str(val) if val is not None else None
        except Exception:
            return row.value

    @staticmethod
    def _sprint_key(
        sprint_label: str,
        sprint_id: Optional[str],
        sprint_start: Optional[str],
    ) -> str:
        identity = sprint_id or sprint_start or sprint_label
        return f"day1_fixed_scope::{re.sub(r'[^A-Za-z0-9_-]+', '_', identity)}"

    @staticmethod
    def _snapshot_sprint_key(
        sprint_label: str,
        sprint_id: Optional[str],
        sprint_start: Optional[str],
    ) -> str:
        identity = sprint_id or sprint_start or sprint_label
        return re.sub(r"[^A-Za-z0-9_-]+", "_", identity).strip("_") or "sprint"

    def _persist_snapshot(
        self,
        sprint_key: str,
        sprint_label: str,
        sprint_id: Optional[str],
        sprint_start: Optional[str],
        sprint_end: Optional[str],
        report_date: str,
        snapshot_type: str,
        result: SprintCalculationResult,
        qa_result: QAResult,
        rows: List[dict],
        developer_order: List[str],
        day1_fixed_scope: Optional[float],
    ) -> Snapshot:
        sprint = self.db.query(Sprint).filter_by(sprint_key=sprint_key).first()
        if sprint is None:
            sprint = Sprint(
                sprint_key=sprint_key,
                name=sprint_label,
                sprint_id=sprint_id,
                start_date=sprint_start,
                end_date=sprint_end,
                day1_fixed_scope=day1_fixed_scope,
            )
            self.db.add(sprint)
            self.db.flush()
        else:
            sprint.name = sprint_label
            sprint.sprint_id = sprint_id or sprint.sprint_id
            sprint.start_date = sprint_start or sprint.start_date
            sprint.end_date = sprint_end or sprint.end_date
            if sprint.day1_fixed_scope is None and day1_fixed_scope is not None:
                sprint.day1_fixed_scope = day1_fixed_scope

        snapshot = (
            self.db.query(Snapshot)
            .filter_by(sprint_id=sprint.id, snapshot_date=report_date, snapshot_type=snapshot_type)
            .first()
        )
        if snapshot is None:
            snapshot = Snapshot(sprint_id=sprint.id, snapshot_date=report_date, snapshot_type=snapshot_type)
            self.db.add(snapshot)
            self.db.flush()
        else:
            for collection in (snapshot.issues, snapshot.developer_metrics, snapshot.qa_metrics):
                for item in list(collection):
                    self.db.delete(item)
            self.db.flush()

        snapshot.overall_scope = result.total_scope
        snapshot.overall_completed = result.total_completed_sp
        snapshot.overall_remaining = result.total_remaining_sp
        snapshot.overall_completion = result.overall_completion_pct
        snapshot.day1_fixed_scope = day1_fixed_scope

        allocations_by_issue: dict[str, tuple[str, float]] = {}
        for allocation in result.allocations:
            if allocation.developer:
                previous = allocations_by_issue.get(allocation.issue_key)
                allocations_by_issue[allocation.issue_key] = (
                    allocation.developer,
                    round((previous[1] if previous else 0.0) + (allocation.sp or 0.0), 2),
                )
        qa_by_issue = {task.issue_key: task for task in qa_result.tasks}
        persisted_issue_keys: set[str] = set()
        for index, row in enumerate(rows):
            issue_key = SprintCalculationEngine._get(row, ["Issue key", "issue key", "Issue Key"]) or f"ROW_{index}"
            if issue_key in persisted_issue_keys:
                continue
            persisted_issue_keys.add(issue_key)
            status = SprintCalculationEngine._get(row, ["Status", "status"]) or ""
            story_points = SprintCalculationEngine._parse_sp(SprintCalculationEngine._story_point_value(row))
            allocation = allocations_by_issue.get(issue_key)
            qa_task = qa_by_issue.get(issue_key)
            self.db.add(IssueSnapshot(
                snapshot_id=snapshot.id,
                issue_key=issue_key,
                parent_key=SprintCalculationEngine._get(row, ["Parent", "Parent key", "Parent Issue Key"]),
                summary=SprintCalculationEngine._get(row, ["Summary", "summary"]),
                status=status,
                issue_type=SprintCalculationEngine._get(row, ["Issue Type", "Type"]),
                assignee=SprintCalculationEngine._get(row, ["Assignee", "assignee"]),
                developer_owner=allocation[0] if allocation else None,
                developer_sp=allocation[1] if allocation else None,
                qa_owner=qa_task.owner if qa_task else None,
                qa_sp=qa_task.story_points if qa_task else None,
                story_points=story_points,
                completed_sp=(story_points if story_points is not None and status.lower() in {s.lower() for s in self._get_completed_statuses()} else 0.0),
            ))
        for stats in result.ordered_developer_stats(developer_order):
            self.db.add(DeveloperMetric(
                snapshot_id=snapshot.id,
                developer_name=stats.name,
                assigned_sp=stats.assigned_sp,
                completed_sp=stats.completed_sp,
                remaining_sp=stats.remaining_sp,
                completion_pct=stats.completion_pct,
            ))
        for stats in qa_result.stats.values():
            self.db.add(QAMetric(
                snapshot_id=snapshot.id,
                qa_member=stats.name,
                assigned_sp=stats.assigned_sp,
                completed_sp=stats.completed_sp,
                remaining_sp=stats.remaining_sp,
                completion_pct=stats.completion_pct,
                task_count=stats.task_count,
                completed_task_count=stats.completed_task_count,
            ))
        self.db.commit()
        self.db.refresh(snapshot)
        return snapshot

    def _get_sprint_baseline(self, sprint_key: str) -> Optional[float]:
        return self._get_setting_float(sprint_key)

    def _save_sprint_baseline(self, sprint_key: str, value: float) -> None:
        setting = self.db.query(AppSetting).filter_by(key=sprint_key).first()
        serialized = json.dumps(round(value, 2))
        if setting:
            existing = self._get_setting_float(sprint_key)
            if existing is not None:
                return
            setting.value = serialized
        else:
            self.db.add(AppSetting(key=sprint_key, value=serialized))
        self.db.commit()

    # ------------------------------------------------------------------ #
    #  Excel / DB helpers                                                  #
    # ------------------------------------------------------------------ #

    def _excel_path(self, sprint_label: str, sprint_id: Optional[str], report_date: str):
        safe_sprint = re.sub(r"[^A-Za-z0-9]+", "_", sprint_label).strip("_") or "Sprint"
        sprint_token = f"_{sprint_id}" if sprint_id else ""
        try:
            report_token = datetime.strptime(report_date, "%d/%m/%Y").strftime("%Y-%m-%d")
        except ValueError:
            report_token = re.sub(r"[^A-Za-z0-9-]+", "-", report_date).strip("-")
        base_name = f"DC_AI_{safe_sprint}{sprint_token}_Report_{report_token}"
        excel_filename = f"{base_name}.xlsx"
        excel_path = os.path.join(settings.REPORT_STORAGE_PATH, excel_filename)
        suffix = 2
        while os.path.exists(excel_path):
            excel_filename = f"{base_name}_{suffix}.xlsx"
            excel_path = os.path.join(settings.REPORT_STORAGE_PATH, excel_filename)
            suffix += 1
        return excel_filename, excel_path

    def _save_report(
        self,
        excel_filename: str,
        excel_path: str,
        sprint_label: str,
        report_date: str,
        snapshot_type: str,
        result: SprintCalculationResult,
        developer_order: List[str],
        warnings: List[str],
        completion_percentage: Optional[float] = None,
        sprint_id: Optional[str] = None,
        sprint_start: Optional[str] = None,
        sprint_end: Optional[str] = None,
        day1_fixed_scope: Optional[float] = None,
    ) -> Report:
        report = Report(
            file_name=excel_filename,
            sprint=sprint_label,
            sprint_id=sprint_id,
            sprint_start=sprint_start,
            sprint_end=sprint_end,
            day1_fixed_scope=day1_fixed_scope,
            report_date=report_date,
            snapshot_type=snapshot_type,
            total_scope=result.total_scope,
            completed_sp=result.total_completed_sp,
            remaining_sp=result.total_remaining_sp,
            completion_percentage=(
                result.overall_completion_pct
                if completion_percentage is None
                else completion_percentage
            ),
            total_stories=result.total_stories,
            completed_stories=result.completed_stories,
            open_stories=result.open_stories,
            stories_without_sp=result.stories_without_sp,
            stories_without_dev=result.stories_without_dev,
            developer_data=self._dev_data_to_json(result, developer_order),
            warnings=warnings,
            data_quality_issues=result.data_quality_issues,
            file_path=excel_path,
        )
        self.db.add(report)
        self.db.commit()
        self.db.refresh(report)
        logger.info("Report saved: id=%d, file=%s", report.id, excel_filename)
        return report

    @staticmethod
    def _dev_data_to_json(result: SprintCalculationResult, order: List[str]) -> list:
        from app.calculations.engine import DeveloperStats
        ordered = []
        for name in order:
            ordered.append(result.developer_stats.get(name) or DeveloperStats(name=name))
        ordered.extend(
            stats for name, stats in result.developer_stats.items() if name not in order
        )
        return [
            {
                "name": s.name,
                "assigned_sp": s.assigned_sp,
                "completed_sp": s.completed_sp,
                "remaining_sp": s.remaining_sp,
                "completion_pct": s.completion_pct,
            }
            for s in ordered
        ]

    @staticmethod
    def _build_response(
        report: Report,
        eod_result: SprintCalculationResult,
        morning_result: Optional[SprintCalculationResult],
        movement: SprintMovementResult,
        extra_warnings: List[str],
        day1_fixed_scope: Optional[float],
        sprint_start: Optional[str],
        developer_order: List[str],
        scenario: str,
        morning_source: str = "none",
        qa_result: Optional[QAResult] = None,
    ) -> dict:
        has_morning = morning_result is not None

        devs = []
        for name in developer_order:
            eod_stats = eod_result.developer_stats.get(name)
            if eod_stats is None:
                from app.calculations.engine import DeveloperStats
                eod_stats = DeveloperStats(name=name)
            mov = movement.developer_movements.get(name)
            devs.append({
                "name": name,
                "assigned_sp": eod_stats.assigned_sp,
                "completed_sp": eod_stats.completed_sp,
                "remaining_sp": eod_stats.remaining_sp,
                "completion_pct": eod_stats.completion_pct,
                "morning_assigned": mov.morning_assigned if (mov and has_morning) else None,
                "morning_completed": mov.morning_completed if (mov and has_morning) else None,
                "morning_pct": mov.morning_pct if (mov and has_morning) else None,
                "movement_pct": mov.movement_pct if (mov and has_morning) else None,
            })
        # Any extra developers not in the fixed order
        for name, eod_stats in eod_result.developer_stats.items():
            if name not in developer_order:
                mov = movement.developer_movements.get(name)
                devs.append({
                    "name": name,
                    "assigned_sp": eod_stats.assigned_sp,
                    "completed_sp": eod_stats.completed_sp,
                    "remaining_sp": eod_stats.remaining_sp,
                    "completion_pct": eod_stats.completion_pct,
                    "morning_assigned": mov.morning_assigned if (mov and has_morning) else None,
                    "morning_completed": mov.morning_completed if (mov and has_morning) else None,
                    "morning_pct": mov.morning_pct if (mov and has_morning) else None,
                    "movement_pct": mov.movement_pct if (mov and has_morning) else None,
                })
        # A developer can exist only in the morning snapshot (for example
        # after ownership changes during the day). Keep that row visible in
        # the comparison instead of silently dropping it from the API.
        if has_morning:
            for name, mov in movement.developer_movements.items():
                if name not in {d["name"] for d in devs}:
                    devs.append({
                        "name": name,
                        "assigned_sp": mov.eod_assigned,
                        "completed_sp": mov.eod_completed,
                        "remaining_sp": max(0.0, mov.eod_assigned - mov.eod_completed),
                        "completion_pct": mov.eod_pct,
                        "morning_assigned": mov.morning_assigned,
                        "morning_completed": mov.morning_completed,
                        "morning_pct": mov.morning_pct,
                        "movement_pct": mov.movement_pct,
                    })

        data_quality_issues = report.data_quality_issues or eod_result.data_quality_issues or []
        qa_result = qa_result or QAResult()
        return {
            "report_id": report.id,
            "sprint": report.sprint,
            "sprint_id": report.sprint_id,
            "sprint_start": report.sprint_start,
            "sprint_end": report.sprint_end,
            "report_date": report.report_date,
            "day1_fixed_scope": report.day1_fixed_scope,
            "file_name": report.file_name,
            "snapshot_type": scenario,
            "morning_source": morning_source,   # "none" | "uploaded" | "saved"
            # Overall scope
            "total_scope": eod_result.total_scope,
            "completed_sp": eod_result.total_completed_sp,
            "remaining_sp": eod_result.total_remaining_sp,
            "completion_pct": movement.eod_pct,
            # Story counts
            "total_stories": eod_result.total_stories,
            "completed_stories": eod_result.completed_stories,
            "open_stories": eod_result.open_stories,
            "stories_without_sp": eod_result.stories_without_sp,
            "stories_without_dev": eod_result.stories_without_dev,
            # Morning/EOD comparison
            "has_morning": has_morning,
            "morning_scope": movement.morning_total_scope if has_morning else None,
            "morning_completed": movement.morning_completed if has_morning else None,
            "morning_pct": movement.morning_pct if has_morning else None,
            "daily_movement": movement.daily_movement if has_morning else None,
            # Baseline
            "day1_fixed_scope": day1_fixed_scope,
            "sprint_start": sprint_start,
            # Developer breakdown (ordered)
            "developers": devs,
            "warnings": eod_result.warnings + extra_warnings,
            "data_quality_issues": data_quality_issues,
            "qa": {
                "total_tasks": len(qa_result.tasks),
                "total_sp": qa_result.total_sp,
                "completed_sp": qa_result.completed_sp,
                "remaining_sp": qa_result.remaining_sp,
                "completion_pct": qa_result.completion_pct,
                "in_progress_tasks": sum(not task.is_completed for task in qa_result.tasks),
                "completed_tasks": sum(task.is_completed for task in qa_result.tasks),
                "members": [
                    {
                        "name": stats.name,
                        "assigned_sp": stats.assigned_sp,
                        "completed_sp": stats.completed_sp,
                        "remaining_sp": stats.remaining_sp,
                        "completion_pct": stats.completion_pct,
                        "task_count": stats.task_count,
                        "completed_task_count": stats.completed_task_count,
                    }
                    for stats in qa_result.stats.values()
                ],
                "tasks": [
                    {
                        "issue_key": task.issue_key,
                        "parent_key": task.parent_key,
                        "summary": task.summary,
                        "issue_type": task.issue_type,
                        "owner": task.owner,
                        "story_points": task.story_points,
                        "completed_sp": task.completed_sp,
                        "remaining_sp": task.remaining_sp,
                        "status": task.status,
                    }
                    for task in qa_result.tasks
                ],
            },
        }


# ------------------------------------------------------------------ #
#  Helpers                                                             #
# ------------------------------------------------------------------ #

def _morning_only_movement(
    morning_result: SprintCalculationResult,
    developer_order: List[str],
    day1_fixed_scope: Optional[float] = None,
) -> SprintMovementResult:
    """
    Build a SprintMovementResult for Scenario 1 (morning-only).
    Morning columns = actual values. EOD columns = same values (no EOD yet).
    The Excel generator uses scenario="MORNING" to render EOD columns as N/A.
    """
    result = SprintMovementResult()
    result.morning_total_scope = morning_result.total_scope
    result.morning_completed = morning_result.total_completed_sp
    denominator = morning_result.total_scope
    result.morning_pct = round(
        morning_result.total_completed_sp / denominator * 100, 2
    ) if denominator > 0 else 0.0
    # EOD mirrors morning (will be shown as N/A by Excel generator)
    result.eod_total_scope = morning_result.total_scope
    result.eod_completed = morning_result.total_completed_sp
    result.eod_pct = result.morning_pct
    result.scope_change = round(
        morning_result.total_scope - (day1_fixed_scope if day1_fixed_scope is not None else 0.0),
        2,
    )
    result.daily_movement = 0.0

    all_devs = list(morning_result.developer_stats.keys())
    for name in developer_order:
        if name not in all_devs:
            all_devs.append(name)

    for name in all_devs:
        m_stats = morning_result.developer_stats.get(name)
        if m_stats is None:
            from app.calculations.engine import DeveloperStats
            m_stats = DeveloperStats(name=name)
        mov = DeveloperMovement(
            name=name,
            morning_assigned=m_stats.assigned_sp,
            morning_completed=m_stats.completed_sp,
            morning_pct=m_stats.completion_pct,
            eod_assigned=m_stats.assigned_sp,
            eod_completed=m_stats.completed_sp,
            eod_pct=m_stats.completion_pct,
            movement_pct=0.0,
        )
        result.developer_movements[name] = mov

    return result
