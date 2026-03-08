/**
 * Tests for DateRangeContext
 *
 * Covers:
 * - useDateRange throws outside DateRangeProvider
 * - Default timeframe is '30d'
 * - setTimeframe updates the timeframe
 * - Child components receive the context value
 */

import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { render, screen } from '@testing-library/react';

import { DateRangeProvider, useDateRange } from '../contexts/DateRangeContext';

// --- Helpers ---

function wrapper({ children }: { children: React.ReactNode }) {
  return <DateRangeProvider>{children}</DateRangeProvider>;
}

// --- Tests ---

describe('DateRangeContext', () => {
  // ---- useDateRange outside provider ----
  describe('useDateRange', () => {
    it('throws if used outside DateRangeProvider', () => {
      const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
      expect(() => {
        renderHook(() => useDateRange());
      }).toThrow('useDateRange must be used within DateRangeProvider');
      spy.mockRestore();
    });
  });

  // ---- Default timeframe ----
  describe('default state', () => {
    it('has default timeframe of 30d', () => {
      const { result } = renderHook(() => useDateRange(), { wrapper });

      expect(result.current.timeframe).toBe('30d');
    });
  });

  // ---- setTimeframe ----
  describe('setTimeframe', () => {
    it('updates timeframe to 7d', () => {
      const { result } = renderHook(() => useDateRange(), { wrapper });

      act(() => {
        result.current.setTimeframe('7d');
      });

      expect(result.current.timeframe).toBe('7d');
    });

    it('updates timeframe to 90d', () => {
      const { result } = renderHook(() => useDateRange(), { wrapper });

      act(() => {
        result.current.setTimeframe('90d');
      });

      expect(result.current.timeframe).toBe('90d');
    });

    it('allows switching between timeframes', () => {
      const { result } = renderHook(() => useDateRange(), { wrapper });

      act(() => {
        result.current.setTimeframe('7d');
      });
      expect(result.current.timeframe).toBe('7d');

      act(() => {
        result.current.setTimeframe('90d');
      });
      expect(result.current.timeframe).toBe('90d');

      act(() => {
        result.current.setTimeframe('30d');
      });
      expect(result.current.timeframe).toBe('30d');
    });
  });

  // ---- Child components receive context ----
  describe('child components', () => {
    it('receive the context value', () => {
      function DisplayTimeframe() {
        const { timeframe } = useDateRange();
        return <span data-testid="timeframe">{timeframe}</span>;
      }

      render(
        <DateRangeProvider>
          <DisplayTimeframe />
        </DateRangeProvider>,
      );

      expect(screen.getByTestId('timeframe')).toHaveTextContent('30d');
    });

    it('re-render when timeframe changes', () => {
      let setTf: ((tf: '7d' | '30d' | '90d') => void) | null = null;

      function DisplayTimeframe() {
        const { timeframe, setTimeframe } = useDateRange();
        setTf = setTimeframe;
        return <span data-testid="timeframe">{timeframe}</span>;
      }

      render(
        <DateRangeProvider>
          <DisplayTimeframe />
        </DateRangeProvider>,
      );

      expect(screen.getByTestId('timeframe')).toHaveTextContent('30d');

      act(() => {
        setTf!('7d');
      });

      expect(screen.getByTestId('timeframe')).toHaveTextContent('7d');
    });
  });
});
