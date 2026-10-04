import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock
import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError, ProgrammingError, TimeoutError as PoolTimeout
from sqlalchemy.pool import QueuePool
from app import db, main
from app.config import settings
from tests.test_configuration import VALID

class ProviderError(Exception):
    def __init__(self,message,sqlstate=None):
        super().__init__(message);self.sqlstate=sqlstate

@pytest.mark.parametrize('name,value',[('DB_POOL_SIZE','0'),('DB_POOL_SIZE','6'),('DB_POOL_SIZE','not-an-integer'),('DB_POOL_TIMEOUT','0'),('DB_POOL_TIMEOUT','nan'),('DB_POOL_TIMEOUT','inf'),('DB_POOL_TIMEOUT','31')])
def test_pool_settings_reject_unbounded_or_invalid_values(name,value):
    with pytest.raises(RuntimeError,match='DB_POOL_SIZE'): settings({**VALID,name:value})

def test_pool_defaults_are_bounded():
    values=settings(VALID)
    assert values['DB_POOL_SIZE']==2 and values['DB_POOL_TIMEOUT']==5

class CandidateEngine:
    def __init__(self,failure=None): self.failure=failure;self.disposed=False;self.connection_closed=False
    def connect(self): return self
    def __enter__(self): return self
    def execute(self,query):
        if self.failure: raise self.failure
    def __exit__(self,*_): self.connection_closed=True
    def dispose(self): self.disposed=True

def install_config(monkeypatch,engines):
    import app.config
    monkeypatch.setattr(app.config,'settings',lambda: settings(VALID))
    factory=Mock(side_effect=engines);monkeypatch.setattr(db,'create_engine',factory)
    session_factory=Mock();monkeypatch.setattr(db,'Session',session_factory)
    monkeypatch.setattr(db,'engine',None)
    return factory,session_factory

def test_configuration_caps_connections_and_disposes_previous_engine(monkeypatch):
    first,second=CandidateEngine(),CandidateEngine()
    factory,sessions=install_config(monkeypatch,[first,second])
    db.configure_runtime()
    kwargs=factory.call_args.kwargs
    assert kwargs['pool_size']==2 and kwargs['max_overflow']==0 and kwargs['pool_timeout']==5
    assert kwargs['connect_args']['connect_timeout']==10 and kwargs['connect_args']['application_name']=='middlegap'
    assert kwargs['pool_pre_ping'] is True and first.connection_closed
    db.configure_runtime()
    assert first.disposed and not second.disposed and db.engine is second
    db.dispose_runtime()
    assert second.disposed and db.engine is None
    sessions.configure.assert_called_with(bind=None)

@pytest.mark.parametrize('error,message',[
    (OperationalError('SELECT secret',{},ProviderError('FATAL: EMAXCONNSESSION password=private-secret')),'capacity is exhausted'),
    (OperationalError('SELECT secret',{},ProviderError('remaining connection slots are reserved','53300')),'capacity is exhausted'),
    (OperationalError('SELECT secret',{},ProviderError('connection refused private-secret','08006')),'Cannot establish'),
    (ProgrammingError('SELECT secret',{},ProviderError('missing relation private-secret','42P01')),'required schema'),
])
def test_failed_candidate_is_closed_and_disposed_without_secret_disclosure(monkeypatch,error,message):
    candidate=CandidateEngine(error);old=CandidateEngine()
    _,sessions=install_config(monkeypatch,[candidate]);monkeypatch.setattr(db,'engine',old)
    with pytest.raises(RuntimeError,match=message) as failure: db.configure_runtime()
    assert candidate.connection_closed and candidate.disposed
    assert db.engine is old and not old.disposed
    assert 'private-secret' not in str(failure.value) and 'SELECT secret' not in str(failure.value)
    sessions.configure.assert_not_called()

def test_creator_failure_does_not_dispose_an_uncreated_engine(monkeypatch):
    install_config(monkeypatch,[RuntimeError('private-secret')])
    with pytest.raises(RuntimeError,match='Cannot initialize') as failure: db.configure_runtime()
    assert 'private-secret' not in str(failure.value)

def test_real_pool_backpressure_never_opens_overflow_connections():
    opened=[]
    def creator():
        connection=sqlite3.connect(':memory:',check_same_thread=False);opened.append(connection);return connection
    engine=create_engine('sqlite://',creator=creator,poolclass=QueuePool,pool_size=2,max_overflow=0,pool_timeout=.05)
    first,second=engine.connect(),engine.connect()
    start=time.monotonic()
    with ThreadPoolExecutor(max_workers=1) as executor:
        future=executor.submit(engine.connect)
        with pytest.raises(PoolTimeout): future.result(timeout=1)
    assert time.monotonic()-start>=.04
    assert len(opened)==2 and engine.pool.checkedout()==2
    first.close()
    with engine.connect() as replacement: assert replacement is not None
    assert len(opened)==2
    second.close();assert engine.pool.checkedout()==0
    engine.dispose()
    for connection in opened:
        with pytest.raises(sqlite3.ProgrammingError): connection.execute('SELECT 1')

