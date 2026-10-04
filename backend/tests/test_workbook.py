import io
import json
import os
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
import pytest
from app import db
from app.services import criteria, score
from app.workbook import preview, imported_definition, read_xlsx, translate_shared_formula

NS='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
HEADERS={'B':'Control ID','C':'Sub-Control','D':'Weight %','E':'#','F':'Assessment Criterion','I':'Document Request / Evidence','O':'Gap Phrasing (for narrative)','W':'GDPR Articles — Criterion','Z':'Key Terms (machine-searchable)'}

def fixture_cells():
    cells={column+'11':value for column,value in HEADERS.items()}
    row=12;group_index=0;control_index=0
    for domain_number in range(1,11):
        domain=f'D.{domain_number:02}'
        cells[f'Q{11+domain_number}']=domain
        cells[f'S{11+domain_number}']=f'=IFERROR(AVERAGEIFS($L$12:$L$199,$B$12:$B$199,Q{11+domain_number}&".*",$M$12:$M$199,"<>N/A",$M$12:$M$199,"<>Not Assessed",$M$12:$M$199,"<>"),0)'
        for control_number in range(1,4 if domain_number<=4 else 3):
            control=f'{domain}.S{control_number:02}'
            cells[f'B{row}']=control
            if control_number==1: cells[f'A{row}']=domain+' — Synthetic domain '+str(domain_number)
            control_start=row;group_count=4 if control_index<8 else 3
            for group in range(group_count):
                length=3 if group_index<28 else 2
                first,last=row,row+length-1;region=f'G{first}:G{last}'
                cells[f'C{row}']='Synthetic sub-control '+str(group+1);cells[f'D{row}']=1/group_count
                cells[f'J{row}']=f'=IFERROR(COUNTIF({region},"Yes")/COUNTIFS({region},"<>N/A",{region},"<>"),0)'
                cells[f'K{row}']=f'=D{row}*J{row}'
                cells[f'M{row}']=f'=IF(COUNTIF({region},"<>")=0,"Not Assessed",IF(COUNTIFS({region},"<>N/A",{region},"<>")=0,"N/A",IF(COUNTIF({region},"Yes")=COUNTIFS({region},"<>N/A",{region},"<>"),"Met",IF(COUNTIF({region},"Yes")=0,"Gap","Partial"))))'
                for number in range(1,length+1):
                    cells[f'E{row}']=number;cells[f'F{row}']='Synthetic criterion '+str(row);cells[f'O{row}']='Synthetic outstanding evidence '+str(row);cells[f'W{row}']='Art. 5';cells[f'U{row}']='Art. 24';cells[f'Z{row}']='document term; alternate term';cells[f'X{row}']=f'=VLOOKUP(W{row},RefLookup,2,FALSE())';row+=1
                group_index+=1
            cells[f'L{control_start}']=f'=SUM(K{control_start}:K{row-1})';control_index+=1
    assert row==200 and group_index==80 and control_index==24
    cells['Q23']='Total Compliance Score';cells['S23']='=AVERAGE(S12:S21)'
    return cells

