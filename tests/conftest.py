import os
import secrets
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ['SECRET_KEY'] = 'test-only-secret-do-not-use-for-deployment-123456'
os.environ['DATABASE_URL'] = 'sqlite://'
os.environ['COOKIE_SECURE'] = 'false'
os.environ['DEMO_MODE'] = 'true'
os.environ['BASE_URL'] = 'http://testserver'

from app.db import Base, get_db
from app.models import Club, Venue, User, PlanningPolicy
from app.security import password_hash
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def db():
    engine = create_engine('sqlite://', poolclass=StaticPool, connect_args={'check_same_thread': False})
    from sqlalchemy import event
    @event.listens_for(engine, 'connect')
    def fk(conn, _):
        conn.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as session:
        session.add(Club(id=1, name='ASC SDW'))
        session.flush()
        session.add(Venue(id=1, club_id=1, name='Sportpark Spieringhorn', address='Amsterdam'))
        session.add(PlanningPolicy(club_id=1, automation_enabled=True))
        session.flush()
        yield session
    engine.dispose()


@pytest.fixture
def users(db):
    encoded = password_hash('Test-Password-4-Parents!')
    for index in range(1,9):
        db.add(User(id=index, username=f'parent{index}', name=f'Parent {index}', email=f'parent{index}@example.invalid',
                    password_hash=encoded, is_demo=True))
    db.add(User(id=9, username='admin', name='Coordinator', email='admin@example.invalid', role='admin',
                volunteering=False, is_demo=True, password_hash=password_hash('Coordinator-Test-Password!')))
    db.commit()
    return list(range(1,9))


@pytest.fixture
def client(db):
    def override():
        yield db
    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
