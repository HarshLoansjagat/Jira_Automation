from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False}  # SQLite only
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database tables and seed default data."""
    from app.models import report, developer, settings_model, morning_snapshot, email_delivery, snapshot  # noqa: F401
    Base.metadata.create_all(bind=engine)
    _ensure_schema_columns()
    _seed_defaults()


def _ensure_schema_columns():
    """Backfill new columns for existing SQLite databases without a destructive migration."""
    with engine.begin() as conn:
        # Snapshot tables are created by Base.metadata.create_all above. The
        # legacy ALTER statements below remain for existing installations.
        for table_name, column_name in [
            ("reports", "data_quality_issues"),
            ("morning_snapshots", "data_quality_issues"),
        ]:
            existing = conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
            if not any(row[1] == column_name for row in existing):
                conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} JSON"))
        for table_name, column_name, sql_type in [
            ("reports", "sprint_id", "VARCHAR(100)"),
            ("reports", "sprint_start", "VARCHAR(100)"),
            ("reports", "sprint_end", "VARCHAR(100)"),
            ("reports", "day1_fixed_scope", "FLOAT"),
            ("morning_snapshots", "sprint_id", "VARCHAR(100)"),
            ("morning_snapshots", "sprint_start", "VARCHAR(100)"),
            ("morning_snapshots", "sprint_end", "VARCHAR(100)"),
            ("morning_snapshots", "day1_fixed_scope", "FLOAT"),
        ]:
            existing = conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
            if not any(row[1] == column_name for row in existing):
                conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {sql_type}"))


def _seed_defaults():
    """Seed default developers and statuses if not present."""
    db = SessionLocal()
    try:
        from app.models.developer import Developer
        from app.models.settings_model import AppSetting

        defaults = [
            "Raj Shinde",
            "Sriniwas Chamreddy",
            "Sunny Shankar",
            "Dinesh Babu",
            "Ayush Srivastava",
            "Harshit Raj",
            "Richa Lakshmi",
        ]
        existing_names = {developer.name for developer in db.query(Developer).all()}
        for name in defaults:
            if name not in existing_names:
                db.add(Developer(name=name, is_active=True))
        db.commit()

        import json
        if db.query(AppSetting).filter_by(key="completed_statuses").count() == 0:
            db.add(AppSetting(
                key="completed_statuses",
                value=json.dumps(["Ready for QA", "QA Testing in Progress", "Done/ Live"])
            ))
            db.commit()

        # Day-1 Fixed Scope baseline (null until user sets it)
        if db.query(AppSetting).filter_by(key="day1_fixed_scope").count() == 0:
            db.add(AppSetting(key="day1_fixed_scope", value="null"))
            db.commit()

        # Sprint Start (null until user sets it)
        if db.query(AppSetting).filter_by(key="sprint_start").count() == 0:
            db.add(AppSetting(key="sprint_start", value="null"))
            db.commit()

        # Sprint End (null until Jira provides it)
        if db.query(AppSetting).filter_by(key="sprint_end").count() == 0:
            db.add(AppSetting(key="sprint_end", value="null"))
            db.commit()

        # Fixed developer order
        desired_order = defaults
        order_setting = db.query(AppSetting).filter_by(key="developer_order").first()
        if order_setting is None:
            db.add(AppSetting(key="developer_order", value=json.dumps(desired_order)))
        else:
            try:
                current_order = json.loads(order_setting.value)
            except Exception:
                current_order = []
            order_setting.value = json.dumps(
                desired_order + [name for name in current_order if name not in desired_order]
            )
        db.commit()

        email_defaults = {
            "email_recipients": json.dumps(["harsh.mishra_cs.aiml23@gla.ac.in"]),
            "email_cc": json.dumps([]),
            "email_subject": "",
            "email_report_type": "EOD",
            "email_morning_time": "10:30",
            "email_eod_time": "19:00",
            "email_timezone": "Asia/Kolkata",
            "email_days": json.dumps([0, 1, 2, 3, 4]),
            "email_enabled": json.dumps(True),
        }
        for key, value in email_defaults.items():
            if db.query(AppSetting).filter_by(key=key).count() == 0:
                db.add(AppSetting(key=key, value=value))
        db.commit()

    finally:
        db.close()
