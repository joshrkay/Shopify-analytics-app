/**
 * AppHeader Component
 *
 * Slim top utility bar with changelog and debug controls.
 * Navigation has moved to the Sidebar component (Phase 0).
 * Includes hamburger toggle for mobile sidebar.
 *
 * Story 9.7 - In-App Changelog & Release Notes
 * Story 9.8 - "What Changed?" Debug Panel
 * Story 0.1.2 - AppHeader becomes slim top utility bar
 * Story 0.3.1 - Mobile hamburger toggles sidebar
 */

import { InlineStack, Box, Icon } from '@shopify/polaris';
import { MenuIcon } from '@shopify/polaris-icons';
import { useNavigate, useLocation } from 'react-router-dom';
import { ChangelogBadge } from '../changelog/ChangelogBadge';
import { WhatChangedButton } from '../whatChanged/WhatChangedButton';
import { useSidebar } from './RootLayout';
import './AppHeader.css';

export function AppHeader() {
  const navigate = useNavigate();
  const location = useLocation();
  const { isOpen, toggle } = useSidebar();

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
      <InlineStack align="space-between" gap="400" blockAlign="center">
        {/* Left: hamburger (mobile only) */}
        <button
          className="sidebar-hamburger"
          onClick={toggle}
          aria-label="Toggle navigation"
          aria-expanded={isOpen}
          aria-controls="sidebar-nav"
          type="button"
        >
          <Icon source={MenuIcon} />
        </button>

        {/* Right: Status indicators */}
        <InlineStack gap="400" blockAlign="center">
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
      </InlineStack>
    </Box>
  );
}

export default AppHeader;
