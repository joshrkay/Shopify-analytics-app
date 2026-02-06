/**
 * DataHealthSupportCTA Component
 *
 * Provides a merchant support escalation path shown only when
 * data health state is UNAVAILABLE.
 *
 * Opens an email with auto-attached tenant_id and timestamp.
 * Never includes internal error details.
 *
 * Story 4.3 - Merchant Data Health Trust Layer
 */

import { Button, InlineStack, Text, Icon } from '@shopify/polaris';
import { EmailIcon } from '@shopify/polaris-icons';
import type { MerchantHealthState } from '../../utils/data_health_copy';

interface DataHealthSupportCTAProps {
  /** Current merchant health state. Only renders for 'unavailable'. */
  healthState: MerchantHealthState;
  /** Tenant ID for the support ticket. */
  tenantId: string;
  /** Optional support email address override. */
  supportEmail?: string;
}

/**
 * DataHealthSupportCTA renders a "Contact Support" button when
 * data is unavailable. Auto-attaches tenant context to the email.
 *
 * Returns null for any state other than 'unavailable'.
 */
export function DataHealthSupportCTA({
  healthState,
  tenantId,
  supportEmail = 'support@example.com',
}: DataHealthSupportCTAProps) {
  if (healthState !== 'unavailable') {
    return null;
  }

  const timestamp = new Date().toISOString();
  const subject = encodeURIComponent('Data Unavailable - Support Request');
  const body = encodeURIComponent(
    `Hi Support,\n\n` +
      `I am experiencing data unavailability in my analytics dashboard.\n\n` +
      `Account ID: ${tenantId}\n` +
      `Reported at: ${timestamp}\n\n` +
      `Please assist.\n`
  );
  const mailtoHref = `mailto:${supportEmail}?subject=${subject}&body=${body}`;

  return (
    <InlineStack gap="200" blockAlign="center">
      <Icon source={EmailIcon} tone="subdued" />
      <Text as="span" tone="subdued" variant="bodySm">
        Need help?
      </Text>
      <Button
        url={mailtoHref}
        variant="plain"
        external
        accessibilityLabel="Contact support about data unavailability"
      >
        Contact Support
      </Button>
    </InlineStack>
  );
}

export default DataHealthSupportCTA;
