import { useState, useRef, useEffect } from 'react';
import { ChevronDown, X, Filter } from 'lucide-react';
import type { FilterData } from '../types';

function FilterDropdown({
  label,
  items,
  selected,
  onChange,
  isOpen,
  onToggle,
  onClose,
}: {
  label: string;
  items: string[];
  selected: string[];
  onChange: (items: string[]) => void;
  isOpen: boolean;
  onToggle: () => void;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    const handleClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        onClose();
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [isOpen, onClose]);

  const toggleItem = (item: string) => {
    if (selected.includes(item)) {
      onChange(selected.filter((i) => i !== item));
    } else {
      onChange([...selected, item]);
    }
  };

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={onToggle}
        disabled={items.length === 0}
        className={`flex items-center gap-2 px-3 py-2 rounded-lg border transition-colors ${
          selected.length > 0
            ? 'bg-blue-600/20 border-blue-500 text-blue-400'
            : 'bg-slate-800 border-slate-600 text-slate-300 hover:border-slate-500'
        } ${items.length === 0 ? 'opacity-50 cursor-not-allowed' : ''}`}
      >
        <span className="text-sm">
          {label}
          {selected.length > 0 && (
            <span className="ml-1 px-1.5 py-0.5 bg-blue-600 text-white text-xs rounded-full">
              {selected.length}
            </span>
          )}
        </span>
        <ChevronDown
          className={`h-4 w-4 transition-transform ${isOpen ? 'rotate-180' : ''}`}
        />
      </button>

      {isOpen && items.length > 0 && (
        <div className="absolute z-50 mt-2 w-64 max-h-64 overflow-y-auto rounded-lg bg-slate-800 border border-slate-700 shadow-xl">
          {items.map((item) => (
            <button
              key={item}
              onClick={() => toggleItem(item)}
              className={`w-full flex items-center gap-2 px-4 py-2 text-left text-sm hover:bg-slate-700 transition-colors ${
                selected.includes(item)
                  ? 'bg-blue-600/20 text-blue-400'
                  : 'text-slate-300'
              }`}
            >
              <div
                className={`w-4 h-4 rounded border flex items-center justify-center ${
                  selected.includes(item)
                    ? 'bg-blue-600 border-blue-600'
                    : 'border-slate-500'
                }`}
              >
                {selected.includes(item) && (
                  <svg
                    className="w-3 h-3 text-white"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={3}
                      d="M5 13l4 4L19 7"
                    />
                  </svg>
                )}
              </div>
              <span className="truncate">{item}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

interface FilterBarProps {
  filters: FilterData;
  selectedTopics: string[];
  selectedSubtopics: string[];
  onTopicsChange: (topics: string[]) => void;
  onSubtopicsChange: (subtopics: string[]) => void;
  isLoading?: boolean;
}

export default function FilterBar({
  filters,
  selectedTopics,
  selectedSubtopics,
  onTopicsChange,
  onSubtopicsChange,
  isLoading,
}: FilterBarProps) {
  const [openDropdown, setOpenDropdown] = useState<string | null>(null);

  const hasActiveFilters =
    selectedTopics.length > 0 ||
    selectedSubtopics.length > 0;

  const clearAllFilters = () => {
    onTopicsChange([]);
    onSubtopicsChange([]);
  };

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 animate-pulse">
        <div className="h-10 w-24 bg-slate-700 rounded-lg" />
        <div className="h-10 w-24 bg-slate-700 rounded-lg" />
      </div>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Filter className="h-4 w-4 text-slate-400" />

      <FilterDropdown
        label="Topics"
        items={filters.topics}
        selected={selectedTopics}
        onChange={onTopicsChange}
        isOpen={openDropdown === 'topics'}
        onToggle={() => setOpenDropdown(openDropdown === 'topics' ? null : 'topics')}
        onClose={() => setOpenDropdown(null)}
      />

      <FilterDropdown
        label="Subtopics"
        items={filters.subtopics}
        selected={selectedSubtopics}
        onChange={onSubtopicsChange}
        isOpen={openDropdown === 'subtopics'}
        onToggle={() => setOpenDropdown(openDropdown === 'subtopics' ? null : 'subtopics')}
        onClose={() => setOpenDropdown(null)}
      />

      {hasActiveFilters && (
        <button
          onClick={clearAllFilters}
          className="flex items-center gap-1 px-3 py-2 text-sm text-slate-400 hover:text-white transition-colors"
        >
          <X className="h-4 w-4" />
          Clear all
        </button>
      )}
    </div>
  );
}
