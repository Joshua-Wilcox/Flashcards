import { Link, useLocation } from 'react-router-dom';
import type { User as UserType } from '../types';

interface LayoutProps {
  children: React.ReactNode;
  user?: UserType;
}

export default function Layout({ children, user }: LayoutProps) {
  const location = useLocation();

  const navItems = [
    { path: '/', label: 'Home' },
    { path: '/leaderboard', label: 'Leaderboard' },
    ...(user?.authenticated
      ? [
          { path: '/stats', label: 'My Stats' },
          { path: '/submit', label: 'Submit Flashcards' },
        ]
      : []),
    ...(user?.is_whitelisted || user?.is_admin
      ? [{ path: '/pdfs', label: 'PDFs' }]
      : []),
    ...(user?.is_admin ? [
      { path: '/admin', label: 'Admin Dashboard' },
    ] : []),
  ];

  return (
    <div className="h-screen flex flex-col bg-gray-50 overflow-hidden">
      <header className="bg-white sticky top-0 z-40 shadow-sm">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <Link
              to="/"
              onClick={() => window.dispatchEvent(new CustomEvent('reset-quiz'))}
              className="flex items-center gap-2.5 font-bold text-gray-900 hover:text-blue-600 transition-colors"
            >
              <img src="/favicon.png" alt="" className="h-7 w-7" />
              <span className="text-base">flashcards.josh.software</span>
            </Link>

            <nav className="hidden md:flex items-center gap-1">
              {navItems.map(({ path, label }) => (
                <Link
                  key={path}
                  to={path}
                  className={`px-3.5 py-2 rounded-lg text-sm font-medium transition-colors ${
                    location.pathname === path
                      ? 'bg-blue-600 text-white'
                      : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                  }`}
                >
                  {label}
                </Link>
              ))}
            </nav>

            <div className="flex items-center gap-3">
              {user?.authenticated ? (
                <>
                  <span className="text-sm font-medium text-gray-600 hidden sm:inline">{user.username}</span>
                  <a
                    href="/logout"
                    className="px-3.5 py-2 rounded-lg text-sm font-medium bg-gray-100 hover:bg-gray-200 text-gray-700 transition-colors"
                  >
                    Logout
                  </a>
                </>
              ) : (
                <a
                  href="/login"
                  className="px-4 py-2 rounded-lg text-sm font-semibold bg-blue-600 hover:bg-blue-700 text-white transition-colors shadow-sm"
                >
                  Login with Discord
                </a>
              )}
            </div>
          </div>
        </div>

        <nav className="md:hidden border-t border-gray-100">
          <div className="flex overflow-x-auto">
            {navItems.map(({ path, label }) => (
              <Link
                key={path}
                to={path}
                className={`flex-1 text-center px-3 py-3 text-xs font-medium whitespace-nowrap ${
                  location.pathname === path
                    ? 'text-blue-600 border-b-2 border-blue-600 bg-blue-50'
                    : 'text-gray-500 hover:text-gray-900'
                }`}
              >
                {label}
              </Link>
            ))}
          </div>
        </nav>
      </header>

      <main className="flex-1 min-h-0 overflow-y-auto">{children}</main>

      <footer className="bg-white border-t border-gray-100 py-4 flex-shrink-0">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <p className="text-gray-500 text-sm">
            made with love by Josh Wilcox &mdash;{' '}
            <a
              href="https://josh.software"
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-600 hover:text-blue-700 font-medium transition-colors"
            >
              See my Website
            </a>
          </p>
        </div>
      </footer>
    </div>
  );
}
