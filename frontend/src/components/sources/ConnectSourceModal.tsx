/**
 * Connect Source Modal Component
 *
 * Multi-step wizard modal for connecting new data sources.
 * Handles platform selection, configuration, OAuth flow, and connection testing.
 *
 * Steps:
 * 1. Select Platform — Browse available integrations
 * 2. Configure — Platform-specific setup (shop domain, API keys, etc.)
 * 3. Authenticate — OAuth redirect or credential validation
 * 4. Test Connection — Verify connectivity
 * 5. Complete — Success confirmation
 *
 * Phase 3 — Subphase 3.5: Connection Wizard UI
 */

import { useState, useCallback, useEffect } from 'react';
import { X, Loader2 } from 'lucide-react';

import type { DataSourceDefinition } from '../../types/sourceConnection';
import { useConnectionWizard, useSourceCatalog } from '../../hooks/useSourceConnection';
import { ConnectionSteps } from './ConnectionSteps';
import { PlatformCard } from './PlatformCard';

interface ConnectSourceModalProps {
  open: boolean;
  onClose: () => void;
  onSuccess?: (connectionId: string) => void;
  initialPlatform?: DataSourceDefinition | null;
}

/**
 * Modal wizard for connecting new data sources.
 */
export function ConnectSourceModal({ open, onClose, initialPlatform }: ConnectSourceModalProps) {
  const { catalog, loading: loadingCatalog } = useSourceCatalog();
  const {
    state,
    selectPlatform,
    configure,
    startOAuth,
    testConnection,
    setError,
    reset,
  } = useConnectionWizard();

  const [shopDomain, setShopDomain] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [configuring, setConfiguring] = useState(false);

  useEffect(() => {
    if (open && initialPlatform) {
      selectPlatform(initialPlatform);
    }
  }, [open, initialPlatform, selectPlatform]);

  const handleClose = useCallback(() => {
    reset();
    setShopDomain('');
    setApiKey('');
    setConfiguring(false);
    onClose();
  }, [reset, onClose]);

  const handlePlatformSelect = useCallback(
    (platform: DataSourceDefinition) => {
      selectPlatform(platform);
    },
    [selectPlatform]
  );

  const handleConfigure = useCallback(async () => {
    if (!state.selectedPlatform) return;

    setConfiguring(true);
    setError(null);

    try {
      const config: Record<string, unknown> = {};

      if (state.selectedPlatform.platform === 'shopify') {
        if (!shopDomain) {
          setError('Shop domain is required');
          setConfiguring(false);
          return;
        }
        config.shop_domain = shopDomain;
      }

      if (state.selectedPlatform.authType === 'api_key') {
        if (!apiKey) {
          setError('API key is required');
          setConfiguring(false);
          return;
        }
        config.api_key = apiKey;
      }

      configure(config);

      if (state.selectedPlatform.authType === 'oauth') {
        await startOAuth();
      } else {
        await testConnection();
      }
    } catch (err) {
      console.error('Configuration failed:', err);
      setError(err instanceof Error ? err.message : 'Configuration failed');
    } finally {
      setConfiguring(false);
    }
  }, [
    state.selectedPlatform,
    shopDomain,
    apiKey,
    configure,
    startOAuth,
    testConnection,
    setError,
  ]);

  const renderSelectStep = () => (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-gray-600">
        Choose a data source to connect. We support e-commerce platforms, advertising networks,
        email marketing, and SMS providers.
      </p>

      {loadingCatalog ? (
        <div className="flex items-center justify-center gap-2 py-4">
          <Loader2 className="h-5 w-5 animate-spin text-blue-600" />
          <span className="text-sm text-gray-600">Loading platforms...</span>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {catalog.map((platform) => (
            <PlatformCard key={platform.id} platform={platform} onSelect={handlePlatformSelect} />
          ))}
        </div>
      )}
    </div>
  );

  const renderConfigureStep = () => {
    if (!state.selectedPlatform) return null;

    const isShopify = state.selectedPlatform.platform === 'shopify';
    const isApiKey = state.selectedPlatform.authType === 'api_key';

    return (
      <div className="flex flex-col gap-4">
        <p className="text-sm text-gray-600">
          {isShopify
            ? 'Enter your Shopify store domain to connect.'
            : isApiKey
              ? `Enter your ${state.selectedPlatform.displayName} API credentials.`
              : `Authorize ${state.selectedPlatform.displayName} to sync your data.`}
        </p>

        {isShopify && (
          <div>
            <label htmlFor="connect-shop-domain" className="block text-sm font-medium text-gray-900 mb-2">
              Shop Domain
            </label>
            <input
              id="connect-shop-domain"
              type="text"
              value={shopDomain}
              onChange={(e) => setShopDomain(e.target.value)}
              placeholder="your-store.myshopify.com"
              autoComplete="off"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
            <p className="mt-1 text-xs text-gray-500">
              Your Shopify store URL (e.g., your-store.myshopify.com)
            </p>
          </div>
        )}

        {isApiKey && (
          <div>
            <label htmlFor="connect-api-key" className="block text-sm font-medium text-gray-900 mb-2">
              API Key
            </label>
            <input
              id="connect-api-key"
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              autoComplete="off"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
            <p className="mt-1 text-xs text-gray-500">
              Your {state.selectedPlatform.displayName} API key
            </p>
          </div>
        )}

        {!isApiKey && !isShopify && (
          <div className="rounded-lg border border-gray-200 bg-gray-50 p-4 text-sm text-gray-700">
            You&apos;ll be redirected to {state.selectedPlatform.displayName} to authorize access to your
            account. After authorization, you&apos;ll be redirected back here.
          </div>
        )}

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={handleClose}
            className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleConfigure}
            disabled={configuring}
            className="inline-flex items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {configuring && <Loader2 className="h-4 w-4 animate-spin" />}
            {isApiKey ? 'Connect' : 'Continue to Authorization'}
          </button>
        </div>
      </div>
    );
  };

  const renderAuthenticateStep = () => (
    <div className="flex flex-col items-center gap-4 py-8">
      <Loader2 className="h-12 w-12 animate-spin text-blue-600" />
      <p className="text-sm text-gray-600 text-center">Redirecting to authorization...</p>
    </div>
  );

  const renderTestStep = () => (
    <div className="flex flex-col items-center gap-4 py-8">
      <Loader2 className="h-12 w-12 animate-spin text-blue-600" />
      <p className="text-sm text-gray-600 text-center">Testing connection...</p>
    </div>
  );

  const renderCompleteStep = () => (
    <div className="flex flex-col gap-4">
      <div className="rounded-lg border border-green-200 bg-green-50 p-4 text-sm text-green-800">
        {state.selectedPlatform?.displayName} connected successfully! Your data will begin syncing
        shortly.
      </div>

      <p className="text-sm text-gray-800">
        You can now view and manage this connection in your Data Sources page. The initial sync may take a
        few minutes depending on your data volume.
      </p>

      <button
        type="button"
        onClick={handleClose}
        className="self-start rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
      >
        Done
      </button>
    </div>
  );

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50"
      role="dialog"
      aria-modal="true"
      aria-labelledby="connect-source-modal-title"
      onClick={handleClose}
    >
      <div
        className="bg-white rounded-xl shadow-xl max-w-4xl w-full max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
          <h2 id="connect-source-modal-title" className="text-lg font-semibold text-gray-900">
            Connect Data Source
          </h2>
          <button
            type="button"
            onClick={handleClose}
            className="p-2 hover:bg-gray-100 rounded-lg"
            aria-label="Close"
          >
            <X className="w-5 h-5 text-gray-600" />
          </button>
        </div>

        <div className="p-6 flex flex-col gap-4">
          <ConnectionSteps currentStep={state.step} />

          {state.error && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-4 flex justify-between gap-4 items-start">
              <p className="text-sm text-red-800 flex-1">{state.error}</p>
              <button
                type="button"
                onClick={() => setError(null)}
                className="text-sm font-medium text-red-800 hover:underline shrink-0"
              >
                Dismiss
              </button>
            </div>
          )}

          {state.step === 'select' && renderSelectStep()}
          {state.step === 'configure' && renderConfigureStep()}
          {state.step === 'authenticate' && renderAuthenticateStep()}
          {state.step === 'test' && renderTestStep()}
          {state.step === 'complete' && renderCompleteStep()}
        </div>
      </div>
    </div>
  );
}
