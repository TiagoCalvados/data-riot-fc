"""Run every ten minutes from alwaysdata's scheduled tasks (not from web requests)."""
from datetime import timedelta
from sqlalchemy import select, delete
from app.db import SessionLocal
from app.models import SyncRun, JobRun, LoginAttempt, LoginSession, utcnow
from app.planning import planning_lock, generate_shifts, run_planning
from app.fixtures import sync_sportlink
from app.mailer import deliver_outbox
from app.analytics import prune_visitors


def run_job(db):
    with planning_lock(db):
        last = db.scalar(select(SyncRun).order_by(SyncRun.id.desc()).limit(1))
        sync = {'state': 'recent'}
        from app.models import aware
        if not last or aware(last.created_at) < utcnow() - timedelta(hours=1):
            sync = sync_sportlink(db)
        shifts = generate_shifts(db)
        result = run_planning(db)
        sent = deliver_outbox(db)
        db.execute(delete(LoginSession).where(LoginSession.expires_at < utcnow()))
        db.execute(delete(LoginAttempt).where(LoginAttempt.created_at < utcnow() - timedelta(days=1)))
        # Bound operational history; invitation/audit history remains intact.
        db.execute(delete(JobRun).where(JobRun.created_at < utcnow() - timedelta(days=90)))
        db.execute(delete(SyncRun).where(SyncRun.created_at < utcnow() - timedelta(days=90)))
        prune_visitors(db)
        report = {'shifts': shifts, **result, 'emails': sent, 'sync': sync}
        db.add(JobRun(state='success', detail=report))
        db.commit()
        return report


if __name__ == '__main__':
    import json
    with SessionLocal() as session:
        print(json.dumps(run_job(session)))
