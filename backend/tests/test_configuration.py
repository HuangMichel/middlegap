import os
import subprocess
import sys
from pathlib import Path
import pytest
from app.config import settings
from app.load_template import validate_template
from tests.fakes import sample
VALID=dict(DATABASE_URL='postgresql://fixture:fixture@127.0.0.1/fixture',SUPABASE_URL='https://fixture.supabase.co',SUPABASE_SERVICE_ROLE_KEY='synthetic-key',MISTRAL_API_KEY='synthetic-key')
def test_required_configuration_names_without_values():
    with pytest.raises(RuntimeError) as failure: settings({})
    for name in VALID: assert name in str(failure.value)
    for secret in ('synthetic-key','fixture:fixture'): assert secret not in str(failure.value)
@pytest.mark.parametrize('mode',['demo','connected'])
def test_removed_mode_is_rejected(mode):
    with pytest.raises(RuntimeError,match='APP_MODE has been removed'): settings({**VALID,'APP_MODE':mode})
@pytest.mark.parametrize('url',['sqlite:///:memory:','not-a-database-url','postgresql://fixture:fixture@/fixture'])
def test_local_or_invalid_database_rejected_without_url_disclosure(url):
    with pytest.raises(RuntimeError) as failure: settings({**VALID,'DATABASE_URL':url})
    assert url not in str(failure.value)
def test_valid_configuration_normalizes_driver():
    assert settings(VALID)['DATABASE_URL'].startswith('postgresql+psycopg://')
def test_import_does_not_configure_database_or_seed():
    environment=dict(os.environ)
    for name in (*VALID,'APP_MODE'): environment.pop(name,None)
    script="from app import db, main; assert db.engine is None; assert db.Session.kw.get('bind') is None; assert main.health()=={'status':'ok','ai_provider':'mistral'}"
    result=subprocess.run([sys.executable,'-c',script],env=environment,capture_output=True,text=True,cwd=Path(__file__).resolve().parents[1])
    assert result.returncode==0,result.stderr
def test_template_validation_preserves_fields_and_rejects_duplicate_numbers():
    value=sample();assert validate_template(value)['domains']==value['domains']
    value['domains'][0]['controls'][0]['subcontrols'][0]['criteria'][1]['number']=1
    with pytest.raises(ValueError,match='numbers'): validate_template(value)
def test_startup_missing_config_fails_without_service_access(monkeypatch):
    from fastapi.testclient import TestClient
    from app import main
    for name in (*VALID,'APP_MODE'): monkeypatch.delenv(name,raising=False)
    with pytest.raises(RuntimeError,match='Missing required configuration'):
        with TestClient(main.app): pass

def test_worker_entrypoint_requires_configuration(monkeypatch):
    from app import worker
    for name in (*VALID,'APP_MODE'): monkeypatch.delenv(name,raising=False)
    with pytest.raises(RuntimeError,match='Missing required configuration'): worker.main()

def test_harness_marker_is_not_a_production_health_field(tmp_path):
    script='''
import sys
from fastapi.testclient import TestClient
from app import main
from tests.integration_server import configure
configure(sys.argv[1])
assert main.health() == {'status': 'ok', 'ai_provider': 'mistral'}
with TestClient(main.app) as client:
    assert client.get('/health').json() == {'status': 'ok', 'ai_provider': 'synthetic', 'test_harness': True}
    assert client.get('/workspaces').json() == []
    assert client.get('/checklist-templates').json() == []
'''
    result=subprocess.run([sys.executable,'-c',script,str(tmp_path)],capture_output=True,text=True,cwd=Path(__file__).resolve().parents[1])
    assert result.returncode==0,result.stderr
