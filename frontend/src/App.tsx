/**
 * Main App Component
 *
 * Sets up Shopify App Bridge, Polaris provider, and routing.
 */

import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ShopifyProvider } from './providers/ShopifyProvider';
import { ShopifyApiProvider } from './providers/ShopifyApiProvider';
import AdminPlans from './pages/AdminPlans';

function App() {
  return (
    <ShopifyProvider>
      <ShopifyApiProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/admin/plans" element={<AdminPlans />} />
            <Route path="/" element={<Navigate to="/admin/plans" replace />} />
          </Routes>
        </BrowserRouter>
      </ShopifyApiProvider>
    </ShopifyProvider>
  );
}

export default App;
