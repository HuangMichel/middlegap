import argparse, time
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, or_, text
import httpx
from .db import Checklist, Document, Evidence, Result, Run, Session, is_connection_failure, is_pool_capacity_error, now
from .services import criteria, require
from .ai import assess_document, aggregate

def progress(s,run):
    s.execute(text('INSERT INTO assessment_progress (run_id,status,processed_criteria,total_criteria,failed_criteria) VALUES (:id,:status,:processed,:total,:failed) ON CONFLICT (run_id) DO UPDATE SET status=EXCLUDED.status, processed_criteria=EXCLUDED.processed_criteria,total_criteria=EXCLUDED.total_criteria,failed_criteria=EXCLUDED.failed_criteria'),dict(id=run.id,status=run.status,processed=run.processed_criteria,total=run.total_criteria,failed=run.failed_criteria))

def failure_message(error):
    if is_pool_capacity_error(error): return 'Database connection limit reached during assessment. Restore database capacity, then retry.'
    if is_connection_failure(error): return 'Database connection failed during assessment. Check database availability, then retry.'
    if isinstance(error,httpx.TimeoutException): return 'AI provider timed out during assessment. Wait briefly, then retry.'
    if isinstance(error,httpx.HTTPStatusError):
        status=error.response.status_code
        if status in (401,403): return 'AI provider rejected server credentials. Check the backend configuration, then retry.'
        if status==429: return 'AI provider rate limit reached. Wait briefly, then retry.'
        if status>=500: return 'AI provider is temporarily unavailable. Wait briefly, then retry.'
        return f'AI provider rejected the assessment request (HTTP {status}). Check the backend configuration, then retry.'
    if isinstance(error,httpx.RequestError): return 'Could not reach the AI provider. Check network availability, then retry.'
    return 'Technical assessment failure. Verify provider configuration and retry failed criteria.'

def claim():
    with Session.begin() as s:
        run=s.scalars(select(Run).where(or_(Run.status=='queued',(Run.status=='running') & (Run.lease_until<now()))).order_by(Run.started_at).with_for_update(skip_locked=True)).first()
        if not run: return None
        run.status='running';run.lease_until=(datetime.now(timezone.utc)+timedelta(minutes=20)).isoformat();progress(s,run);return run.id

