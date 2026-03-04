import type { CohortRow } from '../../services/cohortAnalysisApi';

interface RetentionHeatmapProps {
  cohorts: CohortRow[];
}

function getHeatmapColor(rate: number): string {
  // Green gradient: low retention = light, high = dark
  return `rgba(0, 164, 124, ${Math.max(0.1, rate)})`;
}

function formatPercent(rate: number): string {
  return `${(rate * 100).toFixed(1)}%`;
}

export function RetentionHeatmap({ cohorts }: RetentionHeatmapProps) {
  if (cohorts.length === 0) {
    return <p>No cohort data available.</p>;
  }

  // Find max period across all cohorts
  const maxPeriod = Math.max(
    ...cohorts.flatMap(c => c.periods.map(p => p.period)),
    0,
  );
  const periodHeaders = Array.from({ length: maxPeriod + 1 }, (_, i) => i);

  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 'var(--font-size-sm)' }}>
        <thead>
          <tr>
            <th scope="col" style={{ padding: '8px 12px', textAlign: 'left', borderBottom: '2px solid #e1e3e5' }}>
              Cohort
            </th>
            <th scope="col" style={{ padding: '8px 12px', textAlign: 'right', borderBottom: '2px solid #e1e3e5' }}>
              Customers
            </th>
            {periodHeaders.map(p => (
              <th key={p} scope="col" style={{ padding: '8px 12px', textAlign: 'center', borderBottom: '2px solid #e1e3e5' }}>
                {p === 0 ? 'M0' : `M${p}`}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {cohorts.map(cohort => {
            const periodMap = new Map(cohort.periods.map(p => [p.period, p]));
            return (
              <tr key={cohort.cohort_month}>
                <td style={{ padding: '6px 12px', borderBottom: '1px solid #f1f2f3', fontWeight: 'var(--font-weight-medium)' as unknown as number }}>
                  {cohort.cohort_month.slice(0, 7)}
                </td>
                <td style={{ padding: '6px 12px', textAlign: 'right', borderBottom: '1px solid #f1f2f3' }}>
                  {cohort.customers_total.toLocaleString()}
                </td>
                {periodHeaders.map(p => {
                  const period = periodMap.get(p);
                  if (!period) {
                    return <td key={p} style={{ padding: '6px 12px', borderBottom: '1px solid #f1f2f3' }} />;
                  }
                  return (
                    <td
                      key={p}
                      title={`${formatPercent(period.retention_rate)} (${period.customers} customers, $${period.revenue.toFixed(0)} revenue)`}
                      style={{
                        padding: '6px 12px',
                        textAlign: 'center',
                        backgroundColor: getHeatmapColor(period.retention_rate),
                        color: period.retention_rate > 0.5 ? '#fff' : '#333',
                        borderBottom: '1px solid #f1f2f3',
                        borderRadius: 'var(--radius-sm)',
                      }}
                    >
                      {formatPercent(period.retention_rate)}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
