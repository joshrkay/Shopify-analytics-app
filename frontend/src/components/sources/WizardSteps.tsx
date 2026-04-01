/**
 * Wizard Steps Component
 *
 * Visual step indicator for the 6-step connect source wizard.
 * Shows current progress with active/completed/future styling.
 *
 * Follows the same pattern as ConnectionSteps.tsx.
 *
 * Phase 3 — Subphase 3.4: Connection Wizard
 */

import { cn } from '../ui/utils';
import type { WizardStep, WizardStepMeta } from '../../types/sourceConnection';

interface WizardStepsProps {
  currentStep: WizardStep;
}

const WIZARD_STEPS: WizardStepMeta[] = [
  { key: 'intro', label: 'Intro', order: 1 },
  { key: 'oauth', label: 'Authorize', order: 2 },
  { key: 'accounts', label: 'Accounts', order: 3 },
  { key: 'syncConfig', label: 'Configure', order: 4 },
  { key: 'syncing', label: 'Syncing', order: 5 },
  { key: 'success', label: 'Done', order: 6 },
];

function stepBadgeClass(isActive: boolean, isCompleted: boolean) {
  if (isActive) return 'bg-blue-100 text-blue-800';
  if (isCompleted) return 'bg-green-100 text-green-800';
  return 'bg-gray-100 text-gray-700';
}

export function WizardSteps({ currentStep }: WizardStepsProps) {
  const currentOrder = WIZARD_STEPS.find((s) => s.key === currentStep)?.order ?? 1;

  return (
    <div className="flex flex-wrap items-center gap-3">
      {WIZARD_STEPS.map((step, index) => {
        const isActive = step.key === currentStep;
        const isCompleted = step.order < currentOrder;
        const isFuture = step.order > currentOrder;

        return (
          <div key={step.key} className="flex items-center gap-2 shrink-0">
            {index > 0 && (
              <span className="text-gray-400 text-sm" aria-hidden>
                →
              </span>
            )}
            <div className="flex items-center gap-1.5">
              <span
                className={cn(
                  'inline-flex items-center justify-center min-w-[1.5rem] h-6 px-1.5 rounded-full text-xs font-medium',
                  stepBadgeClass(isActive, isCompleted)
                )}
              >
                {String(step.order)}
              </span>
              <span
                className={cn(
                  'text-sm',
                  isActive ? 'font-semibold text-gray-900' : isFuture ? 'text-gray-400' : 'text-gray-700'
                )}
              >
                {step.label}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
