"""Synthetic adapters exclusively for isolated tests; never imported by app modules."""
import re
from pathlib import Path
from app import ai, main, services, worker

def sample():
    fields=[('Legal basis is included','legal basis',['legal basis','consent']),('Purpose of processing is included','processing purpose',['purpose','processing']),('Retention period is included','retention period',['retention','retained']),('Controller contact is included','controller contact',['contact','controller'])]
    criteria=[dict(id=f'D.03.S01.SC01.C{i:02}',number=i,text=text,gap_phrasing=f'Please provide documentary evidence of the {gap}.',key_terms=keys,legal_references=['GDPR Article 13'],expected_evidence='Privacy Notice',applicability_condition=None) for i,(text,gap,keys) in enumerate(fields,1)]
    return dict(id='sample-privacy',name='Privacy Notice integration fixture',description='Isolated synthetic test fixture; not workbook data.',domains=[dict(id='D.03',code='D.03',title='Consent and Privacy Notice',controls=[dict(id='D.03.S01',code='D.03.S01',title='Privacy Notice',subcontrols=[dict(id='D.03.S01.SC01',code='D.03.S01.SC01',title='Privacy Notice clauses',weight=10,evidence_binding='same_document',population_rule='all_relevant_documents',criteria=criteria)])])])


def assess_document(s, doc, criterion, sub):
    spans=[span for span in doc.spans if any(term.lower() in span['text'].lower() for term in criterion['key_terms'])]
    evidence=[]
    for span in spans:
        negative=bool(re.search(r'\b(no|not|never|without)\b',span['text'],re.I))
        evidence.append(dict(classification='contradicts' if negative else 'supports',span_ids=[span['id']],explanation='Synthetic test-provider result.'))
    supports=any(item['classification']=='supports' for item in evidence)
    contradicts=any(item['classification']=='contradicts' for item in evidence)
    state='conflict' if supports and contradicts else ('gap' if contradicts or not supports else 'fulfilled')
    return dict(state=state,evidence=evidence),doc.spans

def discover_population(s, docs, sub, criteria):
    expectations=[criterion.get('expected_evidence','') for criterion in criteria]
    if not any(expectations): return docs
    tokens=set(re.findall(r'[a-z]+',' '.join(expectations).lower()))-{'copy','of','the','a','an','provided','to','document','evidence','documents','required'}
    return [doc for doc in docs if tokens & set(re.findall(r'[a-z]+',(doc.original_filename+' '+' '.join(span['text'] for span in doc.spans)).lower()))]

def install(set_attribute, storage_root):
    storage_root=Path(storage_root)
    storage_root.mkdir(parents=True,exist_ok=True)
    def storage(data=None,path=None):
        target=storage_root/path
        if data is None: return target.read_bytes()
        target.write_bytes(data)
    set_attribute(services,'storage',storage)
    set_attribute(main,'storage',storage)
    set_attribute(services,'index_chunk',lambda s,chunk: None)
    set_attribute(worker,'assess_document',assess_document)
    set_attribute(ai,'discover_population',discover_population)
    set_attribute(worker,'progress',lambda s,run: None)
    set_attribute(main,'configure_runtime',lambda: None)
