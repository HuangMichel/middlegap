"""Bounded XLSX import for the supplied Criteria Engine layout; never evaluates formulas."""
import hashlib
import io
import json
import math
import posixpath
import re
import zipfile
from dataclasses import dataclass
from xml.etree import ElementTree as ET
from fastapi import HTTPException
from .db import uid
from .load_template import validate_template

NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
SHEET = '2b. Criteria Engine'
MAX_FILE = 5 * 1024 * 1024
MAX_EXPANDED = 40 * 1024 * 1024
@dataclass(frozen=True)
class Cell:
    value: object = None
    formula: str | None = None
    error: bool = False

def fail(message): raise HTTPException(422,message)

def translate_shared_formula(formula,origin,destination):
    def coordinates(address):
        match=re.fullmatch(r'([A-Z]+)([0-9]+)',address)
        column=0
        for letter in match.group(1): column=column*26+ord(letter)-64
        return column,int(match.group(2))
    original_column,original_row=coordinates(origin)
    target_column,target_row=coordinates(destination)
    def replace(match):
        absolute_column,column,absolute_row,row=match.groups()
        column_index,_=coordinates(column+'1')
        if not absolute_column: column_index+=target_column-original_column
        row_index=int(row)+(0 if absolute_row else target_row-original_row)
        if not 1<=column_index<=16384 or not 1<=row_index<=1048576: fail('Shared formula references an invalid cell')
        letters=''
        while column_index:
            column_index,remainder=divmod(column_index-1,26);letters=chr(65+remainder)+letters
        return absolute_column+letters+absolute_row+str(row_index)
    segments=re.split(r'("(?:[^"]|"")*")',formula)
    for index in range(0,len(segments),2):
        segments[index]=re.sub(r'(?<![A-Za-z0-9_.])(\$?)([A-Z]{1,3})(\$?)([1-9][0-9]*)',replace,segments[index])
    return ''.join(segments)

def read_xlsx(data):
    if len(data)>MAX_FILE: raise HTTPException(413,'Workbook must be smaller than 5 MB')
    try:
        archive=zipfile.ZipFile(io.BytesIO(data))
        entries=archive.infolist()
        names=[entry.filename for entry in entries]
        if len(entries)>1000 or len(names)!=len(set(names)) or sum(entry.file_size for entry in entries)>MAX_EXPANDED:
            fail('Workbook archive exceeds safe processing limits or contains duplicate entries')
        for entry in entries:
            if entry.flag_bits & 1 or entry.file_size>10*1024*1024 or entry.file_size>max(1024*1024,entry.compress_size*200):
                fail('Workbook contains encrypted or excessively compressed content')
            if entry.filename.endswith('vbaProject.bin'): fail('Macro-enabled workbooks are unsupported')
        def xml(name):
            content=archive.read(name).decode('utf-8-sig')
            if '<!DOCTYPE' in content.upper() or '<!ENTITY' in content.upper(): fail('Workbook XML declarations are unsupported')
            return ET.fromstring(content)
        workbook=xml('xl/workbook.xml')
        relationships=xml('xl/_rels/workbook.xml.rels')
        targets={item.attrib['Id']:item.attrib.get('Target','') for item in relationships if item.attrib.get('TargetMode')!='External'}
        sheet=next((item for item in workbook.findall(f'{{{NS}}}sheets/{{{NS}}}sheet') if item.attrib.get('name')==SHEET),None)
        if sheet is None: fail('Expected worksheet "2b. Criteria Engine" was not found')
        target=targets[sheet.attrib[f'{{{REL}}}id']]
        path=posixpath.normpath(target.lstrip('/') if target.startswith('/') else posixpath.join('xl',target))
        if not path.startswith('xl/worksheets/'): fail('Worksheet relationship points outside the workbook')
        shared=[]
        if 'xl/sharedStrings.xml' in names:
            shared=[''.join(item.itertext()) for item in xml('xl/sharedStrings.xml').findall(f'{{{NS}}}si')]
        cells={}; shared_masters={}; shared_followers={}
        for item in xml(path).iter(f'{{{NS}}}c'):
            address=item.attrib.get('r','')
            if not re.fullmatch(r'[A-Z]{1,3}[1-9][0-9]{0,5}',address): fail('Workbook contains an invalid cell address')
            formula=item.find(f'{{{NS}}}f')
            value=item.find(f'{{{NS}}}v')
            raw=value.text if value is not None else None
            kind=item.attrib.get('t')
            if formula is not None:
                formula_text=''.join(formula.itertext())
                if formula.attrib.get('t')=='shared':
                    index=formula.attrib.get('si')
                    if formula_text: shared_masters[index]=(address,'='+formula_text)
                    else: shared_followers[address]=index
                cell=Cell(formula='='+formula_text,error=kind=='e')
            elif kind=='s': cell=Cell(shared[int(raw)])
            elif kind=='inlineStr':
                inline=item.find(f'{{{NS}}}is');cell=Cell(''.join(inline.itertext()) if inline is not None else '')
            elif kind=='e': cell=Cell(raw,error=True)
            elif raw is None: cell=Cell()
            elif kind in ('str','b'): cell=Cell(raw)
            else:
                number=float(raw)
                cell=Cell(int(number) if number.is_integer() else number)
            cells[address]=cell
        for address,index in shared_followers.items():
            if index not in shared_masters: fail('Shared formula is missing its source definition')
            origin,formula=shared_masters[index]
            cells[address]=Cell(formula=translate_shared_formula(formula,origin,address),error=cells[address].error)
        defined={item.attrib.get('name'):''.join(item.itertext()) for item in workbook.findall(f'{{{NS}}}definedNames/{{{NS}}}definedName')}
        archive.close()
        return cells,defined
    except HTTPException: raise
    except (ValueError,TypeError,LookupError,zipfile.BadZipFile,ET.ParseError,OverflowError,RuntimeError,NotImplementedError,OSError):
        fail('Invalid or unsupported XLSX workbook')

