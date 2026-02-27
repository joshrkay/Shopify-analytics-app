/**
 * OAuth Callback Page
 *
 * Handles the OAuth redirect from external platforms (Meta Ads, Google Ads, etc.)
 * after the user grants authorization in a popup window.
 *
 * Flow:
 *   1. Platform redirects popup to /oauth/callback?code=...&state=...
 *   2. This page reads code + state from URL params
 *   3. Posts {type:'OAUTH_COMPLETE', code, state} to window.opener
 *   4. Closes the popup
 *
 * The parent window (wizard) receives the message, calls the backend to
 * exchange the code, and drives the rest of the wizard flow (including
 * account selection for Meta Ads).
 *
 * Security: State parameter is validated by the backend during exchange.
 *
 * Phase 3 — Subphase 3.4: OAuth Redirect Handler
 */

import { useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Page, Card, Spinner, BlockStack, Text } from '@shopify/polaris';

export const OAUTH_COMPLETE_MESSAGE = 'OAUTH_COMPLETE';
export const OAUTH_ERROR_MESSAGE = 'OAUTH_ERROR';

export default function OAuthCallback() {
  const [searchParams] = useSearchParams();

  useEffect(() => {
    const code = searchParams.get('code');
    const state = searchParams.get('state');
    const errorParam = searchParams.get('error');
    const errorDescription = searchParams.get('error_description');

    if (!window.opener) {
      // Not in a popup — nothing to post to. Show a message and let the user
      // navigate manually. This shouldn't happen in normal use.
      return;
    }

    if (errorParam) {
      window.opener.postMessage(
        {
          type: OAUTH_ERROR_MESSAGE,
          error: errorDescription || errorParam || 'Authorization was denied',
        },
        window.location.origin,
      );
      window.close();
      return;
    }

    if (!code || !state) {
      window.opener.postMessage(
        {
          type: OAUTH_ERROR_MESSAGE,
          error: 'Invalid OAuth callback: missing code or state parameter',
        },
        window.location.origin,
      );
      window.close();
      return;
    }

    // Send code + state to the parent window — the wizard will call the backend.
    window.opener.postMessage(
      { type: OAUTH_COMPLETE_MESSAGE, code, state },
      window.location.origin,
    );
    window.close();
  }, [searchParams]);

  // Shown briefly while useEffect runs (typically < 100ms before popup closes)
  return (
    <Page narrowWidth>
      <Card>
        <BlockStack gap="400" inlineAlign="center">
          <Spinner size="large" />
          <BlockStack gap="200" inlineAlign="center">
            <Text as="h2" variant="headingMd">
              Completing Authorization...
            </Text>
            <Text as="p" tone="subdued">
              This window will close automatically.
            </Text>
          </BlockStack>
        </BlockStack>
      </Card>
    </Page>
  );
}
