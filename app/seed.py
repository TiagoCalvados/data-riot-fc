"""Explicit, idempotent demo installation. Credentials are supplied on stdin."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import json
import secrets
import sys
from sqlalchemy import select
from app.db import SessionLocal
from app.config import settings
from app.models import Club, Venue, Team, User, ParentTeam, Fixture, PlanningPolicy, Invitation, utcnow
from app.security import password_hash
from app.planning import generate_shifts, run_planning, planning_lock, audit
from app.mailer import deliver_outbox


def seed(db, admin_password, parent_password):
    if db.scalar(select(Club.id)):
        return {'state': 'already_initialized'}
    db.add(Club(id=1, name='ASC SDW'))
    db.flush()
    db.add(Venue(id=1, club_id=1, name='Sportpark Spieringhorn', address='Sportpark Spieringhorn 11, 1043 AA Amsterdam'))
    db.add(PlanningPolicy(club_id=1, automation_enabled=settings().demo_mode))
    coordinator = User(username='beheer.test', name='Kantinecoördinator', email='beheer@example.invalid',
                       password_hash=password_hash(admin_password), role='admin', volunteering=False, is_demo=True)
    db.add(coordinator)
    db.flush()
    if not settings().demo_mode:
        audit(db, 'installation.ready', {'demo': False})
        db.commit()
        return {'state': 'production_initialized'}
    teams = [Team(name=n) for n in ('SDW JO10-1', 'SDW JO12-1', 'SDW JO15-1', 'SDW MO13-1')]
    db.add_all(teams)
    db.flush()
    names = ['Test Ouder', 'Sam de Vries', 'Noor Bakker', 'Alex Jansen', 'Robin Visser', 'Jules Smit',
             'Charlie Meijer', 'Bo van Dijk', 'Lou de Boer', 'Riley Mulder', 'Dani Bos', 'Isa Vos',
             'Jamie Peters', 'Sasha Hendriks', 'Max Dekker', 'Luca Brouwer', 'Kim van Leeuwen', 'Tess Smits']
    for index, name in enumerate(names):
        parent = User(username='ouder.test' if index == 0 else f'demo.{index:02d}', name=name,
                      email=f'demo{index}@example.invalid', is_demo=True,
                      password_hash=password_hash(parent_password if index == 0 else secrets.token_urlsafe(32)))
        db.add(parent)
        db.flush()
        db.add(ParentTeam(user_id=parent.id, team_id=teams[index % len(teams)].id))
    tz = ZoneInfo('Europe/Amsterdam')
    today = utcnow().astimezone(tz).date()
    saturday = today + timedelta(days=((5 - today.weekday()) % 7 or 7))
    if (saturday - today).days < 3:
        saturday += timedelta(days=7)
    opponents = ['AFC JO10-2', 'SDZ JO12-1', 'ASV Arsenal JO15-1', 'TABA MO13-1']
    for week in range(4):
        day = saturday + timedelta(weeks=week)
        for index, hour in enumerate((10, 11, 13)):
            start = datetime(day.year, day.month, day.day, hour, 30 if index == 2 else 0, tzinfo=tz)
            db.add(Fixture(external_id=f'demo:{week}:{index}', source='demo', team_id=teams[index].id,
                venue_id=1, home_team=teams[index].name, away_team=opponents[(index + week) % 4], kickoff=start,
                venue_text='Sportpark Spieringhorn', city='Amsterdam', is_home=True, is_demo=True))
        start = datetime(day.year, day.month, day.day, 12, 0, tzinfo=tz)
        db.add(Fixture(external_id=f'demo:away:{week}', source='demo', team_id=teams[3].id,
            home_team='TABA MO13-1', away_team=teams[3].name, kickoff=start,
            venue_text='Sportpark Drieburg', city='Amsterdam', is_home=False, is_demo=True))
    db.flush()
    with planning_lock(db):
        generate_shifts(db)
        run_planning(db)
        deliver_outbox(db)
        for invite in db.scalars(select(Invitation).where(Invitation.state == 'pending').order_by(Invitation.id)):
            if invite.user_id != 2 and invite.id % 3 != 0:
                invite.state = 'confirmed'
                invite.responded_at = utcnow()
        audit(db, 'demo.initialized', {'notice': 'Alle personen en wedstrijden zijn fictieve testgegevens.'})
        db.commit()
    return {'state': 'demo_initialized'}


if __name__ == '__main__':
    credentials = json.load(sys.stdin)
    with SessionLocal() as db:
        print(json.dumps(seed(db, credentials['admin_password'], credentials['parent_password'])))
