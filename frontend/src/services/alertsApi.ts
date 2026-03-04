/**
 * Alerts API Service
 *
 * Backend routes:
 *   GET    /api/alerts/rules
 *   POST   /api/alerts/rules
 *   PUT    /api/alerts/rules/{id}
 *   DELETE /api/alerts/rules/{id}
 *   PATCH  /api/alerts/rules/{id}/toggle
 *   GET    /api/alerts/history
 *   GET    /api/alerts/rules/{id}/history
 */

import { API_BASE_URL, createHeadersAsync, handleResponse } from './apiUtils';

export interface AlertRule {
  id: string;
  name: string;
  description: string | null;
  metric_name: string;
  comparison_operator: string;
  threshold_value: number;
  evaluation_period: string;
  severity: 'info' | 'warning' | 'critical';
  enabled: boolean;
}

export interface AlertRuleCreate {
  name: string;
  metric_name: string;
  comparison_operator: string;
  threshold_value: number;
  evaluation_period: string;
  severity?: string;
  description?: string;
}

export interface AlertExecution {
  id: string;
  alert_rule_id: string;
  fired_at: string;
  metric_value: number;
  threshold_value: number;
  resolved_at: string | null;
}

export interface RulesListResponse {
  rules: AlertRule[];
  count: number;
  limit: number;
}

export async function listAlertRules(): Promise<RulesListResponse> {
  const headers = await createHeadersAsync();
  const response = await fetch(`${API_BASE_URL}/api/alerts/rules`, { headers });
  return handleResponse<RulesListResponse>(response);
}

export async function createAlertRule(data: AlertRuleCreate): Promise<AlertRule> {
  const headers = await createHeadersAsync();
  const response = await fetch(`${API_BASE_URL}/api/alerts/rules`, {
    method: 'POST',
    headers: { ...headers, 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return handleResponse<AlertRule>(response);
}

export async function updateAlertRule(id: string, data: Partial<AlertRuleCreate>): Promise<AlertRule> {
  const headers = await createHeadersAsync();
  const response = await fetch(`${API_BASE_URL}/api/alerts/rules/${id}`, {
    method: 'PUT',
    headers: { ...headers, 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return handleResponse<AlertRule>(response);
}

export async function deleteAlertRule(id: string): Promise<void> {
  const headers = await createHeadersAsync();
  const response = await fetch(`${API_BASE_URL}/api/alerts/rules/${id}`, {
    method: 'DELETE',
    headers,
  });
  if (!response.ok) throw new Error(`Failed to delete rule: ${response.status}`);
}

export async function toggleAlertRule(id: string, enabled: boolean): Promise<AlertRule> {
  const headers = await createHeadersAsync();
  const response = await fetch(`${API_BASE_URL}/api/alerts/rules/${id}/toggle`, {
    method: 'PATCH',
    headers: { ...headers, 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled }),
  });
  return handleResponse<AlertRule>(response);
}

export async function getAlertHistory(limit = 50, offset = 0): Promise<AlertExecution[]> {
  const headers = await createHeadersAsync();
  const query = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  const response = await fetch(`${API_BASE_URL}/api/alerts/history?${query}`, { headers });
  return handleResponse<AlertExecution[]>(response);
}

export async function getRuleHistory(ruleId: string, limit = 50, offset = 0): Promise<AlertExecution[]> {
  const headers = await createHeadersAsync();
  const query = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  const response = await fetch(`${API_BASE_URL}/api/alerts/rules/${ruleId}/history?${query}`, { headers });
  return handleResponse<AlertExecution[]>(response);
}
