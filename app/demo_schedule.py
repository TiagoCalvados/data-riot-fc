"""Audited, one-time replacement of the existing fictional shift presentation."""
from sqlalchemy import select
from app.config import settings
from app.models import Shift, AuditEvent, utcnow
from app.planning import (planning_lock, policy, cancel_shift, generate_shifts,
                          fill_demo_assignments, audit)

ACTION = 'demo.opening_0800.applied'


def apply_demo_opening(db):
    if not (settings().demo_mode and settings().demo_staffing_enabled
            and settings().canteen_opening_hour == 8):
        raise ValueError('Enable fictional staffing and 08:00 opening in demo mode first')
    with planning_lock(db):
        if db.scalar(select(AuditEvent.id).where(AuditEvent.action == ACTION)):
            return {'state': 'already_applied'}
        old = list(db.scalars(select(Shift).where(Shift.is_demo.is_(True),
            Shift.state == 'open', Shift.starts_at > utcnow())))
        p = policy(db)
        p.shift_minutes, p.volunteers_per_shift = 120, 3
        for shift in old:
            cancel_shift(db, shift, 'Fictieve demo-indeling vervangen: opening 08:00, volledige twee-uursblokken.')
        db.flush()
        created = generate_shifts(db)
        assigned = fill_demo_assignments(db)
        result = {'state': 'applied', 'cancelled_shift_ids': [s.id for s in old],
                  'new_shifts': created, 'fictional_assignments': assigned,
                  'opening': '08:00 Europe/Amsterdam', 'closing': 'provisional demo coverage',
                  'real_fixture_verification': False}
        audit(db, ACTION, result)
        db.commit()
        return result


if __name__ == '__main__':
    import json
    from app.db import SessionLocal
    with SessionLocal() as db:
        print(json.dumps(apply_demo_opening(db)))
