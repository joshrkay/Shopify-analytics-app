import { createContext, useContext, useState, type ReactNode } from 'react';

type TimeframeOption = '7d' | '30d' | '90d';

interface DateRangeContextValue {
  timeframe: TimeframeOption;
  setTimeframe: (tf: TimeframeOption) => void;
}

const DateRangeContext = createContext<DateRangeContextValue | null>(null);

export function DateRangeProvider({ children }: { children: ReactNode }) {
  const [timeframe, setTimeframe] = useState<TimeframeOption>('30d');
  return (
    <DateRangeContext.Provider value={{ timeframe, setTimeframe }}>
      {children}
    </DateRangeContext.Provider>
  );
}

export function useDateRange(): DateRangeContextValue {
  const ctx = useContext(DateRangeContext);
  if (!ctx) throw new Error('useDateRange must be used within DateRangeProvider');
  return ctx;
}
