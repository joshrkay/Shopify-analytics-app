/**
 * Authenticated API client fixture for E2E tests.
 *
 * Provides a Playwright APIRequestContext pre-configured with
 * auth headers for making direct backend API calls within tests.
 * Useful for verifying data integrity (assert API response matches UI).
 */
import { test as base, APIRequestContext } from '@playwright/test';
import { createTestToken, createAdminToken, TokenOptions } from '../helpers/jwt-generator';

const API_BASE = process.env.E2E_API_URL || 'http://localhost:8000';

export interface ApiFixtures {
  /** Authenticated API client for a specific tenant. */
  createApiClient: (tenantId: string, options?: Partial<TokenOptions>) => Promise<AuthenticatedApiClient>;
}

export class AuthenticatedApiClient {
  constructor(
    private request: APIRequestContext,
    private token: string,
    public tenantId: string,
  ) {}

  private headers() {
    return {
      Authorization: `Bearer ${this.token}`,
      'Content-Type': 'application/json',
    };
  }

  private async _handleResponse(response: { status(): number; headers(): Record<string, string>; json(): Promise<unknown>; text(): Promise<string> }): Promise<{ status: number; data: unknown }> {
    const data = response.headers()['content-type']?.includes('json')
      ? await response.json()
      : await response.text();
    return { status: response.status(), data };
  }

  async get(path: string): Promise<{ status: number; data: unknown }> {
    const response = await this.request.get(`${API_BASE}${path}`, {
      headers: this.headers(),
    });
    return this._handleResponse(response);
  }

  async post(path: string, body?: unknown): Promise<{ status: number; data: unknown }> {
    const response = await this.request.post(`${API_BASE}${path}`, {
      headers: this.headers(),
      data: body,
    });
    return this._handleResponse(response);
  }

  async put(path: string, body?: unknown): Promise<{ status: number; data: unknown }> {
    const response = await this.request.put(`${API_BASE}${path}`, {
      headers: this.headers(),
      data: body,
    });
    return this._handleResponse(response);
  }

  async patch(path: string, body?: unknown): Promise<{ status: number; data: unknown }> {
    const response = await this.request.patch(`${API_BASE}${path}`, {
      headers: this.headers(),
      data: body,
    });
    return this._handleResponse(response);
  }

  async delete(path: string): Promise<{ status: number; data: unknown }> {
    const response = await this.request.delete(`${API_BASE}${path}`, {
      headers: this.headers(),
    });
    return this._handleResponse(response);
  }
}

export const test = base.extend<ApiFixtures>({
  createApiClient: async ({ request }, use) => {
    const factory = async (
      tenantId: string,
      options?: Partial<TokenOptions>,
    ): Promise<AuthenticatedApiClient> => {
      const token = createTestToken({ tenantId, ...options });
      return new AuthenticatedApiClient(request, token, tenantId);
    };
    await use(factory);
  },
});

export { expect } from '@playwright/test';
