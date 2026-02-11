/**
 * AppHeader Component
 *
 * Slim top utility bar with changelog and debug controls.
 * Navigation has moved to the Sidebar component (Phase 0).
 *
 * Story 9.7 - In-App Changelog & Release Notes
 * Story 9.8 - "What Changed?" Debug Panel
 * Story 0.1.2 - AppHeader becomes slim top utility bar
 */

import { InlineStack, Box } from '@shopify/polaris';
import { useNavigate, useLocation } from 'react-router-dom';
import { ChangelogBadge } from '../changelog/ChangelogBadge';
import { WhatChangedButton } from '../whatChanged/WhatChangedButton';

export function AppHeader() {
  const navigate = useNavigate();
  const location = useLocation();

  const handleWhatsNewClick = () => {
    navigate('/whats-new');
  };

  const isOnWhatsNewPage = location.pathname === '/whats-new';

  return (
    <Box
      paddingBlockStart="200"
      paddingBlockEnd="200"
      paddingInlineStart="400"
      paddingInlineEnd="400"
      background="bg-surface-secondary"
      borderBlockEndWidth="025"
      borderColor="border"
    >
      <InlineStack align="end" gap="400" blockAlign="center">
        {!isOnWhatsNewPage && (
          <ChangelogBadge
            onClick={handleWhatsNewClick}
            showLabel
            label="What's New"
            refreshInterval={60000}
          />
        )}
        <WhatChangedButton
          variant="inline"
          showBadge
          refreshInterval={60000}
        />
      </InlineStack>
    </Box>
  );
}

export default AppHeader;
