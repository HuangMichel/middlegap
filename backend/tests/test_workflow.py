from reportlab.pdfgen import canvas
import io, pytest
from app import db, main, worker
from tests.fakes import sample
from app.ai import aggregate


def pdf(lines):
    out=io.BytesIO();c=canvas.Canvas(out)
    for i,line in enumerate(lines): c.drawString(50,780-i*25,line)
    c.save();return out.getvalue()

def setup(client,definition=None):
    w=client.post('/workspaces',json={'name':'Test'}).json()['id']
    if definition:
        with db.Session.begin() as s: s.get(db.Template,'sample-privacy').definition=definition
    cl=client.post(f'/workspaces/{w}/checklists',json={'template_id':'sample-privacy'}).json()['id']
    return w,cl

def upload(client,w,name,lines):
    response=client.post(f'/workspaces/{w}/documents',files={'file':(name,pdf(lines),'application/pdf')});assert response.status_code==200;return response.json()

def run(client,cl):
    r=client.post(f'/checklists/{cl}/assessment-runs').json();worker.process(r['id']);return r['id'],client.get(f"/assessment-runs/{r['id']}/results").json()

def review(client,result,value,override=False):
    for e in result['evidence']: assert client.patch(f"/evidence/{e['id']}/review",json={'review_status':'accepted'}).status_code==200
    return client.put(f"/criterion-results/{result['id']}/review",json={'final_value':value,'decision_type':'override' if override else 'verified_ai','override_note':'Human clarification' if override else None})

def test_snapshot_retains_removed_document(client):
    w,cl=setup(client);old=upload(client,w,'Customer Privacy Notice.pdf',['Privacy Notice','Retention period: seven years.'])
    r=client.post(f'/checklists/{cl}/assessment-runs').json();client.delete(f"/workspaces/{w}/documents/{old['id']}")
    upload(client,w,'New Privacy Notice.pdf',['Privacy Notice','Legal basis: consent.']);worker.process(r['id'])
    after=client.get(f"/assessment-runs/{r['id']}").json();assert [d['document_id'] for d in after['snapshot_documents']]==[old['id']]
    assert client.get(f"/documents/{old['id']}/file").content.startswith(b'%PDF')

def test_inspection_override_invalidation_and_stale_report(client):
    w,cl=setup(client);upload(client,w,'Privacy Notice.pdf',['Privacy Notice','Legal basis: consent.','Purpose: payroll.','Retention: seven years.','Controller contact: hr@example.test'])
    rid,results=run(client,cl);r=results[0]
    assert client.put(f"/criterion-results/{r['id']}/review",json={'final_value':'Yes','decision_type':'verified_ai'}).status_code==409
    for item in results: assert review(client,item,'Yes').status_code==200
    report=client.post(f'/assessment-runs/{rid}/reports',json={}).json();assert client.post(f"/reports/{report['id']}/export",json={}).status_code==200
    client.patch(f"/evidence/{r['evidence'][0]['id']}/review",json={'review_status':'rejected'})
    fresh=client.get(f'/assessment-runs/{rid}/results').json()[0];assert fresh['review'] is None;assert fresh['ai_state']=='fulfilled'
    assert client.put(f"/criterion-results/{r['id']}/review",json={'final_value':'Yes','decision_type':'verified_ai'}).status_code==422
    assert review(client,fresh,'Yes',True).status_code==200
    assert client.post(f"/reports/{report['id']}/export",json={}).status_code==409

def test_draft_gap_coverage_and_score(client):
    w,cl=setup(client);rid,results=run(client,cl)
    report=client.post(f'/assessment-runs/{rid}/reports').json()
    assert client.post(f"/reports/{report['id']}/export",json={'draft':True}).status_code==409
    response=client.post(f"/reports/{report['id']}/export",json={'draft':True,'confirm_incomplete':True});assert response.status_code==200
    import fitz
    assert 'DRAFT' in ''.join(p.get_text() for p in fitz.open(stream=response.content,filetype='pdf'))
    for r in results: assert review(client,r,'No').status_code==200
    score=client.get(f'/assessment-runs/{rid}').json()['score'];assert score['total_score']==0;assert not score['provisional']
    report=client.post(f'/assessment-runs/{rid}/reports').json();assert report['gap_count']==4
    with db.Session.begin() as s:
        item=s.get(db.Report,report['id']);item.items=[]
    assert client.post(f"/reports/{report['id']}/export",json={}).status_code==409

