from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select, func

from app.config import settings
from app.models import (Fixture, Team, Shift, ShiftFixture, DemoAssignment, Invitation,
                        Outbox, User, aware, utcnow)
from app.planning import generate_shifts, run_planning, candidate_parents, cancel_shift

TZ = ZoneInfo('Europe/Amsterdam')


def add_fixture(db, day, hour, minute=0, **overrides):
    team = db.scalar(select(Team))
    if not team:
        team = Team(name='SDW fictional team')
        db.add(team)
        db.flush()
    f = Fixture(external_id=f'test:{day}:{hour}:{minute}:{len(db.new)}', team_id=team.id,
                home_team=team.name, away_team='Fictional opponent', source='demo',
                kickoff=datetime.combine(day, datetime.min.time(), TZ).replace(hour=hour, minute=minute).astimezone(timezone.utc),
                venue_id=1, venue_text='Sportpark Spieringhorn', city='Amsterdam',
                is_home=True, is_demo=True)
    for key, value in overrides.items():
        setattr(f, key, value)
    db.add(f)
    db.flush()
    return f


def test_opening_full_blocks_exclusions_and_old_coverage(db):
    day = (utcnow().astimezone(TZ)+timedelta(days=7)).date()
    f = add_fixture(db, day, 13, 30)
    add_fixture(db, day, 20, is_home=False)
    add_fixture(db, day, 21, status='cancelled')
    add_fixture(db, day, 22, venue_id=None)
    old = Shift(venue_id=1, starts_at=f.kickoff-timedelta(hours=4),
                ends_at=f.kickoff+timedelta(hours=3), is_demo=True, state='cancelled')
    db.add(old)
    db.flush()
    assert generate_shifts(db) == 5
    rows = list(db.scalars(select(Shift).where(Shift.state=='open').order_by(Shift.starts_at)))
    assert [(aware(s.starts_at).astimezone(TZ).strftime('%H:%M'),
             aware(s.ends_at).astimezone(TZ).strftime('%H:%M')) for s in rows] == [
                 ('08:00','10:00'),('10:00','12:00'),('12:00','14:00'),('14:00','16:00'),('16:00','18:00')]
    assert all(list(db.scalars(select(ShiftFixture.fixture_id).where(ShiftFixture.shift_id==s.id))) == [f.id] for s in rows)
    assert generate_shifts(db) == 0


def test_demo_staffing_is_separate_fair_and_survives_worker(db, users, monkeypatch):
    monkeypatch.setattr(settings(), 'demo_staffing_enabled', True)
    first = (utcnow().astimezone(TZ)+timedelta(days=7)).date()
    for offset in (0, 7, 14):
        add_fixture(db, first+timedelta(days=offset), 13, 30)
    generate_shifts(db)
    run_planning(db)
    assignments = list(db.scalars(select(DemoAssignment)))
    shifts = {s.id:s for s in db.scalars(select(Shift))}
    assert len(assignments) == 36
    assert db.scalar(select(func.count()).select_from(Invitation)) == 0
    assert db.scalar(select(func.count()).select_from(Outbox)) == 0
    for s in shifts.values():
        assert sum(a.shift_id==s.id for a in assignments) == 3
    by_person = {}
    for a in assignments:
        by_person.setdefault(a.person_key, []).append(aware(shifts[a.shift_id].starts_at).astimezone(TZ).date())
    assert all(len(days)==len(set(days)) and all(abs((x-y).days)>=14 for i,x in enumerate(days) for y in days[i+1:])
               for days in by_person.values())
    original = [(s.id, s.starts_at, s.ends_at) for s in shifts.values()]
    generate_shifts(db)
    run_planning(db)
    assert db.scalar(select(func.count()).select_from(DemoAssignment)) == 36
    assert original == [(s.id,s.starts_at,s.ends_at) for s in db.scalars(select(Shift))]
    assert not candidate_parents(db, next(iter(shifts.values())))


def test_demo_staffing_disabled_in_live_mode(db, users, monkeypatch):
    monkeypatch.setattr(settings(), 'demo_staffing_enabled', True)
    monkeypatch.setattr(settings(), 'demo_mode', False)
    day = (utcnow().astimezone(TZ)+timedelta(days=7)).date()
    add_fixture(db, day, 13, 30)
    generate_shifts(db)
    from app.planning import fill_demo_assignments
    assert fill_demo_assignments(db) == 0


def test_demo_api_has_no_fabricated_confirmations_and_parent_privacy(client, db, users, monkeypatch):
    from test_system import signin
    monkeypatch.setattr(settings(), 'demo_staffing_enabled', True)
    day = (utcnow().astimezone(TZ)+timedelta(days=7)).date()
    add_fixture(db, day, 13, 30)
    generate_shifts(db)
    run_planning(db)
    db.commit()
    signin(client,'admin','Coordinator-Test-Password!')
    admin = client.get('/api/dashboard').json()
    assert all(s['demo_assigned']==3 and len(s['demo_assignments'])==3
               and s['confirmed']==0 and not s['invitations'] for s in admin['shifts'])
    signin(client)
    parent = client.get('/api/dashboard').json()
    assert parent['shifts']
    assert all(len(s['demo_assignments'])==1 and s['demo_assignments'][0]['name']=='Parent 1' for s in parent['shifts'])


def test_replacement_preserves_history_and_is_idempotent(db, users, monkeypatch):
    from app.demo_schedule import apply_demo_opening
    from test_system import shift, fill_shift
    monkeypatch.setattr(settings(), 'demo_staffing_enabled', True)
    day = (utcnow().astimezone(TZ)+timedelta(days=7)).date()
    f = add_fixture(db, day, 13, 30)
    old = shift(db, f)
    fill_shift(db, old)
    invitation = db.scalar(select(Invitation))
    result = apply_demo_opening(db)
    assert result['state']=='applied' and result['new_shifts']==4
    assert old.state=='cancelled' and invitation.state=='cancelled'
    assert db.get(Invitation, invitation.id) and db.get(User,1).name=='Parent 1'
    assert apply_demo_opening(db)=={'state':'already_applied'}
    assert db.scalar(select(func.count()).select_from(DemoAssignment))==12
