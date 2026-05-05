import { useState, useRef, useEffect, useCallback } from 'react';
import { X, Plus } from 'lucide-react';

interface Suggestion {
  name: string;
  count: number;
}

interface TagInputProps {
  tags: string[];
  onChange: (tags: string[]) => void;
  onFetch?: (query: string) => Promise<Suggestion[]>;
  minCount?: number;
  disabled?: boolean;
}

export default function TagInput({
  tags,
  onChange,
  onFetch,
  minCount = 3,
  disabled = false,
}: TagInputProps) {
  const [inputValue, setInputValue] = useState('');
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchSuggestions = useCallback(
    async (q: string) => {
      if (!onFetch) return;
      try {
        const results = await onFetch(q);
        setSuggestions((results ?? []).filter((s) => !tags.includes(s.name)));
        setIsOpen(true);
      } catch {
        setSuggestions([]);
      }
    },
    [onFetch, tags]
  );

  const handleInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const q = e.target.value;
    setInputValue(q);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => fetchSuggestions(q), 200);
  };

  const addTag = (value: string) => {
    const trimmed = value.trim();
    if (trimmed && !tags.includes(trimmed)) {
      onChange([...tags, trimmed]);
    }
    setInputValue('');
    setSuggestions([]);
    setIsOpen(false);
  };

  const removeTag = (tag: string) => {
    onChange(tags.filter((t) => t !== tag));
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      if (inputValue.trim()) addTag(inputValue);
    }
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

  const belowMin = tags.length < minCount;

  return (
    <div ref={containerRef}>
      {tags.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-2">
          {tags.map((tag) => (
            <span
              key={tag}
              className="inline-flex items-center gap-1 px-3 py-1 rounded-full bg-blue-900/40 text-blue-300 text-sm"
            >
              {tag}
              {!disabled && (
                <button
                  type="button"
                  onClick={() => removeTag(tag)}
                  className="ml-1 text-blue-400 hover:text-white transition-colors"
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </span>
          ))}
        </div>
      )}

      {!disabled && (
        <div className="relative flex gap-2">
          <input
            type="text"
            value={inputValue}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
            onFocus={() => fetchSuggestions(inputValue)}
            placeholder="Enter a tag..."
            maxLength={32}
            className="input flex-1"
          />
          <button
            type="button"
            onClick={() => { if (inputValue.trim()) addTag(inputValue); }}
            className="px-3 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm flex items-center gap-1 transition-colors"
          >
            <Plus className="h-4 w-4" />
            Add Tag
          </button>

          {isOpen && suggestions.length > 0 && (
            <div className="absolute top-full left-0 right-0 z-50 mt-1 max-h-48 overflow-y-auto rounded-lg bg-slate-800 border border-slate-700 shadow-xl">
              {inputValue.trim() && !tags.includes(inputValue.trim()) && (
                <button
                  type="button"
                  onMouseDown={(e) => { e.preventDefault(); addTag(inputValue); }}
                  className="w-full px-4 py-2.5 text-left text-sm text-blue-400 bg-blue-900/20 hover:bg-blue-900/40 transition-colors"
                >
                  + Create &ldquo;{inputValue.trim()}&rdquo;
                </button>
              )}
              {suggestions.map((s) => (
                <button
                  key={s.name}
                  type="button"
                  onMouseDown={(e) => { e.preventDefault(); addTag(s.name); }}
                  className="w-full flex items-center justify-between px-4 py-2.5 text-left text-sm text-slate-200 hover:bg-slate-700 transition-colors"
                >
                  <span>{s.name}</span>
                  <span className="text-xs text-slate-500">{s.count} questions</span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {belowMin && !disabled && (
        <p className="mt-1.5 text-xs text-red-400">
          Please add at least {minCount} tags ({minCount - tags.length} more needed)
        </p>
      )}
    </div>
  );
}
