/**
 * AppHeader Component
 *
 * Global header with navigation links and status indicators.
 * Includes ChangelogBadge and WhatChangedButton for stories 9.7 and 9.8.
 *
 * Story 9.7 - In-App Changelog & Release Notes
 * Story 9.8 - "What Changed?" Debug Panel
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

  // Don't show header on the What's New page itself
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
        {/* What's New badge with unread count */}
        {!isOnWhatsNewPage && (
          <ChangelogBadge
            onClick={handleWhatsNewClick}
            showLabel
            label="What's New"
            refreshInterval={60000}
          />
        )}

        {/* What Changed debug panel button */}
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
