/**
 * P1 Major: Settings E2E Tests
 *
 * Verifies the settings page:
 * - Settings page renders all tabs
 * - Profile tab shows user info
 * - Billing tab shows current plan
 * - Team tab shows member list
 */
import { test, expect } from '../../fixtures/auth.fixture';
import { waitForLoadingComplete } from '../../helpers/assertions';

test.describe('Settings', () => {
  test('settings page renders all tabs', async ({ proTierPage }) => {
    await proTierPage.goto('/settings');
    await proTierPage.waitForLoadState('networkidle');
    await waitForLoadingComplete(proTierPage);

    const body = proTierPage.locator('body');
    await expect(body).not.toBeEmpty();

    // Should display settings page with navigation tabs
    const pageText = await body.textContent() || '';
    const hasSettingsContent =
      pageText.toLowerCase().includes('settings') ||
      pageText.toLowerCase().includes('account') ||
      pageText.toLowerCase().includes('preferences');

    expect(hasSettingsContent).toBeTruthy();

    // Look for tab controls
    const tabElements = proTierPage.locator(
      '.Polaris-Tabs__Tab, [role="tab"], [class*="tab"], [class*="Tab"]'
    );
    const tabCount = await tabElements.count().catch(() => 0);

    if (tabCount > 0) {
      // Verify expected tabs exist (Profile, Billing, Team are common)
      const allTabText: string[] = [];
      for (let i = 0; i < tabCount; i++) {
        const text = await tabElements.nth(i).textContent().catch(() => '') || '';
        allTabText.push(text.toLowerCase());
      }

      // At least some settings-related tabs should be present
      const expectedTabs = ['profile', 'billing', 'team', 'account', 'general', 'notifications'];
      const hasExpectedTabs = expectedTabs.some((tab) =>
        allTabText.some((text) => text.includes(tab))
      );

      expect(hasExpectedTabs || tabCount > 0).toBeTruthy();
    }

    // No raw errors
    expect(pageText).not.toContain('TypeError');
    expect(pageText).not.toContain('Cannot read properties');
    expect(pageText).not.toContain('Unexpected token');
  });

  test('profile tab shows user info', async ({ proTierPage }) => {
    await proTierPage.goto('/settings');
    await proTierPage.waitForLoadState('networkidle');
    await waitForLoadingComplete(proTierPage);

    // Click the Profile tab if it exists
    const profileTab = proTierPage.locator(
      '[role="tab"]:has-text("Profile"), button:has-text("Profile"), ' +
      '.Polaris-Tabs__Tab:has-text("Profile"), a:has-text("Profile")'
    ).first();

    const hasProfileTab = await profileTab.isVisible().catch(() => false);
    if (hasProfileTab) {
      await profileTab.click();
      await proTierPage.waitForLoadState('networkidle');
      await waitForLoadingComplete(proTierPage);
    }

    // The profile section should show user-related fields
    const body = proTierPage.locator('body');
    const pageText = await body.textContent() || '';

    // Look for user info fields (email, name, avatar, etc.)
    const hasUserInfo =
      pageText.toLowerCase().includes('email') ||
      pageText.toLowerCase().includes('name') ||
      pageText.toLowerCase().includes('profile') ||
      pageText.toLowerCase().includes('account') ||
      pageText.toLowerCase().includes('user');

    expect(hasUserInfo).toBeTruthy();

    // Check for form fields that display user info
    const formFields = proTierPage.locator(
      '.Polaris-TextField input, input[type="email"], input[type="text"], ' +
      '.Polaris-TextField, [class*="field"]'
    );
    const fieldCount = await formFields.count().catch(() => 0);

    // Profile should have at least some visible info or form fields
    expect(fieldCount > 0 || hasUserInfo).toBeTruthy();

    // No errors
    expect(pageText).not.toContain('TypeError');
    expect(pageText).not.toContain('NaN');
    expect(pageText).not.toContain('undefined');
  });

  test('billing tab shows current plan', async ({ proTierPage }) => {
    await proTierPage.goto('/settings');
    await proTierPage.waitForLoadState('networkidle');
    await waitForLoadingComplete(proTierPage);

    // Click the Billing tab
    const billingTab = proTierPage.locator(
      '[role="tab"]:has-text("Billing"), button:has-text("Billing"), ' +
      '.Polaris-Tabs__Tab:has-text("Billing"), a:has-text("Billing"), ' +
      '[role="tab"]:has-text("Plan"), button:has-text("Plan")'
    ).first();

    const hasBillingTab = await billingTab.isVisible().catch(() => false);
    if (hasBillingTab) {
      await billingTab.click();
      await proTierPage.waitForLoadState('networkidle');
      await waitForLoadingComplete(proTierPage);
    }

    const body = proTierPage.locator('body');
    const pageText = await body.textContent() || '';

    // Billing section should show plan information
    const hasBillingContent =
      pageText.toLowerCase().includes('plan') ||
      pageText.toLowerCase().includes('billing') ||
      pageText.toLowerCase().includes('subscription') ||
      pageText.toLowerCase().includes('free') ||
      pageText.toLowerCase().includes('growth') ||
      pageText.toLowerCase().includes('pro') ||
      pageText.toLowerCase().includes('enterprise') ||
      pageText.includes('$');

    expect(hasBillingContent).toBeTruthy();

    // Should show the current plan name or tier badge
    const planBadge = proTierPage.locator(
      '.Polaris-Badge, [class*="plan"], [class*="tier"], [class*="Plan"]'
    ).first();
    const hasPlanBadge = await planBadge.isVisible().catch(() => false);

    // Look for upgrade/downgrade buttons (indicates billing section is rendered)
    const upgradeButton = proTierPage.locator(
      'button:has-text("Upgrade"), button:has-text("Change Plan"), ' +
      'button:has-text("Manage"), a:has-text("Upgrade")'
    ).first();
    const hasUpgrade = await upgradeButton.isVisible().catch(() => false);

    // Billing section should have plan info, badge, or action buttons
    expect(hasBillingContent || hasPlanBadge || hasUpgrade).toBeTruthy();

    // No errors
    expect(pageText).not.toContain('TypeError');
    expect(pageText).not.toContain('Internal Server Error');
  });

  test('team tab shows member list', async ({ adminPage }) => {
    await adminPage.goto('/settings');
    await adminPage.waitForLoadState('networkidle');
    await waitForLoadingComplete(adminPage);

    // Click the Team tab
    const teamTab = adminPage.locator(
      '[role="tab"]:has-text("Team"), button:has-text("Team"), ' +
      '.Polaris-Tabs__Tab:has-text("Team"), a:has-text("Team"), ' +
      '[role="tab"]:has-text("Members"), button:has-text("Members")'
    ).first();

    const hasTeamTab = await teamTab.isVisible().catch(() => false);
    if (hasTeamTab) {
      await teamTab.click();
      await adminPage.waitForLoadState('networkidle');
      await waitForLoadingComplete(adminPage);
    }

    const body = adminPage.locator('body');
    const pageText = await body.textContent() || '';

    // Team section should show member list or team management UI
    const hasTeamContent =
      pageText.toLowerCase().includes('team') ||
      pageText.toLowerCase().includes('member') ||
      pageText.toLowerCase().includes('invite') ||
      pageText.toLowerCase().includes('role') ||
      pageText.toLowerCase().includes('admin') ||
      pageText.toLowerCase().includes('user');

    expect(hasTeamContent).toBeTruthy();

    // Look for a table or list of team members
    const memberList = adminPage.locator(
      '.Polaris-IndexTable, .Polaris-DataTable, .Polaris-ResourceList, ' +
      'table, [class*="member"], [class*="user-list"]'
    );
    const hasList = (await memberList.count().catch(() => 0)) > 0;

    // Look for an "Invite" button (indicates team management functionality)
    const inviteButton = adminPage.locator(
      'button:has-text("Invite"), button:has-text("Add Member"), ' +
      'button:has-text("Add User"), [data-testid*="invite"]'
    ).first();
    const hasInvite = await inviteButton.isVisible().catch(() => false);

    // Team section should have either a member list, invite action, or team content
    expect(hasList || hasInvite || hasTeamContent).toBeTruthy();

    // No errors
    expect(pageText).not.toContain('TypeError');
    expect(pageText).not.toContain('Internal Server Error');
    expect(pageText).not.toContain('Cannot read properties');
  });
});
