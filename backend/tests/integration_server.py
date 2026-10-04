"""Explicit isolated test processes; never selected by production configuration.

Start one worker per root. SQLite exercises API/worker persistence but does not
model Postgres row locking, live providers, or public Realtime delivery.
"""

import argparse
import io
import time
from pathlib import Path

from fastapi.routing import APIRoute
from reportlab.pdfgen import canvas
from sqlalchemy import create_engine, event, select

from app import db, main, services, worker
from tests.fakes import install, sample

FIXTURE_WORKSPACE = 'Integration legal data room'


def harness_health():
    return dict(status='ok', ai_provider='synthetic', test_harness=True)


def harness_runtime():
    # Ambient production configuration must never connect this UI to live data.
    return dict(supabase_url=None, supabase_anon_key=None)


def configure(root):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        'sqlite:///' + str(root / 'integration.db'),
        connect_args={'check_same_thread': False, 'timeout': 30},
    )

    @event.listens_for(engine, 'connect')
    def configure_sqlite(connection, _record):
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('PRAGMA journal_mode=WAL')

    db.engine = engine
    db.Session.configure(bind=engine)
    db.Base.metadata.create_all(engine)
    install(setattr, root / 'files')
    for route in main.app.routes:
        if isinstance(route, APIRoute) and route.path in ('/health', '/runtime-config'):
            endpoint = harness_health if route.path == '/health' else harness_runtime
            route.endpoint = endpoint
            route.dependant.call = endpoint
    return engine


def seed():
    with db.Session.begin() as session:
        if not session.get(db.Template, 'sample-privacy'):
            session.add(db.Template(id='sample-privacy', definition=sample()))
        workspace = session.scalars(
            select(db.Workspace).where(db.Workspace.name == FIXTURE_WORKSPACE)
        ).first()
        if workspace is not None:
            return
        workspace = db.Workspace(name=FIXTURE_WORKSPACE)
        session.add(workspace)
        session.flush()
        populations = [
            ('Customer', [
                'Privacy Notice',
                'Legal basis: consent.',
                'Purpose of processing: customer services.',
                'Retention period: retained seven years.',
                'Controller contact: privacy@example.test.',
            ]),
            ('Employee', [
                'Privacy Notice',
                'Legal basis: employment contract.',
                'Purpose of processing: payroll and benefits.',
                'Controller contact: hr@example.test.',
            ]),
        ]
        for label, lines in populations:
            output = io.BytesIO()
            pdf = canvas.Canvas(output)
            for index, line in enumerate(lines):
                pdf.drawString(50, 770 - 30 * index, line)
            pdf.save()
            services.ingest(
                session, workspace.id, label + ' Privacy Notice.pdf', output.getvalue()
            )


def main_cli():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['seed', 'api', 'worker'])
    parser.add_argument('--root', required=True)
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    configure(args.root)
    if args.command == 'seed':
        seed()
    elif args.command == 'api':
        import uvicorn
        uvicorn.run(main.app, host='127.0.0.1', port=args.port)
    else:
        while True:
            ident = worker.claim()
            if ident:
                worker.process(ident)
            if args.once:
                break
            if not ident:
                time.sleep(1)


if __name__ == '__main__':
    main_cli()
