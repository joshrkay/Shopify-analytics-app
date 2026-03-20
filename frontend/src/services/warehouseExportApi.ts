/**
 * Warehouse Export API client.
 *
 * Provides functions for managing data warehouse destinations
 * (BigQuery, Snowflake, Redshift).
 */

import { API_BASE_URL, createHeadersAsync, handleResponse } from './apiUtils';

export interface WarehouseDestinationType {
  id: string;
  name: string;
  description: string;
  requiredFields: string[];
}

export interface WarehouseDestination {
  id: string;
  destinationType: string;
  displayName: string;
  status: string;
  lastSyncAt: string | null;
  createdAt: string | null;
}

export interface WarehouseDestinationListResponse {
  destinations: WarehouseDestination[];
  total: number;
  maxDestinations: number;
}

export interface WarehouseTypesResponse {
  types: WarehouseDestinationType[];
}

export interface CreateWarehouseDestinationRequest {
  destination_type: string;
  display_name: string;
  configuration: Record<string, unknown>;
}

export interface WarehouseTestResponse {
  success: boolean;
  message: string;
}

export interface WarehouseSyncResponse {
  success: boolean;
  syncJobId?: string;
  message: string;
}

export async function getWarehouseTypes(): Promise<WarehouseTypesResponse> {
  const headers = await createHeadersAsync();
  const response = await fetch(`${API_BASE_URL}/api/warehouse/types`, { headers });
  return handleResponse<WarehouseTypesResponse>(response);
}

export async function listWarehouseDestinations(): Promise<WarehouseDestinationListResponse> {
  const headers = await createHeadersAsync();
  const response = await fetch(`${API_BASE_URL}/api/warehouse/destinations`, { headers });
  return handleResponse<WarehouseDestinationListResponse>(response);
}

export async function createWarehouseDestination(
  request: CreateWarehouseDestinationRequest
): Promise<WarehouseDestination> {
  const headers = await createHeadersAsync();
  const response = await fetch(`${API_BASE_URL}/api/warehouse/destinations`, {
    method: 'POST',
    headers: { ...headers, 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  return handleResponse<WarehouseDestination>(response);
}

export async function deleteWarehouseDestination(destinationId: string): Promise<void> {
  const headers = await createHeadersAsync();
  const response = await fetch(`${API_BASE_URL}/api/warehouse/destinations/${destinationId}`, {
    method: 'DELETE',
    headers,
  });
  if (!response.ok) {
    throw new Error(`Failed to delete warehouse destination: ${response.status}`);
  }
}

export async function testWarehouseConnection(destinationId: string): Promise<WarehouseTestResponse> {
  const headers = await createHeadersAsync();
  const response = await fetch(`${API_BASE_URL}/api/warehouse/destinations/${destinationId}/test`, {
    method: 'POST',
    headers,
  });
  return handleResponse<WarehouseTestResponse>(response);
}

export async function triggerWarehouseSync(destinationId: string): Promise<WarehouseSyncResponse> {
  const headers = await createHeadersAsync();
  const response = await fetch(`${API_BASE_URL}/api/warehouse/destinations/${destinationId}/sync`, {
    method: 'POST',
    headers,
  });
  return handleResponse<WarehouseSyncResponse>(response);
}
