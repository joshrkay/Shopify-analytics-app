import {
  LineChart,
  Line,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';

export interface DailyDataPoint {
  date: string;
  revenue?: number;
  spend?: number;
  [key: string]: string | number | undefined;
}

interface PerformanceChartProps {
  data: DailyDataPoint[];
  type?: 'line' | 'area';
  dataKeys?: string[];
  colors?: string[];
}

export function PerformanceChart({
  data,
  type = 'area',
  dataKeys = ['revenue', 'spend'],
  colors = ['#3b82f6', '#10b981'],
}: PerformanceChartProps) {
  const formattedData = data.map((item) => ({
    ...item,
    date: new Date(item.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
  }));

  const Chart = type === 'line' ? LineChart : AreaChart;

  return (
    <ResponsiveContainer width="100%" height={350}>
      <Chart data={formattedData}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis
          dataKey="date"
          tick={{ fill: '#6b7280', fontSize: 12 }}
          tickMargin={10}
        />
        <YAxis
          tick={{ fill: '#6b7280', fontSize: 12 }}
          tickMargin={10}
          tickFormatter={(value) => `$${(value / 1000).toFixed(1)}k`}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: 'white',
            border: '1px solid #e5e7eb',
            borderRadius: '8px',
            padding: '12px',
          }}
          formatter={(value: number) => [`$${value.toFixed(2)}`, '']}
        />
        <Legend wrapperStyle={{ paddingTop: '20px' }} iconType="circle" />
        {type === 'area' ? (
          <>
            {dataKeys.map((key, index) => (
              <Area
                key={key}
                type="monotone"
                dataKey={key}
                stroke={colors[index]}
                fill={colors[index]}
                fillOpacity={0.2}
                strokeWidth={2}
              />
            ))}
          </>
        ) : (
          <>
            {dataKeys.map((key, index) => (
              <Line
                key={key}
                type="monotone"
                dataKey={key}
                stroke={colors[index]}
                strokeWidth={2}
                dot={false}
              />
            ))}
          </>
        )}
      </Chart>
    </ResponsiveContainer>
  );
}