def test_population_and_joint_same_document(client):
    definition=sample();sub=definition['domains'][0]['controls'][0]['subcontrols'][0];sub['population_rule']='any_relevant_document';sub['criteria']=sub['criteria'][:2]
    w,cl=setup(client,definition)
    upload(client,w,'Customer Privacy Notice.pdf',['Privacy Notice','Legal basis: consent.'])
    upload(client,w,'Employee Privacy Notice.pdf',['Privacy Notice','Purpose: payroll.'])
    _,results=run(client,cl);assert all(r['ai_state']=='gap' for r in results)

def test_all_documents_conflict_precedence(client):
    w,cl=setup(client)
    upload(client,w,'Customer Privacy Notice.pdf',['Privacy Notice','Retention: seven years.'])
    upload(client,w,'Employee Privacy Notice.pdf',['Privacy Notice'])
    _,results=run(client,cl);assert results[2]['ai_state']=='gap'
    assert aggregate(['fulfilled','conflict'],'any_relevant_document')=='conflict'
    assert aggregate([],'all_relevant_documents')=='gap'

def test_failure_retry_preserves_success_and_reviews(client,monkeypatch):
    w,cl=setup(client);upload(client,w,'Privacy Notice.pdf',['Privacy Notice','Legal basis: consent.'])
    original=worker.assess_document
    def fail(s,d,c,sub):
        if c['number']==2: raise RuntimeError('provider failure')
        return original(s,d,c,sub)
    monkeypatch.setattr(worker,'assess_document',fail);rid,rs=run(client,cl)
    assert rs[1]['ai_state']=='analysis_failed'
    assert client.put(f"/criterion-results/{rs[1]['id']}/review",json={'final_value':'No','decision_type':'verified_ai'}).status_code==409
    assert review(client,rs[0],'Yes').status_code==200
    snapshot=client.get(f'/assessment-runs/{rid}').json()['snapshot_documents']
    assert client.post(f'/assessment-runs/{rid}/retry-failed').status_code==200
    monkeypatch.setattr(worker,'assess_document',original);worker.process(rid)
    refreshed=client.get(f'/assessment-runs/{rid}/results').json();assert refreshed[0]['review'] is not None;assert refreshed[1]['ai_state']=='gap'
    assert client.get(f'/assessment-runs/{rid}').json()['snapshot_documents']==snapshot

def test_na_and_override_rationale(client):
    w,cl=setup(client);_,rs=run(client,cl)
    r=rs[0]
    assert client.put(f"/criterion-results/{r['id']}/review",json={'final_value':'N/A','decision_type':'verified_ai'}).status_code==422
    assert client.put(f"/criterion-results/{r['id']}/review",json={'final_value':'N/A','decision_type':'override','override_note':' '}).status_code==422
    assert review(client,r,'N/A',True).status_code==200

def test_cross_document_conflict(client):
    definition=sample();definition['domains'][0]['controls'][0]['subcontrols'][0]['population_rule']='any_relevant_document'
    w,cl=setup(client,definition)
    upload(client,w,'Customer Privacy Notice.pdf',['Privacy Notice','Legal basis: consent.'])
    upload(client,w,'Employee Privacy Notice.pdf',['Privacy Notice','No legal basis is provided.'])
    _,results=run(client,cl);assert results[0]['ai_state']=='conflict'

