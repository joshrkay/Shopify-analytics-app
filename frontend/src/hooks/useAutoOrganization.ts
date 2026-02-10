/**
 * Auto Organization Selection Hook
 *
 * Automatically selects the user's first Clerk organization if none is active.
 * This ensures the Clerk session token includes org_id, org_role, etc.
 *
 * In a Shopify embedded app, each merchant belongs to one organization.
 * Without an active org, getToken() returns a token without org_id,
 * which the backend tenant_context middleware rejects.
 */

import { useEffect } from 'react';
import { useOrganization, useOrganizationList } from '@clerk/clerk-react';

export function useAutoOrganization(): {
  isLoading: boolean;
  hasOrg: boolean;
} {
  const { organization, isLoaded: isOrgLoaded } = useOrganization();
  const { isLoaded: isListLoaded, setActive, userMemberships } =
    useOrganizationList({
      userMemberships: { infinite: true },
    });

  useEffect(() => {
    // Wait for both hooks to load
    if (!isOrgLoaded || !isListLoaded) return;

    // Already have an active org — nothing to do
    if (organization) return;

    // Auto-select first org the user belongs to
    const memberships = userMemberships?.data;
    if (memberships && memberships.length > 0 && setActive) {
      const firstOrg = memberships[0].organization;
      console.log('[useAutoOrganization] Auto-selecting org:', firstOrg.id);
      setActive({ organization: firstOrg.id });
    }
  }, [isOrgLoaded, isListLoaded, organization, userMemberships?.data, setActive]);

  const isLoaded = isOrgLoaded && isListLoaded;
  const memberships = userMemberships?.data;

  // Still loading if:
  // - Clerk data hasn't loaded yet, OR
  // - User has orgs but none is active yet (setActive in progress)
  const isLoading =
    !isLoaded ||
    (!organization && !!memberships && memberships.length > 0);

  return {
    isLoading,
    hasOrg: !!organization,
  };
}
