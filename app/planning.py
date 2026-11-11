"""Deterministic, conservative planning. All writes run under one database lock."""
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, time, timedelta, timezone
import threading
from zoneinfo import ZoneInfo
from sqlalchemy import select, text
from fastapi import HTTPException
from app.config import settings
from app.models import (User, Fixture, Shift, ShiftFixture, Invitation, PlanningPolicy,
                        Outbox, Unavailability, AuditEvent, DemoAssignment, utcnow, aware)
from app.security import new_token, digest, encrypt_payload

TZ = ZoneInfo('Europe/Amsterdam')
LIVE = ('queued', 'pending', 'confirmed')
LOCAL_LOCK = threading.RLock()


@contextmanager
def planning_lock(db):
    # Transaction scoped: web responses, cron, and manual planning serialize together.
    if db.bind.dialect.name == 'postgresql':
        db.execute(text('SELECT pg_advisory_xact_lock(736490271)'))
        yield
    else:
        with LOCAL_LOCK:
            yield


def audit(db, action, detail, actor=None):
    db.add(AuditEvent(action=action, detail=detail, actor_id=actor))


def policy(db):
    return db.scalar(select(PlanningPolicy).where(PlanningPolicy.club_id == 1))


def linked_fixtures(db, shift):
    return list(db.scalars(select(Fixture).join(ShiftFixture, ShiftFixture.fixture_id == Fixture.id)
                           .where(ShiftFixture.shift_id == shift.id)))


def valid_shift(db, shift, now=None, require_fresh=True):
    now = now or utcnow()
    if shift.state != 'open' or aware(shift.starts_at) <= now:
        return False
    fixtures = linked_fixtures(db, shift)
    return bool(fixtures) and all(
        f.is_home and f.venue_id == shift.venue_id and f.status == 'scheduled'
        and (f.is_demo == shift.is_demo or
             (shift.is_demo and not f.is_demo and settings().demo_mode and settings().demo_staffing_enabled))
        and aware(f.kickoff).astimezone(TZ).date() == aware(shift.starts_at).astimezone(TZ).date()
        and (not require_fresh or f.source == 'manual' or f.is_demo or aware(f.verified_at) > now - timedelta(hours=24))
        for f in fixtures)


def queue_notice(db, invitation, kind, token=''):
    parent = db.get(User, invitation.user_id)
    shift = db.get(Shift, invitation.shift_id)
    local_start = aware(shift.starts_at).astimezone(TZ)
    local_end = aware(shift.ends_at).astimezone(TZ)
    when = f'{local_start:%d-%m-%Y %H:%M}–{local_end:%H:%M}'
    language = parent.language or 'nl'
    link = settings().base_url.rstrip('/') + '/?lang=' + language
    if token:
        link += '&invitation=' + token
    if language == 'en' and kind == 'invitation':
        subject = 'SDW • Can you help in the canteen?'
        body = (f'Dear {parent.name},\n\nCan you help in the canteen on {when}?\n'
                'Location: Sportpark Spieringhorn 11, Amsterdam. All times are Amsterdam local time.\n\n'
                f'Log in and accept or decline here:\n{link}\n\n'
                f'You have up to {policy(db).response_hours} hours to respond, no later than two hours before the shift. '
                'Your exact deadline is shown in the invitation. If you do not reply, we will invite another parent.\n\n'
                'Thank you!\nThe SDW canteen coordinators')
    elif language == 'en':
        subject = 'SDW • Your canteen shift has been cancelled'
        body = (f'Dear {parent.name},\n\nYour invitation or canteen shift on {when} has been cancelled. '
                'You do not need to attend this shift. Log in to see the current schedule:\n'
                f'{link}\n\nThe SDW canteen coordinators')
    elif kind == 'invitation':
        subject = 'SDW • Wil je helpen in de kantine?'
        body = (f'Beste {parent.name},\n\nWil je helpen in de kantine op {when}?\n'
                'Locatie: Sportpark Spieringhorn 11, Amsterdam.\n\n'
                f'Log in en bevestig of weiger via:\n{link}\n\n'
                f'Je hebt maximaal {policy(db).response_hours} uur om te reageren, uiterlijk twee uur voor de dienst. '
                'De precieze deadline staat in de uitnodiging. Zonder reactie vragen we een andere ouder.\n\n'
                'Alvast bedankt!\nDe kantinecoördinatie van SDW')
    else:
        subject = 'SDW • Je kantinedienst is geannuleerd'
        body = (f'Beste {parent.name},\n\nJe uitnodiging of kantinedienst op {when} is geannuleerd. '
                'Je hoeft voor deze dienst niet te komen. Bekijk de actuele planning na inloggen:\n'
                f'{link}\n\nDe kantinecoördinatie van SDW')
    payload = {'to': parent.email, 'subject': subject, 'body': body}
    db.add(Outbox(invitation_id=invitation.id, kind=kind, encrypted_payload=encrypt_payload(payload)))


