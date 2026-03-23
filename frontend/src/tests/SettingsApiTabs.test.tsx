import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import Settings from '../pages/Settings';

vi.mock('../contexts/AgencyContext', () => ({
  useAgency: vi.fn(),
}));

vi.mock('../hooks/useDataSources', () => ({
  useDataSources: vi.fn(() => ({
    sources: [],
    isLoading: false,
    error: null,
    hasConnectedSources: false,
    refetch: vi.fn(),
  })),
}));

vi.mock('../hooks/useTeamMembers', () => ({
  useTeamMembers: vi.fn(() => ({ members: [], isLoading: false, error: null })),
  useInviteMember: vi.fn(() => ({ mutate: vi.fn(), isLoading: false })),
  useUpdateMemberRole: vi.fn(() => ({ mutate: vi.fn(), isLoading: false })),
  useRemoveMember: vi.fn(() => ({ mutate: vi.fn(), isLoading: false })),
  useResendInvite: vi.fn(() => ({ mutate: vi.fn(), isLoading: false })),
  TEAM_MEMBERS_QUERY_KEY: 'team-members',
  REMOVE_UNDO_WINDOW_MS: 5000,
}));

import { useAgency } from '../contexts/AgencyContext';

const mockedUseAgency = vi.mocked(useAgency);

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function renderSettings(route: string) {
  mockedUseAgency.mockReturnValue({ userRoles: ['owner'] } as never);
  return render(
    <MemoryRouter initialEntries={[route]}>
      <Routes>
        <Route path="/settings" element={<Settings />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('Settings API and AI tabs', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('loads API keys and creates a new key', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(jsonResponse({ keys: [{
        id: 'key-1',
        name: 'Build Key',
        key_prefix: 'mi_abcd1234',
        created_at: '2026-01-01T00:00:00Z',
        last_used_at: null,
        expires_at: null,
        revoked_at: null,
        is_active: true,
      }] }))
      .mockResolvedValueOnce(jsonResponse({
        key: {
          id: 'key-2',
          name: 'CI Key',
          key_prefix: 'mi_new1234',
          created_at: '2026-01-02T00:00:00Z',
          last_used_at: null,
          expires_at: null,
          revoked_at: null,
          is_active: true,
        },
        plaintext_key: 'mi_secret_key',
      }, 201));

    const user = userEvent.setup();
    renderSettings('/settings?tab=api');

    expect(await screen.findByText('Build Key')).toBeInTheDocument();

    await user.type(screen.getByPlaceholderText('Key name (e.g. CI pipeline)'), 'CI Key');
    await user.click(screen.getByRole('button', { name: 'Create key' }));

    expect(await screen.findByText(/Save this key now/)).toBeInTheDocument();
    expect(screen.getByText('CI Key')).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('shows API load errors', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      jsonResponse({ detail: 'Permission denied: settings:manage' }, 403),
    );

    renderSettings('/settings?tab=api');

    expect(await screen.findByText('Permission denied: settings:manage')).toBeInTheDocument();
  });

  it('loads AI settings and saves changes', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(jsonResponse({
        settings: {
          enabled: true,
          model: 'gpt-4.1-mini',
          cadence: 'weekly',
          include_recommendations: true,
          max_insights_per_run: 5,
        },
        entitled: true,
        entitlement_reason: null,
      }))
      .mockResolvedValueOnce(jsonResponse({
        settings: {
          enabled: true,
          model: 'gpt-5-mini',
          cadence: 'daily',
          include_recommendations: true,
          max_insights_per_run: 8,
        },
        entitled: true,
        entitlement_reason: null,
      }));

    const user = userEvent.setup();
    renderSettings('/settings?tab=ai');

    const modelSelect = await screen.findByLabelText('Model');
    await user.selectOptions(modelSelect, 'gpt-5-mini');

    const cadenceSelect = screen.getByLabelText('Insight cadence');
    await user.selectOptions(cadenceSelect, 'daily');

    const maxInput = screen.getByLabelText('Max insights per run');
    await user.clear(maxInput);
    await user.type(maxInput, '8');

    await user.click(screen.getByRole('button', { name: 'Save AI settings' }));

    expect(await screen.findByText('Saved AI insights settings.')).toBeInTheDocument();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  });

  it('shows AI save errors', async () => {
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(jsonResponse({
        settings: {
          enabled: true,
          model: 'gpt-4.1-mini',
          cadence: 'weekly',
          include_recommendations: true,
          max_insights_per_run: 5,
        },
        entitled: true,
        entitlement_reason: null,
      }))
      .mockResolvedValueOnce(jsonResponse({ detail: 'Current plan does not include AI Insights.' }, 403));

    const user = userEvent.setup();
    renderSettings('/settings?tab=ai');

    await screen.findByText('Save AI settings');
    await user.click(screen.getByRole('button', { name: 'Save AI settings' }));

    expect(await screen.findByText('Current plan does not include AI Insights.')).toBeInTheDocument();
  });
});
