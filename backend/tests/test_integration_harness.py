"""Check the explicit test entrypoint without patching the pytest process."""

import json
import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def process(root, code, **environment):
    result = subprocess.run(
        [sys.executable, '-c', code, str(root)],
        cwd=BACKEND,
        env={**os.environ, **environment},
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_seed_is_idempotent_and_keeps_unrelated_workspaces(tmp_path):
    state = process(tmp_path, '''
import json, sys
from app import db
from tests.integration_server import configure, seed
configure(sys.argv[1])
with db.Session.begin() as session:
    session.add(db.Workspace(name='Unrelated test workspace'))
seed()
seed()
with db.Session() as session:
    print(json.dumps({
        'workspaces': session.query(db.Workspace).count(),
        'documents': session.query(db.Document).count(),
        'templates': session.query(db.Template).count(),
    }))
''')
    assert state == {'workspaces': 2, 'documents': 2, 'templates': 1}
    assert len(list((tmp_path / 'files').iterdir())) == 2


def test_separate_worker_persists_api_run_and_harness_is_isolated(tmp_path):
    created = process(tmp_path, '''
import json, sys
from fastapi.testclient import TestClient
from app import main
from tests.integration_server import configure, seed
configure(sys.argv[1])
seed()
with TestClient(main.app) as client:
    workspace = client.get('/workspaces').json()[0]
    checklist = client.post('/workspaces/' + workspace['id'] + '/checklists',
        json={'template_id': 'sample-privacy'}).json()
    response = client.post('/checklists/' + checklist['id'] + '/assessment-runs')
    response.raise_for_status()
    print(json.dumps({'run': response.json()['id'],
        'health': client.get('/health').json(),
        'runtime': client.get('/runtime-config').json()}))
''', SUPABASE_URL='https://ambient.example.test', SUPABASE_ANON_KEY='ambient-public-key')
    assert created['health'] == {
        'status': 'ok', 'ai_provider': 'synthetic', 'test_harness': True,
    }
    assert created['runtime'] == {'supabase_url': None, 'supabase_anon_key': None}
    subprocess.run(
        [sys.executable, '-m', 'tests.integration_server', 'worker',
         '--root', str(tmp_path), '--once'],
        cwd=BACKEND, check=True, capture_output=True, text=True, timeout=30,
    )
    completed = process(tmp_path, '''
import json, sys
from app import db
from tests.integration_server import configure
configure(sys.argv[1])
with db.Session() as session:
    run = session.query(db.Run).one()
    print(json.dumps({'id': run.id, 'status': run.status,
        'processed': run.processed_criteria, 'failed': run.failed_criteria,
        'states': [result.ai_state for result in session.query(db.Result)
            .order_by(db.Result.criterion_id)],
        'evidence': session.query(db.Evidence).count()}))
''')
    assert completed['id'] == created['run']
    assert completed['status'] == 'completed'
    assert completed['processed'] == 4
    assert completed['failed'] == 0
    assert completed['states'] == ['fulfilled', 'fulfilled', 'gap', 'fulfilled']
    assert completed['evidence'] > 0
