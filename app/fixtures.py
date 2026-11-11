"""Sportlink Club.Dataservice adapter; only public fixture/team fields are requested."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import httpx
from sqlalchemy import select
from app.config import settings
from app.models import Fixture, Team, Venue, SyncRun, aware, utcnow
from app.planning import reconcile_days


def normalise_fixture(row, club_code):
    raw_time = row.get('wedstrijddatum')
    if not raw_time or not row.get('wedstrijdcode'):
        raise ValueError('Fixture is missing a stable ID or kickoff timestamp')
    kickoff = datetime.fromisoformat(str(raw_time).replace('Z', '+00:00'))
    if kickoff.tzinfo is None:
        kickoff = kickoff.replace(tzinfo=ZoneInfo('Europe/Amsterdam'))
    home = str(row.get('thuisteamclubrelatiecode', '')) == club_code
    away = str(row.get('uitteamclubrelatiecode', '')) == club_code
    if not home and not away:
        raise ValueError('Fixture does not belong to the configured club')
    status_text = str(row.get('status', '')).casefold()
    status = 'cancelled' if any(s in status_text for s in ('afgelast', 'cancel', 'gestaakt')) else (
        'postponed' if any(s in status_text for s in ('uitgesteld', 'verplaatst', 'te plannen')) else 'scheduled')
    name = str(row.get('thuisteam' if home else 'uitteam', ''))
    if not name or not row.get('thuisteam') or not row.get('uitteam'):
        raise ValueError('Fixture is missing team names')
    return dict(external_id='sportlink:' + str(row['wedstrijdcode']), home_team=str(row['thuisteam']),
                away_team=str(row['uitteam']), kickoff=kickoff, venue_text=str(row.get('accommodatie', '')),
                city=str(row.get('plaats', '')), is_home=home, status=status,
                team_name=name, team_external=str(row.get('thuisteamid' if home else 'uitteamid') or name))


def sync_sportlink(db, transport=None):
    config = settings()
    if not config.sportlink_client_id or not config.sportlink_club_code:
        return {'state': 'not_configured', 'count': 0}
    try:
        with httpx.Client(timeout=25, transport=transport) as client:
            response = client.get('https://data.sportlink.com/programma', params={
                'client_id': config.sportlink_client_id, 'aantaldagen': 42,
                'aantalregels': 500})
            response.raise_for_status()
            rows = response.json()
        if not isinstance(rows, list) or len(rows) >= 500:
            raise ValueError('Incomplete fixture response')
        # Validate the whole snapshot before making changes, so parse errors never erase fixtures.
        normalised = [normalise_fixture(row, config.sportlink_club_code) for row in rows]
        if len({r['external_id'] for r in normalised}) != len(normalised):
            raise ValueError('Duplicate fixture identifiers')
    except (httpx.HTTPError, ValueError, TypeError, KeyError):
        db.add(SyncRun(source='sportlink', state='failed', detail='Wedstrijdfeed niet beschikbaar of onvolledig. Bestaande planning behouden.'))
        return {'state': 'failed', 'count': 0}
    changed = set()
    tz = ZoneInfo('Europe/Amsterdam')
    home_venue = db.scalar(select(Venue).where(Venue.is_home.is_(True)))
    now = utcnow()
    for row in normalised:
        team_name = row.pop('team_name')
        external = row.pop('team_external')
        team = db.scalar(select(Team).where(Team.external_id == external)) or db.scalar(select(Team).where(Team.name == team_name))
        if team is None:
            team = Team(name=team_name, external_id=external)
            db.add(team)
            db.flush()
        row['team_id'] = team.id
        # A home designation alone is insufficient: require SDW's actual Amsterdam home venue.
        approved_venue = row['is_home'] and 'spieringhorn' in row['venue_text'].casefold() and row['city'].casefold().startswith('amsterdam')
        row['venue_id'] = home_venue.id if approved_venue else None
        fixture = db.scalar(select(Fixture).where(Fixture.external_id == row['external_id']))
        if fixture:
            if any((aware(getattr(fixture, k)) != aware(v) if k == 'kickoff' else getattr(fixture, k) != v)
                   for k, v in row.items()):
                changed.add(aware(fixture.kickoff).astimezone(tz).date())
                changed.add(aware(row['kickoff']).astimezone(tz).date())
            for k, v in row.items():
                setattr(fixture, k, v)
            fixture.verified_at = now
        else:
            fixture = Fixture(**row, source='sportlink', verified_at=now)
            db.add(fixture)
            changed.add(aware(fixture.kickoff).astimezone(tz).date())
    # Missing fixtures are ambiguous (e.g. feed horizon/privacy): require coordinator review.
    # Do not infer cancellation or silently retain an invitation for a vanished match.
    ids = {r['external_id'] for r in normalised}
    for fixture in db.scalars(select(Fixture).where(Fixture.source == 'sportlink', Fixture.kickoff > now,
            Fixture.kickoff < now + timedelta(days=41), Fixture.status == 'scheduled')):
        if fixture.external_id not in ids:
            fixture.status = 'review'
            changed.add(aware(fixture.kickoff).astimezone(tz).date())
    db.flush()
    if changed:
        reconcile_days(db, changed)
    db.add(SyncRun(source='sportlink', state='success', count=len(rows)))
    return {'state': 'success', 'count': len(rows)}
