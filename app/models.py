from datetime import date, datetime, timezone
from sqlalchemy import (String, Text, Boolean, DateTime, ForeignKey, Integer,
                        UniqueConstraint, CheckConstraint, Index, text, JSON, Date)
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


def utcnow():
    return datetime.now(timezone.utc)


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class Club(Base):
    __tablename__ = 'clubs'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    timezone: Mapped[str] = mapped_column(String(64), default='Europe/Amsterdam')


class Venue(Base):
    __tablename__ = 'venues'
    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey('clubs.id'))
    name: Mapped[str] = mapped_column(String(160))
    address: Mapped[str] = mapped_column(String(250))
    city: Mapped[str] = mapped_column(String(80), default='Amsterdam')
    is_home: Mapped[bool] = mapped_column(Boolean, default=True)


class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey('clubs.id'), default=1)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(254))
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(20), default='parent')
    language: Mapped[str] = mapped_column(String(2), default='nl', server_default='nl')
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    volunteering: Mapped[bool] = mapped_column(Boolean, default=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (CheckConstraint("role IN ('admin','parent')", name='user_role'),)


class Team(Base):
    __tablename__ = 'teams'
    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey('clubs.id'), default=1)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    external_id: Mapped[str | None] = mapped_column(String(100), unique=True)


class ParentTeam(Base):
    __tablename__ = 'parent_teams'
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey('teams.id'), primary_key=True)


class Fixture(Base):
    __tablename__ = 'fixtures'
    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(160), unique=True)
    source: Mapped[str] = mapped_column(String(40), default='manual')
    team_id: Mapped[int] = mapped_column(ForeignKey('teams.id'))
    venue_id: Mapped[int | None] = mapped_column(ForeignKey('venues.id'))
    home_team: Mapped[str] = mapped_column(String(160))
    away_team: Mapped[str] = mapped_column(String(160))
    kickoff: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    venue_text: Mapped[str] = mapped_column(String(250), default='')
    city: Mapped[str] = mapped_column(String(80), default='')
    is_home: Mapped[bool] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(String(30), default='scheduled')
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (CheckConstraint("status IN ('scheduled','cancelled','postponed','review')", name='fixture_status'),)


class PlanningPolicy(Base):
    __tablename__ = 'planning_policies'
    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey('clubs.id'), unique=True, default=1)
    min_gap_days: Mapped[int] = mapped_column(Integer, default=14)
    volunteers_per_shift: Mapped[int] = mapped_column(Integer, default=3)
    shift_minutes: Mapped[int] = mapped_column(Integer, default=120)
    lookahead_days: Mapped[int] = mapped_column(Integer, default=28)
    response_hours: Mapped[int] = mapped_column(Integer, default=48)
    automation_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (
        CheckConstraint('min_gap_days >= 1 AND min_gap_days <= 90', name='policy_gap'),
        CheckConstraint('response_hours BETWEEN 1 AND 48', name='policy_reply'),
        CheckConstraint('volunteers_per_shift BETWEEN 1 AND 10', name='policy_staff'),
        CheckConstraint('shift_minutes BETWEEN 30 AND 480', name='policy_duration'),
    )


class Shift(Base):
    __tablename__ = 'shifts'
    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey('clubs.id'), default=1)
    venue_id: Mapped[int] = mapped_column(ForeignKey('venues.id'))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    capacity: Mapped[int] = mapped_column(Integer, default=3)
    state: Mapped[str] = mapped_column(String(24), default='open')
    note: Mapped[str] = mapped_column(Text, default='')
    managed: Mapped[bool] = mapped_column(Boolean, default=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (
        CheckConstraint('ends_at > starts_at', name='shift_duration'),
        CheckConstraint('capacity BETWEEN 1 AND 10', name='shift_capacity'),
        CheckConstraint("state IN ('open','cancelled','review','completed')", name='shift_state'),
    )


class ShiftFixture(Base):
    __tablename__ = 'shift_fixtures'
    shift_id: Mapped[int] = mapped_column(ForeignKey('shifts.id'), primary_key=True)
    fixture_id: Mapped[int] = mapped_column(ForeignKey('fixtures.id'), primary_key=True)


class DemoAssignment(Base):
    """Fictional staffing examples; never an invitation, confirmation or attendance."""
    __tablename__ = 'demo_assignments'
    shift_id: Mapped[int] = mapped_column(ForeignKey('shifts.id'), primary_key=True)
    person_key: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Invitation(Base):
    __tablename__ = 'invitations'
    id: Mapped[int] = mapped_column(primary_key=True)
    shift_id: Mapped[int] = mapped_column(ForeignKey('shifts.id'), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    state: Mapped[str] = mapped_column(String(24), default='queued', index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint('shift_id', 'user_id', name='one_offer_per_parent_per_shift'),
        CheckConstraint("state IN ('queued','pending','confirmed','declined','expired','cancelled','completed','no_show')", name='invitation_state'),
    )


class Outbox(Base):
    __tablename__ = 'email_outbox'
    id: Mapped[int] = mapped_column(primary_key=True)
    invitation_id: Mapped[int] = mapped_column(ForeignKey('invitations.id'))
    kind: Mapped[str] = mapped_column(String(30), default='invitation')
    encrypted_payload: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(24), default='queued', index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(String(250), default='')
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint('invitation_id', 'kind', name='one_email_per_kind'),)


class Unavailability(Base):
    __tablename__ = 'unavailability'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint('ends_at > starts_at', name='unavailable_duration'),)


class LoginSession(Base):
    __tablename__ = 'login_sessions'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class LoginAttempt(Base):
    __tablename__ = 'login_attempts'
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class AuditEvent(Base):
    __tablename__ = 'audit_events'
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
    action: Mapped[str] = mapped_column(String(100))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SyncRun(Base):
    __tablename__ = 'sync_runs'
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(40))
    state: Mapped[str] = mapped_column(String(24))
    count: Mapped[int] = mapped_column(Integer, default=0)
    detail: Mapped[str] = mapped_column(String(250), default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class JobRun(Base):
    __tablename__ = 'job_runs'
    id: Mapped[int] = mapped_column(primary_key=True)
    state: Mapped[str] = mapped_column(String(24))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


Index('active_shift_start', Shift.starts_at, Shift.state)


class ShareLink(Base):
    __tablename__ = 'share_links'
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    label: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class VisitorDay(Base):
    __tablename__ = 'visitor_days'
    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    visitor_hash: Mapped[str] = mapped_column(String(64))
    share_link_id: Mapped[int] = mapped_column(ForeignKey('share_links.id'), index=True)
    mobile: Mapped[bool] = mapped_column(Boolean)
    views: Mapped[int] = mapped_column(Integer, default=1)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint('day','visitor_hash','share_link_id',name='visitor_day_link'),)
