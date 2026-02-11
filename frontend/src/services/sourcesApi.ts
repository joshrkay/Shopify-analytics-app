/**
 * Sources API Service
 *
 * Fetches all data source connections from the unified /api/sources endpoint.
 *
 * Story 2.1.1 — Unified Source domain model
 */

import { API_BASE_URL, createHeadersAsync, handleResponse } from './apiUtils';
import { normalizeApiSource, type RawApiSource } from './sourceNormalizer';
import type { Source } from '../types/sources';

interface RawSourceListResponse {
  sources: RawApiSource[];
  total: number;
}

/**
 * List all data source connections for the current tenant.
 *
 * Returns a unified list of Shopify and ad platform connections.
 */
export async function listSources(): Promise<Source[]> {
  const headers = await createHeadersAsync();
  const response = await fetch(`${API_BASE_URL}/api/sources`, {
    method: 'GET',
    headers,
  });
  const data = await handleResponse<RawSourceListResponse>(response);
  return data.sources.map(normalizeApiSource);
}
