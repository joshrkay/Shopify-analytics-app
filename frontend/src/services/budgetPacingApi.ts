/**
 * Budget Pacing API Service
 *
 * CRUD for ad spend budgets + pacing data.
 *
 * Backend routes:
 *   GET    /api/budgets
 *   POST   /api/budgets
 *   PUT    /api/budgets/{id}
 *   DELETE /api/budgets/{id}
 *   GET    /api/budget-pacing
 */

import { API_BASE_URL, createHeadersAsync, handleResponse } from './apiUtils';

export interface Budget {
  id: string;
  source_platform: string;
  budget_monthly_cents: number;
  start_date: string;
  end_date: string | null;
  enabled: boolean;
}

export interface BudgetCreate {
  source_platform: string;
  budget_monthly_cents: number;
  start_date: string;
  end_date?: string | null;
}

export interface PacingItem {
  platform: string;
  budget_cents: number;
  spent_cents: number;
  pct_spent: number;
  pct_time: number;
  pace_ratio: number;
  projected_total_cents: number;
  status: 'on_pace' | 'slightly_over' | 'over_budget';
  budget_id: string;
}

export interface PacingResponse {
  pacing: PacingItem[];
}

export async function listBudgets(): Promise<Budget[]> {
  const headers = await createHeadersAsync();
  const response = await fetch(`${API_BASE_URL}/api/budgets`, { headers });
  return handleResponse<Budget[]>(response);
}

export async function createBudget(data: BudgetCreate): Promise<Budget> {
  const headers = await createHeadersAsync();
  const response = await fetch(`${API_BASE_URL}/api/budgets`, {
    method: 'POST',
    headers: { ...headers, 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return handleResponse<Budget>(response);
}

export async function updateBudget(id: string, data: Partial<BudgetCreate & { enabled: boolean }>): Promise<Budget> {
  const headers = await createHeadersAsync();
  const response = await fetch(`${API_BASE_URL}/api/budgets/${id}`, {
    method: 'PUT',
    headers: { ...headers, 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return handleResponse<Budget>(response);
}

export async function deleteBudget(id: string): Promise<void> {
  const headers = await createHeadersAsync();
  const response = await fetch(`${API_BASE_URL}/api/budgets/${id}`, {
    method: 'DELETE',
    headers,
  });
  if (!response.ok) {
    throw new Error(`Failed to delete budget: ${response.status}`);
  }
}

export async function getPacing(): Promise<PacingResponse> {
  const headers = await createHeadersAsync();
  const response = await fetch(`${API_BASE_URL}/api/budget-pacing`, { headers });
  return handleResponse<PacingResponse>(response);
}
