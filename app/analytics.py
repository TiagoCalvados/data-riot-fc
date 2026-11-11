"""First-party, aggregate-only statistics; no IP, referrer, URL or account history."""
from datetime import timedelta
import hashlib
import hmac
import re
import secrets
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException, Request, Response, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, func, case, delete
from sqlalchemy.orm import Session
from app.config import settings
from app.db import get_db
from app.models import ShareLink, VisitorDay, LoginSession, User, utcnow
from app.security import digest

RETENTION_DAYS=90
COOKIE='sdw_visitor'
CHOICE='sdw_statistics'


def signed_hash(value):
    return hmac.new(settings().secret_key.encode(),value.encode(),hashlib.sha256).hexdigest()


def visitor_identity(cookie, now):
    if cookie and len(cookie)<180:
        parts=cookie.split('.')
        if len(parts)==3:
            issued,random,signature=parts
            if issued.isdigit() and re.fullmatch(r'[A-Za-z0-9_-]{32}',random) and re.fullmatch(r'[a-f0-9]{64}',signature):
                age=now.timestamp()-int(issued)
                if 0<=age<RETENTION_DAYS*86400 and hmac.compare_digest(signature,signed_hash('visitor-cookie:'+issued+'.'+random)):
                    return signed_hash('visitor-id:'+issued+'.'+random),None
    raw=str(int(now.timestamp()))+'.'+secrets.token_urlsafe(24)
    return signed_hash('visitor-id:'+raw),raw+'.'+signed_hash('visitor-cookie:'+raw)


def dialect_insert(db, model):
    if db.bind.dialect.name=='postgresql':
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    return insert(model)


def excluded(request, db):
    if request.cookies.get(CHOICE)=='off' or request.headers.get('dnt')=='1' or request.headers.get('sec-gpc')=='1':
        return True
    agent=request.headers.get('user-agent','').lower()
    if not agent or any(word in agent for word in ('bot','crawler','spider','facebookexternalhit','whatsapp','headless')):
        return True
    token=request.cookies.get('sdw_session')
    if token:
        role=db.scalar(select(User.role).join(LoginSession,User.id==LoginSession.user_id).where(
            LoginSession.token_hash==digest(token),LoginSession.expires_at>utcnow(),User.active==True))
        if role=='admin':return True
    return False


def prune_visitors(db, now=None):
    today=(now or utcnow()).astimezone(ZoneInfo('Europe/Amsterdam')).date()
    db.execute(delete(VisitorDay).where(VisitorDay.day<today-timedelta(days=RETENTION_DAYS-1)))


class VisitBody(BaseModel):
    share: str = Field(default='',max_length=32,pattern=r'^[a-zA-Z0-9_-]*$')


class ShareBody(BaseModel):
    label: str = Field(min_length=1,max_length=120)
    @field_validator('label')
    @classmethod
    def not_blank(cls,value):
        if not value.strip():raise ValueError('Enter a name for this sharing link.')
        return value.strip()


class ChoiceBody(BaseModel):
    enabled: bool


def link_view(link):
    return {'id':link.id,'code':link.code,'label':link.label,
            'url':settings().base_url.rstrip('/')+('/?share='+link.code if link.id else '/')}


def report(db, days, mobile_only=False, now=None):
    today=(now or utcnow()).astimezone(ZoneInfo('Europe/Amsterdam')).date()
    start=today-timedelta(days=days-1)
    conditions=[VisitorDay.day>=start,VisitorDay.day<=today]
    if mobile_only:conditions.append(VisitorDay.mobile==True)
    visits=select(VisitorDay).where(*conditions).subquery()
    def totals(rows):
        return {'visitors':rows[0] or 0,'views':rows[1] or 0,'mobile_visitors':rows[2] or 0}
    expressions=[func.count(func.distinct(visits.c.visitor_hash)),func.sum(visits.c.views),
                 func.count(func.distinct(case((visits.c.mobile==True,visits.c.visitor_hash))))]
    total=totals(db.execute(select(*expressions)).one())
    grouped={row[0]:totals(row[1:]) for row in db.execute(select(visits.c.share_link_id,*expressions).group_by(visits.c.share_link_id))}
    daily={row[0]:totals(row[1:]) for row in db.execute(select(visits.c.day,*expressions).group_by(visits.c.day))}
    links=[{**link_view(link),**grouped.get(link.id,{'visitors':0,'views':0,'mobile_visitors':0})}
           for link in db.scalars(select(ShareLink).order_by(ShareLink.id.desc()))]
    return {'days':days,'mobile_only':mobile_only,'totals':total,'links':links,
            'daily':[{'day':(start+timedelta(days=index)).isoformat(),**daily.get(start+timedelta(days=index),{'visitors':0,'views':0,'mobile_visitors':0})} for index in range(days)]}


def analytics_router(admin):
    router=APIRouter()

    @router.post('/api/visits',status_code=204)
    def record(body: VisitBody,request: Request,response: Response,db: Session=Depends(get_db)):
        if request.headers.get('x-sdw-statistics')!='1':raise HTTPException(400,'Invalid statistics request.')
        if excluded(request,db):return
        now=utcnow()
        visitor,cookie=visitor_identity(request.cookies.get(COOKIE),now)
        if cookie:
            response.set_cookie(COOKIE,cookie,max_age=RETENTION_DAYS*86400,httponly=True,
                                secure=settings().cookie_secure,samesite='lax',path='/')
        db.execute(dialect_insert(db,ShareLink).values(id=0,code='direct',label='Direct / overige links',created_at=now).on_conflict_do_nothing(index_elements=['id']))
        link=db.scalar(select(ShareLink.id).where(ShareLink.code==body.share)) if body.share else 0
        agent=request.headers.get('user-agent','').lower()
        mobile=request.headers.get('sec-ch-ua-mobile')=='?1' or any(word in agent for word in ('android','iphone','ipad','mobile'))
        statement=dialect_insert(db,VisitorDay).values(day=now.astimezone(ZoneInfo('Europe/Amsterdam')).date(),
            visitor_hash=visitor,share_link_id=link or 0,mobile=mobile,views=1,first_seen=now,last_seen=now)
        db.execute(statement.on_conflict_do_update(index_elements=['day','visitor_hash','share_link_id'],
            set_={'views':VisitorDay.views+1,'last_seen':now}))
        db.commit()

    @router.post('/api/statistics-choice')
    def choice(body: ChoiceBody,response: Response):
        response.set_cookie(CHOICE,'on' if body.enabled else 'off',max_age=RETENTION_DAYS*86400,
                            secure=settings().cookie_secure,samesite='lax',path='/')
        if not body.enabled:response.delete_cookie(COOKIE,path='/')
        return {'enabled':body.enabled}

    @router.get('/api/admin/analytics')
    def statistics(days: int=Query(default=30,ge=1,le=90),mobile_only: bool=False,
                   actor=Depends(admin),db: Session=Depends(get_db)):
        return report(db,days,mobile_only)

    @router.post('/api/admin/share-links',status_code=201)
    def create_share(body: ShareBody,actor=Depends(admin),db: Session=Depends(get_db)):
        link=ShareLink(code=secrets.token_urlsafe(12),label=body.label)
        db.add(link);db.commit()
        return link_view(link)

    return router
