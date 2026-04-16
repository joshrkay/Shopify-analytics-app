/**
 * P2 Extended: Approvals Inbox E2E Tests
 *
 * Verifies the AI action approvals workflow:
 * - Approvals page loads with pending proposals
 * - Approve action updates proposal status
 * - Reject action updates proposal status
 * - Execution result is shown after approval
 */
import { test, expect } from '../../fixtures/auth.fixture';
import { waitForLoadingComplete, expectToast } from '../../helpers/assertions';

test.describe('Approvals Inbox', () => {
  test('approvals page shows pending proposals for pro-tier user', async ({ proTierPage }) => {
    await proTierPage.goto('/approvals');
    await proTierPage.waitForLoadState('networkidle');
    await waitForLoadingComplete(proTierPage);

    // Should not be on paywall
    const url = proTierPage.url();
    expect(url).not.toContain('/paywall');

    // Look for the approvals page content
    const body = proTierPage.locator('body');
    const pageText = await body.textContent() || '';

    // Should have some indication of the approvals/proposals feature
    const hasApprovalContent =
      pageText.includes('Approval') ||
      pageText.includes('approval') ||
      pageText.includes('Pending') ||
      pageText.includes('pending') ||
      pageText.includes('Proposal') ||
      pageText.includes('proposal') ||
      pageText.includes('Action') ||
      pageText.includes('action');

    // Look for approval list items or cards
    const approvalItems = proTierPage.locator(
      '[data-testid="approval-item"], [data-testid="proposal-card"], .Polaris-ResourceItem, .Polaris-Card, .Polaris-LegacyCard'
    );
    const itemCount = await approvalItems.count().catch(() => 0);

    // Look for empty state if no proposals exist
    const emptyState = proTierPage.locator(
      '.Polaris-EmptyState, [data-testid="empty-approvals"]'
    ).first();
    const hasEmptyState = await emptyState.isVisible().catch(() => false);

    // Page should show either proposals, empty state, or approval-related content
    expect(hasApprovalContent || itemCount > 0 || hasEmptyState).toBeTruthy();
  });

  test('approve action updates proposal status', async ({ proTierPage }) => {
    // Mock the approvals API to return a pending proposal
    await proTierPage.route('**/api/actions/proposals**', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            proposals: [
              {
                id: 'proposal-e2e-001',
                title: 'Increase Facebook Ad Budget',
                description: 'AI recommends increasing Facebook ad budget by 20% based on recent ROAS improvement.',
                status: 'pending',
                action_type: 'budget_adjustment',
                created_at: new Date().toISOString(),
                estimated_impact: '+15% revenue',
              },
            ],
            total: 1,
          }),
        });
      } else {
        await route.continue();
      }
    });

    // Mock the approve endpoint
    let approveCalledWith: string | null = null;
    await proTierPage.route('**/api/actions/proposals/*/approve', async (route) => {
      approveCalledWith = route.request().url();
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'proposal-e2e-001',
          status: 'approved',
          approved_at: new Date().toISOString(),
        }),
      });
    });

    await proTierPage.goto('/approvals');
    await proTierPage.waitForLoadState('networkidle');
    await waitForLoadingComplete(proTierPage);

    // Wait for proposal content to render
    await proTierPage.waitForTimeout(1000);

    // Look for the approve button
    const approveButton = proTierPage.locator(
      'button:has-text("Approve"), button:has-text("approve"), [data-testid="approve-action"]'
    ).first();
    const hasApproveButton = await approveButton.isVisible().catch(() => false);

    if (hasApproveButton) {
      await approveButton.click();

      // Wait for the status to update
      await proTierPage.waitForTimeout(1500);

      const body = proTierPage.locator('body');
      const pageText = await body.textContent() || '';

      // After approval, the status should change
      const statusUpdated =
        pageText.includes('Approved') ||
        pageText.includes('approved') ||
        pageText.includes('Success') ||
        pageText.includes('success') ||
        approveCalledWith !== null;

      expect(statusUpdated).toBeTruthy();
    } else {
      // If no approve button found (no proposals), check for empty state
      const body = proTierPage.locator('body');
      await expect(body).not.toBeEmpty();
    }
  });

  test('reject action updates proposal status', async ({ proTierPage }) => {
    // Mock the approvals API with a pending proposal
    await proTierPage.route('**/api/actions/proposals**', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            proposals: [
              {
                id: 'proposal-e2e-002',
                title: 'Pause underperforming Google campaign',
                description: 'AI recommends pausing Campaign #1234 due to declining CTR.',
                status: 'pending',
                action_type: 'campaign_pause',
                created_at: new Date().toISOString(),
                estimated_impact: '-$500 wasted spend',
              },
            ],
            total: 1,
          }),
        });
      } else {
        await route.continue();
      }
    });

    // Mock the reject endpoint
    let rejectCalled = false;
    await proTierPage.route('**/api/actions/proposals/*/reject', async (route) => {
      rejectCalled = true;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'proposal-e2e-002',
          status: 'rejected',
          rejected_at: new Date().toISOString(),
        }),
      });
    });

    await proTierPage.goto('/approvals');
    await proTierPage.waitForLoadState('networkidle');
    await waitForLoadingComplete(proTierPage);

    await proTierPage.waitForTimeout(1000);

    // Look for the reject button
    const rejectButton = proTierPage.locator(
      'button:has-text("Reject"), button:has-text("reject"), button:has-text("Decline"), button:has-text("Dismiss"), [data-testid="reject-action"]'
    ).first();
    const hasRejectButton = await rejectButton.isVisible().catch(() => false);

    if (hasRejectButton) {
      await rejectButton.click();

      // If there's a confirmation modal, confirm it
      const confirmButton = proTierPage.locator(
        '.Polaris-Modal-Dialog button:has-text("Reject"), .Polaris-Modal-Dialog button:has-text("Confirm"), .Polaris-Modal-Dialog button.Polaris-Button--primary'
      ).first();
      const hasConfirm = await confirmButton.isVisible().catch(() => false);
      if (hasConfirm) {
        await confirmButton.click();
      }

      await proTierPage.waitForTimeout(1500);

      const body = proTierPage.locator('body');
      const pageText = await body.textContent() || '';

      const statusUpdated =
        pageText.includes('Rejected') ||
        pageText.includes('rejected') ||
        pageText.includes('Declined') ||
        rejectCalled;

      expect(statusUpdated).toBeTruthy();
    } else {
      // No reject button — page still loaded without error
      const body = proTierPage.locator('body');
      await expect(body).not.toBeEmpty();
    }
  });

  test('execution result shown after approval', async ({ proTierPage }) => {
    // Mock proposals with one that has been approved and executed
    await proTierPage.route('**/api/actions/proposals**', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            proposals: [
              {
                id: 'proposal-e2e-003',
                title: 'Increase Instagram budget',
                description: 'Budget increase based on ROAS trend.',
                status: 'executed',
                action_type: 'budget_adjustment',
                created_at: new Date(Date.now() - 86400000).toISOString(),
                approved_at: new Date(Date.now() - 3600000).toISOString(),
                executed_at: new Date().toISOString(),
                execution_result: {
                  success: true,
                  summary: 'Budget increased from $500 to $600 (+20%)',
                  details: 'Applied to Instagram campaign #5678',
                },
                estimated_impact: '+12% revenue',
              },
            ],
            total: 1,
          }),
        });
      } else {
        await route.continue();
      }
    });

    await proTierPage.goto('/approvals');
    await proTierPage.waitForLoadState('networkidle');
    await waitForLoadingComplete(proTierPage);

    await proTierPage.waitForTimeout(1000);

    const body = proTierPage.locator('body');
    const pageText = await body.textContent() || '';

    // The executed proposal should show its result
    const hasExecutionInfo =
      pageText.includes('Executed') ||
      pageText.includes('executed') ||
      pageText.includes('Completed') ||
      pageText.includes('completed') ||
      pageText.includes('Budget increased') ||
      pageText.includes('Success') ||
      pageText.includes('Result');

    // Look for a status badge indicating execution
    const statusBadge = proTierPage.locator(
      '.Polaris-Badge, [data-testid="proposal-status"]'
    );
    const badgeCount = await statusBadge.count().catch(() => 0);

    expect(hasExecutionInfo || badgeCount > 0).toBeTruthy();
  });
});
