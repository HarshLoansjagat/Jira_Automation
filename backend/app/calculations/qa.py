"""Task-level QA classification and aggregation."""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Optional


@dataclass
class QATask:
    issue_key: str
    parent_key: Optional[str]
    summary: str
    issue_type: str
    owner: Optional[str]
    story_points: float
    completed_sp: float
    status: str
    is_completed: bool
    raw_row_index: int

    @property
    def remaining_sp(self) -> float:
        return max(0.0, self.story_points - self.completed_sp)


@dataclass
class QAStats:
    name: str
    assigned_sp: float = 0.0
    completed_sp: float = 0.0
    task_count: int = 0
    completed_task_count: int = 0

    @property
    def remaining_sp(self) -> float:
        return max(0.0, self.assigned_sp - self.completed_sp)

    @property
    def completion_pct(self) -> float:
        return round(self.completed_sp / self.assigned_sp * 100, 2) if self.assigned_sp else 0.0


@dataclass
class QAResult:
    tasks: list[QATask] = field(default_factory=list)
    stats: dict[str, QAStats] = field(default_factory=dict)
    total_sp: float = 0.0
    completed_sp: float = 0.0

    @property
    def remaining_sp(self) -> float:
        return max(0.0, self.total_sp - self.completed_sp)

    @property
    def completion_pct(self) -> float:
        return round(self.completed_sp / self.total_sp * 100, 2) if self.total_sp else 0.0


class QACalculationEngine:
    def __init__(self, completed_statuses: Optional[list[str]] = None):
        self.completed_statuses = {
            value.strip().lower()
            for value in (completed_statuses or ["Done/ Live", "QA Testing Completed", "QA Done"])
        }

    def calculate(self, rows: list[dict], detected_columns: list[str]) -> QAResult:
        result = QAResult()
        for index, row in enumerate(rows):
            if not self._is_qa_row(row):
                continue
            issue_key = self._value(row, "issue key", "issue") or f"ROW_{index}"
            status = self._value(row, "status") or ""
            raw_sp = self._qa_sp(row)
            if raw_sp is None:
                continue
            owner = self._value(row, "qa owner", "qa assignee", "assignee")
            task = QATask(
                issue_key=issue_key,
                parent_key=self._value(row, "parent", "parent key", "parent issue key"),
                summary=self._value(row, "summary") or "",
                issue_type=self._value(row, "issue type", "type") or "",
                owner=owner,
                story_points=raw_sp,
                completed_sp=raw_sp if status.lower() in self.completed_statuses else 0.0,
                status=status,
                is_completed=status.lower() in self.completed_statuses,
                raw_row_index=index,
            )
            result.tasks.append(task)
            result.total_sp += task.story_points
            result.completed_sp += task.completed_sp
            if owner:
                stats = result.stats.setdefault(owner, QAStats(name=owner))
                stats.assigned_sp += task.story_points
                stats.completed_sp += task.completed_sp
                stats.task_count += 1
                stats.completed_task_count += int(task.is_completed)
        result.total_sp = round(result.total_sp, 2)
        result.completed_sp = round(result.completed_sp, 2)
        for stats in result.stats.values():
            stats.assigned_sp = round(stats.assigned_sp, 2)
            stats.completed_sp = round(stats.completed_sp, 2)
        return result

    @classmethod
    def _is_qa_row(cls, row: dict) -> bool:
        values = " ".join(str(row.get(key, "")) for key in row)
        normalized = cls._normalize(values)
        keys = " ".join(cls._normalize(str(key)) for key in row)
        issue_type = cls._value(row, "issue type", "type") or ""
        return "qa" in normalized or "qa" in keys or "sub task" in cls._normalize(issue_type)

    @classmethod
    def _qa_sp(cls, row: dict) -> Optional[float]:
        for key, value in row.items():
            normalized = cls._normalize(str(key))
            if "qa" in normalized and ("point" in normalized or normalized.endswith(" sp")):
                parsed = cls._parse_sp(value)
                if parsed is not None:
                    return parsed
        if cls._is_explicit_qa_type(row):
            for key, value in row.items():
                normalized = cls._normalize(str(key))
                if "story point" in normalized or normalized.endswith(" sp"):
                    parsed = cls._parse_sp(value)
                    if parsed is not None:
                        return parsed
        return None

    @classmethod
    def _is_explicit_qa_type(cls, row: dict) -> bool:
        issue_type = cls._normalize(cls._value(row, "issue type", "type") or "")
        summary = cls._normalize(cls._value(row, "summary") or "")
        return (
            "qa" in issue_type
            or "sub task" in issue_type
            or summary.startswith("qa ")
            or summary.startswith("qa ")
        )

    @classmethod
    def _value(cls, row: dict, *names: str) -> Optional[str]:
        wanted = {cls._normalize(name) for name in names}
        for key, value in row.items():
            if cls._normalize(str(key)) in wanted and value is not None:
                text = str(value).strip()
                if text and text.lower() not in {"nan", "none", "n/a"}:
                    return text
        return None

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()

    @staticmethod
    def _parse_sp(value: object) -> Optional[float]:
        try:
            parsed = float(str(value).strip())
        except (TypeError, ValueError):
            return None
        return parsed if parsed >= 0 else None