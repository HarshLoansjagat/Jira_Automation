from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Sprint(Base):
    __tablename__ = "sprints"
    id = Column(Integer, primary_key=True)
    sprint_key = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    sprint_id = Column(String(100), nullable=True)
    project_key = Column(String(100), nullable=True)
    start_date = Column(String(100), nullable=True)
    end_date = Column(String(100), nullable=True)
    day1_fixed_scope = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    snapshots = relationship("Snapshot", back_populates="sprint", cascade="all, delete-orphan")


class Snapshot(Base):
    __tablename__ = "snapshots"
    id = Column(Integer, primary_key=True)
    sprint_id = Column(Integer, ForeignKey("sprints.id"), nullable=False, index=True)
    snapshot_date = Column(String(50), nullable=False)
    snapshot_type = Column(String(20), nullable=False)
    captured_at = Column(DateTime(timezone=True), server_default=func.now())
    overall_scope = Column(Float, default=0.0)
    overall_completed = Column(Float, default=0.0)
    overall_remaining = Column(Float, default=0.0)
    overall_completion = Column(Float, default=0.0)
    day1_fixed_scope = Column(Float, nullable=True)
    sprint = relationship("Sprint", back_populates="snapshots")
    issues = relationship("IssueSnapshot", back_populates="snapshot", cascade="all, delete-orphan")
    developer_metrics = relationship("DeveloperMetric", back_populates="snapshot", cascade="all, delete-orphan")
    qa_metrics = relationship("QAMetric", back_populates="snapshot", cascade="all, delete-orphan")
    __table_args__ = (UniqueConstraint("sprint_id", "snapshot_date", "snapshot_type", name="uq_snapshot_identity"),)


class IssueSnapshot(Base):
    __tablename__ = "issue_snapshots"
    id = Column(Integer, primary_key=True)
    snapshot_id = Column(Integer, ForeignKey("snapshots.id"), nullable=False, index=True)
    issue_key = Column(String(200), nullable=False)
    parent_key = Column(String(200), nullable=True)
    summary = Column(String(1000), nullable=True)
    status = Column(String(200), nullable=True)
    issue_type = Column(String(200), nullable=True)
    assignee = Column(String(255), nullable=True)
    developer_owner = Column(String(255), nullable=True)
    developer_sp = Column(Float, nullable=True)
    qa_owner = Column(String(255), nullable=True)
    qa_sp = Column(Float, nullable=True)
    story_points = Column(Float, nullable=True)
    completed_sp = Column(Float, default=0.0)
    snapshot = relationship("Snapshot", back_populates="issues")
    __table_args__ = (UniqueConstraint("snapshot_id", "issue_key", name="uq_issue_snapshot_identity"),)


class DeveloperMetric(Base):
    __tablename__ = "developer_metrics"
    id = Column(Integer, primary_key=True)
    snapshot_id = Column(Integer, ForeignKey("snapshots.id"), nullable=False, index=True)
    developer_name = Column(String(255), nullable=False)
    assigned_sp = Column(Float, default=0.0)
    completed_sp = Column(Float, default=0.0)
    remaining_sp = Column(Float, default=0.0)
    completion_pct = Column(Float, default=0.0)
    snapshot = relationship("Snapshot", back_populates="developer_metrics")
    __table_args__ = (UniqueConstraint("snapshot_id", "developer_name", name="uq_developer_metric_identity"),)


class QAMetric(Base):
    __tablename__ = "qa_metrics"
    id = Column(Integer, primary_key=True)
    snapshot_id = Column(Integer, ForeignKey("snapshots.id"), nullable=False, index=True)
    qa_member = Column(String(255), nullable=False)
    assigned_sp = Column(Float, default=0.0)
    completed_sp = Column(Float, default=0.0)
    remaining_sp = Column(Float, default=0.0)
    completion_pct = Column(Float, default=0.0)
    task_count = Column(Integer, default=0)
    completed_task_count = Column(Integer, default=0)
    snapshot = relationship("Snapshot", back_populates="qa_metrics")
    __table_args__ = (UniqueConstraint("snapshot_id", "qa_member", name="uq_qa_metric_identity"),)