def process(run_id):
    with Session() as s:
        run=require(s,Run,run_id); definition=require(s,Checklist,run.checklist_id).definition; snapshots=run.snapshot
        docs=[require(s,Document,item['document_id']) for item in snapshots]
        selected_ids=set(s.scalars(select(Result.criterion_id).where(Result.run_id==run_id)))
        grouped={}
        for _,_,sub,c in criteria(definition):
            if c['id'] in selected_ids: grouped.setdefault(sub['id'],(sub,[]))[1].append(c)
    for sub,cs in grouped.values():
        # Explicit expected document descriptions select the same population for all clauses.
        from .ai import discover_population
        try:
            with Session.begin() as discovery_session:
                current=require(discovery_session,Run,run_id)
                populations=dict(current.populations or {})
                if sub['id'] in populations:
                    population=[d for d in docs if d.id in populations[sub['id']]]
                else:
                    population=discover_population(discovery_session,docs,sub,cs)
                    populations[sub['id']]=[d.id for d in population]
                    current.populations=populations
        except Exception as error:
            with Session.begin() as s:
                for r in s.scalars(select(Result).where(Result.run_id==run_id,Result.subcontrol_id==sub['id'])):
                    if r.ai_state in ('pending','analysis_failed'):
                        r.ai_state='analysis_failed';r.ai_explanation='Document discovery failed. '+failure_message(error)
                s.flush()
                run=require(s,Run,run_id)
                all_results=list(s.scalars(select(Result).where(Result.run_id==run_id)))
                run.processed_criteria=sum(r.ai_state!='pending' for r in all_results);run.failed_criteria=sum(r.ai_state=='analysis_failed' for r in all_results);progress(s,run)
            continue
        joint=sub['evidence_binding']=='same_document' and sub['population_rule']=='any_relevant_document'
        with (Session() if joint else nullcontext(None)) as joint_session:
            for c in cs:
                with (nullcontext(joint_session) if joint else Session.begin()) as s:
                    run=require(s,Run,run_id); result=s.scalars(select(Result).where(Result.run_id==run.id,Result.criterion_id==c['id'])).one()
                    if result.ai_state not in ('pending','analysis_failed'): continue
                    try:
                        with s.begin_nested():
                            doc_results=[];items=[]
                            for doc in population:
                                assessed,spans=assess_document(s,doc,c,sub); by_id={sp['id']:sp for sp in spans}
                                for ev in assessed.get('evidence',[]):
                                    anchors=[{k:v for k,v in by_id[ident].items() if k!='id'} for ident in ev['span_ids']]
                                    items.append(Evidence(result_id=result.id,document_id=doc.id,classification=ev['classification'],confidence_signal='strong_evidence' if ev['classification']!='contextual' else 'possible_evidence',quoted_passage=' '.join(a['text'] for a in anchors),ai_explanation=ev['explanation'],anchors=anchors))
                                classifications={e['classification'] for e in assessed.get('evidence',[])}
                                state='conflict' if {'supports','contradicts'}<=classifications else assessed['state']
                                if state=='fulfilled' and 'supports' not in classifications: state='uncertain'
                                doc_results.append(dict(document_id=doc.id,original_filename=doc.original_filename,ai_state=state,evidence_summary='Source-grounded documentary assessment.'))
                            all_classes={e.classification for e in items}
                            result.ai_state='conflict' if {'supports','contradicts'}<=all_classes else aggregate([d['ai_state'] for d in doc_results],sub['population_rule']); result.document_results=doc_results
                            result.confidence_signal='strong_evidence' if result.ai_state=='fulfilled' else ('possible_evidence' if items else 'insufficient_evidence')
                            result.ai_explanation='Potential gap — no sufficient evidence was found in the provided data room.' if result.ai_state=='gap' else 'Assessment of the immutable document population; human verification required.'
                            for e in list(s.scalars(select(Evidence).where(Evidence.result_id==result.id))): s.delete(e)
                            s.add_all(items)
                    except Exception as error:
                        result.ai_state='analysis_failed';result.ai_explanation=failure_message(error);result.document_results=[]
                    s.flush()
                    all_results=list(s.scalars(select(Result).where(Result.run_id==run.id)));run.processed_criteria=sum(r.ai_state!='pending' for r in all_results);run.failed_criteria=sum(r.ai_state=='analysis_failed' for r in all_results);run.lease_until=(datetime.now(timezone.utc)+timedelta(minutes=20)).isoformat();progress(s,run)
            # same_document + any requires one document satisfying all clauses simultaneously.
            if joint:
                with nullcontext(joint_session) as s:
                    rs=list(s.scalars(select(Result).where(Result.run_id==run_id,Result.subcontrol_id==sub['id'])))
                    incomplete=any(r.ai_state=='analysis_failed' for r in rs)
                    if incomplete:
                        # Persist intermediate evidence, but publish no binding-dependent conclusions.
                        for r in rs:
                            if r.ai_state!='analysis_failed' and r.review is None:
                                r.ai_state='pending'
                                r.ai_explanation='Awaiting successful joint document assessment; retry failed criteria.'
                    else:
                        applicable=[r for r in rs if r.ai_state!='proposed_not_applicable']
                        eligible=[{d['document_id'] for d in r.document_results if d['ai_state']=='fulfilled'} for r in applicable]
                        if eligible and not set.intersection(*eligible):
                            for r in applicable:
                                if r.ai_state=='fulfilled' and r.review is None:
                                    r.ai_state='gap';r.ai_explanation='No single relevant document satisfies all required clauses.'
                    s.flush()
                    all_results=list(s.scalars(select(Result).where(Result.run_id==run_id)))
                    run=require(s,Run,run_id)
                    run.processed_criteria=sum(r.ai_state!='pending' for r in all_results)
                    run.failed_criteria=sum(r.ai_state=='analysis_failed' for r in all_results)
                    progress(s,run)
            if joint:
                joint_session.commit()
    with Session.begin() as s:
        run=require(s,Run,run_id);run.status='completed_with_errors' if run.failed_criteria else 'completed';run.completed_at=now();run.lease_until=None;progress(s,run)

def main():
    from .db import configure_runtime, dispose_runtime
    configure_runtime()
    try:
        parser=argparse.ArgumentParser();parser.add_argument('--once',action='store_true');args=parser.parse_args()
        while True:
            try:
                ident=claim()
            except Exception:
                ident=None
                print('Worker could not claim a job; database unavailable. Will retry.',flush=True)
            if ident:
                try:
                    process(ident)
                except Exception:
                    # A broken transaction must be closed before recording job failure.
                    try:
                        with Session.begin() as s:
                            run=require(s,Run,ident);run.status='failed';run.completed_at=now();run.lease_until=None
                            progress(s,run)
                    except Exception:
                        print('Worker could not persist job failure; expired lease will permit recovery.',flush=True)
            if args.once: break
            if not ident: time.sleep(1)
    finally:
        dispose_runtime()
if __name__=='__main__': main()
