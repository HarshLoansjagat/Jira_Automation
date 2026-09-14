from fastapi import APIRouter, HTTPException

from app.datasources.jira_api import JiraAPIError, JiraApiDataSource

router = APIRouter(prefix="/api/jira", tags=["jira"])


@router.get("/status")
def jira_status():
    source = JiraApiDataSource()
    configured = bool(source.base_url and source.email and source.token and source.board_id)
    return {
        "configured": configured,
        "project_key": source.project_key,
        "board_id": source.board_id,
    }


@router.get("/active-sprint")
def active_sprint():
    try:
        return JiraApiDataSource().active_sprint()
    except JiraAPIError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/preview")
def preview_issues():
    try:
        issues, source, warnings = JiraApiDataSource().fetch()
        return {
            "source": source,
            "warnings": warnings,
            "issue_count": len(issues),
            "issues": [issue.as_dict() for issue in issues],
        }
    except JiraAPIError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc