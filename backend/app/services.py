import hashlib, io, os
from pathlib import Path
import fitz, httpx
from fastapi import HTTPException
from sqlalchemy import select
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from xml.sax.saxutils import escape
from .db import Checklist, Chunk, Document, Evidence, Report, Result, Run, Workspace, now, uid

def require(s, cls, ident):
    item=s.get(cls,ident)
    if item is None: raise HTTPException(404,f'{cls.__name__} not found')
    return item

def criteria(definition):
    for domain in definition['domains']:
        for control in domain['controls']:
            for sub in control['subcontrols']:
                for criterion in sub['criteria']: yield domain,control,sub,criterion

def storage(data=None,path=None):
    url=os.environ['SUPABASE_URL'].rstrip('/')+'/storage/v1/object/'+os.getenv('SUPABASE_STORAGE_BUCKET','original-pdfs')+'/'+path
    headers={'Authorization':'Bearer '+os.environ['SUPABASE_SERVICE_ROLE_KEY'],'apikey':os.environ['SUPABASE_SERVICE_ROLE_KEY']}
    with httpx.Client(timeout=60) as client:
        response=client.post(url,headers={**headers,'Content-Type':'application/pdf'},content=data) if data is not None else client.get(url,headers=headers)
        response.raise_for_status()
        if data is None: return response.content


def mistral_embeddings(texts):
    with httpx.Client(timeout=60) as client:
        r=client.post('https://api.mistral.ai/v1/embeddings',headers={'Authorization':'Bearer '+os.environ['MISTRAL_API_KEY']},json={'model':'mistral-embed','input':texts}); r.raise_for_status()
        return [item['embedding'] for item in sorted(r.json()['data'],key=lambda x:x['index'])]

def index_chunk(s,chunk):
    from sqlalchemy import text
    vector=mistral_embeddings([chunk.text])[0]
    s.execute(text('UPDATE document_chunks SET embedding=CAST(:embedding AS vector) WHERE id=:id'),{'embedding':str(vector),'id':chunk.id})


def ingest(s,workspace_id,name,data,source='upload',external_id=None,version=None):
    require(s,Workspace,workspace_id)
    if len(data)>25*1024*1024: raise HTTPException(413,'PDF must be smaller than 25 MB')
    try:
        pdf=fitz.open(stream=data,filetype='pdf')
        if pdf.is_encrypted: raise ValueError('Encrypted PDFs are unsupported')
        spans=[]
        for page_idx,page in enumerate(pdf):
            for block in page.get_text('dict')['blocks']:
                for line in block.get('lines',[]):
                    for span in line['spans']:
                        if span['text'].strip():
                            rect=fitz.Rect(span['bbox'])*page.rotation_matrix; x0,y0,x1,y1=rect; spans.append(dict(id=f'p{page_idx+1}s{len(spans)}',page_number=page_idx+1,text=span['text'],x0=max(0,x0/page.rect.width),y0=max(0,y0/page.rect.height),x1=min(1,x1/page.rect.width),y1=min(1,y1/page.rect.height),sort_order=len(spans)))
        if not spans: raise ValueError('No extractable text; scanned PDFs are out of scope')
    except Exception as exc: raise HTTPException(422,str(exc)) from exc
    ident=uid(); path=ident+'.pdf'; storage(data,path)
    doc=Document(id=ident,workspace_id=workspace_id,original_filename=Path(name).name,source_type=source,external_document_id=external_id,external_version_id=version,fetched_at=now() if source!='upload' else None,content_hash=hashlib.sha256(data).hexdigest(),storage_path=path,page_count=len(pdf),spans=spans)
    s.add(doc); s.flush()
    for i in range(0,len(spans),8):
        subset=spans[i:i+8]; chunk=Chunk(document_id=ident,text=' '.join(x['text'] for x in subset),spans=subset); s.add(chunk); s.flush()
        index_chunk(s,chunk)

    return doc

def document_json(doc):
    return {key:getattr(doc,key) for key in ['id','workspace_id','original_filename','source_type','content_hash','uploaded_at','page_count','status','storage_path','external_document_id','external_version_id','fetched_at']}

def evidence_json(s,e):
    return {**{key:getattr(e,key) for key in ['id','document_id','classification','confidence_signal','quoted_passage','ai_explanation','review_status','anchors']},'original_filename':require(s,Document,e.document_id).original_filename}

def result_json(s,r):
    run=require(s,Run,r.run_id); checklist=require(s,Checklist,run.checklist_id)
    c=next(c for _,_,_,c in criteria(checklist.definition) if c['id']==r.criterion_id)
    return {**{key:getattr(r,key) for key in ['id','criterion_id','subcontrol_id','ai_state','confidence_signal','ai_explanation','gap_id','document_results','review']},'criterion_code':r.criterion_id,'criterion_text':c['text'],'evidence':[evidence_json(s,e) for e in s.scalars(select(Evidence).where(Evidence.result_id==r.id))]}

def score(s,run):
    definition=require(s,Checklist,run.checklist_id).definition
    workbook_policy=definition.get('scoring_policy')=='criteria_engine_v1'
    results={r.criterion_id:r for r in s.scalars(select(Result).where(Result.run_id==run.id))}
    output=dict(provisional=True,reviewed_criteria=0,total_criteria=run.total_criteria,total_score=0,max_score=0,domains=[])
    for domain in definition['domains']:
        d={k:domain[k] for k in ['id','code','title']}; d.update(score=0,max_score=0,controls=[])
        for control in domain['controls']:
            co={k:control[k] for k in ['id','code','title']}; co.update(score=0,max_score=0,subcontrols=[])
            for sub in control['subcontrols']:
                values=[results[c['id']].review['final_value'] if c['id'] in results and results[c['id']].review else None for c in sub['criteria']]
                yes,no,na=values.count('Yes'),values.count('No'),values.count('N/A'); un=values.count(None); applicable=yes+no
                status='Not Assessed' if not yes+no+na else ('N/A' if not applicable else ('Met' if no==0 else ('Gap' if yes==0 else 'Partial')))
                achievement=yes/applicable if applicable else 0
                maximum=sub['weight'] if workbook_policy else (0 if na==len(values) else sub['weight'])
                sc={k:sub[k] for k in ['id','code','title']}; sc.update(status=status,achievement=achievement,score=sub['weight']*achievement,max_score=maximum,applicable_count=applicable,yes_count=yes,no_count=no,na_count=na,unreviewed_count=un)
                co['subcontrols'].append(sc); co['score']+=sc['score']; co['max_score']+=maximum; output['reviewed_criteria']+=yes+no+na
            d['controls'].append(co); d['score']+=co['score']; d['max_score']+=co['max_score']
        if workbook_policy:
            eligible=[control['score'] for control in d['controls'] if control['subcontrols'][0]['status'] not in ('N/A','Not Assessed')]
            d['score']=sum(eligible)/len(eligible) if eligible else 0
            d['max_score']=1
        output['domains'].append(d); output['total_score']+=d['score']; output['max_score']+=d['max_score']
    if workbook_policy:
        output['total_score']=output['total_score']/len(output['domains']) if output['domains'] else 0
        output['max_score']=1
        output['aggregation']='criteria_engine_v1'
    else:
        output['aggregation']='weighted_sum'
    output['provisional']=output['reviewed_criteria']<sum(1 for _ in criteria(definition))
    return output

def run_json(s,run):
    states=[r.ai_state for r in s.scalars(select(Result).where(Result.run_id==run.id))]; scoring=score(s,run)
    scope_limited=run.total_criteria<sum(1 for _ in criteria(require(s,Checklist,run.checklist_id).definition))
    return {**{key:getattr(run,key) for key in ['id','checklist_id','status','started_at','completed_at','model_provider','model_name','prompt_version','total_criteria','processed_criteria','failed_criteria']},'scope_limited':scope_limited,'snapshot_documents':run.snapshot,'counts':{state:states.count(state) for state in ['fulfilled','gap','uncertain','conflict','proposed_not_applicable','analysis_failed']},'reviewed_criteria':scoring['reviewed_criteria'],'score':scoring}

def final_review(s,result,body):
    if result.ai_state in ('pending','analysis_failed'): raise HTTPException(409,'Analysis must complete successfully before review')
    evidence=list(s.scalars(select(Evidence).where(Evidence.result_id==result.id)))
    if any(e.review_status=='unreviewed' for e in evidence): raise HTTPException(409,'Inspect and accept or reject every citation first')
    expected={'fulfilled':'Yes','gap':'No','proposed_not_applicable':'N/A'}.get(result.ai_state)
    unsupported_yes=body.final_value=='Yes' and not any(e.classification=='supports' and e.review_status=='accepted' for e in evidence)
    if body.decision_type=='override':
        if not body.override_note or not body.override_note.strip(): raise HTTPException(422,'An override rationale is required')
    elif body.final_value!=expected or unsupported_yes: raise HTTPException(422,'This decision requires an override and rationale')
    run=require(s,Run,result.run_id); run.review_revision+=1
    result.review=dict(final_value=body.final_value,decision_type=body.decision_type,override_note=body.override_note,reviewed_at=now())

def report_json(s,report):
    run=require(s,Run,report.run_id); sc=score(s,run)
    full_count=sum(1 for _ in criteria(require(s,Checklist,run.checklist_id).definition))
    return dict(id=report.id,run_id=run.id,status='draft' if sc['provisional'] else 'ready',review_complete=not sc['provisional'],unreviewed_count=full_count-sc['reviewed_criteria'],gap_count=sum(len(i['gap_ids']) for i in report.items),items=report.items)

def make_report(s,run):
    results=list(s.scalars(select(Result).where(Result.run_id==run.id))); mapping={r.criterion_id:r for r in results}; grouped={}
    for _,_,sub,c in criteria(require(s,Checklist,run.checklist_id).definition):
        r=mapping.get(c['id'])
        if r is not None and r.review and r.review['final_value']=='No':
            item=grouped.setdefault(sub['id'],dict(id=sub['id'],title=sub['title']+' — Outstanding information',request_text='',gap_ids=[])); item['gap_ids'].append(r.gap_id); item['request_text']+=c['gap_phrasing']+' '
    report=Report(run_id=run.id,items=list(grouped.values()),review_revision=run.review_revision); s.add(report); s.flush(); return report

def export_pdf(s,report,draft,confirm):
    run=require(s,Run,report.run_id); sc=score(s,run)
    if report.review_revision!=run.review_revision: raise HTTPException(409,'Report is stale after review changes; regenerate it')
    expected={r.gap_id for r in s.scalars(select(Result).where(Result.run_id==run.id)) if r.review and r.review['final_value']=='No'}
    mapped=[gap for item in report.items for gap in item['gap_ids']]
    if expected!=set(mapped) or len(mapped)!=len(set(mapped)): raise HTTPException(409,'Report coverage is stale or invalid; regenerate the report')
    if sc['provisional'] and not (draft and confirm): raise HTTPException(409,'Review incomplete: explicitly confirm draft export')
    buffer=io.BytesIO(); styles=getSampleStyleSheet(); elements=[]
    if draft: elements.append(Paragraph('DRAFT — REVIEW INCOMPLETE' if sc['provisional'] else 'DRAFT',styles['Title']))
    elements += [Paragraph('Documentary Gap Report',styles['Title']),Paragraph('Findings concern only documentary evidence in the assessed data room.',styles['Normal']),Spacer(1,20)]
    if not expected: elements.append(Paragraph('No human-confirmed documentary gaps.',styles['Normal']))
    for item in report.items:
        elements += [Paragraph(escape(item['title']),styles['Heading2']),Paragraph(escape(item['request_text']),styles['Normal']),Paragraph(escape(', '.join(item['gap_ids'])),styles['Normal']),Spacer(1,12)]
    SimpleDocTemplate(buffer).build(elements); return buffer.getvalue()
