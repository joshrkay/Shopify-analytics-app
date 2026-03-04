/**
 * Cohort Analysis API Service
 *
 * Fetches cohort retention data for the retention heatmap.
 *
 * Backend route: GET /api/analytics/cohort-analysis?timeframe=
 */

import { API_BASE_URL, createHeadersAsync, handleResponse } from './apiUtils';

export interface CohortPeriod {
  period: number;
  retention_rate: number;
  customers: number;
  revenue: number;
}

export interface CohortRow {
  cohort_month: string;
  customers_total: number;
  periods: CohortPeriod[];
}

export interface CohortSummary {
  avg_retention_month_1: number;
  best_cohort: string;
  worst_cohort: string;
  total_cohorts: number;
}

export interface CohortAnalysisResponse {
  cohorts: CohortRow[];
  summary: CohortSummary;
}

export async function getCohortRetention(
  timeframe: string = '12m',
): Promise<CohortAnalysisResponse> {
  const headers = await createHeadersAsync();
  const query = new URLSearchParams({ timeframe });
  const response = await fetch(
    `${API_BASE_URL}/api/analytics/cohort-analysis?${query}`,
    { method: 'GET', headers },
  );
  return handleResponse<CohortAnalysisResponse>(response);
}
