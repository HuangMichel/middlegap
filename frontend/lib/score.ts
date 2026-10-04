import type { Score } from './types';

export function formatScore(
  value: number,
  maximum: number,
  aggregation?: Score['aggregation'],
): string {
  if (aggregation === 'criteria_engine_v1') {
    if (!maximum) return 'N/A';
    return `${((value / maximum) * 100).toFixed(1)}%`;
  }
  return `${Number(value).toFixed(1)} / ${Number(maximum).toFixed(1)}`;
}
