"""Shared issue model used by CSV and Jira data sources."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Optional


@dataclass
class NormalizedIssue:
    issue_key: str
    summary: str = ""
    issue_type: str = ""
    status: str = ""
    assignee: Optional[str] = None
    parent_key: Optional[str] = None
    sprint_id: Optional[str] = None
    sprint_name: Optional[str] = None
    sprint_start: Optional[str] = None
    sprint_end: Optional[str] = None
    story_points: Optional[float] = None
    developer_owner_1: Optional[str] = None
    developer_owner_1_sp: Optional[float] = None
    developer_owner_2: Optional[str] = None
    developer_owner_2_sp: Optional[float] = None
    developer_owner_3: Optional[str] = None
    developer_owner_3_sp: Optional[float] = None
    qa_owner: Optional[str] = None
    qa_story_points: Optional[float] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    raw: dict[str, Any] | None = None

    def to_row(self) -> dict[str, Any]:
        """Return legacy engine-compatible keys plus the normalized fields."""
        row = dict(self.raw or {})
        row.update({
            "Issue key": self.issue_key,
            "Summary": self.summary,
            "Issue Type": self.issue_type,
            "Status": self.status,
            "Assignee": self.assignee,
            "Parent": self.parent_key,
            "Sprint": self.sprint_name,
            "Story Points": self.story_points,
            "Developer Owner 1": self.developer_owner_1,
            "Dev Owner 1 SP": self.developer_owner_1_sp,
            "Developer Owner 2": self.developer_owner_2,
            "Dev Owner 2 SP": self.developer_owner_2_sp,
            "Developer Owner 3": self.developer_owner_3,
            "Dev Owner 3 SP": self.developer_owner_3_sp,
            "QA Owner": self.qa_owner,
            "QA Story Points": self.qa_story_points,
        })
        return row

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class NormalizedDataSource:
    """Small protocol-like base for future sources and test doubles."""

    def fetch(self) -> tuple[list[NormalizedIssue], list[str], list[str]]:
        raise NotImplementedError