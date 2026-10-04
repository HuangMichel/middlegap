export type EvidenceBinding = 'corpus' | 'same_document';
export type PopulationRule = 'any_relevant_document' | 'all_relevant_documents';
export type WorkbookPreview = {
  preview_hash: string;
  source_filename: string;
  sheet_name: string;
  counts: { domains: number; controls: number; subcontrols: number; criteria: number };
  warnings: { code: string; message: string }[];
  subcontrols: {
    id: string;
    domain_id: string;
    control_id: string;
    title: string;
    weight: number;
    criterion_count: number;
    source_rows: number[];
  }[];
};
export type SubcontrolRule = {
  evidence_binding?: EvidenceBinding;
  population_rule?: PopulationRule;
  expected_evidence?: string;
};
export type WorkbookImportValues = {
  file: File | null;
  preview: WorkbookPreview | null;
  name: string;
  binding: EvidenceBinding | '';
  population: PopulationRule | '';
  confirmWarnings: boolean;
  rules: Record<string, SubcontrolRule>;
};

/** A changed file or later request makes all earlier previews obsolete. */
export class PreviewRequests {
  private generation = 0;
  begin() {
    return ++this.generation;
  }
  invalidate() {
    ++this.generation;
  }
  isCurrent(request: number) {
    return request === this.generation;
  }
  async resolve<T>(request: number, result: Promise<T>, apply: (value: T) => void) {
    try {
      const value = await result;
      if (!this.isCurrent(request)) return false;
      apply(value);
      return true;
    } catch (error) {
      if (!this.isCurrent(request)) return false;
      throw error;
    }
  }
}

export function workbookImportError(values: WorkbookImportValues): string | null {
  if (!values.file || !values.file.name.toLowerCase().endsWith('.xlsx'))
    return 'Select an Excel .xlsx workbook.';
  if (!values.preview?.preview_hash || values.preview.source_filename !== values.file.name)
    return 'Preview this workbook before importing it.';
  if (!values.name.trim()) return 'Enter a template name.';
  if (!values.binding || !values.population) return 'Choose both assessment rule defaults.';
  if (values.preview.warnings.length && !values.confirmWarnings)
    return 'Confirm the workbook warnings before importing.';
  return null;
}

export function workbookImportForm(values: WorkbookImportValues): FormData {
  const error = workbookImportError(values);
  if (error) throw new Error(error);
  const form = new FormData();
  form.append('file', values.file!);
  form.append('name', values.name.trim());
  form.append('preview_hash', values.preview!.preview_hash);
  form.append('default_evidence_binding', values.binding);
  form.append('default_population_rule', values.population);
  form.append('confirm_warnings', String(values.confirmWarnings));
  const rules = Object.fromEntries(
    Object.entries(values.rules)
      .map(([id, rule]) => {
        const cleaned = { ...rule };
        if (cleaned.expected_evidence?.trim())
          cleaned.expected_evidence = cleaned.expected_evidence.trim();
        else delete cleaned.expected_evidence;
        return [id, cleaned];
      })
      .filter(([, rule]) => Object.keys(rule).length),
  );
  form.append('subcontrol_rules', JSON.stringify(rules));
  return form;
}
