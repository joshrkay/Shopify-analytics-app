/**
 * Connection Steps Component
 *
 * Visual step indicator for the connection wizard.
 * Shows current progress through the 5-step connection flow.
 *
 * Phase 3 — Subphase 3.5: Connection Wizard UI
 */

import { cn } from '../ui/utils';
import type { ConnectionStep } from '../../types/sourceConnection';

interface ConnectionStepsProps {
  currentStep: ConnectionStep;
}

const STEPS: Array<{ key: ConnectionStep; label: string; order: number }> = [
  { key: 'select', label: 'Select Platform', order: 1 },
  { key: 'configure', label: 'Configure', order: 2 },
  { key: 'authenticate', label: 'Authenticate', order: 3 },
  { key: 'test', label: 'Test Connection', order: 4 },
  { key: 'complete', label: 'Complete', order: 5 },
];

function stepBadgeClass(isActive: boolean, isCompleted: boolean) {
  if (isActive) return 'bg-blue-100 text-blue-800';
  if (isCompleted) return 'bg-green-100 text-green-800';
  return 'bg-gray-100 text-gray-700';
}

/**
 * Step indicator for connection wizard.
 *
 * Shows numbered badges with labels for each step.
 * Highlights current step, dims completed steps, grays out future steps.
 */
export function ConnectionSteps({ currentStep }: ConnectionStepsProps) {
  const currentOrder = STEPS.find((s) => s.key === currentStep)?.order ?? 1;

  return (
    <div className="flex flex-wrap items-center justify-center gap-3">
      {STEPS.map((step, index) => {
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
