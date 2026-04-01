/**
 * Intro Step Component
 *
 * Step 1 of the connection wizard.
 * Shows source info, features, required permissions, and a security notice.
 *
 * Phase 3 — Subphase 3.4: Connection Wizard Steps 1-3
 */

import type { DataSourceDefinition } from '../../../types/sourceConnection';
import type { SourcePlatform } from '../../../types/sources';

interface IntroStepProps {
  platform: DataSourceDefinition;
  onContinue: () => void;
  onCancel: () => void;
}

const PLATFORM_FEATURES: Record<string, string[]> = {
  shopify: [
    'Order and revenue tracking',
    'Product performance analytics',
    'Customer behavior insights',
    'Inventory sync',
  ],
  meta_ads: [
    'Campaign performance metrics',
    'Ad spend tracking and ROAS',
    'Audience insights',
    'Creative performance analysis',
  ],
  google_ads: [
    'Search and display campaign metrics',
    'Keyword performance tracking',
    'Conversion attribution',
    'Budget utilization reports',
  ],
  tiktok_ads: [
    'Video ad performance metrics',
    'Audience engagement analytics',
    'Conversion tracking',
    'Creative performance insights',
  ],
};

const PLATFORM_PERMISSIONS: Record<string, string[]> = {
  shopify: [
    'Read access to orders and products',
    'Read access to customer data',
    'Read access to store analytics',
  ],
  meta_ads: [
    'Read access to ad campaigns',
    'Read access to ad insights and reporting',
    'Read access to ad account settings',
  ],
  google_ads: [
    'Read access to campaigns and ad groups',
    'Read access to performance reports',
    'Read access to conversion data',
  ],
  tiktok_ads: [
    'Read access to ad campaigns',
    'Read access to ad performance data',
    'Read access to audience data',
  ],
};

const DEFAULT_FEATURES = [
  'Data sync and analytics',
  'Performance metrics',
  'Historical data import',
];

const DEFAULT_PERMISSIONS = [
  'Read access to account data',
  'Read access to performance metrics',
];

function getFeatures(platform: SourcePlatform): string[] {
  return PLATFORM_FEATURES[platform] ?? DEFAULT_FEATURES;
}

function getPermissions(platform: SourcePlatform): string[] {
  return PLATFORM_PERMISSIONS[platform] ?? DEFAULT_PERMISSIONS;
}

export function IntroStep({ platform, onContinue, onCancel }: IntroStepProps) {
  const features = getFeatures(platform.platform);
  const permissions = getPermissions(platform.platform);

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-col gap-2 text-center">
        <h2 className="text-xl font-semibold text-gray-900">{platform.displayName}</h2>
        <p className="text-sm text-gray-600">{platform.description}</p>
      </div>

      <div>
        <h3 className="text-sm font-semibold text-gray-900 mb-2">What you&apos;ll get</h3>
        <ul className="list-disc pl-5 space-y-1 text-sm text-gray-700">
          {features.map((feature) => (
            <li key={feature}>{feature}</li>
          ))}
        </ul>
      </div>

      <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
        <h3 className="text-sm font-semibold text-amber-900 mb-2">Required Permissions</h3>
        <ul className="list-disc pl-5 space-y-1 text-sm text-amber-900">
          {permissions.map((permission) => (
            <li key={permission}>{permission}</li>
          ))}
        </ul>
      </div>

      <div className="rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900">
        Your data is encrypted and secure. We only request read-only access.
      </div>

      <div className="flex flex-wrap justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={onContinue}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          Continue with {platform.displayName}
        </button>
      </div>
    </div>
  );
}
