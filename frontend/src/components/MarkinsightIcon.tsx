interface MarkinsightIconProps {
  className?: string;
  variant?: 'default' | 'white' | 'gradient';
}

export function MarkinsightIcon({ className = 'w-8 h-8', variant = 'default' }: MarkinsightIconProps) {
  if (variant === 'gradient') {
    return (
      <svg className={className} viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <linearGradient id="markinsight-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#3b82f6" />
            <stop offset="100%" stopColor="#8b5cf6" />
          </linearGradient>
        </defs>
        <path
          d="M15 75 L15 35 L30 55 L45 25 L60 50 L60 75"
          stroke="url(#markinsight-gradient)"
          strokeWidth="8"
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        />
        <rect x="68" y="60" width="8" height="15" rx="2" fill="url(#markinsight-gradient)" />
        <rect x="80" y="50" width="8" height="25" rx="2" fill="url(#markinsight-gradient)" />
      </svg>
    );
  }

  const fillColor = variant === 'white' ? '#ffffff' : '#3b82f6';

  return (
    <svg className={className} viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path
        d="M15 75 L15 35 L30 55 L45 25 L60 50 L60 75"
        stroke={fillColor}
        strokeWidth="8"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
      <rect x="68" y="60" width="8" height="15" rx="2" fill={fillColor} />
      <rect x="80" y="50" width="8" height="25" rx="2" fill={fillColor} />
    </svg>
  );
}
