import type { AIState, FinalValue, Result } from './types';
export const stateLabels: Record<AIState, string> = {
  pending: 'Pending',
  fulfilled: 'Evidence found',
  gap: 'Potential gap',
  uncertain: 'Uncertain',
  conflict: 'Conflicting evidence',
  proposed_not_applicable: 'Proposed N/A',
  analysis_failed: 'Analysis failed',
};
export function suggestedValue(state: AIState): FinalValue | null {
  return state === 'fulfilled'
    ? 'Yes'
    : state === 'gap'
      ? 'No'
      : state === 'proposed_not_applicable'
        ? 'N/A'
        : null;
}
export function requiresOverride(result: Result, value: FinalValue): boolean {
  return (
    suggestedValue(result.ai_state) !== value ||
    (value === 'Yes' &&
      !result.evidence.some(
        (e) => e.classification === 'supports' && e.review_status === 'accepted',
      ))
  );
}
export function reviewBlockReason(result: Result | null): string | null {
  if (!result) return 'Assessment has not reached this criterion yet.';
  if (result.ai_state === 'pending') return 'Wait for this criterion to finish assessment.';
  if (result.ai_state === 'analysis_failed')
    return 'Retry the failed analysis before reviewing this criterion.';
  if (result.evidence.some((e) => e.review_status === 'unreviewed'))
    return 'Accept or reject every citation before saving a final determination.';
  return null;
}
export function formatList(value: string[] | string | null | undefined): string {
  return Array.isArray(value) ? value.join(' · ') : value || 'Not specified';
}
