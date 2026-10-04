from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import create_engine, String, JSON, Text, Boolean, ForeignKey, UniqueConstraint, Integer
from sqlalchemy.orm import DeclarativeBase, mapped_column, sessionmaker


def uid(): return str(uuid4())
def now(): return datetime.now(timezone.utc).isoformat()
engine = None
Session = sessionmaker(expire_on_commit=False)

def is_pool_capacity_error(error):
    from sqlalchemy.exc import TimeoutError as PoolTimeout
    if isinstance(error,PoolTimeout): return True
    original=getattr(error,'orig',error)
    if getattr(original,'sqlstate',None)=='53300': return True
    # Inspect provider markers without exposing its message, connection URL or SQL.
    message=str(original).lower()
    return any(marker in message for marker in ('emaxconnsession','maxclientsinsessionmode','max client connections reached','too many clients','remaining connection slots'))

def is_connection_failure(error):
    from sqlalchemy.exc import DataError, IntegrityError, InterfaceError, OperationalError, ProgrammingError, TimeoutError as PoolTimeout
    if isinstance(error,(DataError,IntegrityError,ProgrammingError)): return False
    if isinstance(error,PoolTimeout): return True
    sqlstate=getattr(getattr(error,'orig',None),'sqlstate','') or ''
    if sqlstate.startswith(('22','23','42')): return False
    return bool(getattr(error,'connection_invalidated',False) or isinstance(error,(OperationalError,InterfaceError)) or sqlstate.startswith('08'))

def dispose_runtime():
    global engine
    previous=engine
    engine=None
    Session.configure(bind=None)
    if previous is not None: previous.dispose()

def configure_runtime():
    from .config import settings
    from sqlalchemy import text
    config = settings()
    global engine
    configured_engine=None
    try:
        configured_engine = create_engine(config['DATABASE_URL'], connect_args={'options':'-c search_path=public,extensions','connect_timeout':10,'application_name':'middlegap'}, pool_size=config['DB_POOL_SIZE'], max_overflow=0, pool_timeout=config['DB_POOL_TIMEOUT'], pool_pre_ping=True)
        with configured_engine.connect() as connection:
            connection.execute(text('SELECT id FROM assessment_runs LIMIT 0'))
    except Exception as error:
        if configured_engine is not None: configured_engine.dispose()
        if is_pool_capacity_error(error):
            raise RuntimeError('Supabase connection capacity is exhausted. Stop duplicate API/worker processes or wait for existing database sessions to close, then restart.') from None
        if is_connection_failure(error):
            raise RuntimeError('Cannot establish a Supabase database connection. Verify service availability and DATABASE_URL, then restart.') from None
        raise RuntimeError('Cannot initialize the Supabase database. Verify the installed driver, DATABASE_URL and required schema migration.') from None
    previous=engine
    Session.configure(bind=configured_engine)
    engine=configured_engine
    if previous is not None and previous is not configured_engine: previous.dispose()

class Base(DeclarativeBase): pass
class Workspace(Base):
    __tablename__='workspaces'
    id=mapped_column(String, primary_key=True, default=uid)
    name=mapped_column(String)
    created_at=mapped_column(String, default=now)
class Template(Base):
    __tablename__='checklist_templates'
    id=mapped_column(String, primary_key=True)
    definition=mapped_column(JSON)
class Checklist(Base):
    __tablename__='checklists'
    id=mapped_column(String, primary_key=True, default=uid)
    workspace_id=mapped_column(ForeignKey('workspaces.id'))
    definition=mapped_column(JSON)
class Document(Base):
    __tablename__='documents'
    id=mapped_column(String, primary_key=True, default=uid)
    workspace_id=mapped_column(ForeignKey('workspaces.id'))
    original_filename=mapped_column(String)
    source_type=mapped_column(String, default='upload')
    content_hash=mapped_column(String)
    uploaded_at=mapped_column(String, default=now)
    fetched_at=mapped_column(String, nullable=True)
    external_document_id=mapped_column(String, nullable=True)
    external_version_id=mapped_column(String, nullable=True)
    page_count=mapped_column(Integer, default=0)
    status=mapped_column(String, default='ready')
    storage_path=mapped_column(String)
    removed=mapped_column(Boolean, default=False)
    spans=mapped_column(JSON)
class Chunk(Base):
    __tablename__='document_chunks'
    id=mapped_column(String, primary_key=True, default=uid)
    document_id=mapped_column(ForeignKey('documents.id'))
    text=mapped_column(Text)
    spans=mapped_column(JSON)
class Run(Base):
    __tablename__='assessment_runs'
    id=mapped_column(String, primary_key=True, default=uid)
    checklist_id=mapped_column(ForeignKey('checklists.id'))
    status=mapped_column(String, default='queued')
    started_at=mapped_column(String, default=now)
    completed_at=mapped_column(String, nullable=True)
    model_provider=mapped_column(String)
    model_name=mapped_column(String)
    prompt_version=mapped_column(String, default='grounded-v1')
    snapshot=mapped_column(JSON)
    populations=mapped_column(JSON, default=dict)
    lease_until=mapped_column(String, nullable=True)
    review_revision=mapped_column(Integer, default=0)
    total_criteria=mapped_column(Integer, default=0)
    processed_criteria=mapped_column(Integer, default=0)
    failed_criteria=mapped_column(Integer, default=0)
class Result(Base):
    __tablename__='criterion_results'
    __table_args__=(UniqueConstraint('run_id','criterion_id'),)
    id=mapped_column(String, primary_key=True, default=uid)
    run_id=mapped_column(ForeignKey('assessment_runs.id'))
    criterion_id=mapped_column(String)
    subcontrol_id=mapped_column(String)
    ai_state=mapped_column(String, default='pending')
    confidence_signal=mapped_column(String, default='insufficient_evidence')
    ai_explanation=mapped_column(Text, default='Waiting for assessment')
    document_results=mapped_column(JSON, default=list)
    review=mapped_column(JSON, nullable=True)
    gap_id=mapped_column(String)
class Evidence(Base):
    __tablename__='evidence_items'
    id=mapped_column(String, primary_key=True, default=uid)
    result_id=mapped_column(ForeignKey('criterion_results.id'))
    document_id=mapped_column(ForeignKey('documents.id'))
    classification=mapped_column(String)
    confidence_signal=mapped_column(String)
    quoted_passage=mapped_column(Text)
    ai_explanation=mapped_column(Text)
    review_status=mapped_column(String, default='unreviewed')
    anchors=mapped_column(JSON)
class Report(Base):
    __tablename__='reports'
    id=mapped_column(String, primary_key=True, default=uid)
    run_id=mapped_column(ForeignKey('assessment_runs.id'))
    items=mapped_column(JSON)
    review_revision=mapped_column(Integer, default=0)