@pytest.mark.parametrize('error,expected',[
    (PoolTimeout('postgresql://private-secret@host/database'),503),
    (OperationalError('private SQL',{},ProviderError('EMAXCONNSESSION private-secret')),503),
    (DBAPIError('private SQL',{},ProviderError('lost private-secret'),connection_invalidated=True),503),
    (IntegrityError('private SQL',{},ProviderError('duplicate private-secret','23505')),500),
    (ProgrammingError('private SQL',{},ProviderError('syntax private-secret','42601')),500),
    (OperationalError('private SQL',{},ProviderError('syntax private-secret','42601')),500),
])
def test_api_dependency_failure_response_is_safe_and_semantically_scoped(client,monkeypatch,error,expected):
    class FailedSession:
        def __enter__(self): raise error
        def __exit__(self,*_): pass
    monkeypatch.setattr(main,'Session',lambda: FailedSession())
    response=client.get('/workspaces')
    assert response.status_code==expected
    assert 'private-secret' not in response.text and 'private SQL' not in response.text and 'postgresql://' not in response.text
    if expected==503:
        assert response.headers['Retry-After']=='5'
        assert 'Database temporarily unavailable' in response.json()['detail']
    else: assert 'Retry-After' not in response.headers

def test_api_shutdown_disposes_runtime_engine(monkeypatch):
    from fastapi.testclient import TestClient
    candidate=CandidateEngine();monkeypatch.setattr(db,'engine',candidate)
    monkeypatch.setattr(db,'Session',Mock());monkeypatch.setattr(main,'configure_runtime',lambda: None)
    with TestClient(main.app): assert not candidate.disposed
    assert candidate.disposed and db.engine is None

def test_worker_once_closes_its_pool(monkeypatch):
    import sys
    from app import worker
    candidate=CandidateEngine();monkeypatch.setattr(db,'engine',candidate)
    monkeypatch.setattr(db,'Session',Mock());monkeypatch.setattr(db,'configure_runtime',lambda: None)
    monkeypatch.setattr(worker,'claim',lambda: None);monkeypatch.setattr(sys,'argv',['worker','--once'])
    worker.main()
    assert candidate.disposed and db.engine is None

@pytest.mark.parametrize('failure_stage',['progress','commit'])
def test_joint_failure_returns_single_connection_before_main_recovery(client,tmp_path,monkeypatch,failure_stage):
    import sys
    from sqlalchemy import event, select
    from sqlalchemy.orm import Session as SQLSession, sessionmaker
    from app import worker
    from tests.fakes import sample
    from tests.test_workflow import setup, upload
    pooled=create_engine('sqlite:///'+str(tmp_path/'joint-failure.db'),connect_args={'check_same_thread':False},poolclass=QueuePool,pool_size=1,max_overflow=0,pool_timeout=.05)
    # Explicit outer transactions simulate PostgreSQL rollback semantics across savepoints.
    @event.listens_for(pooled,'connect')
    def explicit_transactions(connection,_): connection.isolation_level=None
    @event.listens_for(pooled,'begin')
    def begin_transaction(connection): connection.exec_driver_sql('BEGIN')
    class FaultSession(SQLSession):
        def commit(self):
            if failure_stage=='commit' and self.info.get('joint_group'):
                raise RuntimeError('Injected joint commit failure')
            return super().commit()
    factory=sessionmaker(bind=pooled,class_=FaultSession,expire_on_commit=False)
    monkeypatch.setattr(db,'Session',factory);monkeypatch.setattr(main,'Session',factory);monkeypatch.setattr(worker,'Session',factory);monkeypatch.setattr(db,'engine',pooled)
    db.Base.metadata.create_all(pooled)
    value=sample();group=value['domains'][0]['controls'][0]['subcontrols'][0];group['population_rule']='any_relevant_document';group['criteria']=group['criteria'][:2]
    with factory.begin() as session: session.add(db.Template(id='sample-privacy',definition=value))
    workspace,checklist=setup(client)
    upload(client,workspace,'Privacy Notice.pdf',['Privacy Notice','Legal basis: consent.','Purpose: payroll.'])
    run=client.post(f'/checklists/{checklist}/assessment-runs').json()
    def fault_progress(session,run):
        if any(isinstance(item,db.Result) for item in session.identity_map.values()):
            session.info['joint_group']=True
            if failure_stage=='progress': raise RuntimeError('Injected joint progress failure')
    monkeypatch.setattr(worker,'progress',fault_progress)
    original_process=worker.process;returned_before_recovery=[]
    def process_and_observe(identifier):
        try: original_process(identifier)
        except RuntimeError:
            returned_before_recovery.append(pooled.pool.checkedout())
            raise
    monkeypatch.setattr(worker,'process',process_and_observe)
    monkeypatch.setattr(db,'configure_runtime',lambda: None)
    monkeypatch.setattr(sys,'argv',['worker','--once'])
    worker.main() # Actual main failure handler obtains its own session and persists failure.
    assert returned_before_recovery==[0]
    with SQLSession(pooled) as verification:
        assert verification.get(db.Run,run['id']).status=='failed'
        assert all(result.ai_state=='pending' for result in verification.scalars(select(db.Result).where(db.Result.run_id==run['id'])))
        assert list(verification.scalars(select(db.Evidence)))==[]
    assert pooled.pool.checkedout()==0
    pooled.dispose()
