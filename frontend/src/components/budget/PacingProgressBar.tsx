interface PacingProgressBarProps {
  platform: string;
  pctSpent: number;
  pctTime: number;
  budgetCents: number;
  spentCents: number;
  status: 'on_pace' | 'slightly_over' | 'over_budget';
}

function formatCents(cents: number): string {
  return `$${(cents / 100).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

const STATUS_COLORS: Record<string, string> = {
  on_pace: 'var(--color-success)',
  slightly_over: 'var(--color-warning)',
  over_budget: 'var(--color-danger)',
};

const STATUS_LABELS: Record<string, string> = {
  on_pace: 'On pace',
  slightly_over: 'Slightly over',
  over_budget: 'Over budget',
};

export function PacingProgressBar({ platform, pctSpent, pctTime, budgetCents, spentCents, status }: PacingProgressBarProps) {
  const barWidth = Math.min(pctSpent * 100, 100);
  const timeMarker = pctTime * 100;

  return (
    <div style={{ marginBottom: '16px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
        <span style={{ fontWeight: 'var(--font-weight-semibold)' as unknown as number, textTransform: 'capitalize' }}>
          {platform.replace(/_/g, ' ')}
        </span>
        <span style={{ fontSize: 'var(--font-size-sm)', color: STATUS_COLORS[status] }}>
          {STATUS_LABELS[status]}
        </span>
      </div>
      <div
        style={{
          position: 'relative',
          height: '12px',
          backgroundColor: '#f1f2f3',
          borderRadius: 'var(--radius-sm)',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            height: '100%',
            width: `${barWidth}%`,
            backgroundColor: STATUS_COLORS[status],
            borderRadius: 'var(--radius-sm)',
            transition: 'width 0.3s ease',
          }}
        />
        <div
          style={{
            position: 'absolute',
            top: 0,
            left: `${timeMarker}%`,
            width: '2px',
            height: '100%',
            backgroundColor: '#333',
            opacity: 0.5,
          }}
          title={`${(pctTime * 100).toFixed(0)}% of month elapsed`}
        />
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '4px', fontSize: 'var(--font-size-sm)', color: '#6d7175' }}>
        <span>{formatCents(spentCents)} spent</span>
        <span>{formatCents(budgetCents)} budget</span>
      </div>
    </div>
  );
}
