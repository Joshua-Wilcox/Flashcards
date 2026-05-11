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
        className={`w-full flex items-center justify-between px-5 py-4 bg-white border-2 border-gray-200 rounded-xl hover:border-blue-400 hover:shadow-sm transition-all ${
          disabled ? 'opacity-50 cursor-not-allowed' : ''
        } ${isOpen ? 'border-blue-500 shadow-sm' : ''}`}
      >
        <span className={selectedModule ? 'text-gray-900 font-semibold text-lg' : 'text-gray-400 text-lg'}>
          {buttonLabel}
        </span>
        <ChevronDown
          className={`h-5 w-5 text-gray-400 transition-transform ${isOpen ? 'rotate-180' : ''}`}
        />
      </button>

      {isOpen && (
        <div className="absolute z-50 mt-2 w-full max-h-80 overflow-y-auto rounded-xl bg-white shadow-lg">
          {!activeYear ? (
            <>
              {selectedModule && (
                <>
                  <button
                    onClick={handleClear}
                    className="w-full px-4 py-3 text-left text-sm text-gray-400 hover:bg-gray-50 hover:text-gray-700 transition-colors"
                  >
                    Clear selection
                  </button>
                  <div className="border-t border-gray-100" />
                </>
              )}

              {moduleGroups.length > 0 ? (
                moduleGroups.map((group) => (
                  <button
                    key={group.year}
                    onClick={() => setActiveYear(group.year)}
                    className="w-full flex items-center justify-between px-4 py-3.5 text-left hover:bg-gray-50 transition-colors"
                  >
                    <span className="text-sm font-semibold text-gray-900">{group.year}</span>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-gray-400">
                        {group.modules.length} module{group.modules.length !== 1 ? 's' : ''}
                      </span>
                      <span className="text-gray-300 text-sm">&#8250;</span>
                    </div>
                  </button>
                ))
              ) : (
                modules.map((module) => (
                  <button
                    key={module.id}
                    onClick={() => handleSelectModule(module.name)}
                    className={`w-full px-4 py-3 text-left text-sm hover:bg-gray-50 transition-colors ${
                      selectedModule === module.name
                        ? 'bg-blue-50 text-blue-700 font-medium'
                        : 'text-gray-700'
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
                className="w-full px-4 py-3 text-left text-sm text-gray-400 hover:bg-gray-50 hover:text-gray-700 transition-colors"
              >
                &larr; All years
              </button>
              <div className="border-t border-gray-100" />

              {activeGroup && activeGroup.modules.length > 0 ? (
                activeGroup.modules.map((module) => (
                  <button
                    key={module.id}
                    onClick={() => handleSelectModule(module.name)}
                    className={`w-full px-4 py-3 text-left text-sm hover:bg-gray-50 transition-colors ${
                      selectedModule === module.name
                        ? 'bg-blue-50 text-blue-700 font-medium'
                        : 'text-gray-700'
                    }`}
                  >
                    {module.name}
                  </button>
                ))
              ) : (
                <div className="px-4 py-3 text-sm text-gray-400">
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
