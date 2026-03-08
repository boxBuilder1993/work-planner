import { useState, useEffect, useCallback } from 'react';
import type { SearchFilters, StatusFilter, DueDateFilter } from '../types';
import { DEFAULT_SEARCH_FILTERS } from '../types';
import styles from './SearchFilterBar.module.css';

interface Props {
  onSearchChange: (query: string) => void;
  onFiltersChange: (filters: SearchFilters) => void;
}

export default function SearchFilterBar({ onSearchChange, onFiltersChange }: Props) {
  const [query, setQuery] = useState('');
  const [filters, setFilters] = useState<SearchFilters>(DEFAULT_SEARCH_FILTERS);

  // 300ms debounce for search
  useEffect(() => {
    const timer = setTimeout(() => onSearchChange(query), 300);
    return () => clearTimeout(timer);
  }, [query, onSearchChange]);

  const updateFilter = useCallback(
    <K extends keyof SearchFilters>(key: K, value: SearchFilters[K]) => {
      setFilters((prev) => {
        const next = { ...prev, [key]: value };
        onFiltersChange(next);
        return next;
      });
    },
    [onFiltersChange],
  );

  return (
    <div className={styles.container}>
      <input
        className={styles.searchInput}
        type="text"
        placeholder="Search tasks..."
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
      <div className={styles.filterRow}>
        {/* Status filter */}
        <div className={styles.filterGroup}>
          {(['ALL', 'PENDING', 'CLOSED'] as StatusFilter[]).map((s) => (
            <button
              key={s}
              className={`${styles.chip} ${filters.status === s ? styles.chipActive : ''}`}
              onClick={() => updateFilter('status', s)}
            >
              {s === 'ALL' ? 'All' : s === 'PENDING' ? 'Pending' : 'Closed'}
            </button>
          ))}
        </div>

        {/* Priority filter */}
        <div className={styles.filterGroup}>
          {[
            { label: 'All', min: 1, max: 5 },
            { label: '1', min: 1, max: 1 },
            { label: '1-2', min: 1, max: 2 },
            { label: '1-3', min: 1, max: 3 },
            { label: '4-5', min: 4, max: 5 },
          ].map((opt) => (
            <button
              key={opt.label}
              className={`${styles.chip} ${
                filters.minPriority === opt.min && filters.maxPriority === opt.max
                  ? styles.chipActive
                  : ''
              }`}
              onClick={() => {
                updateFilter('minPriority', opt.min);
                updateFilter('maxPriority', opt.max);
              }}
            >
              {opt.label === 'All' ? 'P: All' : `P: ${opt.label}`}
            </button>
          ))}
        </div>

        {/* Due date filter */}
        <div className={styles.filterGroup}>
          {(
            [
              { value: 'ANY', label: 'Any' },
              { value: 'HAS_DUE_DATE', label: 'Has date' },
              { value: 'OVERDUE', label: 'Overdue' },
              { value: 'NO_DUE_DATE', label: 'No date' },
            ] as { value: DueDateFilter; label: string }[]
          ).map((opt) => (
            <button
              key={opt.value}
              className={`${styles.chip} ${filters.dueDate === opt.value ? styles.chipActive : ''}`}
              onClick={() => updateFilter('dueDate', opt.value)}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