def cancel_invitation(db, invitation, reason):
    previous = invitation.state
    invitation.state = 'cancelled'
    for mail in db.scalars(select(Outbox).where(Outbox.invitation_id == invitation.id,
                                               Outbox.kind == 'invitation', Outbox.state == 'queued')):
        mail.state = 'cancelled'
        mail.encrypted_payload = ''
    if previous in ('pending', 'confirmed'):
        queue_notice(db, invitation, 'cancellation')
    audit(db, 'invitation.cancelled', {'id': invitation.id, 'reason': reason})


def cancel_shift(db, shift, reason, state='cancelled'):
    shift.state = state
    shift.note = reason
    for invitation in db.scalars(select(Invitation).where(Invitation.shift_id == shift.id,
                                                         Invitation.state.in_(LIVE))):
        cancel_invitation(db, invitation, reason)


def reconcile_days(db, changed_days):
    """Invalidate old promises before generating a changed matchday's replacement shifts."""
    now = utcnow()
    for shift in db.scalars(select(Shift).where(Shift.starts_at > now, Shift.state.in_(('open', 'review')))):
        if aware(shift.starts_at).astimezone(TZ).date() in changed_days:
            cancel_shift(db, shift, 'Wedstrijdprogramma gewijzigd; opnieuw plannen.',
                         'cancelled' if shift.managed else 'review')
    db.flush()
    return generate_shifts(db)


def generate_shifts(db):
    p = policy(db)
    now = utcnow()
    fixtures = list(db.scalars(select(Fixture).where(Fixture.is_home.is_(True),
        Fixture.status == 'scheduled', Fixture.venue_id.is_not(None), Fixture.kickoff > now,
        Fixture.kickoff < now + timedelta(days=p.lookahead_days)).order_by(Fixture.kickoff)))
    groups = defaultdict(list)
    for fixture in fixtures:
        demo_staffing = fixture.is_demo or (settings().demo_mode and settings().demo_staffing_enabled)
        groups[(aware(fixture.kickoff).astimezone(TZ).date(), fixture.venue_id, demo_staffing)].append(fixture)
    count = 0
    for (day, venue_id, demo), matches in groups.items():
        existing = list(db.scalars(select(Shift).where(Shift.venue_id == venue_id, Shift.is_demo == demo)))
        if any(aware(s.starts_at).astimezone(TZ).date() == day and
               (s.state in ('open', 'review') or s.note == 'Geannuleerd door coördinator.') for s in existing):
            continue
        # Open at 08:00 Amsterdam, then cover the matchday in complete blocks.
        # Day-wide links also validate the opening/preparation block before kickoff.
        start = datetime.combine(day, time(settings().canteen_opening_hour), TZ).astimezone(timezone.utc)
        end = max(aware(f.kickoff) + timedelta(hours=2) for f in matches)
        # Retain prior displayed coverage when replacing a demo day's old shifts.
        if demo:
            end = max([end] + [aware(s.ends_at) for s in existing
                              if aware(s.starts_at).astimezone(TZ).date() == day])
        if start < end:
            while start < end:
                stop = start + timedelta(minutes=p.shift_minutes)
                shift = Shift(venue_id=venue_id, starts_at=start, ends_at=stop,
                              capacity=p.volunteers_per_shift, is_demo=demo,
                              note=('Demo-bezetting bij echte wedstrijden; geen echte ouderbevestigingen.'
                                    if demo and all(not f.is_demo for f in matches) else
                                    'Demo: opening 08:00; eindtijd voorlopig op basis van fictief programma.' if demo else ''))
                db.add(shift)
                db.flush()
                for f in matches:
                    db.add(ShiftFixture(shift_id=shift.id, fixture_id=f.id))
                count += 1
                start = stop
    db.flush()
    return count


