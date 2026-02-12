/**
 * Tests for IntegrationCard component
 *
 * Verifies rendering of platform info, connected badge, and Connect button callback.
 *
 * Phase 3 — Subphase 3.3: Source Catalog Page
 */

import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AppProvider } from '@shopify/polaris';
import '@shopify/polaris/build/esm/styles.css';

import { IntegrationCard } from '../components/sources/IntegrationCard';
import type { DataSourceDefinition } from '../types/sourceConnection';

const mockTranslations = {
  Polaris: { Common: { ok: 'OK', cancel: 'Cancel' } },
};

const renderWithPolaris = (ui: React.ReactElement) => {
  return render(<AppProvider i18n={mockTranslations as any}>{ui}</AppProvider>);
};

const mockPlatform: DataSourceDefinition = {
  id: 'meta_ads',
  platform: 'meta_ads',
  displayName: 'Meta Ads',
  description: 'Connect your Facebook and Instagram ad accounts',
  authType: 'oauth',
  category: 'ads',
  isEnabled: true,
};

describe('IntegrationCard', () => {
  it('renders platform name and description', () => {
    renderWithPolaris(
      <IntegrationCard platform={mockPlatform} isConnected={false} onConnect={vi.fn()} />,
    );

    expect(screen.getByText('Meta Ads')).toBeInTheDocument();
    expect(screen.getByText('Connect your Facebook and Instagram ad accounts')).toBeInTheDocument();
  });

  it('shows "Connected" badge when isConnected is true', () => {
    renderWithPolaris(
      <IntegrationCard platform={mockPlatform} isConnected={true} onConnect={vi.fn()} />,
    );

    // Badge and button both show "Connected" text
    const connectedElements = screen.getAllByText('Connected');
    expect(connectedElements.length).toBeGreaterThanOrEqual(1);
  });

  it('calls onConnect when Connect button is clicked', async () => {
    const user = userEvent.setup();
    const onConnect = vi.fn();

    renderWithPolaris(
      <IntegrationCard platform={mockPlatform} isConnected={false} onConnect={onConnect} />,
    );

    await user.click(screen.getByRole('button', { name: /connect/i }));
    expect(onConnect).toHaveBeenCalledWith(mockPlatform);
  });
});
