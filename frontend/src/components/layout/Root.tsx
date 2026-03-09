import { Outlet, Link, useLocation, useNavigate } from 'react-router-dom';
import {
  Home,
  TrendingUp,
  ShoppingBag,
  Sparkles,
  Bell,
  Gauge,
  Users,
  FileBarChart,
  RefreshCw,
  Settings,
  LogOut,
  User,
  Menu,
  X,
} from 'lucide-react';
import { useUser, useClerk } from '@clerk/clerk-react';
import { useEffect, useState } from 'react';
import { MarkinsightIcon } from '../MarkinsightIcon';

const CHANNEL_EMOJI: Record<string, string> = {
  google: '🔵',
  facebook: '🔷',
  instagram: '📸',
  tiktok: '🎵',
  pinterest: '📌',
  twitter: '🐦',
  organic: '🌱',
};

const channels = [
  { key: 'google', name: 'Google Ads' },
  { key: 'facebook', name: 'Facebook Ads' },
  { key: 'instagram', name: 'Instagram Ads' },
  { key: 'tiktok', name: 'TikTok Ads' },
  { key: 'pinterest', name: 'Pinterest Ads' },
  { key: 'twitter', name: 'Twitter Ads' },
  { key: 'organic', name: 'Organic' },
];

function SectionLabel({ label }: { label: string }) {
  return (
    <div className="pt-5 pb-1.5 px-4">
      <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">{label}</p>
    </div>
  );
}

function NavLink({
  to,
  icon: Icon,
  emoji,
  label,
  isActivePrefix,
}: {
  to: string;
  icon?: React.ComponentType<{ className?: string }>;
  emoji?: string;
  label: string;
  isActivePrefix?: boolean;
}) {
  const location = useLocation();
  const active = isActivePrefix
    ? location.pathname.startsWith(to)
    : location.pathname === to;

  return (
    <Link
      to={to}
      className={`flex items-center gap-3 px-4 py-2.5 rounded-lg transition-colors ${
        active ? 'bg-blue-50 text-blue-600' : 'text-gray-700 hover:bg-gray-50'
      }`}
    >
      {emoji ? (
        <span className="text-base w-5 text-center">{emoji}</span>
      ) : Icon ? (
        <Icon className="w-5 h-5 flex-shrink-0" />
      ) : null}
      <span className="font-medium text-sm">{label}</span>
    </Link>
  );
}

