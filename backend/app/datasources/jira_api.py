"""Jira Cloud REST data source with dynamic custom-field mapping."""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

import httpx

from app.config import settings
from app.datasources.normalized import NormalizedDataSource, NormalizedIssue

logger = logging.getLogger(__name__)


class JiraAPIError(RuntimeError):
    pass


class JiraApiDataSource(NormalizedDataSource):
    def __init__(self, client: Optional[httpx.Client] = None):
        self.base_url = (settings.JIRA_BASE_URL or "").rstrip("/")
        self.email = settings.JIRA_EMAIL
        self.token = settings.JIRA_API_TOKEN
        self.project_key = settings.JIRA_PROJECT_KEY
        self.board_id = settings.JIRA_BOARD_ID
        self.client = client or httpx.Client(timeout=30.0)

    def _ensure_configured(self) -> None:
        if not self.base_url or not self.email or not self.token:
            raise JiraAPIError("Jira API is not configured. Set JIRA_BASE_URL, JIRA_EMAIL, and JIRA_API_TOKEN.")

    def _get(self, path: str, **params: Any) -> dict[str, Any]:
        self._ensure_configured()
        response = self.client.get(
            f"{self.base_url}{path}",
            params={key: value for key, value in params.items() if value is not None},
            auth=(self.email, self.token),
            headers={"Accept": "application/json"},
        )
        if response.status_code in (401, 403):
            raise JiraAPIError("Jira API authentication or permission check failed.")
        if response.status_code >= 400:
            raise JiraAPIError(f"Jira API request failed with status {response.status_code}.")
        return response.json()

    def active_sprint(self) -> dict[str, Any]:
        if not self.board_id:
            raise JiraAPIError("JIRA_BOARD_ID is required to detect the active sprint.")
        payload = self._get(f"/rest/agile/1.0/board/{self.board_id}/sprint", state="active", maxResults=50)
        sprints = payload.get("values", [])
        if not sprints:
            raise JiraAPIError("No active Jira sprint was found for the configured board.")
        if len(sprints) > 1:
            logger.warning("Jira returned multiple active sprints; using the first result.")
        return sprints[0]

    def fetch(self) -> tuple[list[NormalizedIssue], list[str], list[str]]:
        sprint = self.active_sprint()
        sprint_id = str(sprint.get("id")) if sprint.get("id") is not None else None
        jql = f"sprint = {sprint_id}"
        if self.project_key:
            jql = f"project = {self.project_key} AND {jql}"
        fields = self._get("/rest/api/3/field").get("values", [])
        field_map = self._field_map(fields)
        issues: list[NormalizedIssue] = []
        start_at = 0
        while True:
            payload = self._get(
                "/rest/api/3/search",
                jql=jql,
                startAt=start_at,
                maxResults=100,
                fields="*all",
            )
            issues.extend(self._normalize_issue(item, sprint, field_map) for item in payload.get("issues", []))
            start_at += len(payload.get("issues", []))
            if start_at >= payload.get("total", 0) or not payload.get("issues"):
                break
        return issues, ["Jira REST API"], []

    @classmethod
    def _field_map(cls, fields: list[dict[str, Any]]) -> dict[str, str]:
        result: dict[str, str] = {}
        for field in fields:
            name = cls._normalize(field.get("name", ""))
            field_id = field.get("id")
            if field_id:
                result[name] = field_id
        return result

    @classmethod
    def _normalize_issue(cls, item: dict[str, Any], sprint: dict[str, Any], field_map: dict[str, str]) -> NormalizedIssue:
        fields = item.get("fields", {})
        get_field = lambda *names: cls._first(fields, [field_map.get(cls._normalize(name), name) for name in names])
        assignee = fields.get("assignee") or {}
        issue_type = fields.get("issuetype") or {}
        parent = fields.get("parent") or {}
        return NormalizedIssue(
            issue_key=item.get("key", ""),
            summary=fields.get("summary") or "",
            issue_type=issue_type.get("name", ""),
            status=(fields.get("status") or {}).get("name", ""),
            assignee=assignee.get("displayName") if assignee else None,
            parent_key=parent.get("key") if parent else None,
            sprint_id=str(sprint.get("id")) if sprint.get("id") is not None else None,
            sprint_name=sprint.get("name"),
            sprint_start=sprint.get("startDate"),
            sprint_end=sprint.get("endDate"),
            story_points=cls._number(get_field("Story Points", "Story point estimate")),
            developer_owner_1=cls._text(get_field("Developer Owner 1", "Developer 1")),
            developer_owner_1_sp=cls._number(get_field("Dev Owner 1 SP", "Developer 1 SP")),
            developer_owner_2=cls._text(get_field("Developer Owner 2", "Developer 2")),
            developer_owner_2_sp=cls._number(get_field("Dev Owner 2 SP", "Developer 2 SP")),
            developer_owner_3=cls._text(get_field("Developer Owner 3", "Developer 3")),
            developer_owner_3_sp=cls._number(get_field("Dev Owner 3 SP", "Developer 3 SP")),
            qa_owner=cls._text(get_field("QA Owner", "QA Assignee")),
            qa_story_points=cls._number(get_field("QA Story Points", "QA SP")),
            created_at=fields.get("created"),
            updated_at=fields.get("updated"),
            raw=fields,
        )

    @staticmethod
    def _first(fields: dict[str, Any], keys: list[str]) -> Any:
        for key in keys:
            value = fields.get(key)
            if value not in (None, "", []):
                return value
        return None

    @staticmethod
    def _text(value: Any) -> Optional[str]:
        if isinstance(value, dict):
            return value.get("displayName") or value.get("value")
        return str(value).strip() if value not in (None, "") else None

    @staticmethod
    def _number(value: Any) -> Optional[float]:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if number >= 0 else None

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()