@pytest.mark.parametrize('rotation',[90,180,270])
def test_rotated_pdf_anchors(client,rotation):
    import fitz
    w,_=setup(client);document=fitz.open(stream=pdf(['Privacy Notice','Legal basis: consent.']),filetype='pdf');document[0].set_rotation(rotation)
    response=client.post(f'/workspaces/{w}/documents',files={'file':('Rotated.pdf',document.tobytes(),'application/pdf')});assert response.status_code==200
    with db.Session() as s:
        stored=s.get(db.Document,response.json()['id']);span=stored.spans[0]
        original=document[0].get_text('dict')['blocks'][0]['lines'][0]['spans'][0]
        expected=fitz.Rect(original['bbox'])*document[0].rotation_matrix
        assert span['x0']==pytest.approx(expected.x0/document[0].rect.width)
        assert span['y0']==pytest.approx(expected.y0/document[0].rect.height)
        assert 0<=span['x0']<=span['x1']<=1 and 0<=span['y0']<=span['y1']<=1

def test_joint_failure_retry_publishes_only_resolved_group(client,monkeypatch):
    definition=sample();sub=definition['domains'][0]['controls'][0]['subcontrols'][0];sub['population_rule']='any_relevant_document';sub['criteria']=sub['criteria'][:2]
    w,cl=setup(client,definition);upload(client,w,'Privacy Notice.pdf',['Privacy Notice','Legal basis: consent.','Purpose: payroll.'])
    original=worker.assess_document
    def fail(s,d,c,sub):
        if c['number']==2: raise RuntimeError('provider failed')
        return original(s,d,c,sub)
    monkeypatch.setattr(worker,'assess_document',fail);rid,rs=run(client,cl)
    assert rs[0]['ai_state']=='pending' and rs[0]['evidence']
    assert rs[1]['ai_state']=='analysis_failed'
    assert review(client,rs[0],'Yes').status_code==409
    assert client.post(f'/assessment-runs/{rid}/retry-failed').status_code==200
    monkeypatch.setattr(worker,'assess_document',original);worker.process(rid)
    rs=client.get(f'/assessment-runs/{rid}/results').json()
    assert all(r['ai_state']=='fulfilled' for r in rs)

def test_joint_na_excluded_from_document_intersection(client,monkeypatch):
    definition=sample();sub=definition['domains'][0]['controls'][0]['subcontrols'][0];sub['population_rule']='any_relevant_document';sub['criteria']=sub['criteria'][:2];sub['criteria'][1]['applicability_condition']='Only when payroll processing occurs.'
    w,cl=setup(client,definition);upload(client,w,'Privacy Notice.pdf',['Privacy Notice','Legal basis: consent.'])
    original=worker.assess_document
    def assess(s,d,c,sub):
        if c['number']==2: return {'state':'proposed_not_applicable','evidence':[]},d.spans
        return original(s,d,c,sub)
    monkeypatch.setattr(worker,'assess_document',assess);_,rs=run(client,cl)
    assert rs[0]['ai_state']=='fulfilled';assert rs[1]['ai_state']=='proposed_not_applicable'

def test_sql_failure_isolated_before_failed_result_persistence(client,monkeypatch):
    from sqlalchemy import text
    w,cl=setup(client);upload(client,w,'Privacy Notice.pdf',['Privacy Notice','Legal basis: consent.','Purpose: payroll.'])
    original=worker.assess_document
    def query_failure(s,d,c,sub):
        if c['number']==1: s.execute(text('SELECT * FROM deliberately_missing_relation'))
        return original(s,d,c,sub)
    monkeypatch.setattr(worker,'assess_document',query_failure);rid,rs=run(client,cl)
    assert rs[0]['ai_state']=='analysis_failed'
    assert rs[1]['ai_state']=='fulfilled'
    assert client.get(f'/assessment-runs/{rid}').json()['status']=='completed_with_errors'

def test_pdf_upload_only_runtime_has_no_connector_routes(client):
    w,_=setup(client)
    assert client.get('/connectors').status_code==404
    assert client.post(f'/workspaces/{w}/imports',files={'file':('source.pdf',pdf(['Text PDF']))},data={'source_type':'google_drive','external_document_id':'external','external_version_id':'version'}).status_code==404
    assert client.post(f'/workspaces/{w}/connectors/google_drive/fetch',json={'external_document_id':'external'}).status_code==404
    doc=upload(client,w,'Upload.pdf',['Text PDF upload remains available.'])
    assert doc['source_type']=='upload' and doc['external_document_id'] is None and doc['external_version_id'] is None
