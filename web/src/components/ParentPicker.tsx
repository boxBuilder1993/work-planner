import { useState, useMemo, useEffect } from 'react';
import { useTasks } from '../hooks/useTasks';
import type { TaskEntity } from '../types';
import styles from './ParentPicker.module.css';

interface Props {
  currentTaskId: string;
  currentParentId: string | null;
  onSelect: (parentId: string | null) => void;
  onClose: () => void;
}

export default function ParentPicker({
  currentTaskId,
  currentParentId,
  onSelect,
  onClose,
}: Props) {
  const { getAllTasks, getDescendantIds, getBreadcrumbs } = useTasks();
  const [search, setSearch] = useState('');
  const [pathMap, setPathMap] = useState<Record<string, string>>({});

  const eligibleTasks = useMemo(() => {
    const allTasks = getAllTasks();
    const descendantIds = getDescendantIds(currentTaskId);
    const eligible: TaskEntity[] = [];

    for (const task of allTasks.values()) {
      // Exclude: self, descendants, CLOSED tasks
      if (
        task.id === currentTaskId ||
        descendantIds.has(task.id) ||
        task.status === 'CLOSED'
      ) {
        continue;
      }
      eligible.push(task);
    }

    if (search.trim()) {
      const lower = search.toLowerCase();
      return eligible.filter((t) => t.title.toLowerCase().includes(lower));
    }

    return eligible.sort((a, b) => a.title.localeCompare(b.title));
  }, [getAllTasks, getDescendantIds, currentTaskId, search]);

  // Load breadcrumb paths for eligible tasks
  useEffect(() => {
    let cancelled = false;
    for (const task of eligibleTasks) {
      if (pathMap[task.id] !== undefined) continue;
      getBreadcrumbs(task.id).then((crumbs) => {
        if (cancelled) return;
        setPathMap((prev) => ({
          ...prev,
          [task.id]: crumbs.map((t) => t.title).join(' > '),
        }));
      });
    }
    return () => { cancelled = true; };
  }, [eligibleTasks, getBreadcrumbs, pathMap]);

  const getPath = (taskId: string): string => pathMap[taskId] ?? '';

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <div className={styles.header}>
          <span className={styles.title}>Select Parent</span>
          <button className={styles.closeButton} onClick={onClose}>
            &times;
          </button>
        </div>
        <input
          className={styles.searchInput}
          type="text"
          placeholder="Search tasks..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          autoFocus
        />
        <div className={styles.list}>
          {/* None option */}
          <button
            className={`${styles.option} ${currentParentId === null ? styles.optionSelected : ''}`}
            onClick={() => onSelect(null)}
          >
            <span className={styles.checkmark}>
              {currentParentId === null ? '\u2713' : ''}
            </span>
            None (root-level theme)
          </button>
          {eligibleTasks.map((task) => (
            <button
              key={task.id}
              className={`${styles.option} ${currentParentId === task.id ? styles.optionSelected : ''}`}
              onClick={() => onSelect(task.id)}
            >
              <span className={styles.checkmark}>
                {currentParentId === task.id ? '\u2713' : ''}
              </span>
              <span>
                {task.title}
                <span className={styles.optionPath}>{getPath(task.id)}</span>
              </span>
            </button>
          ))}
          {eligibleTasks.length === 0 && search && (
            <div className={styles.empty}>No matching tasks</div>
          )}
        </div>
      </div>
    </div>
  );
}
