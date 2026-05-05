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
    <div className="min-h-screen flex flex-col">
      <header className="bg-slate-800 border-b border-slate-700 sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-14">
            <Link to="/" className="text-lg font-semibold text-white hover:text-slate-200 transition-colors">
              flashcards.josh.software
            </Link>

            <nav className="hidden md:flex items-center gap-1">
              {navItems.map(({ path, label }) => (
                <Link
                  key={path}
                  to={path}
                  className={`px-3 py-1.5 rounded-md text-sm transition-colors ${
                    location.pathname === path
                      ? 'bg-blue-600 text-white'
                      : 'text-slate-300 hover:bg-slate-700 hover:text-white'
                  }`}
                >
                  {label}
                </Link>
              ))}
            </nav>

            <div className="flex items-center gap-3">
              {user?.authenticated ? (
                <>
                  <span className="text-sm text-slate-300 hidden sm:inline">{user.username}</span>
                  <a
                    href="/logout"
                    className="px-3 py-1.5 rounded-md text-sm bg-slate-700 hover:bg-slate-600 text-slate-300 hover:text-white transition-colors"
                  >
                    Logout
                  </a>
                </>
              ) : (
                <a
                  href="/login"
                  className="px-4 py-1.5 rounded-md text-sm bg-blue-600 hover:bg-blue-700 text-white transition-colors"
                >
                  Login with Discord
                </a>
              )}
            </div>
          </div>
        </div>

        <nav className="md:hidden border-t border-slate-700">
          <div className="flex overflow-x-auto">
            {navItems.map(({ path, label }) => (
              <Link
                key={path}
                to={path}
                className={`flex-1 text-center px-3 py-2.5 text-xs whitespace-nowrap ${
                  location.pathname === path
                    ? 'bg-blue-600/20 text-blue-400 border-b-2 border-blue-500'
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                {label}
              </Link>
            ))}
          </div>
        </nav>
      </header>

      <main className="flex-1">{children}</main>

      <footer className="bg-slate-800 border-t border-slate-700 py-4">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <p className="text-slate-400 text-sm">
            made with love by Josh Wilcox &mdash;{' '}
            <a
              href="https://josh.software"
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-400 hover:text-blue-300 transition-colors"
            >
              See my Website
            </a>
          </p>
        </div>
      </footer>
    </div>
  );
}