def text(cells,address,required=False):
    cell=cells.get(address,Cell())
    if cell.formula is not None or cell.error: fail(f'Cell {address} must contain an explicit value, not a formula or error')
    value='' if cell.value is None else str(cell.value).strip()
    if required and not value: fail(f'Missing required workbook value at {address}')
    return value

def parse(data,filename):
    cells,defined=read_xlsx(data)
    expected={'B11':'Control ID','C11':'Sub-Control','D11':'Weight %','E11':'#','F11':'Assessment Criterion','I11':'Document Request / Evidence','O11':'Gap Phrasing (for narrative)','W11':'GDPR Articles — Criterion','Z11':'Key Terms (machine-searchable)'}
    for address,header in expected.items():
        if text(cells,address)!=header: fail(f'Unsupported workbook header at {address}; expected {header}')
    domains=[];domain_map={};control=None;sub=None;criterion_sources={};warnings=[]
    for row in range(12,200):
        criterion_text=text(cells,f'F{row}')
        if not criterion_text: continue
        control_code=text(cells,f'B{row}')
        if control_code:
            match=re.fullmatch(r'(D\.[0-9]{2})\.S[0-9]{2}',control_code)
            if not match: fail(f'Invalid control ID at B{row}')
            domain_code=match.group(1)
            heading=text(cells,f'A{row}')
            if domain_code not in domain_map:
                if not heading.startswith(domain_code): fail(f'Domain heading at A{row} must match control {control_code}')
                title=heading[len(domain_code):].lstrip(' —–-').strip()
                if not title: fail(f'Missing domain title at A{row}')
                domain_map[domain_code]=dict(id=domain_code,code=domain_code,title=title,controls=[])
                domains.append(domain_map[domain_code])
            if any(existing['id']==control_code for existing in domain_map[domain_code]['controls']): fail(f'Repeated control start at B{row}')
            control=dict(id=control_code,code=control_code,title=control_code,subcontrols=[])
            domain_map[domain_code]['controls'].append(control);sub=None
        if control is None: fail(f'Criterion row {row} has no preceding control ID')
        sub_title=text(cells,f'C{row}')
        if sub_title:
            cell=cells.get(f'D{row}',Cell())
            if cell.formula or cell.error or isinstance(cell.value,bool) or not isinstance(cell.value,(int,float)) or not math.isfinite(cell.value) or cell.value<0:
                fail(f'Sub-control weight at D{row} must be a finite non-negative number')
            identifier=control['id']+f'.SC{len(control["subcontrols"])+1:02}'
            sub=dict(id=identifier,code=identifier,title=sub_title,weight=float(cell.value),evidence_binding=None,population_rule=None,criteria=[],source_rows=[])
            control['subcontrols'].append(sub)
        if sub is None: fail(f'Criterion row {row} has no preceding sub-control')
        cell=cells.get(f'E{row}',Cell())
        if cell.formula or cell.error or type(cell.value)!=int or cell.value<1: fail(f'Criterion number at E{row} must be a positive integer')
        number=cell.value
        if any(item['number']==number for item in sub['criteria']): fail(f'Duplicate criterion number at E{row}')
        ident=sub['id']+f'.C{number:02}'
        legal=text(cells,f'W{row}',True)
        criterion=dict(id=ident,number=number,text=criterion_text,gap_phrasing=text(cells,f'O{row}',True),key_terms=[value.strip() for value in text(cells,f'Z{row}',True).split(';') if value.strip()],legal_references=[legal],expected_evidence=text(cells,f'I{row}'),applicability_condition=None)
        sub['criteria'].append(criterion);sub['source_rows'].append(row)
        criterion_sources[ident]=dict(row=row,control_legal_references=text(cells,f'U{row}'),lookup_formulas={column:cells.get(f'{column}{row}',Cell()).formula for column in ('V','X','Y') if cells.get(f'{column}{row}',Cell()).formula})
    if not domains: fail('Workbook contains no criteria in F12:F199')
    controls=[item for domain in domains for item in domain['controls']]
    groups=[group for item in controls for group in item['subcontrols']]
    for address,cell in cells.items():
        if re.fullmatch(r'F[0-9]+',address) and int(address[1:])>199 and (cell.value is not None or cell.formula is not None):
            fail('Criterion-like content outside F12:F199 requires a supported workbook mapping')
    scoring_formulas={}
    for item in controls:
        if not math.isclose(sum(group['weight'] for group in item['subcontrols']),1,abs_tol=1e-8): fail(f'Weights for control {item["id"]} must sum to 1')
        start=item['subcontrols'][0]['source_rows'][0];end=item['subcontrols'][-1]['source_rows'][-1]
        expected_control=f'=SUM(K{start}:K{end})'
        if cells.get(f'L{start}',Cell()).formula!=expected_control: fail(f'Unsupported control scoring formula at L{start}')
        scoring_formulas[f'L{start}']=expected_control
        for group in item['subcontrols']:
            first,last=group['source_rows'][0],group['source_rows'][-1]
            region=f'G{first}' if first==last else f'G{first}:G{last}'
            expected_j=f'=IFERROR(COUNTIF({region},"Yes")/COUNTIFS({region},"<>N/A",{region},"<>"),0)'
            expected_k=f'=D{first}*J{first}'
            expected_m=f'=IF(COUNTIF({region},"<>")=0,"Not Assessed",IF(COUNTIFS({region},"<>N/A",{region},"<>")=0,"N/A",IF(COUNTIF({region},"Yes")=COUNTIFS({region},"<>N/A",{region},"<>"),"Met",IF(COUNTIF({region},"Yes")=0,"Gap","Partial"))))'
            for column,formula in [('J',expected_j),('K',expected_k),('M',expected_m)]:
                address=f'{column}{first}'
                if cells.get(address,Cell()).formula!=formula: fail(f'Unsupported scoring formula at {address}')
                scoring_formulas[address]=formula
            for row in group['source_rows'][1:]:
                if any(cells.get(f'{column}{row}',Cell()).formula is not None or cells.get(f'{column}{row}',Cell()).value is not None for column in ('J','K','M','L')):
                    fail(f'Unexpected additional scoring values or formulas at row {row}')
        for group in item['subcontrols'][1:]:
            row=group['source_rows'][0]
            if cells.get(f'L{row}',Cell()).value is not None or cells.get(f'L{row}',Cell()).formula is not None: fail(f'Unexpected additional control score at L{row}')
    warnings.append(dict(code='explicit_evidence_rules_required',message='The workbook has no evidence-binding or population rules. Choose explicit defaults and any sub-control overrides before import.'))
    if any(not criterion['expected_evidence'] for domain in domains for item in domain['controls'] for group in item['subcontrols'] for criterion in group['criteria']):
        warnings.append(dict(code='missing_evidence_expectations',message='Some or all Document Request / Evidence cells are empty. No document expectations will be invented; optional sub-control descriptions can narrow document discovery.'))
    warnings.append(dict(code='no_applicability_conditions',message='The workbook contains no explicit applicability conditions. AI cannot propose N/A; human N/A requires an override rationale.'))
    if '#REF!' in defined.get('RefLookup',''):
        warnings.append(dict(code='broken_reference_lookup',message='RefLookup contains #REF!. Supporting guidance and legal-basis lookup formulas are retained for traceability, not evaluated. Criterion legal references are retained from column W.'))
    warnings.append(dict(code='first_subcontrol_domain_filter',message='Workbook domain scores exclude an entire control when its first sub-control is N/A or Not Assessed, even if later sub-controls are reviewed. This literal formula behavior is preserved.'))
    # Whitelist the workbook's known aggregation formulas; arbitrary Excel formulas are never executed.
    domain_formulas={}
    for row in range(12,22):
        code=text(cells,f'Q{row}')
        formula=cells.get(f'S{row}',Cell()).formula
        if code in domain_map and formula: domain_formulas[code]=formula
    total_formula=cells.get('S23',Cell()).formula
    if total_formula!='=AVERAGE(S12:S21)': fail('Unsupported overall scoring formula at S23; expected =AVERAGE(S12:S21)')
    if len(domains)!=10 or len(domain_formulas)!=10: fail('Workbook must contain the ten configured domain summary formulas in S12:S21')
    for row in range(12,22):
        formula=domain_formulas.get(text(cells,f'Q{row}'))
        expected_formula=f'=IFERROR(AVERAGEIFS($L$12:$L$199,$B$12:$B$199,Q{row}&".*",$M$12:$M$199,"<>N/A",$M$12:$M$199,"<>Not Assessed",$M$12:$M$199,"<>"),0)'
        if formula!=expected_formula: fail(f'Unsupported domain scoring formula at S{row}')
    definition=dict(id='',name='',description='Imported Criteria Engine workbook',domains=domains,scoring_policy='criteria_engine_v1',provenance=dict(source_hash=hashlib.sha256(data).hexdigest(),source_filename=filename,sheet_name=SHEET,criterion_rows=criterion_sources,domain_formulas=domain_formulas,total_formula=total_formula,warnings=warnings,defined_names=defined,scoring_formulas=scoring_formulas))
    return definition

