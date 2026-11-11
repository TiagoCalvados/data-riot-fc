from datetime import datetime, timedelta
from pathlib import Path
import secrets
import re
from typing import Literal
from zoneinfo import ZoneInfo
from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select, func, delete, text
from sqlalchemy.orm import Session
from app import __version__
from app.config import settings
from app.db import get_db
from app.models import (User, Team, ParentTeam, Fixture, Venue, Shift, Invitation, Outbox,
                        LoginSession, LoginAttempt, Unavailability, AuditEvent, SyncRun, JobRun, DemoAssignment,
                        utcnow, aware)
from app.security import password_hash, verify_password, digest, new_token, DUMMY_HASH, hasher
from app.planning import (planning_lock, policy, audit, generate_shifts, fill_shift, expire_invitations,
                          run_planning, respond, cancel_shift, cancel_invitation, reconcile_days, LIVE)
from app.mailer import deliver_outbox
from app.fixtures import sync_sportlink

ROOT = Path(__file__).parent
app = FastAPI(title='SDW Kantine', version=__version__, docs_url=None, redoc_url=None, openapi_url=None)
app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')


@app.middleware('http')
async def security_headers(request: Request, call_next):
    # Browser writes must originate at this app. Non-browser API clients still need session + CSRF.
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        origin = request.headers.get('origin')
        if origin and origin.rstrip('/') != settings().base_url.rstrip('/'):
            return JSONResponse({'detail': 'Ongeldige oorsprong.'}, status_code=403)
        if request.headers.get('sec-fetch-site') == 'cross-site':
            return JSONResponse({'detail': 'Ongeldige oorsprong.'}, status_code=403)
    response = await call_next(request)
    response.headers.update({
        'X-Content-Type-Options': 'nosniff', 'X-Frame-Options': 'DENY',
        'Referrer-Policy': 'no-referrer', 'Cache-Control': 'no-store',
        'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
        'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
    })
    if settings().cookie_secure:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000'
    return response


