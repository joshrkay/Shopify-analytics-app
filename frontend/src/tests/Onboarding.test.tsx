import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import type { DataSourceDefinition } from '../types/sourceConnection';

const mockUseDataSourceCatalog = vi.fn();

vi.mock('../hooks/useDataSources', () => ({
  useDataSourceCatalog: () => mockUseDataSourceCatalog(),
}));

vi.mock('react-router-dom', () => ({
  useNavigate: () => vi.fn(),
}));

vi.mock('../components/sources/ConnectSourceWizard', () => ({
  ConnectSourceWizard: () => null,
}));

import Onboarding from '../pages/Onboarding';

const buildCatalogEntry = (
  platform: DataSourceDefinition['platform'],
  overrides?: Partial<DataSourceDefinition>
): DataSourceDefinition => ({
  id: platform,
  platform,
  displayName: platform,
  description: `${platform} description`,
  authType: 'oauth',
  category: 'ads',
  isEnabled: true,
  ...overrides,
});

const renderAtAdPlatformsStep = async (catalog: DataSourceDefinition[]) => {
  mockUseDataSourceCatalog.mockReturnValue({
    catalog,
  });

  const user = userEvent.setup();
  render(<Onboarding />);

  await user.click(screen.getByRole('button', { name: /get started/i }));
  await user.click(screen.getByRole('button', { name: /continue anyway/i }));
};

const getPlatformRow = (name: string): HTMLElement => {
  const title = screen.getByText(name);
  const row = title.closest('div.flex-1')?.parentElement;
  if (!row) throw new Error(`Could not find row for ${name}`);
  return row;
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('Onboarding support status', () => {
  it('shows Connect for newly supported ad platforms from catalog flags', async () => {
    await renderAtAdPlatformsStep([
      buildCatalogEntry('shopify', { category: 'ecommerce' }),
      buildCatalogEntry('pinterest_ads', { capabilities: { connect: true } }),
      buildCatalogEntry('meta_ads', { capabilities: { connect: false } }),
      buildCatalogEntry('google_ads', { capabilities: { connect: false } }),
      buildCatalogEntry('tiktok_ads', { capabilities: { connect: false } }),
      buildCatalogEntry('snapchat_ads', { capabilities: { connect: false } }),
      buildCatalogEntry('twitter_ads', { capabilities: { connect: false } }),
    ]);

    const pinterestRow = getPlatformRow('Pinterest Ads');
    expect(within(pinterestRow).getByRole('button', { name: 'Connect' })).toBeEnabled();
    expect(within(pinterestRow).queryByText('Not available')).not.toBeInTheDocument();
  });

  it('disables unsupported ad platforms using backend capability flags', async () => {
    await renderAtAdPlatformsStep([
      buildCatalogEntry('shopify', { category: 'ecommerce' }),
      buildCatalogEntry('meta_ads', { canConnect: false }),
      buildCatalogEntry('google_ads', { capabilities: { canConnect: true } }),
      buildCatalogEntry('tiktok_ads', { capabilities: { canConnect: true } }),
      buildCatalogEntry('snapchat_ads', { capabilities: { canConnect: true } }),
      buildCatalogEntry('pinterest_ads', { capabilities: { canConnect: true } }),
      buildCatalogEntry('twitter_ads', { capabilities: { canConnect: true } }),
    ]);

    const metaRow = getPlatformRow('Facebook / Meta Ads');
    expect(within(metaRow).getByText('Not available')).toBeInTheDocument();
    expect(within(metaRow).getByRole('button', { name: 'Unavailable' })).toBeDisabled();
  });

  it('updates Shopify CTA copy and disabled state when not connectable', async () => {
    mockUseDataSourceCatalog.mockReturnValue({
      catalog: [buildCatalogEntry('shopify', { capabilities: { connect: false }, category: 'ecommerce' })],
    });

    render(<Onboarding />);
    const user = userEvent.setup();

    await user.click(screen.getByRole('button', { name: /get started/i }));

    const cta = screen.getByRole('button', { name: 'Not available yet' });
    expect(cta).toBeDisabled();
  });
});
