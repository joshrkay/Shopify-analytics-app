/**
 * External Analytics Shell
 *
 * Standalone analytics shell for non-Shopify (external) surfaces.
 * Renders a Superset dashboard iframe with JWT authentication
 * and automatic token refresh, without Shopify Polaris dependency
 * for the outer shell (uses plain HTML/CSS).
 *
 * Phase 2 - Silent Refresh / External Surface
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { generateEmbedToken } from '../services/embedApi';
import type { EmbedTokenResponse } from '../services/embedApi';
import { UnifiedTokenRefreshManager } from '../utils/tokenRefresh';
import { AnalyticsHealthBanner } from './AnalyticsHealthBanner';

export interface ExternalAnalyticsShellProps {
  /** Superset dashboard ID to embed */
  dashboardId: string;
  /** Tenant ID (optional) */
  tenantId?: string;
  /** Custom height for iframe */
  height?: string | number;
  /** Custom CSS class name */
  className?: string;
  /** Callback when dashboard loads successfully */
  onLoad?: () => void;
  /** Callback when error occurs */
  onError?: (error: Error) => void;
}

type ShellStatus = 'loading' | 'ready' | 'error';

const DEFAULT_HEIGHT = '600px';

/**
 * ExternalAnalyticsShell Component
 *
 * Embeds a Superset dashboard for external (non-Shopify) surfaces.
 * Uses plain HTML/CSS for the outer shell -- no Polaris dependency
 * except for the AnalyticsHealthBanner used in the error state.
 */
export const ExternalAnalyticsShell: React.FC<ExternalAnalyticsShellProps> = ({
  dashboardId,
  tenantId,
  height = DEFAULT_HEIGHT,
  className = '',
  onLoad,
  onError,
}) => {
  const [status, setStatus] = useState<ShellStatus>('loading');
  const [dashboardUrl, setDashboardUrl] = useState<string | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [isRetrying, setIsRetrying] = useState(false);

  const iframeRef = useRef<HTMLIFrameElement>(null);
  const refreshManagerRef = useRef<UnifiedTokenRefreshManager | null>(null);

  /**
   * Handle successful token refresh.
   */
  const handleTokenRefreshed = useCallback((tokenResponse: EmbedTokenResponse) => {
    setDashboardUrl(tokenResponse.dashboard_url);
    setStatus('ready');
    setError(null);
  }, []);

  /**
   * Handle token refresh failure after all retries exhausted.
   */
  const handleRefreshError = useCallback(
    (err: Error) => {
      console.error('[ExternalAnalyticsShell] Token refresh failed:', err);
      setStatus('error');
      setError(err);
      onError?.(err);
    },
    [onError]
  );

  /**
   * Fetch embed token and initialize refresh manager.
   */
  const fetchToken = useCallback(async () => {
    setStatus('loading');
    setError(null);

    try {
      const tokenResponse = await generateEmbedToken(dashboardId, 'external_app');

      // Initialize refresh manager
      if (refreshManagerRef.current) {
        refreshManagerRef.current.stop();
      }
      refreshManagerRef.current = new UnifiedTokenRefreshManager({
        dashboardId,
        accessSurface: 'external_app',
        onRefreshed: handleTokenRefreshed,
        onError: handleRefreshError,
      });
      refreshManagerRef.current.start(tokenResponse);

      setDashboardUrl(tokenResponse.dashboard_url);
      setStatus('ready');
    } catch (err) {
      console.error('[ExternalAnalyticsShell] Failed to fetch token:', err);
      setStatus('error');
      setError(err as Error);
      onError?.(err as Error);
    }
  }, [dashboardId, handleTokenRefreshed, handleRefreshError, onError]);

  /**
   * Handle iframe load event.
   */
  const handleIframeLoad = useCallback(() => {
    console.log('[ExternalAnalyticsShell] Dashboard iframe loaded');
    onLoad?.();
  }, [onLoad]);

  /**
   * Handle iframe error.
   */
  const handleIframeError = useCallback(() => {
    const err = new Error('Failed to load dashboard');
    console.error('[ExternalAnalyticsShell] Iframe error');
    setStatus('error');
    setError(err);
    onError?.(err);
  }, [onError]);

  /**
   * Handle retry from error banner.
   */
  const handleRetry = useCallback(() => {
    setIsRetrying(true);
    fetchToken().finally(() => setIsRetrying(false));
  }, [fetchToken]);

  /**
   * Initialize on mount and clean up on unmount.
   */
  useEffect(() => {
    fetchToken();

    return () => {
      if (refreshManagerRef.current) {
        refreshManagerRef.current.stop();
      }
    };
  }, [dashboardId, tenantId]); // Re-fetch when dashboard or tenant changes

  const iframeHeight = typeof height === 'number' ? `${height}px` : height;

  return (
    <div
      className={`external-analytics-shell ${className}`}
      style={{
        width: '100%',
        minHeight: iframeHeight,
        position: 'relative',
      }}
    >
      {/* Loading state */}
      {status === 'loading' && (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            minHeight: iframeHeight,
            padding: '20px',
            color: '#6d7175',
            fontSize: '14px',
          }}
        >
          <div
            style={{
              width: '40px',
              height: '40px',
              border: '3px solid #e1e3e5',
              borderTopColor: '#2c6ecb',
              borderRadius: '50%',
              animation: 'external-shell-spin 0.8s linear infinite',
              marginBottom: '16px',
            }}
          />
          <p style={{ margin: 0 }}>Loading analytics dashboard...</p>
          <style>{`
            @keyframes external-shell-spin {
              to { transform: rotate(360deg); }
            }
          `}</style>
        </div>
      )}

      {/* Error state */}
      {status === 'error' && (
        <div style={{ padding: '16px' }}>
          <AnalyticsHealthBanner
            onRetry={handleRetry}
            isRetrying={isRetrying}
            errorType={error?.message || 'unknown'}
            accessSurface="external_app"
          />
        </div>
      )}

      {/* Ready state - iframe */}
      {status === 'ready' && dashboardUrl && (
        <iframe
          ref={iframeRef}
          src={dashboardUrl}
          title={`Analytics Dashboard: ${dashboardId}`}
          style={{
            width: '100%',
            height: iframeHeight,
            border: 'none',
            borderRadius: '8px',
            backgroundColor: '#ffffff',
          }}
          onLoad={handleIframeLoad}
          onError={handleIframeError}
          allow="fullscreen"
          sandbox="allow-same-origin allow-scripts allow-popups allow-forms allow-presentation"
        />
      )}
    </div>
  );
};

export default ExternalAnalyticsShell;
