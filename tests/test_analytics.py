from datetime import timedelta
from sqlalchemy import select, func
from app.models import VisitorDay, utcnow
from app.analytics import visitor_identity, report, prune_visitors

MOBILE={'X-SDW-Statistics':'1','User-Agent':'Mozilla/5.0 (Linux; Android 14) Mobile'}
DESKTOP={'X-SDW-Statistics':'1','User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}


def signin(client,name='admin',password='Coordinator-Test-Password!'):
    response=client.post('/api/login',json={'username':name,'password':password})
    assert response.status_code==200
    return {'X-CSRF-Token':response.json()['csrf']}


def test_repeat_visit_same_browser_is_one_visitor(client,db):
    for _ in range(3):assert client.post('/api/visits',headers=MOBILE,json={}).status_code==204
    result=report(db,30)
    assert result['totals']=={'visitors':1,'views':3,'mobile_visitors':1}
    assert len(list(db.scalars(select(VisitorDay))))==1
    assert len(db.scalar(select(VisitorDay)).visitor_hash)==64


def test_different_browsers_same_ip_count_separately(client,db):
    response=client.post('/api/visits',headers=MOBILE,json={})
    assert 'HttpOnly' in response.headers['set-cookie'] and 'Max-Age=7776000' in response.headers['set-cookie']
    client.cookies.clear()
    client.post('/api/visits',headers=DESKTOP,json={})
    assert report(db,30)['totals']=={'visitors':2,'views':2,'mobile_visitors':1}
    assert report(db,30,True)['totals']=={'visitors':1,'views':1,'mobile_visitors':1}


def test_share_attribution_and_global_dedup(client,db,users):
    h=signin(client)
    link=client.post('/api/admin/share-links',headers=h,json={'label':'Parents WhatsApp'}).json()
    assert '?share='+link['code'] in link['url']
    client.post('/api/logout',headers=h,json={})
    client.post('/api/visits',headers=MOBILE,json={'share':link['code']})
    client.post('/api/visits',headers=MOBILE,json={'share':'unknown-code'})
    data=report(db,30)
    assert data['totals']['visitors']==1 and data['totals']['views']==2
    assert all(row['visitors']==1 for row in data['links'])
    assert not any('visitor_hash' in row for row in data['links'])


def test_statistics_are_coordinator_only_and_writes_need_csrf(client,db,users):
    assert client.get('/api/admin/analytics').status_code==401
    h=signin(client,'parent1','Test-Password-4-Parents!')
    assert client.get('/api/admin/analytics').status_code==403
    assert client.post('/api/admin/share-links',headers=h,json={'label':'x'}).status_code==403
    client.post('/api/logout',headers=h,json={})
    h=signin(client)
    assert client.get('/api/admin/analytics?days=91').status_code==422
    assert client.post('/api/admin/share-links',json={'label':'x'}).status_code==403
    assert client.post('/api/admin/share-links',headers=h,json={'label':'   '}).status_code==422
    assert client.get('/api/admin/analytics').status_code==200
    client.post('/api/visits',headers=MOBILE,json={})
    assert db.scalar(select(func.count()).select_from(VisitorDay))==0


def test_opt_out_privacy_signals_and_bots(client,db):
    for extra in [{'DNT':'1'},{'Sec-GPC':'1'},{'User-Agent':'WhatsApp/2.0'},{'User-Agent':'facebookexternalhit/1.1'}]:
        response=client.post('/api/visits',headers={**MOBILE,**extra},json={})
        assert response.status_code==204 and 'set-cookie' not in response.headers
    client.post('/api/statistics-choice',json={'enabled':False})
    client.post('/api/visits',headers=MOBILE,json={})
    assert db.scalar(select(func.count()).select_from(VisitorDay))==0
    client.post('/api/statistics-choice',json={'enabled':True})
    client.post('/api/visits',headers=MOBILE,json={})
    assert db.scalar(select(func.count()).select_from(VisitorDay))==1
    assert client.post('/api/visits',headers={**MOBILE,'Origin':'https://other.invalid'},json={}).status_code==403
    assert client.post('/api/visits',json={}).status_code==400


def test_tokens_are_signed_bounded_and_retention_is_enforced(client,db):
    now=utcnow()
    first,cookie=visitor_identity('',now)
    assert visitor_identity(cookie,now)==(first,None)
    assert visitor_identity(cookie+'bad',now)[0]!=first
    assert visitor_identity(cookie,now+timedelta(days=91))[0]!=first
    client.post('/api/visits',headers=MOBILE,json={})
    row=db.scalar(select(VisitorDay))
    row.day-=timedelta(days=90)
    db.commit()
    prune_visitors(db,now)
    assert db.scalar(select(func.count()).select_from(VisitorDay))==0


def test_unique_range_is_not_sum_of_daily_unique_counts(client,db):
    client.post('/api/visits',headers=MOBILE,json={})
    row=db.scalar(select(VisitorDay))
    db.add(VisitorDay(day=row.day-timedelta(days=1),visitor_hash=row.visitor_hash,
        share_link_id=row.share_link_id,mobile=True,views=2))
    db.commit()
    data=report(db,7)
    assert data['totals']['visitors']==1 and data['totals']['views']==3
    assert sum(day['visitors'] for day in data['daily'])==2
