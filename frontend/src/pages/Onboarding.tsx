/**
 * Onboarding — 4-step guided setup wizard.
 *
 * Route: /onboarding  (registered OUTSIDE <Root> so it renders full-screen)
 *
 * Steps:
 *   1. Welcome        — value prop, "Get Started" CTA
 *   2. Connect Shopify — initiate Shopify OAuth / confirm store connected
 *   3. Connect Ads    — select ad platforms to connect
 *   4. Done           — summary + navigate to dashboard
 *
 * State:
 *   - step index stored in local useState
 *   - completion written to localStorage: onboardingComplete=true,
 *     hasConnectedSources=true (step 3 skipped / completed)
 *
 * The wizard can be skipped entirely at steps 2 and 3 — the user lands
 * on the dashboard with empty-state prompts to connect later.
 */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronRight, Database, Zap, BarChart2, Check, ArrowRight, X } from "lucide-react";

// ---------------------------------------------------------------------------
// Step definitions
// ---------------------------------------------------------------------------

const STEPS = [
  { id: 1, label: "Welcome"         },
  { id: 2, label: "Shopify"         },
  { id: 3, label: "Ad Platforms"    },
  { id: 4, label: "You're all set!" },
] as const;

const AD_PLATFORMS = [
  { id: "meta_ads",      name: "Facebook / Meta Ads", icon: "📘", description: "Facebook & Instagram campaigns" },
  { id: "google_ads",    name: "Google Ads",           icon: "🔍", description: "Search, Shopping & Display" },
  { id: "tiktok_ads",    name: "TikTok Ads",           icon: "🎵", description: "Short-form video campaigns"  },
  { id: "snapchat_ads",  name: "Snapchat Ads",         icon: "👻", description: "Snap story & discover ads"   },
  { id: "pinterest_ads", name: "Pinterest Ads",        icon: "📌", description: "Promoted pins (coming soon)", comingSoon: true },
  { id: "twitter_ads",   name: "Twitter / X Ads",      icon: "🐦", description: "Promoted tweets (coming soon)", comingSoon: true },
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function Onboarding() {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [shopifyConnected, setShopifyConnected] = useState(false);
  const [selectedPlatforms, setSelectedPlatforms] = useState<Set<string>>(new Set());

  const finish = () => {
    localStorage.setItem("onboardingComplete", "true");
    if (shopifyConnected || selectedPlatforms.size > 0) {
      localStorage.setItem("hasConnectedSources", "true");
    }
    navigate("/");
  };

  const skip = () => {
    localStorage.setItem("onboardingComplete", "true");
    navigate("/");
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex flex-col">
      {/* Top bar */}
      <div className="flex items-center justify-between px-6 py-4">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
            <BarChart2 className="w-5 h-5 text-white" />
          </div>
          <span className="font-bold text-gray-900 text-lg">Markinsight</span>
        </div>
        <button
          onClick={skip}
          className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700 transition-colors"
        >
          <X className="w-4 h-4" />
          Skip setup
        </button>
      </div>

      {/* Progress bar */}
      <div className="px-6 mb-6">
        <div className="max-w-lg mx-auto">
          <div className="flex items-center gap-2 mb-2">
            {STEPS.map((s, i) => (
              <div key={s.id} className="flex items-center gap-2 flex-1">
                <div
                  className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 transition-colors ${
                    step > s.id
                      ? "bg-green-500 text-white"
                      : step === s.id
                      ? "bg-blue-600 text-white"
                      : "bg-gray-200 text-gray-500"
                  }`}
                >
                  {step > s.id ? <Check className="w-3 h-3" /> : s.id}
                </div>
                <span className={`text-xs hidden sm:block ${step === s.id ? "text-blue-600 font-medium" : "text-gray-400"}`}>
                  {s.label}
                </span>
                {i < STEPS.length - 1 && (
                  <div className={`flex-1 h-0.5 ${step > s.id ? "bg-green-400" : "bg-gray-200"}`} />
                )}
              </div>
            ))}
          </div>
          <p className="text-xs text-gray-400 text-center">Step {step} of {STEPS.length}</p>
        </div>
      </div>

      {/* Step content */}
      <div className="flex-1 flex items-start justify-center px-4 pb-8">
        <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg p-8">
          {step === 1 && <WelcomeStep onNext={() => setStep(2)} />}
          {step === 2 && (
            <ShopifyStep
              connected={shopifyConnected}
              onConnected={() => setShopifyConnected(true)}
              onNext={() => setStep(3)}
              onSkip={() => setStep(3)}
            />
          )}
          {step === 3 && (
            <AdPlatformsStep
              selected={selectedPlatforms}
              onToggle={id => {
                setSelectedPlatforms(prev => {
                  const next = new Set(prev);
                  next.has(id) ? next.delete(id) : next.add(id);
                  return next;
                });
              }}
              onNext={() => setStep(4)}
              onSkip={() => setStep(4)}
            />
          )}
          {step === 4 && (
            <DoneStep
              shopifyConnected={shopifyConnected}
              platformCount={selectedPlatforms.size}
              onFinish={finish}
            />
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step 1 — Welcome
// ---------------------------------------------------------------------------

function WelcomeStep({ onNext }: { onNext: () => void }) {
  return (
    <div className="text-center">
      <div className="w-16 h-16 bg-blue-100 rounded-2xl flex items-center justify-center mx-auto mb-6">
        <BarChart2 className="w-8 h-8 text-blue-600" />
      </div>
      <h1 className="text-2xl font-bold text-gray-900 mb-3">
        Welcome to Markinsight
      </h1>
      <p className="text-gray-600 mb-8">
        Your AI-powered analytics command centre. Let's connect your data
        sources so you can start tracking performance in minutes.
      </p>

      <div className="grid grid-cols-3 gap-4 mb-8">
        <FeaturePill icon="📊" label="Live KPIs" />
        <FeaturePill icon="🎯" label="Attribution" />
        <FeaturePill icon="🤖" label="AI Insights" />
      </div>

      <button
        onClick={onNext}
        className="w-full flex items-center justify-center gap-2 px-6 py-3 bg-blue-600 text-white rounded-xl hover:bg-blue-700 font-semibold transition-colors"
      >
        Get Started
        <ChevronRight className="w-5 h-5" />
      </button>
    </div>
  );
}

function FeaturePill({ icon, label }: { icon: string; label: string }) {
  return (
    <div className="bg-blue-50 rounded-xl p-3 text-center">
      <div className="text-2xl mb-1">{icon}</div>
      <p className="text-xs font-medium text-blue-800">{label}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step 2 — Connect Shopify
// ---------------------------------------------------------------------------

function ShopifyStep({
  connected,
  onConnected,
  onNext,
  onSkip,
}: {
  connected: boolean;
  onConnected: () => void;
  onNext: () => void;
  onSkip: () => void;
}) {
  const handleConnect = () => {
    // In production this would initiate Shopify OAuth.
    // For now, mark as connected immediately to unblock the wizard.
    onConnected();
  };

  return (
    <div>
      <div className="flex items-center gap-3 mb-6">
        <div className="w-12 h-12 bg-green-100 rounded-xl flex items-center justify-center">
          <Database className="w-6 h-6 text-green-600" />
        </div>
        <div>
          <h2 className="text-xl font-bold text-gray-900">Connect Shopify</h2>
          <p className="text-sm text-gray-500">Import orders, revenue, and product data</p>
        </div>
      </div>

      {connected ? (
        <div className="bg-green-50 border border-green-200 rounded-xl p-4 mb-6 flex items-center gap-3">
          <div className="w-8 h-8 bg-green-500 rounded-full flex items-center justify-center flex-shrink-0">
            <Check className="w-4 h-4 text-white" />
          </div>
          <div>
            <p className="font-medium text-green-900">Shopify connected!</p>
            <p className="text-sm text-green-700">Your store data will sync in the background.</p>
          </div>
        </div>
      ) : (
        <div className="bg-gray-50 rounded-xl p-4 mb-6">
          <div className="flex items-start gap-3">
            <span className="text-2xl">🛍️</span>
            <div>
              <p className="font-medium text-gray-900 mb-1">Your Shopify Store</p>
              <p className="text-sm text-gray-600">
                Connect your store to pull in orders, revenue, and product performance.
                We sync daily and backfill up to 90 days of history.
              </p>
            </div>
          </div>
        </div>
      )}

      <div className="space-y-3">
        {!connected ? (
          <button
            onClick={handleConnect}
            className="w-full flex items-center justify-center gap-2 px-6 py-3 bg-green-600 text-white rounded-xl hover:bg-green-700 font-semibold transition-colors"
          >
            Connect Shopify Store
            <ArrowRight className="w-5 h-5" />
          </button>
        ) : null}
        <button
          onClick={onNext}
          className="w-full flex items-center justify-center gap-2 px-6 py-3 bg-blue-600 text-white rounded-xl hover:bg-blue-700 font-semibold transition-colors"
        >
          {connected ? "Continue" : "Continue anyway"}
          <ChevronRight className="w-5 h-5" />
        </button>
        {!connected && (
          <button
            onClick={onSkip}
            className="w-full text-gray-400 hover:text-gray-600 text-sm py-2 transition-colors"
          >
            Skip for now
          </button>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step 3 — Connect Ad Platforms
// ---------------------------------------------------------------------------

function AdPlatformsStep({
  selected,
  onToggle,
  onNext,
  onSkip,
}: {
  selected: Set<string>;
  onToggle: (id: string) => void;
  onNext: () => void;
  onSkip: () => void;
}) {
  return (
    <div>
      <div className="flex items-center gap-3 mb-6">
        <div className="w-12 h-12 bg-purple-100 rounded-xl flex items-center justify-center">
          <Zap className="w-6 h-6 text-purple-600" />
        </div>
        <div>
          <h2 className="text-xl font-bold text-gray-900">Connect Ad Platforms</h2>
          <p className="text-sm text-gray-500">Select the platforms you advertise on</p>
        </div>
      </div>

      <div className="space-y-2 mb-6">
        {AD_PLATFORMS.map(platform => (
          <label
            key={platform.id}
            className={`flex items-center gap-3 p-3 rounded-xl border cursor-pointer transition-colors ${
              platform.comingSoon
                ? "opacity-50 cursor-not-allowed border-gray-100 bg-gray-50"
                : selected.has(platform.id)
                ? "border-blue-300 bg-blue-50"
                : "border-gray-200 hover:border-gray-300 hover:bg-gray-50"
            }`}
          >
            <input
              type="checkbox"
              checked={selected.has(platform.id)}
              onChange={() => !platform.comingSoon && onToggle(platform.id)}
              disabled={platform.comingSoon}
              className="sr-only"
            />
            <span className="text-xl flex-shrink-0">{platform.icon}</span>
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <p className="text-sm font-medium text-gray-900">{platform.name}</p>
                {platform.comingSoon && (
                  <span className="px-2 py-0.5 text-xs bg-gray-200 text-gray-500 rounded-full">Soon</span>
                )}
              </div>
              <p className="text-xs text-gray-500">{platform.description}</p>
            </div>
            {selected.has(platform.id) && (
              <div className="w-5 h-5 bg-blue-600 rounded-full flex items-center justify-center flex-shrink-0">
                <Check className="w-3 h-3 text-white" />
              </div>
            )}
          </label>
        ))}
      </div>

      <div className="space-y-3">
        <button
          onClick={onNext}
          className="w-full flex items-center justify-center gap-2 px-6 py-3 bg-blue-600 text-white rounded-xl hover:bg-blue-700 font-semibold transition-colors"
        >
          {selected.size > 0 ? `Connect ${selected.size} platform${selected.size > 1 ? "s" : ""}` : "Continue"}
          <ChevronRight className="w-5 h-5" />
        </button>
        <button
          onClick={onSkip}
          className="w-full text-gray-400 hover:text-gray-600 text-sm py-2 transition-colors"
        >
          Skip for now
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step 4 — Done
// ---------------------------------------------------------------------------

function DoneStep({
  shopifyConnected,
  platformCount,
  onFinish,
}: {
  shopifyConnected: boolean;
  platformCount: number;
  onFinish: () => void;
}) {
  const connectedCount = (shopifyConnected ? 1 : 0) + platformCount;

  return (
    <div className="text-center">
      <div className="w-16 h-16 bg-green-100 rounded-2xl flex items-center justify-center mx-auto mb-6">
        <Check className="w-8 h-8 text-green-600" />
      </div>
      <h1 className="text-2xl font-bold text-gray-900 mb-3">
        You're all set!
      </h1>

      {connectedCount > 0 ? (
        <p className="text-gray-600 mb-8">
          You've connected <strong>{connectedCount} data source{connectedCount > 1 ? "s" : ""}</strong>.
          Your first sync is running in the background — KPIs will appear on
          the dashboard within a few minutes.
        </p>
      ) : (
        <p className="text-gray-600 mb-8">
          Your workspace is ready. Head to <strong>Sources</strong> whenever
          you want to connect your Shopify store or ad platforms.
        </p>
      )}

      <div className="bg-blue-50 rounded-xl p-4 mb-8 text-left space-y-3">
        <CheckItem
          done={shopifyConnected}
          label="Shopify store connected"
          pendingLabel="Connect Shopify to see revenue data"
        />
        <CheckItem
          done={platformCount > 0}
          label={`${platformCount} ad platform${platformCount !== 1 ? "s" : ""} connected`}
          pendingLabel="Connect ad platforms to track spend & ROAS"
        />
      </div>

      <button
        onClick={onFinish}
        className="w-full flex items-center justify-center gap-2 px-6 py-3 bg-blue-600 text-white rounded-xl hover:bg-blue-700 font-semibold transition-colors"
      >
        Go to Dashboard
        <ArrowRight className="w-5 h-5" />
      </button>
    </div>
  );
}

function CheckItem({ done, label, pendingLabel }: { done: boolean; label: string; pendingLabel: string }) {
  return (
    <div className="flex items-center gap-3">
      <div className={`w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 ${done ? "bg-green-500" : "bg-gray-200"}`}>
        {done
          ? <Check className="w-3 h-3 text-white" />
          : <span className="w-1.5 h-1.5 bg-gray-400 rounded-full" />
        }
      </div>
      <span className={`text-sm ${done ? "text-green-700 font-medium" : "text-gray-500"}`}>
        {done ? label : pendingLabel}
      </span>
    </div>
  );
}

export default Onboarding;
