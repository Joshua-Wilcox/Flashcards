import { useState, useRef, useEffect, useCallback } from 'react';
import { ChevronDown } from 'lucide-react';

interface Suggestion {
  name: string;
  count: number;
}

interface SuggestFieldProps {
  value: string;
  onChange: (value: string) => void;
  onFetch: (query: string) => Promise<Suggestion[]>;
  placeholder?: string;
  disabled?: boolean;
  required?: boolean;
  id?: string;
}

export default function SuggestField({
  value,
  onChange,
  onFetch,
  placeholder = 'Type to search or create...',
  disabled = false,
  required = false,
  id,
}: SuggestFieldProps) {
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [isFetching, setIsFetching] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const fetchSuggestions = useCallback(
    async (q: string) => {
      setIsFetching(true);
      try {
        const results = await onFetch(q);
        setSuggestions(results ?? []);
        setIsOpen(true);
      } catch {
        setSuggestions([]);
      } finally {
        setIsFetching(false);
      }
    },
    [onFetch]
  );

  const handleInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const q = e.target.value;
    onChange(q);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => fetchSuggestions(q), 200);
  };

  const handleFocus = () => {
    if (!disabled) fetchSuggestions(value);
  };

  const handleSelect = (name: string) => {
    onChange(name);
    setIsOpen(false);
    setSuggestions([]);
  };

  useEffect(() => {
    if (!isOpen) return;
    const handleClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [isOpen]);

  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  const showDropdown = isOpen && !disabled && (suggestions.length > 0 || value.trim().length > 0);

  return (
    <div className="relative" ref={containerRef}>
      <div className="relative">
        <input
          id={id}
          type="text"
          value={value}
          onChange={handleInput}
          onFocus={handleFocus}
          placeholder={disabled ? 'Complete previous fields first' : placeholder}
          disabled={disabled}
          required={required}
          className={`input w-full pr-8 ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
        />
        {isFetching && (
          <div className="absolute right-3 top-1/2 -translate-y-1/2">
            <div className="h-4 w-4 rounded-full border-2 border-blue-500 border-t-transparent animate-spin" />
          </div>
        )}
        {!isFetching && !disabled && (
          <ChevronDown
            className={`absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400 transition-transform ${isOpen ? 'rotate-180' : ''}`}
          />
        )}
      </div>

      {showDropdown && (
        <div className="absolute z-50 mt-1 w-full max-h-56 overflow-y-auto rounded-lg bg-slate-800 border border-slate-700 shadow-xl">
          {value.trim() && (
            <button
              type="button"
              onMouseDown={(e) => { e.preventDefault(); handleSelect(value.trim()); }}
              className="w-full px-4 py-2.5 text-left text-sm text-blue-400 bg-blue-900/20 hover:bg-blue-900/40 transition-colors"
            >
              + Create &ldquo;{value.trim()}&rdquo;
            </button>
          )}
          {suggestions
            .filter((s) => s.name.toLowerCase() !== value.trim().toLowerCase())
            .map((s) => (
              <button
                key={s.name}
                type="button"
                onMouseDown={(e) => { e.preventDefault(); handleSelect(s.name); }}
                className="w-full flex items-center justify-between px-4 py-2.5 text-left text-sm text-slate-200 hover:bg-slate-700 transition-colors"
              >
                <span>{s.name}</span>
                <span className="text-xs text-slate-500">{s.count} questions</span>
              </button>
            ))}
        </div>
      )}
    </div>
  );
}
