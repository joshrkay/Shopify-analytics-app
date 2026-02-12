/**
 * Tests for ConnectedSourceCard component
 *
 * Verifies rendering of source info, status badges, timestamps, and action buttons.
 *
 * Phase 3 — Subphase 3.3: Source Catalog Page
 */

import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AppProvider } from '@shopify/polaris';
import '@shopify/polaris/build/esm/styles.css';

import { ConnectedSourceCard } from '../components/sources/ConnectedSourceCard';
import type { Source } from '../types/sources';

const mockTranslations = {
  Polaris: { Common: { ok: 'OK', cancel: 'Cancel' } },
};

const renderWithPolaris = (ui: React.ReactElement) => {
  return render(<AppProvider i18n={mockTranslations as any}>{ui}</AppProvider>);
};

const createMockSource = (overrides?: Partial<Source>): Source => ({
  id: 'src-001',
  platform: 'shopify',
  displayName: 'My Shopify Store',
  authType: 'oauth',
  status: 'active',
  isEnabled: true,
  lastSyncAt: '2025-06-15T10:30:00Z',
  lastSyncStatus: 'succeeded',
  ...overrides,
});

describe('ConnectedSourceCard', () => {
  it('renders source name and platform', () => {
    renderWithPolaris(
      <ConnectedSourceCard
        source={createMockSource()}
        onManage={vi.fn()}
        onDisconnect={vi.fn()}
        onTestConnection={vi.fn()}
      />,
    );

    expect(screen.getByText('My Shopify Store')).toBeInTheDocument();
    expect(screen.getByText('Shopify')).toBeInTheDocument();
  });

  it('shows Active badge for active status', () => {
    renderWithPolaris(
      <ConnectedSourceCard
        source={createMockSource({ status: 'active' })}
        onManage={vi.fn()}
        onDisconnect={vi.fn()}
        onTestConnection={vi.fn()}
      />,
    );

    expect(screen.getByText('Active')).toBeInTheDocument();
  });

  it('shows Error badge for failed status', () => {
    renderWithPolaris(
      <ConnectedSourceCard
        source={createMockSource({ status: 'failed' })}
        onManage={vi.fn()}
        onDisconnect={vi.fn()}
        onTestConnection={vi.fn()}
      />,
    );

    expect(screen.getByText('Error')).toBeInTheDocument();
  });

  it('shows "Never synced" when lastSyncAt is null', () => {
    renderWithPolaris(
      <ConnectedSourceCard
        source={createMockSource({ lastSyncAt: null })}
        onManage={vi.fn()}
        onDisconnect={vi.fn()}
        onTestConnection={vi.fn()}
      />,
    );

    expect(screen.getByText(/Never synced/)).toBeInTheDocument();
  });

  it('calls onManage when Manage button is clicked', async () => {
    const user = userEvent.setup();
    const onManage = vi.fn();
    const source = createMockSource();

    renderWithPolaris(
      <ConnectedSourceCard
        source={source}
        onManage={onManage}
        onDisconnect={vi.fn()}
        onTestConnection={vi.fn()}
      />,
    );

    await user.click(screen.getByRole('button', { name: 'Manage' }));
    expect(onManage).toHaveBeenCalledWith(source);
  });

  it('calls onDisconnect when Disconnect button is clicked', async () => {
    const user = userEvent.setup();
    const onDisconnect = vi.fn();
    const source = createMockSource();

    renderWithPolaris(
      <ConnectedSourceCard
        source={source}
        onManage={vi.fn()}
        onDisconnect={onDisconnect}
        onTestConnection={vi.fn()}
      />,
    );

    await user.click(screen.getByRole('button', { name: 'Disconnect' }));
    expect(onDisconnect).toHaveBeenCalledWith(source);
  });

  it('calls onTestConnection when Test button is clicked', async () => {
    const user = userEvent.setup();
    const onTestConnection = vi.fn();
    const source = createMockSource();

    renderWithPolaris(
      <ConnectedSourceCard
        source={source}
        onManage={vi.fn()}
        onDisconnect={vi.fn()}
        onTestConnection={onTestConnection}
      />,
    );

    await user.click(screen.getByRole('button', { name: 'Test' }));
    expect(onTestConnection).toHaveBeenCalledWith(source);
  });

  it('shows Inactive badge for inactive status', () => {
    renderWithPolaris(
      <ConnectedSourceCard
        source={createMockSource({ status: 'inactive' })}
        onManage={vi.fn()}
        onDisconnect={vi.fn()}
        onTestConnection={vi.fn()}
      />,
    );

    expect(screen.getByText('Inactive')).toBeInTheDocument();
  });
});
