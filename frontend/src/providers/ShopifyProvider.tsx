/**
 * Shopify Provider
 *
 * Wraps the app with Shopify App Bridge when embedded in Shopify Admin.
 * Falls back to Polaris-only when not embedded (for admin routes).
 */

import { ReactNode } from 'react';
import { AppProvider } from '@shopify/polaris';
import { AppBridgeProvider } from '@shopify/app-bridge-react';
import enTranslations from '@shopify/polaris/locales/en.json';
import '@shopify/polaris/build/esm/styles.css';

const SHOPIFY_API_KEY = import.meta.env.VITE_SHOPIFY_API_KEY || '';

/**
 * Extract shop host parameter from URL query string.
 * Shopify embedded apps pass ?host=... parameter.
 */
function getShopifyParams(): { host?: string } {
  const urlParams = new URLSearchParams(window.location.search);
  const host = urlParams.get('host');
  
  return { host: host || undefined };
}

interface ShopifyProviderProps {
  children: ReactNode;
}

export function ShopifyProvider({ children }: ShopifyProviderProps) {
  const { host } = getShopifyParams();

  // If host is present, we're embedded in Shopify Admin
  if (host) {
    if (!SHOPIFY_API_KEY) {
      console.error('VITE_SHOPIFY_API_KEY is not set. App Bridge will not work correctly.');
    }

    return (
      <AppBridgeProvider
        config={{
          apiKey: SHOPIFY_API_KEY,
          host: host,
          forceRedirect: true,
        }}
      >
        <AppProvider i18n={enTranslations}>{children}</AppProvider>
      </AppBridgeProvider>
    );
  }

  // Not embedded (e.g., admin routes), use Polaris only
  return <AppProvider i18n={enTranslations}>{children}</AppProvider>;
}
