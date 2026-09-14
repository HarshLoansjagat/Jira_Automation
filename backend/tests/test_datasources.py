from app.datasources.csv_source import JiraCSVDataSource
from app.datasources.normalized import NormalizedIssue


def test_csv_normalization_produces_shared_issue_contract():
    rows = [{
        "Issue key": "DAP-1",
        "Summary": "QA checkout",
        "Issue Type": "Sub-task",
        "Status": "Done/ Live",
        "Assignee": "Harshit Raj",
        "Story Points": "3",
        "Parent": "DAP-100",
        "QA Owner": "Harshit Raj",
    }]

    issues = JiraCSVDataSource.normalize_rows(rows)

    assert isinstance(issues[0], NormalizedIssue)
    assert issues[0].issue_key == "DAP-1"
    assert issues[0].story_points == 3
    assert issues[0].parent_key == "DAP-100"
    assert issues[0].to_row()["Issue key"] == "DAP-1"