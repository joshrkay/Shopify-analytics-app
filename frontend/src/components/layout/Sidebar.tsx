/**
 * Sidebar Component
 *
 * Fixed left sidebar with navigation sections and user footer.
 * Active route highlighting via useLocation().
 *
 * Epic 0.2 — Sidebar navigation + access control
 * Story 0.2.1 — Nav sections: MAIN, CONNECTIONS, SETTINGS + user footer
 * Story 0.2.2 — Active route highlighting
 */

import { Icon, Text } from '@shopify/polaris';
import type { IconSource } from '@shopify/polaris';
import {
  HomeIcon,
  ChartVerticalIcon,
  LightbulbIcon,
  DatabaseIcon,
  SettingsIcon,
} from '@shopify/polaris-icons';
import { useNavigate, useLocation } from 'react-router-dom';
import { useUser } from '@clerk/clerk-react';
import './Sidebar.css';

interface NavItem {
  label: string;
  path: string;
  icon: IconSource;
  matchPrefix?: boolean;
}

interface NavSection {
  title: string;
  items: NavItem[];
}

const NAV_SECTIONS: NavSection[] = [
  {
    title: 'Main',
    items: [
      { label: 'Analytics', path: '/analytics', icon: HomeIcon },
      { label: 'Dashboards', path: '/dashboards', icon: ChartVerticalIcon, matchPrefix: true },
      { label: 'Insights', path: '/insights', icon: LightbulbIcon },
    ],
  },
  {
    title: 'Connections',
    items: [
      { label: 'Data Sources', path: '/data-sources', icon: DatabaseIcon },
    ],
  },
  {
    title: 'Settings',
    items: [
      { label: 'Settings', path: '/settings', icon: SettingsIcon },
    ],
  },
];

function isActive(location: { pathname: string }, item: NavItem): boolean {
  if (item.matchPrefix) {
    return location.pathname.startsWith(item.path);
  }
  return location.pathname === item.path;
}

export function Sidebar() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user } = useUser();

  const userName = user?.fullName || user?.firstName || 'User';
  const userEmail = user?.primaryEmailAddress?.emailAddress || '';
  const avatarInitial = userName.charAt(0).toUpperCase();

  return (
    <nav className="sidebar" aria-label="Main navigation">
      <div className="sidebar-nav">
        {NAV_SECTIONS.map((section) => (
          <div key={section.title} className="sidebar-section">
            <div className="sidebar-section-header">{section.title}</div>
            {section.items.map((item) => {
              const active = isActive(location, item);
              return (
                <div
                  key={item.path}
                  className={`sidebar-nav-item${active ? ' sidebar-nav-item--active' : ''}`}
                  role="link"
                  tabIndex={0}
                  onClick={() => navigate(item.path)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      navigate(item.path);
                    }
                  }}
                >
                  <Icon source={item.icon} />
                  <Text as="span" variant="bodyMd">
                    {item.label}
                  </Text>
                </div>
              );
            })}
          </div>
        ))}
      </div>

      <div className="sidebar-footer">
        <div className="sidebar-user">
          <div className="sidebar-avatar">{avatarInitial}</div>
          <div className="sidebar-user-info">
            <div className="sidebar-user-name">{userName}</div>
            {userEmail && <div className="sidebar-user-email">{userEmail}</div>}
          </div>
        </div>
      </div>
    </nav>
  );
}
