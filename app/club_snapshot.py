"""Import an explicitly verified public club snapshot; never an automatic feed."""
from datetime import datetime, timedelta, timezone
import re
from zoneinfo import ZoneInfo
from sqlalchemy import select
from app.config import settings
from app.models import Fixture, Team, Venue, Shift, AuditEvent, SyncRun, aware, utcnow
from app.planning import planning_lock, cancel_shift, generate_shifts, fill_demo_assignments, audit

ACTION = 'fixture.snapshot_imported'
TZ = ZoneInfo('Europe/Amsterdam')
SOURCE_URL = 'https://www.ascsdw.nl/116/programma/'


def normalise_snapshot(payload):
    if payload.get('source_url') != SOURCE_URL or not re.fullmatch(r'[a-f0-9]{64}', payload.get('sha256', '')):
        raise ValueError('Missing official snapshot provenance')
    verified = datetime.fromisoformat(payload['verified_at'])
    if verified.tzinfo is None or not utcnow()-timedelta(hours=24) < verified <= utcnow()+timedelta(minutes=5):
        raise ValueError('Snapshot must have a current, timezone-aware verification time')
    if payload.get('cancellation_check') != 'no_cancellations_published':
        raise ValueError('A current explicit cancellation check is required')
    coverage = payload['coverage_dates']
    if not coverage or len(set(coverage)) != len(coverage):
        raise ValueError('Specify the verified coverage dates')
    evidence = payload['venue_evidence']
    if not evidence or any(not re.fullmatch(r'https://www\.ascsdw\.nl/113/\d+/uitslagen/wedstrijd-details/(?:\?tab=1)?', url)
                           for url in evidence.values()):
        raise ValueError('Missing official pitch/venue evidence')
    rows = []
    for row in payload['fixtures']:
        url = row['source_url']
        match = re.fullmatch(r'https://www\.ascsdw\.nl/113/(\d+)/uitslagen/wedstrijd-details/(?:\?tab=1)?', url)
        if not match:
            raise ValueError('Invalid official match URL')
        kickoff = datetime.fromisoformat(row['kickoff'])
        if kickoff.tzinfo is None or kickoff.astimezone(TZ).date().isoformat() not in coverage:
            raise ValueError('Fixture date is outside the verified coverage')
        home, away = row['home_team'].strip(), row['away_team'].strip()
        if not home.startswith(('ASC SDW ', 'SDW ')) or not away or any('...' in n or '…' in n for n in (home, away)):
            raise ValueError('This snapshot accepts fully named SDW home fixtures only')
        pitch = re.match(r'^\((\d+)\)veld ', row['field'])
        if not pitch or pitch[1] not in evidence or 'SDW' not in row['field']:
            raise ValueError('Home pitch has not been verified at Spieringhorn')
        if row['venue'] != 'Sportpark Spieringhorn' or row['city'] != 'Amsterdam':
            raise ValueError('Venue must be verified, not guessed')
        if row['status'] not in ('scheduled', 'cancelled', 'postponed'):
            raise ValueError('Unverified match status')
        rows.append(dict(external_id='ascsdw:'+match[1], home_team=home, away_team=away,
                         kickoff=kickoff.astimezone(timezone.utc), venue_text=row['venue'], city=row['city'],
                         is_home=True, status=row['status'], verified_at=verified.astimezone(timezone.utc)))
    if not rows or len({r['external_id'] for r in rows}) != len(rows):
        raise ValueError('Empty or duplicate snapshot')
    if sorted({r['kickoff'].astimezone(TZ).date().isoformat() for r in rows}) != sorted(coverage):
        raise ValueError('Coverage dates must match imported dates')
    return rows, verified


def import_snapshot(db, payload):
    rows, verified = normalise_snapshot(payload)  # validate everything before changing anything
    if not (settings().demo_mode and settings().demo_staffing_enabled):
        raise ValueError('This rollout keeps explicitly fictional staffing and simulated email')
    with planning_lock(db):
        for event in db.scalars(select(AuditEvent).where(AuditEvent.action == ACTION)):
            if event.detail.get('sha256') == payload['sha256']:
                return {'state': 'already_imported', 'count': len(rows)}
        venue = db.scalar(select(Venue).where(Venue.is_home.is_(True)))
        if not venue or 'spieringhorn' not in venue.name.casefold() or venue.city.casefold() != 'amsterdam':
            raise ValueError('No approved Spieringhorn venue')
        # Fictional rows remain in the database as review/history, not official cancellations.
        retired = []
        for f in db.scalars(select(Fixture).where(Fixture.is_demo.is_(True), Fixture.kickoff > utcnow())):
            f.status = 'review'
            retired.append(f.id)
        old_shifts = list(db.scalars(select(Shift).where(Shift.is_demo.is_(True),
                                Shift.state == 'open', Shift.starts_at > utcnow())))
        for s in old_shifts:
            cancel_shift(db, s, 'Fictief programma vervangen door gecontroleerde clubmomentopname; bezetting blijft fictief.')
        imported = []
        for row in rows:
            team = db.scalar(select(Team).where(Team.name == row['home_team']))
            if team is None:
                team = Team(name=row['home_team'])
                db.add(team)
                db.flush()
            fixture = db.scalar(select(Fixture).where(Fixture.external_id == row['external_id']))
            if fixture is None:
                fixture = Fixture(**row, source='club_snapshot', team_id=team.id, venue_id=venue.id, is_demo=False)
                db.add(fixture)
            else:
                for key, value in row.items():
                    setattr(fixture, key, value)
                fixture.team_id, fixture.venue_id, fixture.is_demo = team.id, venue.id, False
            db.flush()
            imported.append(fixture.id)
        # Omitted real snapshot matches are review items; never infer cancellation.
        ids = {r['external_id'] for r in rows}
        for f in db.scalars(select(Fixture).where(Fixture.source == 'club_snapshot')):
            if aware(f.kickoff).astimezone(TZ).date().isoformat() in payload['coverage_dates'] and f.external_id not in ids:
                f.status = 'review'
        db.flush()
        shifts = generate_shifts(db)
        assignments = fill_demo_assignments(db)
        detail = {k: payload[k] for k in ('source_url', 'sha256', 'verified_at', 'coverage_dates', 'venue_evidence', 'cancellation_check')}
        detail.update({'count': len(rows), 'fixture_ids': imported, 'retired_demo_fixture_ids': retired,
                       'cancelled_demo_shift_ids': [s.id for s in old_shifts],
                       'new_shifts': shifts, 'fictional_assignments': assignments, 'automatic_feed': False})
        audit(db, ACTION, detail)
        db.add(SyncRun(source='club_snapshot', state='success', count=len(rows),
                       detail='Handmatig gecontroleerde clubmomentopname; geen automatische feed.'))
        db.commit()
        return {'state': 'imported', 'count': len(rows), 'new_shifts': shifts, 'fictional_assignments': assignments}


if __name__ == '__main__':
    import json, sys
    from app.db import SessionLocal
    with SessionLocal() as db:
        print(json.dumps(import_snapshot(db, json.load(sys.stdin))))
