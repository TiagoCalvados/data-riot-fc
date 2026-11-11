from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import json
import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import select, func
from app.models import (User, Team, Fixture, Shift, ShiftFixture, Invitation, Unavailability,
                        Outbox, LoginSession, aware, utcnow)
from app.security import password_hash, verify_password, digest, decrypt_payload, new_token
from app.planning import (generate_shifts, fill_shift, candidate_parents, expire_invitations,
                          respond, policy, run_planning, cancel_shift, reconcile_days)
from app.mailer import deliver_outbox
from app.fixtures import normalise_fixture, sync_sportlink
from app.config import settings


def fixture(db, days=7, *, home=True, status='scheduled', approved=True, demo=True):
    team = db.scalar(select(Team))
    if not team:
        team = Team(name='SDW JO12-1')
        db.add(team)
        db.flush()
    start = (utcnow() + timedelta(days=days)).replace(hour=11, minute=0, second=0, microsecond=0)
    f = Fixture(external_id=new_token(), source='manual', team_id=team.id, venue_id=1 if approved else None,
        home_team=team.name if home else 'AFC JO12-1', away_team='AFC JO12-1' if home else team.name,
        kickoff=start, venue_text='Sportpark Spieringhorn', city='Amsterdam', is_home=home, status=status, is_demo=demo)
    db.add(f)
    db.flush()
    return f


def shift(db, f, capacity=1):
    s = Shift(venue_id=1, starts_at=f.kickoff-timedelta(minutes=30), ends_at=f.kickoff+timedelta(hours=1),
              capacity=capacity, is_demo=f.is_demo)
    db.add(s)
    db.flush()
    db.add(ShiftFixture(shift_id=s.id, fixture_id=f.id))
    db.flush()
    return s


def signin(client, username='parent1', password='Test-Password-4-Parents!'):
    r = client.post('/api/login', json={'username': username, 'password': password})
    assert r.status_code == 200, r.text
    return {'X-CSRF-Token': r.json()['csrf']}


def test_argon2_unique_salt():
    a, b = password_hash('same-password-value'), password_hash('same-password-value')
    assert a != b and a.startswith('$argon2id$')
    assert verify_password(a, 'same-password-value')
    assert not verify_password(a, 'wrong-password')


def test_only_home_games_at_approved_venue_generate_shifts(db):
    fixture(db, 7, home=False)
    fixture(db, 8, status='cancelled')
    fixture(db, 9, approved=False)
    fixture(db, 10)
    count = generate_shifts(db)
    assert count >= 2
    assert generate_shifts(db) == 0
    assert len(list(db.scalars(select(Shift)))) == count
    for s in db.scalars(select(Shift)):
        assert aware(s.starts_at).date() == (utcnow()+timedelta(days=10)).date()


def test_unavailable_parents_are_skipped(db, users):
    f = fixture(db)
    s = shift(db, f)
    db.add(Unavailability(user_id=1, starts_at=s.starts_at-timedelta(hours=1), ends_at=s.ends_at+timedelta(hours=1)))
    db.flush()
    assert candidate_parents(db,s)[0].id == 2


def test_fairness_no_adjacent_matchdays_even_after_large_gap(db, users):
    f1, f2 = fixture(db,7), fixture(db,28)
    s1, s2 = shift(db,f1), shift(db,f2)
    assert fill_shift(db,s1) == 1
    assert candidate_parents(db,s2)[0].id == 2  # Gap is 21 days, but still the next home matchday.
    assert all(p.id != 1 for p in candidate_parents(db,s2))


def test_min_gap_counts_declines_and_expiries(db, users):
    f1, f2, f3 = fixture(db,7), fixture(db,10), fixture(db,14)
    s1, s2, s3 = shift(db,f1), shift(db,f2), shift(db,f3)
    fill_shift(db,s1)
    i = db.scalar(select(Invitation))
    i.state = 'declined'
    db.flush()
    assert 1 not in [p.id for p in candidate_parents(db,s3)]  # Non-adjacent but only seven days apart.


def test_confirmation_token_is_hashed_and_outbox_encrypted(db, users):
    s = shift(db, fixture(db))
    fill_shift(db,s)
    i, mail = db.scalar(select(Invitation)), db.scalar(select(Outbox))
    assert i.state == 'queued' and i.expires_at is None
    assert 'https' not in mail.encrypted_payload and 'invitation=' not in mail.encrypted_payload
    payload = decrypt_payload(mail.encrypted_payload)
    token = payload['body'].split('invitation=')[1].split()[0]
    assert digest(token) == i.token_hash