def preview(data,filename):
    definition=parse(data,filename)
    subcontrols=[dict(id=group['id'],domain_id=domain['id'],control_id=item['id'],title=group['title'],weight=group['weight'],criterion_count=len(group['criteria']),source_rows=group['source_rows']) for domain in definition['domains'] for item in domain['controls'] for group in item['subcontrols']]
    return dict(preview_hash=definition['provenance']['source_hash'],source_filename=filename,sheet_name=SHEET,counts=dict(domains=len(definition['domains']),controls=sum(len(domain['controls']) for domain in definition['domains']),subcontrols=len(subcontrols),criteria=sum(item['criterion_count'] for item in subcontrols)),warnings=definition['provenance']['warnings'],subcontrols=subcontrols)

def imported_definition(data,filename,name,preview_hash,default_binding,default_population,confirm_warnings,raw_rules):
    definition=parse(data,filename)
    if definition['provenance']['source_hash']!=preview_hash: raise HTTPException(409,'Workbook differs from its preview; preview this file again')
    if not confirm_warnings: raise HTTPException(409,'Confirm the workbook warnings and explicit rule choices before importing')
    if not name.strip() or len(name)>200: fail('Template name must contain between 1 and 200 characters')
    if not isinstance(raw_rules,str) or len(raw_rules)>200000: fail('subcontrol_rules exceeds the supported size')
    try: rules=json.loads(raw_rules)
    except (json.JSONDecodeError,TypeError,RecursionError): fail('subcontrol_rules must be a JSON object')
    if not isinstance(rules,dict): fail('subcontrol_rules must be a JSON object keyed by sub-control ID')
    known={group['id'] for domain in definition['domains'] for item in domain['controls'] for group in item['subcontrols']}
    if set(rules)-known: fail('subcontrol_rules includes unknown sub-control IDs')
    for domain in definition['domains']:
        for item in domain['controls']:
            for group in item['subcontrols']:
                rule=rules.get(group['id'],{})
                if not isinstance(rule,dict) or set(rule)-{'evidence_binding','population_rule','expected_evidence'}: fail('Invalid sub-control rule fields')
                group['evidence_binding']=rule.get('evidence_binding',default_binding)
                group['population_rule']=rule.get('population_rule',default_population)
                if 'expected_evidence' in rule:
                    if not isinstance(rule['expected_evidence'],str) or len(rule['expected_evidence'])>2000: fail('expected_evidence must be a documentary description of at most 2000 characters')
                    for criterion in group['criteria']: criterion['expected_evidence']=rule['expected_evidence'].strip()
                group.pop('source_rows')
    definition['id']='workbook-'+uid();definition['name']=name.strip()
    definition['provenance']['import_rules']=dict(default_evidence_binding=default_binding,default_population_rule=default_population,subcontrol_rules=rules)
    try: return validate_template(definition)
    except ValueError: fail('Invalid evidence binding or population rule configuration')
