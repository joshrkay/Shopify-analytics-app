import { Outlet, Link, useLocation } from "react-router-dom";
import { Menu, Home, Database, Bell, LayoutDashboard, X } from "lucide-react";
import { ProfileSwitcher } from "./ProfileSwitcher";
import { useEffect, useState } from "react";

export function Root() {
  const location = useLocation();
  const isOnboarding = location.pathname === "/onboarding" || location.pathname === "/signup";
  const [showWelcomeBanner, setShowWelcomeBanner] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);

  useEffect(() => {
    // Check if user just completed onboarding
    const justCompletedOnboarding = localStorage.getItem("onboardingComplete") === "true";
    const hasSeenWelcome = sessionStorage.getItem("hasSeenWelcome") === "true";

    if (justCompletedOnboarding && !hasSeenWelcome && location.pathname === "/") {
      setShowWelcomeBanner(true);
      sessionStorage.setItem("hasSeenWelcome", "true");

      // Auto-hide after 5 seconds
      setTimeout(() => {
        setShowWelcomeBanner(false);
      }, 5000);
    }
  }, [location]);

  // Close mobile sidebar on route change
  useEffect(() => {
    setIsMobileSidebarOpen(false);
  }, [location.pathname]);

  if (isOnboarding) {
    return <Outlet />;
  }

  return (
    <div className="min-h-screen bg-gray-50 flex">
      {/* Mobile sidebar overlay */}
      {isMobileSidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={() => setIsMobileSidebarOpen(false)}
        />
      )}

      {/* Left Sidebar */}
      <aside className={`bg-white border-r border-gray-200 flex flex-col transition-all duration-300
        fixed inset-y-0 left-0 z-50 lg:static
        ${isMobileSidebarOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"}
        ${isSidebarCollapsed ? "w-20" : "w-64"}
      `}>
        {/* Logo & Toggle */}
        <div className="p-4 border-b border-gray-200 flex items-center justify-between">
          {!isSidebarCollapsed && (
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 bg-gradient-to-br from-blue-600 to-purple-600 rounded-lg" />
              <span className="font-semibold text-gray-900">Your Analytics</span>
            </div>
          )}
          {isSidebarCollapsed && (
            <div className="w-8 h-8 bg-gradient-to-br from-blue-600 to-purple-600 rounded-lg mx-auto" />
          )}
          {/* Close button for mobile */}
          <button
            onClick={() => setIsMobileSidebarOpen(false)}
            className="lg:hidden p-1 hover:bg-gray-100 rounded-lg"
          >
            <X className="w-5 h-5 text-gray-600" />
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-4 space-y-2">
          <NavLink to="/" icon={Home} collapsed={isSidebarCollapsed}>Home</NavLink>
          <NavLink to="/builder" icon={LayoutDashboard} collapsed={isSidebarCollapsed}>Builder</NavLink>
          <NavLink to="/sources" icon={Database} collapsed={isSidebarCollapsed}>Sources</NavLink>
        </nav>

        {/* Collapse Toggle */}
        <div className="p-4 border-t border-gray-200">
          <button
            onClick={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
            className="w-full flex items-center justify-center gap-2 px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg transition-colors hidden lg:flex"
          >
            <Menu className="w-5 h-5" />
            {!isSidebarCollapsed && <span className="text-sm">Collapse</span>}
          </button>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top Header */}
        <header className="bg-white border-b border-gray-200 sticky top-0 z-30">
          <div className="flex items-center justify-between px-4 sm:px-6 py-4">
            <div className="flex items-center gap-3">
              {/* Mobile hamburger */}
              <button
                onClick={() => setIsMobileSidebarOpen(true)}
                className="lg:hidden p-2 hover:bg-gray-100 rounded-lg -ml-2"
              >
                <Menu className="w-5 h-5 text-gray-600" />
              </button>
              <h1 className="text-lg sm:text-xl font-semibold text-gray-900">
                {location.pathname === "/" && "Dashboard"}
                {location.pathname === "/builder" && "Dashboard Builder"}
                {location.pathname === "/sources" && "Data Sources"}
                {location.pathname === "/settings" && "Settings"}
              </h1>
            </div>
            <div className="flex items-center gap-3">
              <button className="p-2 hover:bg-gray-100 rounded-lg relative">
                <Bell className="w-5 h-5 text-gray-600" />
                <span className="absolute top-1 right-1 w-2 h-2 bg-red-500 rounded-full" />
              </button>
              <ProfileSwitcher />
            </div>
          </div>
        </header>

        {showWelcomeBanner && (
          <div className="bg-gradient-to-r from-blue-600 to-purple-600 text-white px-6 py-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="text-2xl">🎉</span>
                <div>
                  <p className="font-semibold">Welcome to Your Analytics!</p>
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

        <main className="flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

function NavLink({ to, icon: Icon, children, collapsed }: { to: string; icon: any; children: React.ReactNode; collapsed: boolean }) {
  const location = useLocation();
  const isActive = location.pathname === to;

  return (
    <Link
      to={to}
      className={`flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
        isActive
          ? "bg-blue-50 text-blue-600"
          : "text-gray-600 hover:bg-gray-100"
      } ${collapsed ? "justify-center" : ""}`}
      title={collapsed ? children?.toString() : undefined}
    >
      <Icon className="w-5 h-5 flex-shrink-0" />
      {!collapsed && <span className="font-medium">{children}</span>}
    </Link>
  );
}