def candidate_parents(db, shift):
    p = policy(db)
    all_invites = list(db.scalars(select(Invitation)))
    demo_assignments = list(db.scalars(select(DemoAssignment)))
    shifts = {s.id: s for s in db.scalars(select(Shift))}
    target = aware(shift.starts_at)
    target_day = target.astimezone(TZ).date()
    matchdays = sorted({aware(s.starts_at).astimezone(TZ).date() for s in shifts.values()
                        if s.state != 'cancelled' and s.is_demo == shift.is_demo})
    adjacent = set()
    if target_day in matchdays:
        idx = matchdays.index(target_day)
        if idx:
            adjacent.add(matchdays[idx - 1])
        if idx + 1 < len(matchdays):
            adjacent.add(matchdays[idx + 1])
    eligible = []
    for parent in db.scalars(select(User).where(User.active.is_(True), User.volunteering.is_(True),
                                               User.role == 'parent', User.is_demo == shift.is_demo)):
        history = [i for i in all_invites if i.user_id == parent.id]
        if any(i.shift_id == shift.id for i in history):
            continue
        if any(aware(b.starts_at) < aware(shift.ends_at) and aware(b.ends_at) > target
               for b in db.scalars(select(Unavailability).where(Unavailability.user_id == parent.id))):
            continue
        # All previous proposals count for spacing, including refusals and timeouts.
        relevant = [i for i in history if i.state != 'cancelled' and shifts[i.shift_id].state != 'cancelled']
        # Fictional staffing reserves the same demo identity and observes fairness.
        relevant += [a for a in demo_assignments if a.person_key == f'demo-user:{parent.id}'
                     and shifts[a.shift_id].state != 'cancelled']
        if any(abs((aware(shifts[i.shift_id].starts_at).astimezone(TZ).date() - target_day).days) < p.min_gap_days
               or aware(shifts[i.shift_id].starts_at).astimezone(TZ).date() in adjacent for i in relevant):
            continue
        duty_count = sum(getattr(i, 'state', 'demo') in ('confirmed', 'completed') for i in relevant)
        recent_offers = sum(aware(i.created_at) > utcnow() - timedelta(days=90) for i in relevant)
        last = max((aware(shifts[i.shift_id].starts_at).timestamp() for i in relevant), default=0)
        eligible.append(((duty_count, recent_offers, last, parent.id), parent))
    return [parent for _, parent in sorted(eligible, key=lambda item: item[0])]


def fill_demo_assignments(db):
    """Populate demonstration places without sending mail or inventing responses."""
    if not (settings().demo_mode and settings().demo_staffing_enabled):
        return 0
    shifts = list(db.scalars(select(Shift).where(Shift.is_demo.is_(True),
        Shift.state == 'open', Shift.starts_at > utcnow()).order_by(Shift.starts_at, Shift.id)))
    all_shifts = {s.id: s for s in db.scalars(select(Shift))}
    days = sorted({aware(s.starts_at).astimezone(TZ).date() for s in all_shifts.values()
                   if s.is_demo and s.state != 'cancelled'})
    count = 0
    for shift in shifts:
        if not valid_shift(db, shift):
            continue
        used = len(list(db.scalars(select(DemoAssignment).where(DemoAssignment.shift_id == shift.id))))
        used += len(list(db.scalars(select(Invitation).where(Invitation.shift_id == shift.id, Invitation.state.in_(LIVE)))))
        while used < shift.capacity:
            parents = candidate_parents(db, shift)
            if parents:
                person_key, name = f'demo-user:{parents[0].id}', parents[0].name
            else:
                # Additional fictional identities have no login, email or real person.
                day = aware(shift.starts_at).astimezone(TZ).date()
                idx = days.index(day)
                adjacent = set(days[max(0, idx-1):idx] + days[idx+1:idx+2])
                assignments = list(db.scalars(select(DemoAssignment)))
                number = 1
                while True:
                    person_key = f'fictional:{number:03}'
                    history = [a for a in assignments if a.person_key == person_key
                               and all_shifts[a.shift_id].state != 'cancelled']
                    if not any(abs((aware(all_shifts[a.shift_id].starts_at).astimezone(TZ).date()-day).days)
                               < policy(db).min_gap_days
                               or aware(all_shifts[a.shift_id].starts_at).astimezone(TZ).date() in adjacent for a in history):
                        break
                    number += 1
                name = f'Fictieve ouder {number:02}'
            db.add(DemoAssignment(shift_id=shift.id, person_key=person_key, name=name))
            audit(db, 'demo.staffing_assigned', {'shift_id': shift.id, 'person_key': person_key,
                                               'fictional': True})
            db.flush()
            count += 1
            used += 1
    return count


