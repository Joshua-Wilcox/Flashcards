import { useState, useEffect } from 'react';
import { Heart, Star, ChevronDown, ChevronUp, X } from 'lucide-react';

const DISMISS_KEY = 'never-show-payment-widget';

interface SponsorWidgetProps {
  githubSponsorsUrl?: string;
  githubRepoUrl?: string;
}

export default function SponsorWidget({
  githubSponsorsUrl = 'https://github.com/sponsors/Joshua-Wilcox',
  githubRepoUrl = 'https://github.com/Joshua-Wilcox/Flashcards',
}: SponsorWidgetProps) {
  const [dismissed, setDismissed] = useState(true);
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    const neverShow = localStorage.getItem(DISMISS_KEY) === 'true';
    setDismissed(neverShow);
  }, []);

  if (dismissed) return null;

  const handleClose = () => setDismissed(true);

  const handleNeverShow = () => {
    localStorage.setItem(DISMISS_KEY, 'true');
    setDismissed(true);
  };

  const handleSponsor = () => {
    window.open(githubSponsorsUrl, '_blank');
  };

  const handleStar = () => {
    window.open(githubRepoUrl, '_blank');
  };

  return (
    <div className="fixed bottom-4 right-4 z-50 w-72 bg-slate-800 border border-slate-600 rounded-xl shadow-2xl overflow-hidden">
      <div
        className="flex items-center justify-between px-4 py-2.5 bg-gradient-to-r from-pink-600/20 to-purple-600/20 border-b border-slate-700 cursor-pointer"
        onClick={() => setCollapsed(!collapsed)}
      >
        <span className="text-sm font-semibold text-white flex items-center gap-2">
          <Heart className="h-4 w-4 text-pink-400" />
          Support the site
        </span>
        <div className="flex items-center gap-1">
          <button
            onClick={(e) => { e.stopPropagation(); setCollapsed(!collapsed); }}
            className="p-1 text-slate-400 hover:text-white transition-colors"
          >
            {collapsed ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); handleClose(); }}
            className="p-1 text-slate-400 hover:text-white transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      {!collapsed && (
        <div className="p-4 space-y-3">
          <div className="space-y-2">
            <button
              onClick={handleSponsor}
              className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-gradient-to-r from-pink-600 to-pink-700 hover:from-pink-500 hover:to-pink-600 text-white font-medium text-sm transition-all"
            >
              <Heart className="h-4 w-4" />
              Sponsor on GitHub
            </button>
            <button
              onClick={handleStar}
              className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-slate-700 hover:bg-slate-600 text-white font-medium text-sm transition-colors"
            >
              <Star className="h-4 w-4 text-yellow-400" />
              Star on GitHub
            </button>
          </div>

          <p className="text-xs text-slate-400 text-center leading-relaxed">
            Support would be greatly appreciated for the upkeep of the site.
            If you can't sponsor, please consider{' '}
            <a href="/submit" className="text-blue-400 hover:text-blue-300">
              submitting some flashcards!
            </a>
          </p>

          <div className="text-center">
            <button
              onClick={handleNeverShow}
              className="text-xs text-slate-500 hover:text-slate-400 transition-colors"
            >
              Do not show again
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