def test_no_reply_48_hours_then_next_parent(db, users):
    s = shift(db, fixture(db))
    fill_shift(db,s)
    assert deliver_outbox(db) == 1
    i = db.scalar(select(Invitation))
    assert i.state == 'pending'
    assert 47.99 <= (aware(i.expires_at)-aware(i.sent_at)).total_seconds()/3600 <= 48
    assert expire_invitations(db, aware(i.expires_at)-timedelta(seconds=1)) == 0
    assert expire_invitations(db, aware(i.expires_at)) == 1
    assert fill_shift(db,s) == 1
    assert list(db.scalars(select(Invitation.user_id).order_by(Invitation.id))) == [1,2]


def test_refusal_replaces_parent_and_never_overbooks(db, users):
    s = shift(db, fixture(db), capacity=2)
    assert fill_shift(db,s) == 2
    assert fill_shift(db,s) == 0
    deliver_outbox(db)
    i = db.scalar(select(Invitation).order_by(Invitation.id))
    respond(db,i,1,'declined')
    live = list(db.scalars(select(Invitation).where(Invitation.state.in_(('queued','pending','confirmed')))))
    assert len(live) == 2 and {x.user_id for x in live} == {2,3}
    assert fill_shift(db,s) == 0


def test_expired_link_cannot_confirm_before_job(db, users):
    s = shift(db,fixture(db))
    fill_shift(db,s)
    deliver_outbox(db)
    i = db.scalar(select(Invitation))
    i.expires_at = utcnow()-timedelta(seconds=1)
    with pytest.raises(HTTPException) as e:
        respond(db,i,1,'confirmed')
    assert e.value.status_code == 409


def test_replayed_and_other_parents_responses_rejected(db, users):
    s = shift(db,fixture(db))
    fill_shift(db,s)
    deliver_outbox(db)
    i = db.scalar(select(Invitation))
    with pytest.raises(HTTPException) as e:
        respond(db,i,2,'confirmed')
    assert e.value.status_code == 404
    respond(db,i,1,'confirmed')
    with pytest.raises(HTTPException) as e:
        respond(db,i,1,'declined')
    assert e.value.status_code == 409


def test_cancellation_invalidates_invitation_and_queues_notice(db, users):
    s = shift(db, fixture(db))
    fill_shift(db,s)
    deliver_outbox(db)
    i = db.scalar(select(Invitation))
    respond(db,i,1,'confirmed')
    cancel_shift(db,s,'Match cancelled')
    db.flush()
    assert i.state == 'cancelled'
    assert db.scalar(select(Outbox).where(Outbox.kind=='cancellation'))


def test_matchday_changes_cancel_confirmations_and_replan(db, users):
    f = fixture(db)
    s = shift(db,f)
    fill_shift(db,s)
    deliver_outbox(db)
    i=db.scalar(select(Invitation))
    respond(db,i,1,'confirmed')
    old_day=aware(f.kickoff).astimezone(ZoneInfo('Europe/Amsterdam')).date()
    f.kickoff+=timedelta(hours=1)
    db.flush()
    reconcile_days(db,{old_day})
    assert s.state=='cancelled' and i.state=='cancelled'
    replacements = list(db.scalars(select(Shift).where(Shift.state=='open').order_by(Shift.starts_at)))
    assert replacements and aware(replacements[0].starts_at).astimezone(ZoneInfo('Europe/Amsterdam')).hour == 8
    assert aware(replacements[-1].ends_at) >= aware(f.kickoff) + timedelta(hours=2)


def test_automation_can_be_paused(db, users):
    shift(db,fixture(db))
    policy(db).automation_enabled=False
    assert run_planning(db)['proposed']==0


def test_manual_cancellation_is_not_undone_by_cron(db):
    fixture(db)
    generate_shifts(db)
    for s in db.scalars(select(Shift)):
        cancel_shift(db,s,'Geannuleerd door coördinator.')
    db.flush()
    assert generate_shifts(db)==0


def test_no_eligible_parent_leaves_slot_open(db,users):
    s=shift(db,fixture(db))
    for u in db.scalars(select(User)):
        u.volunteering=False
    db.flush()
    assert fill_shift(db,s)==0
    assert not list(db.scalars(select(Invitation)))


