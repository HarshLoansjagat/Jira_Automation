from datetime import datetime
from statistics import mean

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.snapshot import Snapshot

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _days_remaining(end_date: str | None) -> int | None:
    if not end_date:
        return None
    value = end_date.replace("Z", "")
    try:
        end = datetime.fromisoformat(value[:19])
    except ValueError:
        return None
    return max(0, (end.date() - datetime.now().date()).days)


@router.get("/summary")
def analytics_summary(db: Session = Depends(get_db)):
    snapshots = db.query(Snapshot).join(Snapshot.sprint).order_by(Snapshot.captured_at.asc()).all()
    if not snapshots:
        return {"has_data": False, "health": {"status": "UNKNOWN", "reasons": ["No persisted sprint snapshot exists."]}}
    latest = snapshots[-1]
    days_remaining = _days_remaining(latest.sprint.end_date)
    scope_change = (latest.overall_scope or 0) - (latest.day1_fixed_scope or latest.overall_scope or 0)
    qa_backlog = sum(metric.remaining_sp or 0 for metric in latest.qa_metrics)
    daily_rates = []
    for previous, current in zip(snapshots, snapshots[1:]):
        if previous.sprint_id == current.sprint_id:
            daily_rates.append(max(0.0, (current.overall_completed or 0) - (previous.overall_completed or 0)))
    velocity = mean(daily_rates) if daily_rates else latest.overall_completed or 0.0
    remaining = latest.overall_remaining or 0.0
    estimated_days = remaining / velocity if velocity > 0 else None
    reasons = []
    if remaining > 0:
        reasons.append(f"{remaining:.2f} SP remaining")
    if days_remaining is not None:
        reasons.append(f"{days_remaining} days remaining")
    if scope_change > 0:
        reasons.append(f"Scope increased by {scope_change:.2f} SP")
    if qa_backlog > 0:
        reasons.append(f"QA backlog is {qa_backlog:.2f} SP")
    if days_remaining is not None and estimated_days is not None and estimated_days > days_remaining:
        health = "CRITICAL"
        reasons.append("Current velocity may miss the sprint target")
    elif scope_change > 0 or qa_backlog > 0:
        health = "AT RISK"
    else:
        health = "HEALTHY"
    return {
        "has_data": True,
        "sprint": latest.sprint.name,
        "snapshot_id": latest.id,
        "completion_pct": latest.overall_completion,
        "current_scope": latest.overall_scope,
        "completed_sp": latest.overall_completed,
        "remaining_sp": remaining,
        "day1_fixed_scope": latest.day1_fixed_scope,
        "scope_change": round(scope_change, 2),
        "qa_backlog_sp": round(qa_backlog, 2),
        "days_remaining": days_remaining,
        "current_velocity": round(velocity, 2),
        "estimated_days_required": round(estimated_days, 2) if estimated_days is not None else None,
        "forecast_status": "MAY_MISS" if estimated_days is not None and days_remaining is not None and estimated_days > days_remaining else "ON_TRACK",
        "health": {"status": health, "reasons": reasons},
        "velocity_trend": [
            {"snapshot_id": item.id, "date": item.snapshot_date, "completed_sp": item.overall_completed, "completion_pct": item.overall_completion}
            for item in snapshots
        ],
    }