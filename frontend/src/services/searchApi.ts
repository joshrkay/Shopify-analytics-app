/**
 * Global Search API Service
 *
 * Backend route: GET /api/search?q=<query>
 */

import { API_BASE_URL, createHeadersAsync, handleResponse } from './apiUtils';

export interface SearchResult {
  type: string;
  title: string;
  path: string;
}

export interface SearchResponse {
  results: SearchResult[];
}

export async function globalSearch(query: string): Promise<SearchResponse> {
  const headers = await createHeadersAsync();
  const params = new URLSearchParams({ q: query });
  const response = await fetch(`${API_BASE_URL}/api/search?${params}`, { headers });
  return handleResponse<SearchResponse>(response);
}
