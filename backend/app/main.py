import copy, os
from contextlib import asynccontextmanager
from itertools import islice
from typing import Literal, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, TimeoutError as PoolTimeout
from .db import Checklist, Document, Evidence, Report, Result, Run, Session, Template, Workspace
from .services import criteria, document_json, evidence_json, export_pdf, final_review, ingest, make_report, report_json, require, result_json, run_json, storage
from .db import configure_runtime, dispose_runtime, is_connection_failure
@asynccontextmanager
async def lifespan(app):
    configure_runtime()
    try:
        yield
    finally:
        dispose_runtime()
app=FastAPI(title='MiddleGap',lifespan=lifespan)
@app.exception_handler(PoolTimeout)
@app.exception_handler(DBAPIError)
async def database_error_response(request,error):
    if is_connection_failure(error):
        return JSONResponse(status_code=503,content={'detail':'Database temporarily unavailable or at its connection limit. Wait briefly before retrying; check whether a write completed before submitting it again.'},headers={'Retry-After':'5'})
    return JSONResponse(status_code=500,content={'detail':'Database request failed.'})
app.add_middleware(CORSMiddleware,allow_origins=os.getenv('FRONTEND_ORIGINS','http://localhost:3000,http://127.0.0.1:3000').split(','),allow_methods=['*'],allow_headers=['*'])
class Name(BaseModel): name:str=Field(min_length=1,max_length=200)
class TemplateRequest(BaseModel): template_id:str
class EvidenceReview(BaseModel): review_status:Literal['accepted','rejected']
class Review(BaseModel):
    final_value:Literal['Yes','No','N/A']
    decision_type:Literal['verified_ai','override']
    override_note:Optional[str]=None
class Export(BaseModel): draft:bool=False; confirm_incomplete:bool=False

def lock_run(s,ident):
    run=s.scalars(select(Run).where(Run.id==ident).with_for_update().execution_options(populate_existing=True)).first()
    if run is None: raise HTTPException(404,'Run not found')
    return run
@app.get('/health')
def health(): return dict(status='ok',ai_provider='mistral')
@app.get('/runtime-config')
def runtime(): return dict(supabase_url=os.getenv('SUPABASE_URL'),supabase_anon_key=os.getenv('SUPABASE_ANON_KEY'))
@app.get('/workspaces')
def workspaces():
    with Session() as s: return [dict(id=w.id,name=w.name,created_at=w.created_at) for w in s.scalars(select(Workspace))]
@app.post('/workspaces')
def create_workspace(body:Name):
    with Session.begin() as s:
        w=Workspace(name=body.name);s.add(w);s.flush();return dict(id=w.id,name=w.name,created_at=w.created_at)
@app.get('/workspaces/{ident}')
def workspace(ident:str):
    with Session() as s:
        w=require(s,Workspace,ident);return dict(id=w.id,name=w.name,created_at=w.created_at)
@app.get('/checklist-templates')
def templates():
    with Session() as s: return [dict(id=t.id,name=t.definition['name'],description=t.definition.get('description',''),criterion_count=sum(1 for _ in criteria(t.definition))) for t in s.scalars(select(Template))]
@app.post('/checklist-templates/workbook/preview')
async def workbook_preview(file:UploadFile=File(...)):
    from .workbook import MAX_FILE, preview
    filename=(file.filename or 'workbook.xlsx').replace('\\','/').split('/')[-1][:255]
    return preview(await file.read(MAX_FILE+1),filename)
@app.post('/checklist-templates/workbook')
async def workbook_import(file:UploadFile=File(...),name:str=Form(...),preview_hash:str=Form(...),default_evidence_binding:Literal['corpus','same_document']=Form(...),default_population_rule:Literal['any_relevant_document','all_relevant_documents']=Form(...),confirm_warnings:bool=Form(False),subcontrol_rules:str=Form('{}')):
    from .workbook import MAX_FILE, imported_definition
    filename=(file.filename or 'workbook.xlsx').replace('\\','/').split('/')[-1][:255]
    definition=imported_definition(await file.read(MAX_FILE+1),filename,name,preview_hash,default_evidence_binding,default_population_rule,confirm_warnings,subcontrol_rules)
    with Session.begin() as session:
        session.add(Template(id=definition['id'],definition=definition))
    return dict(id=definition['id'],name=definition['name'],description=definition['description'],criterion_count=sum(1 for _ in criteria(definition)))
@app.get('/workspaces/{ident}/documents')
def documents(ident:str):
    with Session() as s:
        require(s,Workspace,ident);return [document_json(d) for d in s.scalars(select(Document).where(Document.workspace_id==ident,Document.removed==False))]
@app.post('/workspaces/{ident}/documents')
async def upload(ident:str,file:UploadFile=File(...)):
    data=await file.read(25*1024*1024+1)
    with Session.begin() as s: return document_json(ingest(s,ident,file.filename or 'document.pdf',data))
