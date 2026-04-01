/**
 * Connect Source Wizard Component
 *
 * 6-step modal wizard for connecting new data sources.
 * Uses separate step components and the useConnectSourceWizard hook.
 *
 * Steps:
 *   1. Intro — Source info, features, permissions
 *   2. OAuth — Authorization redirect/popup
 *   3. Accounts — Select ad accounts (ads platforms only)
 *   4. SyncConfig — Historical range, frequency
 *   5. Syncing — Real-time sync progress
 *   6. Success — Confirmation + next steps
 *
 * Phase 3 — Subphase 3.4/3.5: Connection Wizard
 */

import { useState, useEffect, useCallback, type ReactNode } from 'react';
import { X } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

import type { DataSourceDefinition } from '../../types/sourceConnection';
import { useConnectSourceWizard } from '../../hooks/useConnectSourceWizard';
import { WizardSteps } from './WizardSteps';
import {
  IntroStep,
  OAuthStep,
  AccountSelectStep,
  SyncConfigStep,
  SyncProgressStep,
  SuccessStep,
} from './steps';

interface ConnectSourceWizardProps {
  open: boolean;
  platform: DataSourceDefinition | null;
  catalog?: DataSourceDefinition[];
  onClose: () => void;
  onSuccess?: (connectionId: string) => void;
}

/** Steps where closing should prompt for confirmation */
const MID_FLOW_STEPS = new Set(['oauth', 'accounts', 'syncConfig', 'syncing']);

function WizardModalShell({
  open,
  title,
  onClose,
  children,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50"
      role="dialog"
      aria-modal="true"
      aria-labelledby="connect-wizard-modal-title"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-xl shadow-xl max-w-4xl w-full max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
          <h2 id="connect-wizard-modal-title" className="text-lg font-semibold text-gray-900">
            {title}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="p-2 hover:bg-gray-100 rounded-lg"
            aria-label="Close"
          >
            <X className="w-5 h-5 text-gray-600" />
          </button>
        </div>
        <div className="p-6">{children}</div>
      </div>
    </div>
  );
}

export function ConnectSourceWizard({
  open,
  platform,
  catalog = [],
  onClose,
  onSuccess,
}: ConnectSourceWizardProps) {
  const navigate = useNavigate();
  const wizard = useConnectSourceWizard();
  const { state, initWithPlatform } = wizard;
  const [showCloseConfirm, setShowCloseConfirm] = useState(false);

  useEffect(() => {
    if (open && platform) {
      initWithPlatform(platform);
    }
  }, [open, platform, initWithPlatform]);

  useEffect(() => {
    if (!open) {
      setShowCloseConfirm(false);
    }
  }, [open]);

  const doClose = useCallback(() => {
    setShowCloseConfirm(false);
    wizard.reset();
    onClose();
  }, [wizard, onClose]);

  const handleClose = useCallback(() => {
    if (MID_FLOW_STEPS.has(state.step)) {
      setShowCloseConfirm(true);
    } else {
      doClose();
    }
  }, [state.step, doClose]);

  const handleViewDashboard = useCallback(() => {
    if (state.connectionId && onSuccess) {
      onSuccess(state.connectionId);
    }
    doClose();
    navigate('/');
  }, [state.connectionId, onSuccess, doClose, navigate]);

  const handleConnectAnother = useCallback(() => {
    if (state.connectionId && onSuccess) {
      onSuccess(state.connectionId);
    }
    doClose();
    navigate('/sources');
  }, [state.connectionId, onSuccess, doClose, navigate]);

  const handleSelectPlatform = useCallback(
    (p: DataSourceDefinition) => {
      wizard.initWithPlatform(p);
    },
    [wizard]
  );

  const activePlatform = state.platform ?? platform;

  if (!open) return null;

  if (!activePlatform) {
    return (
      <WizardModalShell open={open} title="Connect a Data Source" onClose={onClose}>
        <div className="flex flex-col gap-4">
          <p className="text-sm text-gray-800">Select a platform to connect:</p>
          {catalog.length === 0 ? (
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
              No data source platforms available. Please try again later.
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
              {catalog.map((p) => (
                <div
                  key={p.id}
                  className="rounded-lg border border-gray-200 bg-white p-4 flex flex-col gap-3 shadow-sm"
                >
                  <h3 className="text-sm font-semibold text-gray-900">{p.displayName}</h3>
                  {p.description && <p className="text-xs text-gray-600 flex-1">{p.description}</p>}
                  <div className="pt-1">
                    <button
                      type="button"
                      onClick={() => handleSelectPlatform(p)}
                      className="w-full rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700"
                    >
                      Connect
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </WizardModalShell>
    );
  }

  const title = `Connect ${activePlatform.displayName}`;

  return (
    <WizardModalShell open={open} title={title} onClose={handleClose}>
      <div className="flex flex-col gap-4">
        {showCloseConfirm && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
            <h3 className="text-sm font-semibold text-amber-900 mb-2">Leave connection wizard?</h3>
            <p className="text-sm text-amber-900 mb-3">Your progress will be lost if you close now.</p>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setShowCloseConfirm(false)}
                className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
              >
                Continue Setup
              </button>
              <button
                type="button"
                onClick={doClose}
                className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700"
              >
                Leave Wizard
              </button>
            </div>
          </div>
        )}

        <WizardSteps currentStep={state.step} />

        {state.error && state.step !== 'syncing' && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-4 flex justify-between gap-4 items-start">
            <p className="text-sm text-red-800 flex-1">{state.error}</p>
            <button
              type="button"
              onClick={() => wizard.setError(null)}
              className="text-sm font-medium text-red-800 hover:underline shrink-0"
            >
              Dismiss
            </button>
          </div>
        )}

        {state.step === 'intro' && (
          <IntroStep
            platform={activePlatform}
            onContinue={wizard.proceedFromIntro}
            onCancel={handleClose}
          />
        )}
        {state.step === 'oauth' && (
          <OAuthStep
            platform={activePlatform}
            loading={state.loading}
            error={state.error}
            onStartOAuth={wizard.startOAuth}
            onCancel={handleClose}
          />
        )}
        {state.step === 'accounts' && (
          <AccountSelectStep
            accounts={state.accounts}
            selectedAccountIds={state.selectedAccountIds}
            loading={state.loading}
            error={state.error}
            onToggleAccount={wizard.toggleAccount}
            onSelectAll={wizard.selectAllAccounts}
            onDeselectAll={wizard.deselectAllAccounts}
            onConfirm={wizard.confirmAccounts}
            onBack={wizard.goBack}
          />
        )}
        {state.step === 'syncConfig' && (
          <SyncConfigStep
            platform={activePlatform}
            syncConfig={state.syncConfig}
            onUpdateConfig={wizard.updateWizardSyncConfig}
            onConfirm={wizard.confirmSyncConfig}
            onBack={wizard.goBack}
            loading={state.loading}
          />
        )}
        {state.step === 'syncing' && (
          <SyncProgressStep
            platform={activePlatform}
            progress={state.syncProgress}
            error={state.error}
            onNavigateDashboard={handleViewDashboard}
          />
        )}
        {state.step === 'success' && state.connectionId && (
          <SuccessStep
            platform={activePlatform}
            onConnectAnother={handleConnectAnother}
            onViewDashboard={handleViewDashboard}
          />
        )}
      </div>
    </WizardModalShell>
  );
}
