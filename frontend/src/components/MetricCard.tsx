import { LucideIcon } from 'lucide-react';

type IconColor = 'blue' | 'green' | 'red' | 'purple' | 'yellow' | 'orange';

interface MetricCardProps {
  title: string;
  value: string | number;
  change?: number;
  icon: LucideIcon;
  iconColor?: IconColor;
  formatValue?: boolean;
  onClick?: () => void;
}

const iconColorMap: Record<IconColor, { bg: string; text: string }> = {
  blue: { bg: 'bg-blue-50', text: 'text-blue-600' },
  green: { bg: 'bg-green-50', text: 'text-green-600' },
  red: { bg: 'bg-red-50', text: 'text-red-600' },
  purple: { bg: 'bg-purple-50', text: 'text-purple-600' },
  yellow: { bg: 'bg-yellow-50', text: 'text-yellow-600' },
  orange: { bg: 'bg-orange-50', text: 'text-orange-600' },
};

export function MetricCard({
  title,
  value,
  change,
  icon: Icon,
  iconColor = 'blue',
  formatValue = false,
  onClick,
}: MetricCardProps) {
  const displayValue =
    formatValue && typeof value === 'number'
      ? new Intl.NumberFormat('en-US', {
          style: 'currency',
          currency: 'USD',
          minimumFractionDigits: 0,
          maximumFractionDigits: 0,
        }).format(value)
      : value;

  const colors = iconColorMap[iconColor];

  const CardContent = (
    <>
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <p className="text-sm text-gray-600 mb-1">{title}</p>
          <p className="text-3xl font-semibold text-gray-900">{displayValue}</p>
          {change !== undefined && (
            <p className={`text-sm mt-2 ${change >= 0 ? 'text-green-600' : 'text-red-600'}`}>
              {change >= 0 ? '+' : ''}{change.toFixed(1)}% from last period
            </p>
          )}
        </div>
        <div className={`${colors.bg} p-3 rounded-lg`}>
          <Icon className={`w-6 h-6 ${colors.text}`} />
        </div>
      </div>
      {onClick && (
        <div className="mt-3">
          <span className="text-sm text-blue-600 font-medium">View breakdown →</span>
        </div>
      )}
    </>
  );

  if (onClick) {
    return (
      <button
        onClick={onClick}
        className="w-full bg-white rounded-lg p-6 shadow-sm border border-gray-200 hover:shadow-md hover:border-blue-300 transition-all text-left cursor-pointer"
      >
        {CardContent}
      </button>
    );
  }

  return (
    <div className="bg-white rounded-lg p-6 shadow-sm border border-gray-200">
      {CardContent}
    </div>
  );
}