export function Root() {
  const location = useLocation();
  const navigate = useNavigate();
  const { user } = useUser();
  const { signOut } = useClerk();
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);
  const [showWelcomeBanner, setShowWelcomeBanner] = useState(false);

  const isOnboarding =
    location.pathname === '/onboarding' || location.pathname === '/signup';

  useEffect(() => {
    const justCompletedOnboarding =
      localStorage.getItem('onboardingComplete') === 'true';
    const hasSeenWelcome = sessionStorage.getItem('hasSeenWelcome') === 'true';

    if (justCompletedOnboarding && !hasSeenWelcome && location.pathname === '/') {
      setShowWelcomeBanner(true);
      sessionStorage.setItem('hasSeenWelcome', 'true');
      setTimeout(() => setShowWelcomeBanner(false), 5000);
    }
  }, [location]);

  useEffect(() => {
    setIsMobileSidebarOpen(false);
  }, [location.pathname]);

  if (isOnboarding) {
    return <Outlet />;
  }

  const displayName = user?.fullName || user?.firstName || 'User';
  const email = user?.primaryEmailAddress?.emailAddress || '';

  const handleLogout = async () => {
    await signOut();
    navigate('/');
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Mobile Header */}
      <div className="lg:hidden fixed top-0 left-0 right-0 bg-white border-b border-gray-200 px-4 py-3 flex items-center justify-between z-40">
        <div className="flex items-center gap-2">
          <MarkinsightIcon className="w-6 h-6 text-blue-600" />
          <h1 className="text-lg font-semibold text-gray-900">Markinsight</h1>
        </div>
        <button
          onClick={() => setIsMobileSidebarOpen(!isMobileSidebarOpen)}
          className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
        >
          {isMobileSidebarOpen ? (
            <X className="w-6 h-6 text-gray-700" />
          ) : (
            <Menu className="w-6 h-6 text-gray-700" />
          )}
        </button>
      </div>

      {/* Mobile overlay */}
      {isMobileSidebarOpen && (
        <div
          className="lg:hidden fixed inset-0 bg-black bg-opacity-50 z-40"
          onClick={() => setIsMobileSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed left-0 top-0 h-full w-64 bg-white border-r border-gray-200 flex flex-col z-50 transition-transform duration-300 lg:translate-x-0 ${
          isMobileSidebarOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        {/* Logo */}
        <div className="p-5 border-b border-gray-200">
          <div className="flex items-center gap-2">
            <MarkinsightIcon className="w-8 h-8 text-blue-600" />
            <h1 className="text-xl font-semibold text-gray-900">Markinsight</h1>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-3 overflow-y-auto">
          {/* Core */}
          <NavLink to="/" icon={Home} label="Overview" />
          <NavLink to="/attribution" icon={TrendingUp} label="Attribution" />
          <NavLink to="/orders" icon={ShoppingBag} label="Orders" />

          {/* Intelligence */}
          <SectionLabel label="Intelligence" />
          <NavLink to="/ai-consultant" icon={Sparkles} label="AI Consultant" />
          <NavLink to="/alerts" icon={Bell} label="Automated Alerts" />
          <NavLink to="/budget-pacing" icon={Gauge} label="Budget Pacing" />
          <NavLink to="/cohorts" icon={Users} label="Cohort Analysis" />
          <NavLink to="/reports" icon={FileBarChart} label="Report Builder" />

          {/* Channels */}
          <SectionLabel label="Channels" />
          {channels.map((ch) => (
            <NavLink
              key={ch.key}
              to={`/channel/${ch.key}`}
              emoji={CHANNEL_EMOJI[ch.key]}
              label={ch.name}
              isActivePrefix
            />
          ))}

          {/* System */}
          <SectionLabel label="System" />
          <NavLink to="/sync" icon={RefreshCw} label="Sync Status" />
          <NavLink to="/settings" icon={Settings} label="Settings" />
        </nav>

        {/* User footer */}
        <div className="p-4 border-t border-gray-200">
          <div className="mb-3 p-3 bg-gray-50 rounded-lg">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 bg-blue-600 rounded-full flex items-center justify-center flex-shrink-0 overflow-hidden">
                {user?.imageUrl ? (
                  <img
                    src={user.imageUrl}
                    alt={displayName}
                    className="w-8 h-8 rounded-full object-cover"
                  />
                ) : (
                  <User className="w-4 h-4 text-white" />
                )}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-900 truncate">{displayName}</p>
                <p className="text-xs text-gray-500 truncate">{email}</p>
              </div>
            </div>
          </div>
          <button
            onClick={handleLogout}
            className="w-full flex items-center gap-2 px-4 py-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors"
          >
            <LogOut className="w-4 h-4" />
            <span className="text-sm font-medium">Logout</span>
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="lg:ml-64 pt-16 lg:pt-0">
        {showWelcomeBanner && (
          <div className="bg-gradient-to-r from-blue-600 to-purple-600 text-white px-6 py-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="text-2xl">🎉</span>
                <div>
                  <p className="font-semibold">Welcome to Markinsight!</p>
                  <p className="text-sm text-blue-100">Your account is all set up and ready to go.</p>
                </div>
              </div>
              <button
                onClick={() => setShowWelcomeBanner(false)}
                className="px-4 py-2 bg-white/20 hover:bg-white/30 rounded-lg text-sm font-medium"
              >
                Dismiss
              </button>
            </div>
          </div>
        )}
        <Outlet />
      </main>
    </div>
  );
}
