import { Page, EmptyState } from '@shopify/polaris';
import { useNavigate } from 'react-router-dom';

export function NotFound() {
  const navigate = useNavigate();
  return (
    <Page title="Page not found">
      <EmptyState
        heading="The page you're looking for doesn't exist"
        action={{ content: 'Go to Home', onAction: () => navigate('/') }}
        image=""
      >
        <p>Check the URL and try again, or navigate back to the home page.</p>
      </EmptyState>
    </Page>
  );
}
