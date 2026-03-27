/**
 * BrandingSettingsTab - Configure brand name, logo, accent color for emails.
 *
 * Stores branding in tenant.settings JSON column via GET/PUT /api/settings/branding.
 * Includes a live email preview card.
 */

import { useEffect, useState } from 'react';
import { getErrorMessage } from '../../services/apiUtils';
import {
  getBrandingSettings,
  updateBrandingSettings,
  type BrandingSettings,
} from '../../services/brandingApi';

export function BrandingSettingsTab() {
  const [form, setForm] = useState<BrandingSettings>({
    brand_name: 'MarkInsight',
    logo_url: null,
    accent_color: '#4CAF50',
    email_footer_text: null,
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        setLoading(true);
        setError(null);
        const data = await getBrandingSettings();
        if (!mounted) return;
        setForm(data);
      } catch (err) {
        if (!mounted) return;
        setError(getErrorMessage(err, 'Failed to load branding settings'));
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => { mounted = false; };
  }, []);

  const save = async () => {
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const updated = await updateBrandingSettings({
        brand_name: form.brand_name || null,
        logo_url: form.logo_url || null,
        accent_color: form.accent_color || null,
        email_footer_text: form.email_footer_text || null,
      });
      setForm(updated);
      setSuccess('Branding settings saved.');
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to save branding settings'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <section data-testid="settings-panel-branding">
      <h2 className="text-xl font-semibold mb-1">Branding</h2>
      <p className="text-gray-500 text-sm mb-6">
        Customize how your brand appears in notification emails sent to your team.
      </p>

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}
      {success && (
        <div className="mb-4 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
          {success}
        </div>
      )}

      {loading ? (
        <p className="text-sm text-gray-500">Loading branding settings...</p>
      ) : (
        <div className="grid gap-6 lg:grid-cols-2">
          {/* Form */}
          <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
            <label className="block">
              <span className="mb-1 block text-sm font-medium text-gray-700">Brand Name</span>
              <input
                type="text"
                value={form.brand_name}
                onChange={(e) => setForm((prev) => ({ ...prev, brand_name: e.target.value }))}
                placeholder="Your store or company name"
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                maxLength={255}
              />
              <p className="mt-1 text-xs text-gray-400">
                Used in email headers and footers. Falls back to your Shopify store name.
              </p>
            </label>

            <label className="block">
              <span className="mb-1 block text-sm font-medium text-gray-700">Logo URL</span>
              <input
                type="url"
                value={form.logo_url || ''}
                onChange={(e) => setForm((prev) => ({ ...prev, logo_url: e.target.value || null }))}
                placeholder="https://example.com/logo.png"
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
              />
              <p className="mt-1 text-xs text-gray-400">
                HTTPS URL to your logo image. Recommended size: 200x50px.
              </p>
            </label>

            <label className="block">
              <span className="mb-1 block text-sm font-medium text-gray-700">Accent Color</span>
              <div className="flex items-center gap-3">
                <input
                  type="color"
                  value={form.accent_color}
                  onChange={(e) => setForm((prev) => ({ ...prev, accent_color: e.target.value }))}
                  className="w-10 h-10 rounded border border-gray-300 cursor-pointer"
                />
                <input
                  type="text"
                  value={form.accent_color}
                  onChange={(e) => setForm((prev) => ({ ...prev, accent_color: e.target.value }))}
                  placeholder="#4CAF50"
                  className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm font-mono"
                  maxLength={7}
                />
              </div>
              <p className="mt-1 text-xs text-gray-400">
                Used for buttons and highlights in emails.
              </p>
            </label>

            <label className="block">
              <span className="mb-1 block text-sm font-medium text-gray-700">Email Footer Text</span>
              <textarea
                value={form.email_footer_text || ''}
                onChange={(e) =>
                  setForm((prev) => ({ ...prev, email_footer_text: e.target.value || null }))
                }
                placeholder="Custom footer message (optional)"
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                rows={2}
                maxLength={500}
              />
            </label>

            <button
              onClick={save}
              disabled={saving}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 hover:bg-blue-700 transition-colors"
            >
              {saving ? 'Saving...' : 'Save Branding'}
            </button>
          </div>

          {/* Live Email Preview */}
          <div>
            <p className="text-sm font-medium text-gray-700 mb-2">Email Preview</p>
            <div className="bg-gray-100 rounded-xl p-4">
              <div className="bg-white rounded-lg shadow-sm overflow-hidden" style={{ maxWidth: 400 }}>
                {/* Header */}
                <div
                  className="px-5 py-4"
                  style={{ backgroundColor: `${form.accent_color}15`, borderBottom: `3px solid ${form.accent_color}` }}
                >
                  {form.logo_url ? (
                    <img
                      src={form.logo_url}
                      alt={form.brand_name}
                      className="h-8 object-contain"
                      onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                    />
                  ) : (
                    <p className="font-bold text-gray-900 text-lg">{form.brand_name}</p>
                  )}
                </div>

                {/* Body */}
                <div className="px-5 py-4">
                  <p className="font-semibold text-gray-900 mb-2">Sample Notification Title</p>
                  <p className="text-sm text-gray-600 mb-4">
                    This is a preview of how your notification emails will look with your branding applied.
                  </p>
                  <button
                    className="px-4 py-2 rounded text-white text-sm font-medium"
                    style={{ backgroundColor: form.accent_color }}
                  >
                    View Details
                  </button>
                </div>

                {/* Footer */}
                <div className="px-5 py-3 bg-gray-50 border-t border-gray-100">
                  <p className="text-xs text-gray-400">
                    {form.email_footer_text || `This is an automated notification from ${form.brand_name}.`}
                  </p>
                  <p className="text-xs text-gray-400 mt-1">
                    You can manage your notification preferences in settings.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

export default BrandingSettingsTab;
