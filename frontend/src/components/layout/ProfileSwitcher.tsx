import { useState, useCallback } from 'react';
import { Settings, LogOut, ChevronDown } from 'lucide-react';
import { useUser, useClerk } from '@clerk/clerk-react';
import { useNavigate } from 'react-router-dom';

export function ProfileSwitcher() {
  const [isOpen, setIsOpen] = useState(false);
  const { user } = useUser();
  const { signOut } = useClerk();
  const navigate = useNavigate();

  const displayName = user?.fullName || user?.firstName || 'User';
  const email = user?.primaryEmailAddress?.emailAddress || '';
  const initial = displayName.charAt(0).toUpperCase();

  const handleSignOut = useCallback(async () => {
    setIsOpen(false);
    await signOut();
  }, [signOut]);

  const handleSettings = useCallback(() => {
    setIsOpen(false);
    navigate('/settings');
  }, [navigate]);

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-3 py-2 hover:bg-gray-100 rounded-lg transition-colors"
      >
        <div className="w-8 h-8 bg-blue-600 rounded-full flex items-center justify-center text-white font-semibold text-sm">
          {initial}
        </div>
        <span className="text-sm font-medium text-gray-900 hidden sm:inline">{displayName}</span>
        <ChevronDown className="w-4 h-4 text-gray-500 hidden sm:block" />
      </button>

      {isOpen && (
        <>
          <div
            className="fixed inset-0 z-10"
            onClick={() => setIsOpen(false)}
          />
          <div className="absolute right-0 mt-2 w-64 bg-white rounded-lg shadow-lg border border-gray-200 z-20">
            <div className="p-3 border-b border-gray-200">
              <p className="font-semibold text-gray-900 text-sm">{displayName}</p>
              {email && <p className="text-xs text-gray-500 mt-0.5">{email}</p>}
            </div>
            <div className="p-1">
              <button
                onClick={handleSettings}
                className="w-full flex items-center gap-3 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 rounded-lg transition-colors"
              >
                <Settings className="w-4 h-4" />
                Settings
              </button>
              <button
                onClick={handleSignOut}
                className="w-full flex items-center gap-3 px-3 py-2 text-sm text-red-600 hover:bg-red-50 rounded-lg transition-colors"
              >
                <LogOut className="w-4 h-4" />
                Sign out
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
