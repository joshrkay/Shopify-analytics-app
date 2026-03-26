/**
 * Data Export API client.
 *
 * Provides functions for exporting analytics data in CSV/JSON format
 * and to Google Sheets.
 */

import { API_BASE_URL, createHeadersAsync, handleResponse } from './apiUtils';

export interface ExportDataset {
  id: string;
  name: string;
  description: string;
  columns: string[];
}

export interface AvailableDatasetsResponse {
  datasets: ExportDataset[];
}

export interface DataExportRequest {
  dataset: string;
  format: 'csv' | 'json';
  date_from?: string;
  date_to?: string;
  limit?: number;
}

export interface DataExportResponse {
  export_id: string;
  success: boolean;
  record_count: number;
  format: string;
  error?: string;
}

export interface SheetsExportRequest {
  dataset: string;
  date_from?: string;
  date_to?: string;
  limit?: number;
  spreadsheet_name?: string;
}

export interface SheetsExportResponse {
  success: boolean;
  spreadsheet_url?: string;
  spreadsheet_id?: string;
  record_count: number;
  error?: string;
}

export async function getAvailableDatasets(): Promise<AvailableDatasetsResponse> {
  const headers = await createHeadersAsync();
  const response = await fetch(`${API_BASE_URL}/api/exports/datasets`, { headers });
  return handleResponse<AvailableDatasetsResponse>(response);
}

export async function exportData(request: DataExportRequest): Promise<Response> {
  const headers = await createHeadersAsync();
  return fetch(`${API_BASE_URL}/api/exports/data`, {
    method: 'POST',
    headers: { ...headers, 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
}

export async function exportToSheets(request: SheetsExportRequest): Promise<SheetsExportResponse> {
  const headers = await createHeadersAsync();
  const response = await fetch(`${API_BASE_URL}/api/exports/sheets`, {
    method: 'POST',
    headers: { ...headers, 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  return handleResponse<SheetsExportResponse>(response);
}
