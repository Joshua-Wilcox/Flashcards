import { useState, useRef, useEffect, useCallback } from 'react';
import { ChevronDown, X } from 'lucide-react';

interface Suggestion {
  name: string;
  count: number;
}

interface MultiSelectFieldProps {
  values: string[];
  onChange: (values: string[]) => void;
  onFetch: (query: string) => Promise<Suggestion[]>;
  placeholder?: string;
  disabled?: boolean;
  label?: string;
}

export default function MultiSelectField({
  values,
  onChange,
  onFetch,
  placeholder = 'Select or type to add...',
  disabled = false,
  label: _label,
}: MultiSelectFieldProps) {
  const [inputValue, setInputValue] = useState('');
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [isFetching, setIsFetching] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchSuggestions = useCallback(
    async (q: string) => {
      setIsFetching(true);
      try {
        const results = await onFetch(q);
        setSuggestions((results ?? []).filter((s) => !values.includes(s.name)));
        setIsOpen(true);
      } catch {
        setSuggestions([]);
      } finally {
        setIsFetching(false);
      }
    },
    [onFetch, values]
  );

  const handleInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const q = e.target.value;
    setInputValue(q);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => fetchSuggestions(q), 200);
  };

  const addValue = (value: string) => {
    const trimmed = value.trim();
    if (trimmed && !values.includes(trimmed)) {
      onChange([...values, trimmed]);
    }
    setInputValue('');
    setSuggestions([]);
  };

  const removeValue = (value: string) => {
    onChange(values.filter((v) => v !== value));
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      if (inputValue.trim()) addValue(inputValue);
    } else if (e.key === 'Backspace' && !inputValue && values.length > 0) {
      removeValue(values[values.length - 1]);
    }
  };

  const handleFocus = () => {
    if (!disabled) fetchSuggestions(inputValue);
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

  const showDropdown = isOpen && !disabled && (suggestions.length > 0 || inputValue.trim().length > 0);

  return (
    <div ref={containerRef} className="relative">
      <div
        className={`min-h-[42px] px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg flex flex-wrap gap-2 items-center cursor-text ${
          disabled ? 'opacity-50 cursor-not-allowed' : 'focus-within:border-blue-500'
        }`}
        onClick={() => !disabled && inputRef.current?.focus()}
      >
        {values.map((value) => (
          <span
            key={value}
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-blue-600/30 text-blue-300 text-sm"
          >
            {value}
            {!disabled && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  removeValue(value);
                }}
                className="text-blue-400 hover:text-white transition-colors"
              >
                <X className="h-3 w-3" />
              </button>
            )}
          </span>
        ))}
        <input
          ref={inputRef}
          type="text"
          value={inputValue}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          onFocus={handleFocus}
          placeholder={values.length === 0 ? (disabled ? 'Select module first' : placeholder) : ''}
          disabled={disabled}
          className="flex-1 min-w-[120px] bg-transparent border-none outline-none text-white placeholder-slate-500 text-sm"
        />
        {isFetching ? (
          <div className="h-4 w-4 rounded-full border-2 border-blue-500 border-t-transparent animate-spin" />
        ) : (
          <ChevronDown
            className={`h-4 w-4 text-slate-400 transition-transform ${isOpen ? 'rotate-180' : ''}`}
          />
        )}
      </div>

      {showDropdown && (
        <div className="absolute z-50 mt-1 w-full max-h-56 overflow-y-auto rounded-lg bg-slate-800 border border-slate-700 shadow-xl">
          {inputValue.trim() && !values.includes(inputValue.trim()) && (
            <button
              type="button"
              onMouseDown={(e) => {
                e.preventDefault();
                addValue(inputValue);
              }}
              className="w-full px-4 py-2.5 text-left text-sm text-blue-400 bg-blue-900/20 hover:bg-blue-900/40 transition-colors"
            >
              + Create &ldquo;{inputValue.trim()}&rdquo;
            </button>
          )}
          {suggestions.map((s) => (
            <button
              key={s.name}
              type="button"
              onMouseDown={(e) => {
                e.preventDefault();
                addValue(s.name);
              }}
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