def fill_shift(db, shift, now=None):
    now = now or utcnow()
    if not valid_shift(db, shift, now) or aware(shift.starts_at) <= now + timedelta(hours=6):
        return 0
    used = len(list(db.scalars(select(Invitation).where(Invitation.shift_id == shift.id, Invitation.state.in_(LIVE)))))
    used += len(list(db.scalars(select(DemoAssignment).where(DemoAssignment.shift_id == shift.id))))
    count = 0
    while used < shift.capacity:
        candidates = candidate_parents(db, shift)
        if not candidates:
            break
        token = new_token()
        invitation = Invitation(shift_id=shift.id, user_id=candidates[0].id, token_hash=digest(token), created_at=now)
        db.add(invitation)
        db.flush()
        queue_notice(db, invitation, 'invitation', token)
        audit(db, 'invitation.proposed', {'id': invitation.id, 'shift_id': shift.id, 'user_id': candidates[0].id})
        db.flush()
        used += 1
        count += 1
    return count


def expire_invitations(db, now=None):
    now = now or utcnow()
    count = 0
    for invite in db.scalars(select(Invitation).where(Invitation.state == 'pending', Invitation.expires_at <= now)):
        invite.state = 'expired'
        audit(db, 'invitation.expired', {'id': invite.id})
        count += 1
    db.flush()
    return count


def respond(db, invitation, parent_id, decision, now=None):
    now = now or utcnow()
    if invitation.user_id != parent_id:
        raise HTTPException(404, 'Uitnodiging niet gevonden.')
    if invitation.state != 'pending' or not invitation.expires_at or aware(invitation.expires_at) <= now:
        raise HTTPException(409, 'Deze uitnodiging is verlopen of al beantwoord.')
    shift = db.get(Shift, invitation.shift_id)
    if not valid_shift(db, shift, now, require_fresh=False):
        raise HTTPException(409, 'De dienst is gewijzigd of geannuleerd. Neem contact op met de coördinator.')
    if decision not in ('confirmed', 'declined'):
        raise HTTPException(422, 'Kies bevestigen of weigeren.')
    if decision == 'confirmed':
        confirmed = len(list(db.scalars(select(Invitation).where(Invitation.shift_id == shift.id, Invitation.state == 'confirmed'))))
        if confirmed >= shift.capacity:
            raise HTTPException(409, 'De dienst is al bezet.')
    invitation.state = decision
    invitation.responded_at = now
    audit(db, 'invitation.' + decision, {'id': invitation.id}, parent_id)
    db.flush()
    if decision == 'declined' and policy(db).automation_enabled:
        fill_shift(db, shift, now)


def run_planning(db):
    expired = expire_invitations(db)
    fill_demo_assignments(db)
    for shift in db.scalars(select(Shift).where(Shift.state == 'open', Shift.ends_at > utcnow())):
        if aware(shift.starts_at) > utcnow() and not valid_shift(db, shift):
            # Stale feeds pause new offers, but don't cancel promises on network errors.
            continue
        if aware(shift.starts_at) <= utcnow():
            for i in db.scalars(select(Invitation).where(Invitation.shift_id == shift.id, Invitation.state == 'queued')):
                cancel_invitation(db, i, 'Dienst is al begonnen.')
    proposed = 0
    if policy(db).automation_enabled:
        for shift in db.scalars(select(Shift).where(Shift.state == 'open').order_by(Shift.starts_at, Shift.id)):
            proposed += fill_shift(db, shift)
    return {'expired': expired, 'proposed': proposed}
