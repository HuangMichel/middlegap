import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from app import db, main
from tests.fakes import sample, install

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    db.Session.configure(bind=engine);monkeypatch.setattr(db,'engine',engine)
    install(monkeypatch.setattr,tmp_path/'files')
    db.Base.metadata.create_all(engine)
    with db.Session.begin() as s: s.add(db.Template(id='sample-privacy',definition=sample()))
    with TestClient(main.app) as client: yield client

