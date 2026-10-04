"""Provision an explicitly supplied checklist JSON; no sample generation."""
import argparse
import json
import math
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from .db import Session, Template, configure_runtime

class Definition(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(min_length=1)
class CriterionDefinition(Definition):
    number: int = Field(gt=0)
    text: str = Field(min_length=1)
    gap_phrasing: str = Field(min_length=1)
    key_terms: list[str]
    legal_references: list[str]
    expected_evidence: str
    applicability_condition: str | None = None
class SubcontrolDefinition(Definition):
    code: str = Field(min_length=1)
    title: str = Field(min_length=1)
    weight: float = Field(ge=0,allow_inf_nan=False)
    evidence_binding: Literal['corpus','same_document']
    population_rule: Literal['any_relevant_document','all_relevant_documents']
    criteria: list[CriterionDefinition] = Field(min_length=1)
class ControlDefinition(Definition):
    code: str = Field(min_length=1)
    title: str = Field(min_length=1)
    subcontrols: list[SubcontrolDefinition] = Field(min_length=1)
class DomainDefinition(Definition):
    code: str = Field(min_length=1)
    title: str = Field(min_length=1)
    controls: list[ControlDefinition] = Field(min_length=1)
class TemplateDefinition(Definition):
    scoring_policy: Literal['weighted_sum','criteria_engine_v1'] = 'weighted_sum'
    provenance: dict[str, object] | None = None
    name: str = Field(min_length=1)
    description: str = ''
    domains: list[DomainDefinition] = Field(min_length=1)

def validate_template(value):
    definition=TemplateDefinition.model_validate(value)
    identifiers={definition.id}
    def unique(identifier):
        if identifier in identifiers: raise ValueError('Checklist identifiers must be unique within the template.')
        identifiers.add(identifier)
    for domain in definition.domains:
        unique(domain.id)
        for control in domain.controls:
            unique(control.id)
            for subcontrol in control.subcontrols:
                unique(subcontrol.id)
                numbers=set()
                for criterion in subcontrol.criteria:
                    unique(criterion.id)
                    if criterion.number in numbers: raise ValueError('Criterion numbers must be unique within each sub-control.')
                    numbers.add(criterion.number)
    if definition.scoring_policy=='criteria_engine_v1':
        controls=[control for domain in definition.domains for control in domain.controls]
        groups=[group for control in controls for group in control.subcontrols]
        if any(not math.isclose(sum(group.weight for group in control.subcontrols),1,abs_tol=1e-8) for control in controls):
            raise ValueError('Criteria Engine control weights must sum to 1.')
        if not definition.provenance or definition.provenance.get('total_formula')!='=AVERAGE(S12:S21)':
            raise ValueError('Criteria Engine scoring requires the validated workbook formula provenance.')
    return definition.model_dump(exclude_unset=True)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('file',type=Path);args=parser.parse_args()
    try: definition=validate_template(json.loads(args.file.read_text()))
    except Exception: parser.error('Invalid checklist JSON. Check hierarchy, unique IDs, criterion numbers and evidence rules.')
    configure_runtime()
    with Session.begin() as session:
        if session.get(Template,definition['id']): parser.error('Template ID already exists. Use a new version ID; this command never overwrites template data.')
        session.add(Template(id=definition['id'],definition=definition))
    print('Checklist template loaded.')
if __name__=='__main__': main()
