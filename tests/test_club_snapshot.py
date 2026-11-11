from copy import deepcopy
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pytest
from sqlalchemy import select, func
from app.config import settings
from app.models import Fixture, Shift, DemoAssignment, Invitation, Outbox, User, aware, utcnow
from app.club_snapshot import import_snapshot, normalise_snapshot
from app.planning import run_planning, generate_shifts, valid_shift

TZ = ZoneInfo('Europe/Amsterdam')


def snapshot():
    day = (utcnow().astimezone(TZ)+timedelta(days=7)).replace(hour=15, minute=0, second=0, microsecond=0)
    return {'source_url':'https://www.ascsdw.nl/116/programma/', 'sha256':'a'*64,
            'verified_at':utcnow().isoformat(), 'coverage_dates':[day.date().isoformat()],
            'cancellation_check':'no_cancellations_published',
            'venue_evidence':{'07':'https://www.ascsdw.nl/113/34926/uitslagen/wedstrijd-details/'},
            'fixtures':[{'source_url':'https://www.ascsdw.nl/113/34926/uitslagen/wedstrijd-details/',
                         'home_team':'ASC SDW MO17-1', 'away_team':"Geel Wit '20 sv. MO17-1",
                         'kickoff':day.isoformat(), 'field':'(07)veld 1-SDW',
                         'venue':'Sportpark Spieringhorn', 'city':'Amsterdam', 'status':'scheduled'}]}


def test_verified_snapshot_real_fixtures_fictional_staffing_and_history(db, users, monkeypatch):
    from test_system import fixture, shift
    monkeypatch.setattr(settings(), 'demo_staffing_enabled', True)
    fake = fixture(db)
    old = shift(db, fake)
    payload = snapshot()
    result = import_snapshot(db, payload)
    assert result == {'state':'imported','count':1,'new_shifts':5,'fictional_assignments':15}
    assert old.state=='cancelled' and fake.status=='review' and db.get(Fixture,fake.id)
    actual = db.scalar(select(Fixture).where(Fixture.source=='club_snapshot'))
    assert not actual.is_demo and actual.is_home and actual.venue_id==1
    active = list(db.scalars(select(Shift).where(Shift.state=='open').order_by(Shift.starts_at)))
    assert all(s.is_demo and valid_shift(db,s) and s.capacity==3 for s in active)
    assert aware(active[0].starts_at).astimezone(TZ).strftime('%H:%M')=='08:00'
    assert aware(active[-1].ends_at).astimezone(TZ).strftime('%H:%M')=='18:00'
    run_planning(db)
    assert generate_shifts(db)==0
    assert db.scalar(select(func.count()).select_from(Invitation))==0
    assert db.scalar(select(func.count()).select_from(Outbox))==0
    assert import_snapshot(db,payload)=={'state':'already_imported','count':1}
    assert db.scalar(select(func.count()).select_from(DemoAssignment))==15
    assert db.get(User,1).name=='Parent 1'


@pytest.mark.parametrize('change', ['away','venue','pitch','date','duplicate','name','old','status'])
def test_snapshot_rejects_unverified_or_ambiguous_values(change, db):
    p = snapshot(); r=p['fixtures'][0]
    if change=='away':r['home_team']='Other club'
    if change=='venue':r['venue']='Other park'
    if change=='pitch':r['field']='(99)veld 99-SDW'
    if change=='date':p['coverage_dates']=['2000-01-01']
    if change=='duplicate':p['fixtures'].append(deepcopy(r))
    if change=='name':r['away_team']='Truncated...'
    if change=='old':p['verified_at']=(utcnow()-timedelta(days=2)).isoformat()
    if change=='status':p['cancellation_check']='not_checked'
    with pytest.raises(ValueError):import_snapshot(db,p)
    assert db.scalar(select(func.count()).select_from(Fixture))==0


def test_snapshot_api_source_provenance_and_demo_visibility(client, db, users, monkeypatch):
    from test_system import fixture, signin
    monkeypatch.setattr(settings(), 'demo_staffing_enabled', True)
    fixture(db)
    import_snapshot(db,snapshot())
    signin(client,'admin','Coordinator-Test-Password!')
    data=client.get('/api/dashboard').json()
    assert len(data['fixtures'])==1 and not data['fixtures'][0]['is_demo']
    assert data['fixtures'][0]['source_url'].startswith('https://www.ascsdw.nl/113/')
    assert data['fixture_snapshot']['automatic_feed'] is False
    assert data['demo_mode'] is True


def test_two_day_local_kickoffs_keep_correct_closing_block(db, users, monkeypatch):
    monkeypatch.setattr(settings(), 'demo_staffing_enabled', True)
    p=snapshot()
    second=deepcopy(p['fixtures'][0])
    second['source_url']='https://www.ascsdw.nl/113/33896/uitslagen/wedstrijd-details/'
    first_time=datetime.fromisoformat(second['kickoff'])
    second_time=(first_time+timedelta(days=1)).replace(hour=14)
    second['kickoff']=second_time.isoformat()
    p['fixtures'].append(second)
    p['coverage_dates'].append(second_time.date().isoformat())
    assert import_snapshot(db,p)['new_shifts']==9
    rows=list(db.scalars(select(Shift).where(Shift.state=='open').order_by(Shift.starts_at)))
    assert aware(rows[-1].ends_at).astimezone(TZ).strftime('%H:%M')=='16:00'
    assert aware(rows[4].ends_at).astimezone(TZ).strftime('%H:%M')=='18:00'