@app.delete('/workspaces/{ident}/documents/{document_id}')
def remove_document(ident:str,document_id:str):
    with Session.begin() as s:
        doc=require(s,Document,document_id)
        if doc.workspace_id!=ident: raise HTTPException(404,'Document not found in workspace')
        doc.removed=True;return dict(removed=True)
@app.get('/documents/{ident}/file')
def original(ident:str):
    with Session() as s:
        doc=require(s,Document,ident);return Response(storage(path=doc.storage_path),media_type='application/pdf')
@app.post('/workspaces/{ident}/checklists')
def create_checklist(ident:str,body:TemplateRequest):
    with Session.begin() as s:
        require(s,Workspace,ident);template=require(s,Template,body.template_id);cl=Checklist(workspace_id=ident,definition=copy.deepcopy(template.definition));s.add(cl);s.flush();return dict(id=cl.id,workspace_id=ident,name=cl.definition['name'])
@app.get('/workspaces/{ident}/checklists')
def checklists(ident:str):
    with Session() as s:
        require(s,Workspace,ident);return [dict(id=c.id,workspace_id=ident,name=c.definition['name']) for c in s.scalars(select(Checklist).where(Checklist.workspace_id==ident))]
@app.get('/checklists/{ident}')
def checklist(ident:str):
    with Session() as s:
        c=require(s,Checklist,ident);return {**c.definition,'id':c.id,'workspace_id':c.workspace_id}
@app.post('/checklists/{ident}/assessment-runs')
def create_run(ident:str):
    with Session.begin() as s:
        cl=require(s,Checklist,ident);docs=list(s.scalars(select(Document).where(Document.workspace_id==cl.workspace_id,Document.removed==False,Document.status=='ready')))
        # Freeze the demo scope in Result rows; retries and existing runs keep their scope.
        selected_criteria=list(islice(criteria(cl.definition),1))
        run=Run(checklist_id=ident,model_provider='mistral',model_name=os.getenv('MISTRAL_MODEL','mistral-small-latest'),snapshot=[dict(document_id=d.id,original_filename=d.original_filename,content_hash=d.content_hash,storage_path=d.storage_path,external_version_id=d.external_version_id) for d in docs],total_criteria=len(selected_criteria))
        s.add(run);s.flush()
        for _,_,sub,c in selected_criteria: s.add(Result(run_id=run.id,criterion_id=c['id'],subcontrol_id=sub['id'],gap_id=sub['id']+'.GAP.'+str(c['number']).zfill(3)))
        s.flush();return run_json(s,run)
@app.get('/checklists/{ident}/assessment-runs')
def runs(ident:str):
    with Session() as s:
        require(s,Checklist,ident);return [run_json(s,r) for r in s.scalars(select(Run).where(Run.checklist_id==ident).order_by(Run.started_at.desc()))]
@app.get('/assessment-runs/{ident}')
def get_run(ident:str):
    with Session() as s: return run_json(s,require(s,Run,ident))
@app.get('/assessment-runs/{ident}/results')
def results(ident:str):
    with Session() as s:
        require(s,Run,ident);return [result_json(s,r) for r in s.scalars(select(Result).where(Result.run_id==ident).order_by(Result.criterion_id))]
@app.post('/assessment-runs/{ident}/retry-failed')
def retry(ident:str):
    with Session.begin() as s:
        run=lock_run(s,ident)
        if run.status not in ('completed_with_errors','failed'): raise HTTPException(409,'Only a finished failed run can be retried')
        for r in s.scalars(select(Result).where(Result.run_id==ident,Result.ai_state=='analysis_failed')): r.ai_state='pending'
        run.status='queued';run.completed_at=None;return run_json(s,run)
@app.patch('/evidence/{ident}/review')
def evidence_review(ident:str,body:EvidenceReview):
    with Session.begin() as s:
        e=require(s,Evidence,ident);r=require(s,Result,e.result_id);run=lock_run(s,r.run_id);s.refresh(e);s.refresh(r)
        if e.review_status!=body.review_status: e.review_status=body.review_status;r.review=None;run.review_revision+=1
        return evidence_json(s,e)
@app.put('/criterion-results/{ident}/review')
def review(ident:str,body:Review):
    with Session.begin() as s:
        result=require(s,Result,ident);lock_run(s,result.run_id);s.refresh(result);final_review(s,result,body);return result_json(s,result)
@app.post('/assessment-runs/{ident}/reports')
def report(ident:str):
    with Session.begin() as s:
        run=lock_run(s,ident);return report_json(s,make_report(s,run))
@app.get('/reports/{ident}')
def get_report(ident:str):
    with Session() as s: return report_json(s,require(s,Report,ident))
@app.post('/reports/{ident}/export')
def export(ident:str,body:Export):
    with Session.begin() as s:
        report=require(s,Report,ident);lock_run(s,report.run_id);data=export_pdf(s,report,body.draft,body.confirm_incomplete)
        return Response(data,media_type='application/pdf',headers={'Content-Disposition':'attachment; filename="gap-report.pdf"'})
