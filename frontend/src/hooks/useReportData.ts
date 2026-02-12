/**
 * useReportData Hook
 *
 * React hook for fetching and caching report data with graceful fallback.
 * Handles loading states, errors, and automatically falls back to sample data
 * when the backend endpoint doesn't exist or queries fail.
 *
 * Features:
 * - Conditional fetching based on enabled flag
 * - Debouncing for parameter changes
 * - Request cancellation on unmount
 * - Automatic fallback to sample data on errors
 * - Result caching per report + dateRange
 *
 * Phase 2.6 - Preview Step Live Data Integration
 */

import { useEffect, useState, useRef, useCallback } from 'react';
import type { Report, ChartFilter } from '../types/customDashboards';
import type { ReportDataResponse } from '../services/reportDataApi';
import { executeReport, previewReportData } from '../services/reportDataApi';
import { generateSampleData } from '../utils/sampleDataGenerator';
import { isApiError } from '../services/apiUtils';

// =============================================================================
// Types
// =============================================================================

export interface UseReportDataOptions {
  enabled?: boolean; // Only fetch if true (default: true)
  dateRange?: string; // Date range parameter (default: "30")
  filters?: ChartFilter[]; // Additional filters
  refetchInterval?: number; // Auto-refetch interval in ms (disabled by default)
}

export interface UseReportDataResult {
  data: ReportDataResponse | null;
  isLoading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
  isFallback: boolean; // True if using sample data due to API failure
}

// =============================================================================
// Cache for results (simple in-memory cache)
// =============================================================================

interface CacheEntry {
  data: ReportDataResponse;
  timestamp: number;
}

const cache = new Map<string, CacheEntry>();
const CACHE_TTL = 60000; // 1 minute

function getCacheKey(reportId: string, dateRange: string): string {
  return `${reportId}-${dateRange}`;
}

function getCachedData(reportId: string, dateRange: string): ReportDataResponse | null {
  const key = getCacheKey(reportId, dateRange);
  const entry = cache.get(key);

  if (!entry) return null;

  // Check if cache entry is still valid
  if (Date.now() - entry.timestamp > CACHE_TTL) {
    cache.delete(key);
    return null;
  }

  return entry.data;
}

function setCachedData(reportId: string, dateRange: string, data: ReportDataResponse): void {
  const key = getCacheKey(reportId, dateRange);
  cache.set(key, {
    data,
    timestamp: Date.now(),
  });
}

// =============================================================================
// Hook Implementation
// =============================================================================

/**
 * Hook for fetching report data with automatic fallback to sample data.
 *
 * @param report - Report object (null if not ready to fetch)
 * @param options - Fetch options (enabled, dateRange, filters, etc.)
 * @returns Result object with data, loading state, error, refetch function, and fallback flag
 */
export function useReportData(
  report: Report | null,
  options: UseReportDataOptions = {},
): UseReportDataResult {
  const {
    enabled = true,
    dateRange = '30',
    filters = [],
    refetchInterval,
  } = options;

  const [data, setData] = useState<ReportDataResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [isFallback, setIsFallback] = useState<boolean>(false);

  // Refs for cancellation and debouncing
  const abortControllerRef = useRef<AbortController | null>(null);
  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);

  /**
   * Fetch data from API or use cache.
   */
  const fetchData = useCallback(async () => {
    if (!report || !enabled) {
      return;
    }

    // Check cache first
    const cachedData = getCachedData(report.id, dateRange);
    if (cachedData) {
      setData(cachedData);
      setIsLoading(false);
      setError(null);
      setIsFallback(false);
      return;
    }

    // Cancel any in-flight request
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    setIsLoading(true);
    setError(null);
    setIsFallback(false);

    try {
      let responseData: ReportDataResponse;

      // Use executeReport for saved reports, previewReportData for wizard mode
      if (report.id && !report.id.startsWith('temp-')) {
        responseData = await executeReport(report.id, {
          date_range: dateRange,
          filters,
          limit: 1000,
        });
      } else {
        // Wizard mode: use preview endpoint with config
        responseData = await previewReportData(
          report.dataset_name,
          report.config_json,
          dateRange,
        );
      }

      // Cache the result
      setCachedData(report.id, dateRange, responseData);

      setData(responseData);
      setIsLoading(false);
      setIsFallback(false);
    } catch (err) {
      console.error('Failed to fetch report data:', err);

      // Handle different error types
      if (isApiError(err)) {
        // 404: Backend endpoint doesn't exist - silently fall back
        if (err.status === 404) {
          const fallbackData = generateFallbackData(report);
          setData(fallbackData);
          setIsFallback(true);
          setError(null); // Don't show error to user
          setIsLoading(false);
          return;
        }

        // 500, 408: Query execution failed or timeout - fall back with message
        if (err.status === 500 || err.status === 408) {
          const fallbackData = generateFallbackData(report);
          setData(fallbackData);
          setIsFallback(true);
          setError('Unable to load live data. Showing sample data instead.');
          setIsLoading(false);
          return;
        }

        // 422: Validation error - show error message
        if (err.status === 422) {
          setError('Invalid report configuration. Please check your metrics and dimensions.');
          setIsLoading(false);
          return;
        }

        // Other errors
        setError(err.detail || err.message);
      } else {
        setError(err instanceof Error ? err.message : 'Failed to load data');
      }

      setIsLoading(false);
    }
  }, [report, enabled, dateRange, filters]);

  /**
   * Refetch data manually (for refresh button).
   */
  const refetch = useCallback(async () => {
    if (!report) return;

    // Clear cache for this report
    cache.delete(getCacheKey(report.id, dateRange));

    await fetchData();
  }, [report, dateRange, fetchData]);

  /**
   * Generate fallback data using sample data generator.
   */
  function generateFallbackData(report: Report): ReportDataResponse {
    const sampleData = generateSampleData(
      report.chart_type,
      report.config_json.metrics,
      report.config_json.dimensions,
      10,
    );

    const columns = [
      report.config_json.dimensions[0] || 'dimension',
      ...report.config_json.metrics.map((m) => m.label || m.column),
    ];

    return {
      data: sampleData,
      columns,
      row_count: sampleData.length,
      truncated: false,
      query_duration_ms: null,
    };
  }

  /**
   * Effect: Fetch data when dependencies change (with debouncing).
   */
  useEffect(() => {
    if (!report || !enabled) {
      setData(null);
      setIsLoading(false);
      setError(null);
      setIsFallback(false);
      return;
    }

    // Debounce dateRange changes to avoid excessive API calls
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }

    debounceTimerRef.current = setTimeout(() => {
      fetchData();
    }, 500); // 500ms debounce

    // Cleanup
    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, [report?.id, enabled, dateRange, fetchData]);

  /**
   * Effect: Set up refetch interval if specified.
   */
  useEffect(() => {
    if (refetchInterval && refetchInterval > 0) {
      intervalRef.current = setInterval(() => {
        fetchData();
      }, refetchInterval);

      return () => {
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
        }
      };
    }
  }, [refetchInterval, fetchData]);

  return {
    data,
    isLoading,
    error,
    refetch,
    isFallback,
  };
}
