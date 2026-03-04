// components/FilterDropdown.tsx
// Dropdown component for filtering schema vs data nodes

import React, { useState, useRef, useEffect } from "react";
import { Filter, Database, Boxes, Layers, ChevronDown } from "lucide-react";
import { FilterMode } from "@/lib/graph/schemaFilter";

interface FilterDropdownProps {
  currentMode: FilterMode;
  onModeChange: (mode: FilterMode) => void;
  nodeCounts?: {
    data: number;
    schema: number;
    agent: number;
    total: number;
  };
  disabled?: boolean;
}

const FILTER_OPTIONS: Array<{
  mode: FilterMode;
  label: string;
  description: string;
  icon: React.ReactNode;
}> = [
  {
    mode: 'data',
    label: 'Data Only',
    description: 'Show ingested artifacts and entities',
    icon: <Database className="w-4 h-4" />,
  },
  {
    mode: 'data_schema',
    label: 'Data + Schema',
    description: 'Include ontology concepts and taxonomies',
    icon: <Boxes className="w-4 h-4" />,
  },
  {
    mode: 'all',
    label: 'All Nodes',
    description: 'Show everything including agents',
    icon: <Layers className="w-4 h-4" />,
  },
];

export const FilterDropdown: React.FC<FilterDropdownProps> = ({
  currentMode,
  onModeChange,
  nodeCounts,
  disabled = false,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const currentOption = FILTER_OPTIONS.find(opt => opt.mode === currentMode) || FILTER_OPTIONS[0];

  const getCountForMode = (mode: FilterMode): number => {
    if (!nodeCounts) return 0;
    switch (mode) {
      case 'data':
        return nodeCounts.data;
      case 'data_schema':
        return nodeCounts.data + nodeCounts.schema;
      case 'all':
        return nodeCounts.total;
      default:
        return 0;
    }
  };

  return (
    <div className="relative" ref={dropdownRef}>
      {/* Trigger Button */}
      <button
        onClick={() => !disabled && setIsOpen(!isOpen)}
        disabled={disabled}
        className={`
          flex items-center gap-2 px-3 py-1.5 rounded-lg border
          transition-all duration-200
          ${disabled 
            ? 'bg-gray-100 text-gray-400 cursor-not-allowed border-gray-200' 
            : 'bg-white hover:bg-gray-50 text-gray-700 border-gray-300 hover:border-gray-400'
          }
        `}
      >
        <Filter className="w-4 h-4" />
        <span className="text-sm font-medium">{currentOption.label}</span>
        {nodeCounts && (
          <span className="text-xs text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded">
            {getCountForMode(currentMode)}
          </span>
        )}
        <ChevronDown className={`w-4 h-4 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {/* Dropdown Menu */}
      {isOpen && (
        <div className="absolute top-full left-0 mt-1 w-64 bg-white border border-gray-200 rounded-lg shadow-lg z-50 overflow-hidden">
          <div className="p-2 border-b border-gray-100 bg-gray-50">
            <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
              Filter Nodes
            </span>
          </div>
          
          <div className="py-1">
            {FILTER_OPTIONS.map((option) => {
              const isSelected = option.mode === currentMode;
              const count = getCountForMode(option.mode);
              
              return (
                <button
                  key={option.mode}
                  onClick={() => {
                    onModeChange(option.mode);
                    setIsOpen(false);
                  }}
                  className={`
                    w-full px-3 py-2 flex items-start gap-3 text-left
                    transition-colors duration-150
                    ${isSelected 
                      ? 'bg-blue-50 text-blue-700' 
                      : 'hover:bg-gray-50 text-gray-700'
                    }
                  `}
                >
                  <div className={`mt-0.5 ${isSelected ? 'text-blue-600' : 'text-gray-400'}`}>
                    {option.icon}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                      <span className={`text-sm font-medium ${isSelected ? 'text-blue-700' : ''}`}>
                        {option.label}
                      </span>
                      <span className={`text-xs px-1.5 py-0.5 rounded ${
                        isSelected 
                          ? 'bg-blue-100 text-blue-600' 
                          : 'bg-gray-100 text-gray-500'
                      }`}>
                        {count}
                      </span>
                    </div>
                    <p className="text-xs text-gray-500 mt-0.5">
                      {option.description}
                    </p>
                  </div>
                  {isSelected && (
                    <div className="mt-0.5">
                      <div className="w-2 h-2 rounded-full bg-blue-600" />
                    </div>
                  )}
                </button>
              );
            })}
          </div>

          {/* Node breakdown footer */}
          {nodeCounts && (
            <div className="p-2 border-t border-gray-100 bg-gray-50">
              <div className="flex items-center justify-between text-xs text-gray-500">
                <span>Data: {nodeCounts.data}</span>
                <span>Schema: {nodeCounts.schema}</span>
                {nodeCounts.agent > 0 && <span>Agents: {nodeCounts.agent}</span>}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default FilterDropdown;