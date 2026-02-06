/**
 * Tests for data_health_copy.ts
 *
 * Validates all merchant-visible copy for the data health trust layer.
 * Ensures no internal system names leak into merchant-facing text.
 *
 * Story 4.3 - Merchant Data Health Trust Layer
 */

import { describe, it, expect } from 'vitest';
import {
  getMerchantHealthLabel,
  getMerchantHealthMessage,
  getMerchantHealthBannerTitle,
  getMerchantHealthBannerMessage,
  getMerchantHealthTooltip,
  getMerchantHealthBadgeTone,
  getMerchantHealthBannerTone,
  getMerchantHealthFeatures,
} from '../utils/data_health_copy';
import type { MerchantHealthState } from '../utils/data_health_copy';

// Internal system terms that must NEVER appear in merchant copy
const FORBIDDEN_TERMS = [
  'dbt', 'airbyte', 'rls', 'sla', 'threshold',
  'sync_failed', 'grace_window', 'backfill',
  'postgresql', 'supabase', 'temporal', 'kafka',
  'error_code', 'exception', 'traceback',
];

const ALL_STATES: MerchantHealthState[] = ['healthy', 'delayed', 'unavailable'];

// =============================================================================
// getMerchantHealthLabel
// =============================================================================

describe('getMerchantHealthLabel', () => {
  it('returns "Up to date" for healthy', () => {
    expect(getMerchantHealthLabel('healthy')).toBe('Up to date');
  });

  it('returns "Data delayed" for delayed', () => {
    expect(getMerchantHealthLabel('delayed')).toBe('Data delayed');
  });

  it('returns "Unavailable" for unavailable', () => {
    expect(getMerchantHealthLabel('unavailable')).toBe('Unavailable');
  });

  it('never returns empty string', () => {
    for (const state of ALL_STATES) {
      expect(getMerchantHealthLabel(state).length).toBeGreaterThan(0);
    }
  });
});

// =============================================================================
// getMerchantHealthMessage
// =============================================================================

describe('getMerchantHealthMessage', () => {
  it('returns correct healthy message', () => {
    expect(getMerchantHealthMessage('healthy')).toBe('Your data is up to date.');
  });

  it('returns correct delayed message', () => {
    expect(getMerchantHealthMessage('delayed')).toBe(
      'Some data is delayed. Reports may be incomplete.'
    );
  });

  it('returns correct unavailable message', () => {
    expect(getMerchantHealthMessage('unavailable')).toBe(
      'Your data is temporarily unavailable.'
    );
  });

  it('never contains forbidden terms', () => {
    for (const state of ALL_STATES) {
      const msg = getMerchantHealthMessage(state).toLowerCase();
      for (const term of FORBIDDEN_TERMS) {
        expect(msg).not.toContain(term);
      }
    }
  });
});

// =============================================================================
// getMerchantHealthBannerTitle
// =============================================================================

describe('getMerchantHealthBannerTitle', () => {
  it('returns empty string for healthy', () => {
    expect(getMerchantHealthBannerTitle('healthy')).toBe('');
  });

  it('returns non-empty title for delayed', () => {
    const title = getMerchantHealthBannerTitle('delayed');
    expect(title.length).toBeGreaterThan(0);
  });

  it('returns non-empty title for unavailable', () => {
    const title = getMerchantHealthBannerTitle('unavailable');
    expect(title.length).toBeGreaterThan(0);
  });
});

// =============================================================================
// getMerchantHealthBannerMessage
// =============================================================================

describe('getMerchantHealthBannerMessage', () => {
  it('returns empty string for healthy', () => {
    expect(getMerchantHealthBannerMessage('healthy')).toBe('');
  });

  it('returns non-empty body for delayed', () => {
    const msg = getMerchantHealthBannerMessage('delayed');
    expect(msg.length).toBeGreaterThan(0);
    expect(msg).toContain('AI insights');
  });

  it('returns non-empty body for unavailable', () => {
    const msg = getMerchantHealthBannerMessage('unavailable');
    expect(msg.length).toBeGreaterThan(0);
    expect(msg).toContain('support');
  });

  it('never contains forbidden terms', () => {
    for (const state of ALL_STATES) {
      const msg = getMerchantHealthBannerMessage(state).toLowerCase();
      for (const term of FORBIDDEN_TERMS) {
        expect(msg).not.toContain(term);
      }
    }
  });
});

// =============================================================================
// getMerchantHealthTooltip
// =============================================================================

describe('getMerchantHealthTooltip', () => {
  it('returns tooltip for all states', () => {
    for (const state of ALL_STATES) {
      expect(getMerchantHealthTooltip(state).length).toBeGreaterThan(0);
    }
  });

  it('never contains forbidden terms', () => {
    for (const state of ALL_STATES) {
      const tip = getMerchantHealthTooltip(state).toLowerCase();
      for (const term of FORBIDDEN_TERMS) {
        expect(tip).not.toContain(term);
      }
    }
  });
});

// =============================================================================
// getMerchantHealthBadgeTone
// =============================================================================

describe('getMerchantHealthBadgeTone', () => {
  it('maps healthy to success', () => {
    expect(getMerchantHealthBadgeTone('healthy')).toBe('success');
  });

  it('maps delayed to attention', () => {
    expect(getMerchantHealthBadgeTone('delayed')).toBe('attention');
  });

  it('maps unavailable to critical', () => {
    expect(getMerchantHealthBadgeTone('unavailable')).toBe('critical');
  });
});

// =============================================================================
// getMerchantHealthBannerTone
// =============================================================================

describe('getMerchantHealthBannerTone', () => {
  it('maps healthy to info', () => {
    expect(getMerchantHealthBannerTone('healthy')).toBe('info');
  });

  it('maps delayed to warning', () => {
    expect(getMerchantHealthBannerTone('delayed')).toBe('warning');
  });

  it('maps unavailable to critical', () => {
    expect(getMerchantHealthBannerTone('unavailable')).toBe('critical');
  });
});

// =============================================================================
// getMerchantHealthFeatures
// =============================================================================

describe('getMerchantHealthFeatures', () => {
  it('healthy enables all features', () => {
    const features = getMerchantHealthFeatures('healthy');
    expect(features.aiInsightsEnabled).toBe(true);
    expect(features.dashboardsEnabled).toBe(true);
    expect(features.exportsEnabled).toBe(true);
  });

  it('delayed disables AI and exports', () => {
    const features = getMerchantHealthFeatures('delayed');
    expect(features.aiInsightsEnabled).toBe(false);
    expect(features.dashboardsEnabled).toBe(true);
    expect(features.exportsEnabled).toBe(false);
  });

  it('unavailable disables all features', () => {
    const features = getMerchantHealthFeatures('unavailable');
    expect(features.aiInsightsEnabled).toBe(false);
    expect(features.dashboardsEnabled).toBe(false);
    expect(features.exportsEnabled).toBe(false);
  });
});
