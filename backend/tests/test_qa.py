from app.calculations.qa import QACalculationEngine


def test_qa_uses_explicit_qa_points_and_qa_statuses():
    rows = [
        {
            "Issue key": "QA-1",
            "Parent": "STORY-1",
            "Issue Type": "QA Sub-task",
            "Summary": "Verify checkout",
            "Assignee": "Harshit Raj",
            "Status": "QA Testing in Progress",
            "Custom field (QA Story Points)": "3",
        },
        {
            "Issue key": "QA-2",
            "Parent": "STORY-1",
            "Issue Type": "QA Sub-task",
            "Summary": "Verify confirmation",
            "Assignee": "Harshit Raj",
            "Status": "Done/ Live",
            "Custom field (QA Story Points)": "2",
        },
    ]

    result = QACalculationEngine().calculate(rows, list(rows[0]))

    assert result.total_sp == 5
    assert result.completed_sp == 2
    assert result.stats["Harshit Raj"].assigned_sp == 5
    assert result.stats["Harshit Raj"].completed_task_count == 1
    assert result.tasks[0].parent_key == "STORY-1"


def test_qa_rejects_negative_points_and_keeps_development_rows_separate():
    rows = [
        {
            "Issue key": "DEV-1",
            "Issue Type": "Story",
            "Assignee": "Richa Lakshmi",
            "Status": "Done/ Live",
            "Story Points": "8",
        },
        {
            "Issue key": "QA-1",
            "Issue Type": "QA",
            "Assignee": "Richa Lakshmi",
            "Status": "QA Done",
            "QA SP": "-2",
        },
    ]

    result = QACalculationEngine().calculate(rows, list(rows[0]))

    assert result.total_sp == 0
    assert result.tasks == []