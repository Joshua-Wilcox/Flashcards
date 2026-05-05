import { useState, useRef, useEffect, useCallback } from 'react';
import { ChevronDown } from 'lucide-react';
import type { Module, ModuleGroup } from '../types';

interface ModuleSelectorProps {
  modules: Module[];
  moduleGroups: ModuleGroup[];
  selectedModule: string;
  onSelect: (moduleName: string) => void;
  disabled?: boolean;
}

export default function ModuleSelector({
  modules,
  moduleGroups,
  selectedModule,
  onSelect,
  disabled,
}: ModuleSelectorProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [activeYear, setActiveYear] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    const handleClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [isOpen]);

  const handleOpen = useCallback(() => {
    if (disabled) return;
    if (!isOpen) {
      // When opening, jump to the year containing the selected module
      if (selectedModule) {
        const group = moduleGroups.find((g) =>
          g.modules.some((m) => m.name === selectedModule)
        );
        setActiveYear(group?.year ?? null);
      } else {
        setActiveYear(null);
      }
    }
    setIsOpen(!isOpen);
  }, [disabled, isOpen, selectedModule, moduleGroups]);

  const handleSelectModule = (moduleName: string) => {
    onSelect(moduleName);
    setIsOpen(false);
  };

  const handleBack = () => {
    setActiveYear(null);
  };

  const handleClear = () => {
    onSelect('');
    setActiveYear(null);
    setIsOpen(false);
  };

  const activeGroup = activeYear
    ? moduleGroups.find((g) => g.year === activeYear)
    : null;

  const buttonLabel = selectedModule || 'Select Module';

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={handleOpen}
        disabled={disabled}
        className={`w-full flex items-center justify-between px-4 py-3 bg-slate-800 border border-slate-600 rounded-lg hover:border-slate-500 transition-colors ${
          disabled ? 'opacity-50 cursor-not-allowed' : ''
        }`}
      >
        <span className={selectedModule ? 'text-white' : 'text-slate-400'}>
          {buttonLabel}
        </span>
        <ChevronDown
          className={`h-5 w-5 text-slate-400 transition-transform ${isOpen ? 'rotate-180' : ''}`}
        />
      </button>

      {isOpen && (
        <div className="absolute z-50 mt-1 w-full max-h-80 overflow-y-auto rounded-lg bg-slate-800 border border-slate-700 shadow-xl">
          {!activeYear ? (
            <>
              {selectedModule && (
                <>
                  <button
                    onClick={handleClear}
                    className="w-full px-4 py-2.5 text-left text-sm text-slate-400 hover:bg-slate-700 hover:text-white transition-colors"
                  >
                    Clear selection
                  </button>
                  <div className="border-t border-slate-700" />
                </>
              )}

              {moduleGroups.length > 0 ? (
                moduleGroups.map((group) => (
                  <button
                    key={group.year}
                    onClick={() => setActiveYear(group.year)}
                    className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-slate-700 transition-colors"
                  >
                    <span className="text-sm font-medium text-slate-200">{group.year}</span>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-slate-500">
                        {group.modules.length} module{group.modules.length !== 1 ? 's' : ''}
                      </span>
                      <span className="text-slate-500 text-sm">›</span>
                    </div>
                  </button>
                ))
              ) : (
                modules.map((module) => (
                  <button
                    key={module.id}
                    onClick={() => handleSelectModule(module.name)}
                    className={`w-full px-4 py-3 text-left text-sm hover:bg-slate-700 transition-colors ${
                      selectedModule === module.name
                        ? 'bg-blue-600/20 text-blue-400'
                        : 'text-slate-200'
                    }`}
                  >
                    {module.name}
                  </button>
                ))
              )}
            </>
          ) : (
            <>
              <button
                onClick={handleBack}
                className="w-full px-4 py-2.5 text-left text-sm text-slate-400 hover:bg-slate-700 hover:text-white transition-colors"
              >
                ← All years
              </button>
              <div className="border-t border-slate-700" />

              {activeGroup && activeGroup.modules.length > 0 ? (
                activeGroup.modules.map((module) => (
                  <button
                    key={module.id}
                    onClick={() => handleSelectModule(module.name)}
                    className={`w-full px-4 py-3 text-left text-sm hover:bg-slate-700 transition-colors ${
                      selectedModule === module.name
                        ? 'bg-blue-600/20 text-blue-400'
                        : 'text-slate-200'
                    }`}
                  >
                    {module.name}
                  </button>
                ))
              ) : (
                <div className="px-4 py-3 text-sm text-slate-500">
                  No modules in {activeYear}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