def current_user(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get('sdw_session', '')
    login = db.scalar(select(LoginSession).where(LoginSession.token_hash == digest(token), LoginSession.expires_at > utcnow())) if token else None
    user = db.get(User, login.user_id) if login else None
    if not user or not user.active:
        raise HTTPException(401, 'Log in om verder te gaan.')
    if request.method not in ('GET', 'HEAD') and not secrets.compare_digest(request.headers.get('x-csrf-token', ''), login.csrf):
        raise HTTPException(403, 'Je sessie is gewijzigd. Vernieuw de pagina.')
    request.state.login = login
    return user


def admin(user: User = Depends(current_user)):
    if user.role != 'admin':
        raise HTTPException(403, 'Alleen toegankelijk voor de coördinator.')
    return user


from app.analytics import analytics_router
app.include_router(analytics_router(admin))


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


@app.post('/api/login')
def login(body: LoginBody, request: Request, response: Response, db: Session = Depends(get_db)):
    username = body.username.strip().lower()
    keys = [(digest('account:' + username), 10), (digest('ip:' + (request.client.host if request.client else 'unknown')), 60)]
    cutoff = utcnow() - timedelta(minutes=15)
    for key, limit in keys:
        count = db.scalar(select(func.count()).select_from(LoginAttempt).where(LoginAttempt.key == key, LoginAttempt.created_at > cutoff))
        if count >= limit:
            raise HTTPException(429, 'Te veel pogingen. Probeer het over 15 minuten opnieuw.')
    user = db.scalar(select(User).where(User.username == username))
    ok = verify_password(user.password_hash if user else DUMMY_HASH, body.password)
    if not ok or not user or not user.active:
        for key, _ in keys:
            db.add(LoginAttempt(key=key))
        db.commit()
        raise HTTPException(401, 'Gebruikersnaam of wachtwoord klopt niet.')
    if hasher.check_needs_rehash(user.password_hash):
        user.password_hash = password_hash(body.password)
    selected_language = request.cookies.get('sdw_language')
    if selected_language in ('nl', 'en'):
        user.language = selected_language
    # Rotate a pre-existing session on successful authentication.
    old = request.cookies.get('sdw_session')
    if old:
        db.execute(delete(LoginSession).where(LoginSession.token_hash == digest(old)))
    token, csrf = new_token(), new_token()
    db.add(LoginSession(user_id=user.id, token_hash=digest(token), csrf=csrf, expires_at=utcnow() + timedelta(hours=8)))
    db.commit()
    response.set_cookie('sdw_session', token, httponly=True, secure=settings().cookie_secure, samesite='lax', max_age=8 * 3600, path='/')
    return {'csrf': csrf, 'user': user_view(user)}


@app.post('/api/logout')
def logout(request: Request, response: Response, user=Depends(current_user), db: Session = Depends(get_db)):
    db.delete(request.state.login)
    db.commit()
    response.delete_cookie('sdw_session', path='/')
    return {'ok': True}


@app.get('/api/me')
def me(request: Request, user=Depends(current_user)):
    return {'user': user_view(user), 'csrf': request.state.login.csrf}


def user_view(user):
    return {'id': user.id, 'username': user.username, 'name': user.name, 'role': user.role,
            'email': user.email, 'active': user.active, 'volunteering': user.volunteering, 'is_demo': user.is_demo,
            'language': user.language}


class LanguageBody(BaseModel):
    language: Literal['nl', 'en']


@app.post('/api/language')
def update_language(body: LanguageBody, response: Response, user=Depends(current_user), db: Session = Depends(get_db)):
    user.language = body.language
    db.commit()
    response.set_cookie('sdw_language', body.language, secure=settings().cookie_secure, samesite='lax', max_age=31536000)
    return {'ok': True}


def fixture_view(f):
    return {'id': f.id, 'team_id': f.team_id, 'home_team': f.home_team, 'away_team': f.away_team,
            'kickoff': aware(f.kickoff).isoformat(), 'venue': f.venue_text, 'city': f.city,
            'is_home': f.is_home, 'status': f.status, 'source': f.source, 'is_demo': f.is_demo,
            'source_url': ('https://www.ascsdw.nl/113/'+f.external_id.split(':', 1)[1]+'/uitslagen/wedstrijd-details/'
                           if f.source == 'club_snapshot' and f.external_id.startswith('ascsdw:') else None),
            'verified_at': aware(f.verified_at).isoformat(), 'home_venue_approved': f.venue_id is not None}


@app.get('/api/dashboard')
def dashboard(user=Depends(current_user), db: Session = Depends(get_db)):
    is_admin = user.role == 'admin'
    now = utcnow()
    shifts = list(db.scalars(select(Shift).where(Shift.ends_at > now - timedelta(days=30)).order_by(Shift.starts_at)))
    invitations = list(db.scalars(select(Invitation)))
    demo_assignments = list(db.scalars(select(DemoAssignment)))
    users = {p.id: p for p in db.scalars(select(User))}
    shift_rows = []
    for s in shifts:
        own = [i for i in invitations if i.shift_id == s.id and i.user_id == user.id]
        demo_rows = [a for a in demo_assignments if a.shift_id == s.id]
        own_demo = [a for a in demo_rows if a.person_key == f'demo-user:{user.id}']
        if not is_admin and not own and not own_demo:
            continue
        rows = [i for i in invitations if i.shift_id == s.id and (is_admin or i.user_id == user.id)]
        shift_rows.append({'id': s.id, 'starts_at': aware(s.starts_at).isoformat(), 'ends_at': aware(s.ends_at).isoformat(),
            'capacity': s.capacity, 'state': s.state, 'note': s.note, 'is_demo': s.is_demo,
            'demo_assigned': len(demo_rows),
            'demo_assignments': [{'name': a.name, 'fictional': True} for a in (demo_rows if is_admin else own_demo)],
            'confirmed': sum(i.shift_id == s.id and i.state in ('confirmed', 'completed') for i in invitations),
            'waiting': sum(i.shift_id == s.id and i.state in ('queued', 'pending') for i in invitations),
            'invitations': [{'id': i.id, 'user_id': i.user_id, 'name': users[i.user_id].name,
                             'state': 'expired' if i.state == 'pending' and i.expires_at and aware(i.expires_at) <= now else i.state,
                             'expires_at': aware(i.expires_at).isoformat() if i.expires_at else None} for i in rows]})
    snapshot = db.scalar(select(AuditEvent).where(AuditEvent.action == 'fixture.snapshot_imported').order_by(AuditEvent.id.desc()).limit(1))
    fixture_query = select(Fixture).where(Fixture.kickoff >= now - timedelta(days=7))
    if snapshot:
        fixture_query = fixture_query.where(Fixture.is_demo.is_(False))
    fixtures = list(db.scalars(fixture_query.order_by(Fixture.kickoff)))
    p = policy(db)
    sync = db.scalar(select(SyncRun).order_by(SyncRun.id.desc()).limit(1))
    job = db.scalar(select(JobRun).order_by(JobRun.id.desc()).limit(1))
    data = {'user': user_view(user), 'shifts': shift_rows, 'fixtures': [fixture_view(f) for f in fixtures],
        'teams': [{'id': t.id, 'name': t.name} for t in db.scalars(select(Team).order_by(Team.name))],
        'policy': {k: getattr(p, k) for k in ('min_gap_days', 'volunteers_per_shift', 'shift_minutes', 'lookahead_days', 'response_hours', 'automation_enabled')},
        'demo_mode': settings().demo_mode,
        'local_mail_capture': settings().local_mail_capture,
        'fixture_snapshot': ({'source_url': snapshot.detail['source_url'], 'verified_at': snapshot.detail['verified_at'],
                             'coverage_dates': snapshot.detail['coverage_dates'], 'count': snapshot.detail['count'],
                             'automatic_feed': False} if snapshot else None),
        'canteen_opening_hour': settings().canteen_opening_hour,
        'my_unavailability': [{'id': b.id, 'starts_at': aware(b.starts_at).isoformat(), 'ends_at': aware(b.ends_at).isoformat()}
                              for b in db.scalars(select(Unavailability).where(Unavailability.user_id == user.id, Unavailability.ends_at > now))]}
    if is_admin:
        data.update({'parents': [{**user_view(u), 'team_ids': list(db.scalars(select(ParentTeam.team_id).where(ParentTeam.user_id == u.id))),
                'completed': sum(i.user_id == u.id and i.state == 'completed' for i in invitations),
                'confirmed': sum(i.user_id == u.id and i.state == 'confirmed' for i in invitations),
                'proposals': sum(i.user_id == u.id and i.state != 'cancelled' for i in invitations)} for u in users.values()],
            'integrations': {'smtp_ready': settings().mail_ready, 'fixtures_ready': bool(settings().sportlink_client_id and settings().sportlink_club_code),
                             'last_sync': {'state': sync.state, 'at': aware(sync.created_at).isoformat(), 'count': sync.count, 'detail': sync.detail} if sync else None,
                             'last_job': {'state': job.state, 'at': aware(job.created_at).isoformat()} if job else None},
            'emails': [{'id': m.id, 'parent': users[db.get(Invitation, m.invitation_id).user_id].name,
                        'kind': m.kind, 'state': m.state, 'attempts': m.attempts, 'error': m.error,
                        'sent_at': aware(m.sent_at).isoformat() if m.sent_at else None}
                       for m in db.scalars(select(Outbox).order_by(Outbox.id.desc()).limit(100))],
            'activity': [{'action': e.action, 'detail': e.detail, 'at': aware(e.created_at).isoformat()}
                         for e in db.scalars(select(AuditEvent).order_by(AuditEvent.id.desc()).limit(15))]})
    return data


class DecisionBody(BaseModel):
    decision: Literal['confirmed', 'declined']


@app.get('/api/invitations/by-token/{token}')
def invitation_by_token(token: str, user=Depends(current_user), db: Session = Depends(get_db)):
    invitation = db.scalar(select(Invitation).where(Invitation.token_hash == digest(token), Invitation.user_id == user.id))
    if not invitation:
        raise HTTPException(404, 'Deze uitnodiging hoort niet bij dit account of bestaat niet.')
    return {'id': invitation.id, 'shift_id': invitation.shift_id}


@app.post('/api/invitations/{invitation_id}/respond')
def invitation_response(invitation_id: int, body: DecisionBody, user=Depends(current_user), db: Session = Depends(get_db)):
    with planning_lock(db):
        invitation = db.get(Invitation, invitation_id)
        if not invitation:
            raise HTTPException(404, 'Uitnodiging niet gevonden.')
        respond(db, invitation, user.id, body.decision)
        db.commit()
    return {'ok': True}


class ParentBody(BaseModel):
    username: str = Field(pattern=r'^[a-z0-9._-]{3,80}$')
    name: str = Field(min_length=2, max_length=160)
    email: EmailStr
    password: str = Field(min_length=12, max_length=256)
    language: Literal['nl', 'en'] = 'nl'
    team_ids: list[int] = Field(default_factory=list, max_length=15)


@app.post('/api/admin/parents', status_code=201)
def create_parent(body: ParentBody, actor=Depends(admin), db: Session = Depends(get_db)):
    if db.scalar(select(User.id).where(User.username == body.username)):
        raise HTTPException(409, 'Gebruikersnaam bestaat al.')
    teams = set(db.scalars(select(Team.id)))
    if not set(body.team_ids) <= teams:
        raise HTTPException(422, 'Onbekend team.')
    parent = User(username=body.username, name=body.name, email=str(body.email), password_hash=password_hash(body.password),
                  is_demo=settings().demo_mode, language=body.language)
    db.add(parent)
    db.flush()
    for team_id in set(body.team_ids):
        db.add(ParentTeam(user_id=parent.id, team_id=team_id))
    audit(db, 'parent.created', {'user_id': parent.id}, actor.id)
    db.commit()
    return user_view(parent)


class ParentUpdate(BaseModel):
    active: bool
    volunteering: bool
    language: Literal['nl', 'en'] = 'nl'
    team_ids: list[int] = Field(default_factory=list, max_length=15)


@app.patch('/api/admin/parents/{parent_id}')
def update_parent(parent_id: int, body: ParentUpdate, actor=Depends(admin), db: Session = Depends(get_db)):
    with planning_lock(db):
        parent = db.get(User, parent_id)
        if not parent or parent.role == 'admin':
            raise HTTPException(404, 'Ouder niet gevonden.')
        if not set(body.team_ids) <= set(db.scalars(select(Team.id))):
            raise HTTPException(422, 'Onbekend team.')
        parent.active, parent.volunteering = body.active, body.volunteering
        parent.language = body.language
        db.execute(delete(ParentTeam).where(ParentTeam.user_id == parent_id))
        for team_id in set(body.team_ids):
            db.add(ParentTeam(user_id=parent_id, team_id=team_id))
        if not body.active or not body.volunteering:
            for inv in db.scalars(select(Invitation).where(Invitation.user_id == parent_id, Invitation.state.in_(LIVE))):
                if aware(db.get(Shift, inv.shift_id).starts_at) > utcnow():
                    cancel_invitation(db, inv, 'Ouder uit de vrijwilligerspool gehaald.')
            if not body.active:
                db.execute(delete(LoginSession).where(LoginSession.user_id == parent_id))
        audit(db, 'parent.updated', {'user_id': parent_id}, actor.id)
        db.flush()
        run_planning(db)
        db.commit()
    return {'ok': True}


class PasswordBody(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


@app.post('/api/password')
def change_password(body: PasswordBody, response: Response, user=Depends(current_user), db: Session = Depends(get_db)):
    if not verify_password(user.password_hash, body.current_password):
        raise HTTPException(400, 'Huidig wachtwoord klopt niet.')
    user.password_hash = password_hash(body.new_password)
    db.execute(delete(LoginSession).where(LoginSession.user_id == user.id))
    db.commit()
    response.delete_cookie('sdw_session', path='/')
    return {'ok': True}


class AvailabilityBody(BaseModel):
    starts_at: datetime
    ends_at: datetime

    @field_validator('starts_at', 'ends_at')
    @classmethod
    def timezone_required(cls, value):
        if value.tzinfo is None:
            raise ValueError('Tijdzone ontbreekt.')
        return value


@app.post('/api/unavailability', status_code=201)
def unavailable(body: AvailabilityBody, user=Depends(current_user), db: Session = Depends(get_db)):
    if body.ends_at <= body.starts_at or body.ends_at <= utcnow():
        raise HTTPException(422, 'Kies een geldige toekomstige periode.')
    with planning_lock(db):
        conflicts = list(db.scalars(select(Invitation).join(Shift, Shift.id == Invitation.shift_id).where(
            Invitation.user_id == user.id, Invitation.state.in_(LIVE), Shift.starts_at < body.ends_at,
            Shift.ends_at > body.starts_at, Shift.starts_at > utcnow())))
        if any(i.state == 'confirmed' for i in conflicts):
            raise HTTPException(409, 'Je hebt in deze periode een bevestigde dienst. Neem eerst contact op met de coördinator.')
        for invite in conflicts:
            cancel_invitation(db, invite, 'Ouder is niet beschikbaar.')
        db.add(Unavailability(user_id=user.id, starts_at=body.starts_at, ends_at=body.ends_at))
        audit(db, 'availability.updated', {'user_id': user.id}, user.id)
        db.flush()
        run_planning(db)
        db.commit()
    return {'ok': True}


@app.delete('/api/unavailability/{block_id}')
def remove_unavailability(block_id: int, user=Depends(current_user), db: Session = Depends(get_db)):
    block = db.get(Unavailability, block_id)
    if not block or block.user_id != user.id:
        raise HTTPException(404, 'Periode niet gevonden.')
    db.delete(block)
    db.commit()
    return {'ok': True}


class FixtureBody(BaseModel):
    home_team: str = Field(min_length=2, max_length=160)
    away_team: str = Field(min_length=2, max_length=160)
    kickoff: datetime
    is_home: bool = True
    venue: str = Field(default='Sportpark Spieringhorn', max_length=250)
    city: str = Field(default='Amsterdam', max_length=80)


@app.post('/api/admin/fixtures', status_code=201)
def add_fixture(body: FixtureBody, actor=Depends(admin), db: Session = Depends(get_db)):
    if body.kickoff.tzinfo is None or body.kickoff <= utcnow():
        raise HTTPException(422, 'Kies een toekomstige aftraptijd met tijdzone.')
    own_name = body.home_team if body.is_home else body.away_team
    if not re.match(r'^(ASC\s+)?SDW(?:\s|$)', own_name, re.I):
        raise HTTPException(422, 'De eigen ploeg moet een SDW-team zijn.')
    if body.is_home and ('spieringhorn' not in body.venue.casefold() or not body.city.casefold().startswith('amsterdam')):
        raise HTTPException(422, 'Alleen thuiswedstrijden op Sportpark Spieringhorn, Amsterdam kunnen kantinediensten opleveren.')
    with planning_lock(db):
        team = db.scalar(select(Team).where(Team.name == own_name))
        if not team:
            team = Team(name=own_name)
            db.add(team)
            db.flush()
        f = Fixture(external_id='manual:' + new_token(), source='manual', team_id=team.id,
                    home_team=body.home_team, away_team=body.away_team, kickoff=body.kickoff,
                    venue_id=1 if body.is_home else None, venue_text=body.venue, city=body.city,
                    is_home=body.is_home, is_demo=settings().demo_mode)
        db.add(f)
        db.flush()
        reconcile_days(db, {body.kickoff.astimezone(ZoneInfo('Europe/Amsterdam')).date()})
        audit(db, 'fixture.created', {'fixture_id': f.id}, actor.id)
        db.commit()
    return fixture_view(f)


class FixtureUpdate(BaseModel):
    status: Literal['scheduled', 'cancelled', 'postponed']
    kickoff: datetime | None = None


@app.patch('/api/admin/fixtures/{fixture_id}')
def update_fixture(fixture_id: int, body: FixtureUpdate, actor=Depends(admin), db: Session = Depends(get_db)):
    with planning_lock(db):
        f = db.get(Fixture, fixture_id)
        if not f:
            raise HTTPException(404, 'Wedstrijd niet gevonden.')
        if f.source != 'manual' and not f.is_demo:
            raise HTTPException(409, 'Wijzig deze wedstrijd bij de officiële bron en synchroniseer opnieuw.')
        days = {aware(f.kickoff).astimezone(ZoneInfo('Europe/Amsterdam')).date()}
        if body.kickoff:
            if not body.kickoff.tzinfo or body.kickoff <= utcnow():
                raise HTTPException(422, 'Kies een toekomstige aftraptijd met tijdzone.')
            f.kickoff = body.kickoff
            days.add(body.kickoff.astimezone(ZoneInfo('Europe/Amsterdam')).date())
        f.status = body.status
        f.verified_at = utcnow()
        db.flush()
        reconcile_days(db, days)
        audit(db, 'fixture.updated', {'fixture_id': f.id}, actor.id)
        db.commit()
    return {'ok': True}


class ShiftUpdate(AvailabilityBody):
    capacity: int = Field(ge=1, le=10)
    note: str = Field(default='', max_length=1000)


@app.patch('/api/admin/shifts/{shift_id}')
def update_shift(shift_id: int, body: ShiftUpdate, actor=Depends(admin), db: Session = Depends(get_db)):
    from app.models import ShiftFixture
    from app.planning import linked_fixtures
    with planning_lock(db):
        shift = db.get(Shift, shift_id)
        if not shift or shift.state != 'open' or aware(shift.starts_at) <= utcnow():
            raise HTTPException(404, 'Toekomstige open dienst niet gevonden.')
        if body.ends_at <= body.starts_at or body.ends_at - body.starts_at > timedelta(hours=8):
            raise HTTPException(422, 'Een dienst moet tussen 1 minuut en 8 uur duren.')
        day = body.starts_at.astimezone(ZoneInfo('Europe/Amsterdam')).date()
        fixtures = linked_fixtures(db, shift)
        if any(aware(f.kickoff).astimezone(ZoneInfo('Europe/Amsterdam')).date() != day for f in fixtures):
            raise HTTPException(422, 'De dienst moet op dezelfde thuiswedstrijddag blijven.')
        if body.starts_at <= utcnow() or body.ends_at.astimezone(ZoneInfo('Europe/Amsterdam')).date() != day:
            raise HTTPException(422, 'Kies een toekomstige dienst binnen dezelfde dag.')
        opening = datetime.combine(day, datetime.min.time(), ZoneInfo('Europe/Amsterdam')).replace(hour=settings().canteen_opening_hour)
        closing = max((aware(f.kickoff) + timedelta(hours=2) for f in fixtures), default=opening)
        if not (opening < body.ends_at and closing > body.starts_at):
            raise HTTPException(422, 'De dienst moet aansluiten op de thuiswedstrijd.')
        cancel_shift(db, shift, 'Dienst aangepast door de coördinator.')
        # Keep old invitation history on the old shift; new offers need fresh identities.
        replacement = Shift(venue_id=shift.venue_id, starts_at=body.starts_at, ends_at=body.ends_at,
                            capacity=body.capacity, note=body.note, managed=False, is_demo=shift.is_demo)
        db.add(replacement)
        db.flush()
        for f in fixtures:
            db.add(ShiftFixture(shift_id=replacement.id, fixture_id=f.id))
        audit(db, 'shift.updated', {'shift_id': shift_id, 'replacement_id': replacement.id}, actor.id)
        db.commit()
    return {'ok': True}


@app.post('/api/admin/shifts/{shift_id}/cancel')
def shift_cancel(shift_id: int, actor=Depends(admin), db: Session = Depends(get_db)):
    with planning_lock(db):
        shift = db.get(Shift, shift_id)
        if not shift or aware(shift.starts_at) <= utcnow():
            raise HTTPException(404, 'Toekomstige dienst niet gevonden.')
        cancel_shift(db, shift, 'Geannuleerd door coördinator.')
        audit(db, 'shift.cancelled', {'shift_id': shift_id}, actor.id)
        db.commit()
    return {'ok': True}


class AttendanceBody(BaseModel):
    state: Literal['completed', 'no_show']


@app.post('/api/admin/invitations/{invitation_id}/attendance')
def attendance(invitation_id: int, body: AttendanceBody, actor=Depends(admin), db: Session = Depends(get_db)):
    with planning_lock(db):
        i = db.get(Invitation, invitation_id)
        if not i or i.state != 'confirmed' or aware(db.get(Shift, i.shift_id).ends_at) > utcnow():
            raise HTTPException(409, 'Aanwezigheid kan pas na een bevestigde dienst worden vastgelegd.')
        i.state, i.completed_at = body.state, utcnow()
        audit(db, 'attendance.' + body.state, {'invitation_id': i.id}, actor.id)
        db.commit()
    return {'ok': True}


class PolicyBody(BaseModel):
    min_gap_days: int = Field(ge=1, le=90)
    volunteers_per_shift: int = Field(ge=1, le=10)
    shift_minutes: int = Field(ge=30, le=480)
    lookahead_days: int = Field(ge=7, le=42)
    response_hours: int = Field(ge=1, le=48)
    automation_enabled: bool


@app.put('/api/admin/policy')
def update_policy(body: PolicyBody, actor=Depends(admin), db: Session = Depends(get_db)):
    if body.automation_enabled and not settings().demo_mode and not settings().mail_ready:
        raise HTTPException(409, 'Configureer eerst SMTP voordat je automatisch uitnodigt.')
    with planning_lock(db):
        p = policy(db)
        for k, v in body.model_dump().items():
            setattr(p, k, v)
        audit(db, 'policy.updated', body.model_dump(), actor.id)
        db.commit()
    return {'ok': True}


@app.post('/api/admin/plan')
def plan(actor=Depends(admin), db: Session = Depends(get_db)):
    with planning_lock(db):
        count = generate_shifts(db)
        result = run_planning(db)
        sent = deliver_outbox(db)
        audit(db, 'planning.run', {'shifts': count, **result, 'emails': sent}, actor.id)
        db.commit()
    return {'shifts': count, **result, 'emails': sent}


@app.post('/api/admin/sync')
def sync(actor=Depends(admin), db: Session = Depends(get_db)):
    with planning_lock(db):
        result = sync_sportlink(db)
        db.commit()
    return result


@app.get('/health')
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text('SELECT 1'))
        return {'status': 'ok'}
    except Exception:
        return JSONResponse({'status': 'unavailable'}, status_code=503)


@app.get('/')
def index(request: Request):
    language = request.query_params.get('lang', request.cookies.get('sdw_language', 'nl'))
    language = language if language in ('nl', 'en') else 'nl'
    response = FileResponse(ROOT / 'static' / ('index.en.html' if language == 'en' else 'index.html'))
    if request.query_params.get('lang') in ('nl', 'en'):
        response.set_cookie('sdw_language', language, secure=settings().cookie_secure, samesite='lax', max_age=31536000)
    return response