def test_smtp_failure_retries_without_consuming_parent_reply_window(db,users,monkeypatch):
    import smtplib
    from app.config import settings
    cfg=settings()
    for key,value in {'demo_mode':False,'smtp_host':'smtp.example.org','smtp_username':'sender@example.org',
                      'smtp_password':'fake-token','smtp_from':'sender@example.org'}.items():
        monkeypatch.setattr(cfg,key,value)
    parent=db.get(User,1);parent.is_demo=False;parent.email='parent@example.org'
    s=shift(db,fixture(db,demo=False));fill_shift(db,s)
    def fail(*args,**kwargs):
        raise smtplib.SMTPAuthenticationError(535,b'fake-token must not be logged')
    assert deliver_outbox(db,smtp_factory=fail)==0
    invitation=db.scalar(select(Invitation));outbox=db.scalar(select(Outbox))
    assert invitation.state=='queued' and invitation.expires_at is None
    assert outbox.attempts==1 and aware(outbox.next_attempt_at)>utcnow()
    assert 'fake-token' not in outbox.error


def test_smtp_success_sets_delivery_deadline_and_uses_verified_tls(db,users,monkeypatch):
    cfg=settings()
    for key,value in {'demo_mode':False,'smtp_host':'smtp.example.org','smtp_username':'sender@example.org',
                      'smtp_password':'fake-token','smtp_from':'sender@example.org'}.items():
        monkeypatch.setattr(cfg,key,value)
    parent=db.get(User,1);parent.is_demo=False;parent.email='parent@example.org'
    s=shift(db,fixture(db,demo=False));fill_shift(db,s)
    calls=[]
    class FakeSMTP:
        def __init__(self,*args,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def ehlo(self):calls.append('ehlo')
        def starttls(self,context):
            import ssl
            assert context.verify_mode==ssl.CERT_REQUIRED
            calls.append('tls')
        def login(self,*args):calls.append('login')
        def send_message(self,msg):
            assert msg['To']=='parent@example.org' and 'invitation=' in msg.get_content()
            calls.append('send')
    assert deliver_outbox(db,smtp_factory=FakeSMTP)==1
    assert calls==['ehlo','tls','ehlo','login','send']
    assert db.scalar(select(Invitation)).state=='pending'
    assert db.scalar(select(Outbox)).state=='sent'


def test_demo_emails_never_call_smtp(db, users):
    shift1=shift(db,fixture(db))
    fill_shift(db,shift1)
    def forbidden(*args,**kwargs):
        raise AssertionError('Demo mail tried to leave app')
    assert deliver_outbox(db,smtp_factory=forbidden)==1
    m=db.scalar(select(Outbox))
    assert m.state=='simulated' and m.encrypted_payload==''


def test_real_mail_config_missing_never_starts_response_clock(db, users):
    db.get(User,1).is_demo=False
    s=shift(db,fixture(db,demo=False))
    fill_shift(db,s)
    assert deliver_outbox(db)==0
    i=db.scalar(select(Invitation))
    assert i.state=='queued' and i.expires_at is None


def test_stale_feed_pauses_queued_email_without_rotating_parents(db,users):
    f=fixture(db)
    s=shift(db,f)
    fill_shift(db,s)
    f.source='sportlink';f.is_demo=False;s.is_demo=False
    f.verified_at=utcnow()-timedelta(hours=25)
    db.flush()
    invitation=db.scalar(select(Invitation))
    assert deliver_outbox(db)==0
    assert invitation.state=='queued'
    assert '24 uur' in db.scalar(select(Outbox)).error


def test_login_csrf_privacy_and_role_access(client, db, users):
    assert client.get('/api/dashboard').status_code==401
    headers=signin(client)
    assert client.post('/api/admin/plan',headers=headers).status_code==403
    assert client.post('/api/logout').status_code==403
    r=client.get('/api/dashboard')
    assert r.status_code==200 and 'parents' not in r.json() and 'emails' not in r.json()
    assert 'password_hash' not in r.text
    assert 'HttpOnly' in client.post('/api/login',json={'username':'parent1','password':'Test-Password-4-Parents!'}).headers['set-cookie']
    assert client.post('/api/logout',headers=signin(client)).status_code==200
    assert client.get('/api/me').status_code==401


def test_cross_origin_write_rejected(client,users):
    assert client.post('/api/login',json={'username':'parent1','password':'x'},headers={'Origin':'https://evil.example'}).status_code==403


def test_bad_logins_are_rate_limited(client,users):
    for _ in range(10):
        assert client.post('/api/login',json={'username':'parent1','password':'bad'}).status_code==401
    assert client.post('/api/login',json={'username':'parent1','password':'bad'}).status_code==429


def test_get_invitation_does_not_accept_and_requires_own_login(client,db,users):
    s=shift(db,fixture(db));fill_shift(db,s)
    i=db.scalar(select(Invitation));mail=db.scalar(select(Outbox))
    token=decrypt_payload(mail.encrypted_payload)['body'].split('invitation=')[1].split()[0]
    deliver_outbox(db)
    assert client.get('/api/invitations/by-token/'+token).status_code==401
    signin(client)
    assert client.get('/api/invitations/by-token/'+token).status_code==200
    assert i.state=='pending'
    signin(client,'parent2')
    assert client.get('/api/invitations/by-token/'+token).status_code==404


def test_admin_can_create_parent_and_real_password_is_only_hash(client,db,users):
    h=signin(client,'admin','Coordinator-Test-Password!')
    r=client.post('/api/admin/parents',headers=h,json={'username':'new.parent','name':'New Parent','email':'new@example.org','password':'New-Long-Password-234'})
    assert r.status_code==201,r.text
    u=db.scalar(select(User).where(User.username=='new.parent'))
    assert u.password_hash.startswith('$argon2id$') and u.password_hash!='New-Long-Password-234'
    assert client.post('/api/admin/parents',headers=h,json={'username':'short','name':'Test','email':'a@example.org','password':'short'}).status_code==422


def test_fixture_api_rejects_away_as_home_wrong_venue_and_naive_time(client,users):
    h=signin(client,'admin','Coordinator-Test-Password!')
    base={'home_team':'SDW JO12-1','away_team':'AFC JO12-1','kickoff':(utcnow()+timedelta(days=7)).isoformat()}
    assert client.post('/api/admin/fixtures',headers=h,json={**base,'venue':'Other venue'}).status_code==422
    assert client.post('/api/admin/fixtures',headers=h,json={**base,'home_team':'AFC JO12-1'}).status_code==422
    assert client.post('/api/admin/fixtures',headers=h,json={**base,'kickoff':'2030-01-05T12:00:00'}).status_code==422
    assert client.post('/api/admin/fixtures',headers=h,json=base).status_code==201


def test_password_change_revokes_all_sessions(client,db,users):
    h=signin(client)
    r=client.post('/api/password',headers=h,json={'current_password':'Test-Password-4-Parents!','new_password':'A-different-password-987'})
    assert r.status_code==200 and client.get('/api/me').status_code==401
    assert not list(db.scalars(select(LoginSession).where(LoginSession.user_id==1)))


def test_sportlink_normalisation_home_away_venue_time_and_cancellations():
    row={'wedstrijdcode':'123','wedstrijddatum':'2026-11-14T10:00:00+01:00','thuisteam':'SDW JO12-1','uitteam':'AFC JO12-1',
         'thuisteamclubrelatiecode':'CLUB','uitteamclubrelatiecode':'OTHER','accommodatie':'Sportpark Spieringhorn','plaats':'Amsterdam','status':'Afgelast'}
    parsed=normalise_fixture(row,'CLUB')
    assert parsed['is_home'] and parsed['status']=='cancelled' and parsed['kickoff'].utcoffset()==timedelta(hours=1)
    assert not normalise_fixture(row,'OTHER')['is_home']
    with pytest.raises(ValueError):normalise_fixture(row,'WRONG')


def test_feed_failure_retains_existing_fixtures(db,monkeypatch):
    f=fixture(db)
    config=settings()
    monkeypatch.setattr(config,'sportlink_client_id','test-id')
    monkeypatch.setattr(config,'sportlink_club_code','CLUB')
    transport=httpx.MockTransport(lambda request:httpx.Response(503))
    assert sync_sportlink(db,transport)['state']=='failed'
    assert f.status=='scheduled'


def test_feed_sync_and_explicit_cancellation_invalidate_invites(db,users,monkeypatch):
    config=settings()
    monkeypatch.setattr(config,'sportlink_client_id','test-id')
    monkeypatch.setattr(config,'sportlink_club_code','CLUB')
    future=(utcnow()+timedelta(days=7)).isoformat()
    row={'wedstrijdcode':'456','wedstrijddatum':future,'thuisteam':'SDW JO12-1','uitteam':'AFC JO12-1',
         'thuisteamclubrelatiecode':'CLUB','accommodatie':'Sportpark Spieringhorn','plaats':'Amsterdam','status':'Gepland'}
    transport=httpx.MockTransport(lambda r:httpx.Response(200,json=[row]))
    assert sync_sportlink(db,transport)=={'state':'success','count':1}
    f=db.scalar(select(Fixture));assert f.venue_id==1 and f.is_home
    db.get(User,1).is_demo=False
    s=db.scalar(select(Shift).where(Shift.state=='open'))
    fill_shift(db,s)
    i=db.scalar(select(Invitation));assert i
    row['status']='Afgelast'
    sync_sportlink(db,transport)
    assert i.state=='cancelled' and s.state=='cancelled'


def test_security_headers_and_health(client):
    r=client.get('/')
    assert r.status_code==200 and 'script-src' in r.headers['content-security-policy']
    assert r.headers['referrer-policy']=='no-referrer'
    assert client.get('/health').json()=={'status':'ok'}


def test_mobile_manifest_and_icons(client):
    page=client.get('/?lang=en')
    assert 'viewport-fit=cover' in page.text
    assert 'manifest.webmanifest' in page.text and 'apple-touch-icon' in page.text
    manifest=client.get('/static/manifest.webmanifest').json()
    assert manifest['scope']=='/' and manifest['display']=='standalone'
    assert manifest['name']==manifest['short_name']=='SDW Kantine'
    for icon in manifest['icons']:
        response=client.get(icon['src'])
        assert response.status_code==200 and response.content.startswith(b'\x89PNG\r\n\x1a\n')
        import struct
        width,height=struct.unpack('>II',response.content[16:24])
        assert icon['sizes']==f'{width}x{height}'
    assert page.headers['cache-control']=='no-store'
    assert client.get('/static/icons/apple-touch-icon.png').status_code==200


def test_sdw_branding_is_visible_to_link_preview_crawlers(client):
    from html.parser import HTMLParser
    class Metadata(HTMLParser):
        def __init__(self):
            super().__init__()
            self.meta={}
        def handle_starttag(self,tag,attrs):
            attrs=dict(attrs)
            if tag=='meta':
                self.meta[attrs.get('property',attrs.get('name',''))]=attrs.get('content','')
    for language in ('nl','en'):
        response=client.get('/?lang='+language)
        assert 'Data Riot FC' not in response.text and 'DATA RIOT FC' not in response.text
        metadata=Metadata()
        metadata.feed(response.text)
        assert metadata.meta['og:title'].startswith('SDW Kantine')
        assert metadata.meta['og:site_name']=='SDW Kantine'
        assert metadata.meta['apple-mobile-web-app-title']=='SDW Kantine'
        assert metadata.meta['og:type']=='website'
        image=metadata.meta['og:image']
        assert image.startswith('https://datariotfc.alwaysdata.net/static/branding/')
        from urllib.parse import urlsplit
        logo=client.get(urlsplit(image).path)
        assert logo.status_code==200 and logo.headers['content-type'].startswith('image/jpeg')
        assert metadata.meta['twitter:image']==image
        assert metadata.meta['og:image:width']==metadata.meta['og:image:height']=='400'


def test_language_selection_and_persistence(client,db,users):
    response=client.get('/?lang=en')
    assert '<html lang="en">' in response.text
    assert '/static/app.en.js' in response.text and 'Good to see you.' in response.text
    assert client.cookies['sdw_language']=='en'
    h=signin(client)
    assert db.get(User,1).language=='en'
    assert client.post('/api/language',headers=h,json={'language':'nl'}).status_code==200
    assert db.get(User,1).language=='nl'
    assert '<html lang="nl">' in client.get('/').text
    assert client.post('/api/language',headers=h,json={'language':'fr'}).status_code==422
    assert client.post('/api/language',json={'language':'en'}).status_code==403


def test_parent_receives_invitation_and_cancellation_in_preferred_language(db,users):
    db.get(User,1).language='en'
    s=shift(db,fixture(db));fill_shift(db,s)
    invite=db.scalar(select(Invitation));outbox=db.scalar(select(Outbox))
    message=decrypt_payload(outbox.encrypted_payload)
    assert message['subject']=='SDW • Can you help in the canteen?'
    assert 'Log in and accept or decline' in message['body']
    assert '?lang=en&invitation=' in message['body']
    deliver_outbox(db)
    cancel_shift(db,s,'Test cancellation')
    db.flush()
    cancellation=db.scalar(select(Outbox).where(Outbox.kind=='cancellation'))
    assert 'Your canteen shift has been cancelled' in decrypt_payload(cancellation.encrypted_payload)['subject']


def test_three_parent_default_applies_to_new_shifts(db,users):
    fixture(db)
    generate_shifts(db)
    assert policy(db).volunteers_per_shift==3
    assert all(s.capacity==3 for s in db.scalars(select(Shift)))


def test_parent_language_can_be_set_by_coordinator(client,db,users):
    h=signin(client,'admin','Coordinator-Test-Password!')
    r=client.post('/api/admin/parents',headers=h,json={'username':'english.parent','name':'English Parent',
         'email':'english@example.org','password':'Long-Test-Password-33','language':'en'})
    assert r.status_code==201 and r.json()['language']=='en'