def workbook_bytes(cells=None,defined='#REF!'):
    cells=fixture_cells() if cells is None else cells
    root=ET.Element('worksheet',xmlns=NS);sheet_data=ET.SubElement(root,'sheetData');rows={}
    for address,value in cells.items():
        number=''.join(char for char in address if char.isdigit())
        row=rows.get(number)
        if row is None: row=ET.SubElement(sheet_data,'row',r=number);rows[number]=row
        cell=ET.SubElement(row,'c',r=address)
        if isinstance(value,(int,float)): ET.SubElement(cell,'v').text=str(value)
        elif value.startswith('='): ET.SubElement(cell,'f').text=value[1:];ET.SubElement(cell,'v').text='999' # Never use cached formula values.
        else: cell.set('t','inlineStr');ET.SubElement(ET.SubElement(cell,'is'),'t').text=value
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('xl/workbook.xml',f'<workbook xmlns="{NS}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="2b. Criteria Engine" sheetId="1" r:id="rId1"/></sheets><definedNames><definedName name="RefLookup">{defined}</definedName></definedNames></workbook>')
        archive.writestr('xl/_rels/workbook.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        archive.writestr('xl/worksheets/sheet1.xml',ET.tostring(root))
    return output.getvalue()

def definition(data=None):
    data=workbook_bytes() if data is None else data
    p=preview(data,'fixture.xlsx')
    return imported_definition(data,'fixture.xlsx','Synthetic imported fixture',p['preview_hash'],'corpus','any_relevant_document',True,'{}')

def test_preview_maps_forward_filled_control_and_separate_domain_summary():
    result=preview(workbook_bytes(),'fixture.xlsx')
    assert result['counts']==dict(domains=10,controls=24,subcontrols=80,criteria=188)
    assert result['subcontrols'][1]['domain_id']=='D.01' # Q on later rows names unrelated summary domains.
    assert result['subcontrols'][1]['id']=='D.01.S01.SC02'
    assert 'broken_reference_lookup' in {warning['code'] for warning in result['warnings']}
    imported=definition();first=imported['domains'][0]['controls'][0]['subcontrols'][0]['criteria'][0]
    assert first['legal_references']==['Art. 5'] and first['key_terms']==['document term','alternate term']
    assert first['expected_evidence']=='' and first['applicability_condition'] is None
    assert imported['provenance']['total_formula']=='=AVERAGE(S12:S21)'

def test_upload_preview_confirmation_rules_and_immutable_template(client):
    data=workbook_bytes();files={'file':('fixture.xlsx',data,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
    p=client.post('/checklist-templates/workbook/preview',files=files);assert p.status_code==200
    fields=dict(name='Imported',preview_hash=p.json()['preview_hash'],default_evidence_binding='corpus',default_population_rule='any_relevant_document')
    assert client.post('/checklist-templates/workbook',files=files,data=fields).status_code==409
    fields['confirm_warnings']='true';fields['subcontrol_rules']=json.dumps({'D.01.S01.SC01':dict(evidence_binding='same_document',population_rule='all_relevant_documents',expected_evidence='Human-configured document description')})
    response=client.post('/checklist-templates/workbook',files=files,data=fields);assert response.status_code==200;assert response.json()['criterion_count']==188
    with db.Session() as s:
        value=s.get(db.Template,response.json()['id']).definition
        group=value['domains'][0]['controls'][0]['subcontrols'][0]
        assert group['evidence_binding']=='same_document' and group['population_rule']=='all_relevant_documents'
        assert group['criteria'][0]['expected_evidence']=='Human-configured document description'
    fields['preview_hash']='wrong';assert client.post('/checklist-templates/workbook',files=files,data=fields).status_code==409
    fields['preview_hash']=p.json()['preview_hash'];fields['subcontrol_rules']='{"unknown":{}}';assert client.post('/checklist-templates/workbook',files=files,data=fields).status_code==422

def test_required_rule_defaults_are_not_invented(client):
    data=workbook_bytes();p=preview(data,'fixture.xlsx')
    response=client.post('/checklist-templates/workbook',files={'file':('fixture.xlsx',data)},data=dict(name='Imported',preview_hash=p['preview_hash'],confirm_warnings='true'))
    assert response.status_code==422

@pytest.mark.parametrize('address,value',[('F12','=EXTERNAL()'),('W12','=VLOOKUP(A1,RefLookup,1)'),('D12',-1),('K12','=1'),('S23','=SUM(S12:S21)'),('S12','=999'),('E13',1)])
def test_invalid_values_or_changed_scoring_formulas_rejected(address,value):
    cells=fixture_cells();cells[address]=value
    with pytest.raises(Exception) as failure: preview(workbook_bytes(cells),'fixture.xlsx')
    assert failure.value.status_code==422

def test_archive_limits_and_malformed_xml(client):
    assert client.post('/checklist-templates/workbook/preview',files={'file':('bad.xlsx',b'not zip')}).status_code==422
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as archive: archive.writestr('oversized.xml',b'A'*(11*1024*1024))
    assert client.post('/checklist-templates/workbook/preview',files={'file':('bomb.xlsx',buffer.getvalue())}).status_code==422
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w') as archive: archive.writestr('xl/workbook.xml','<!DOCTYPE x [<!ENTITY x "boom">]><x/>')
    assert client.post('/checklist-templates/workbook/preview',files={'file':('entity.xlsx',buffer.getvalue())}).status_code==422

def test_shared_formula_translation_preserves_absolute_references_and_quoted_text():
    assert translate_shared_formula('=D107*J107','K107','K108')=='=D108*J108'
    assert translate_shared_formula('=IF(A1="A1",$B$1,C$2)','D1','D2')=='=IF(A2="A1",$B$1,C$2)'

def scoring_run(session,value,decisions):
    workspace=db.Workspace(name='Scoring fixture');session.add(workspace);session.flush();checklist=db.Checklist(workspace_id=workspace.id,definition=value);session.add(checklist);session.flush()
    run=db.Run(checklist_id=checklist.id,model_provider='mistral',model_name='fixture',snapshot=[],total_criteria=188);session.add(run);session.flush()
    for _,_,group,criterion in criteria(value):
        decision=decisions(criterion)
        session.add(db.Result(run_id=run.id,criterion_id=criterion['id'],subcontrol_id=group['id'],gap_id=criterion['id']+'.gap',ai_state='gap',review={'final_value':decision} if decision else None))
    session.flush();return score(session,run)

@pytest.mark.parametrize('decision,expected',[('Yes',1),('No',0),('N/A',0)])
def test_literal_workbook_all_decisions_score(client,decision,expected):
    with db.Session.begin() as s: result=scoring_run(s,definition(),lambda c: decision)
    assert result['total_score']==pytest.approx(expected) and result['max_score']==1
    assert all(domain['score']==pytest.approx(expected) and domain['max_score']==1 for domain in result['domains'])
    assert result['aggregation']=='criteria_engine_v1' and not result['provisional']

@pytest.mark.parametrize('first_value',[None,'N/A'])
def test_first_subcontrol_status_excludes_control_without_renormalization(client,first_value):
    value=definition();control=value['domains'][0]['controls'][0];first_ids={c['id'] for c in control['subcontrols'][0]['criteria']};later_ids={c['id'] for group in control['subcontrols'][1:] for c in group['criteria']}
    with db.Session.begin() as s:
        result=scoring_run(s,value,lambda c: first_value if c['id'] in first_ids else ('Yes' if c['id'] in later_ids else None))
    assert result['domains'][0]['controls'][0]['score']==pytest.approx(.75)
    assert result['domains'][0]['score']==0 and result['total_score']==0

def test_provisional_review_denominator_and_fixed_weights(client):
    value=definition();first=value['domains'][0]['controls'][0]['subcontrols'][0]['criteria'][0]['id']
    with db.Session.begin() as s: result=scoring_run(s,value,lambda c: 'Yes' if c['id']==first else None)
    assert result['domains'][0]['score']==pytest.approx(.25)
    assert result['total_score']==pytest.approx(.025) and result['provisional']

def test_actual_user_workbook_if_supplied():
    path=os.getenv('WORKBOOK_TEST_PATH')
    if not path: pytest.skip('Set WORKBOOK_TEST_PATH to verify the supplied local workbook without copying it into the repository')
    data=Path(path).read_bytes();value=definition(data);assert len(value['provenance']['criterion_rows'])==188
    assert value['domains'][2]['controls'][0]['subcontrols'][0]['criteria'][0]['id'].startswith('D.03.S01.')
    assert value['provenance']['defined_names']['RefLookup']=='#REF!'

@pytest.mark.parametrize('scenario,expected',[
    ('all_yes',1),('all_na',0),('only_row17_yes',.06),
    ('first_na_later_yes',0),('first_blank_later_yes',0),('first_yes_later_na',.06),
])
def test_actual_workbook_literal_formula_oracles(client,scenario,expected):
    path=os.getenv('WORKBOOK_TEST_PATH')
    if not path: pytest.skip('Actual supplied workbook is optional and never committed')
    value=definition(Path(path).read_bytes())
    row_for={ident:metadata['row'] for ident,metadata in value['provenance']['criterion_rows'].items()}
    def decision(criterion):
        row=row_for[criterion['id']]
        if scenario=='all_yes': return 'Yes'
        if scenario=='all_na': return 'N/A'
        if scenario=='only_row17_yes': return 'Yes' if row==17 else None
        if scenario=='first_na_later_yes': return 'N/A' if 17<=row<=28 else ('Yes' if 29<=row<=31 else None)
        if scenario=='first_blank_later_yes': return 'Yes' if 29<=row<=31 else None
        if scenario=='first_yes_later_na': return 'Yes' if 17<=row<=28 else ('N/A' if 29<=row<=31 else None)
    with db.Session.begin() as s: result=scoring_run(s,value,decision)
    assert result['total_score']==pytest.approx(expected)

def test_non_utf8_entity_xml_is_rejected(client):
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w') as archive:
        archive.writestr('xl/workbook.xml','<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE x [<!ENTITY x "boom">]><x>&x;</x>'.encode('utf-16'))
    assert client.post('/checklist-templates/workbook/preview',files={'file':('entity.xlsx',output.getvalue())}).status_code==422
