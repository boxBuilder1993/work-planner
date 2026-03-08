import { useState, useCallback, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import type { Tab, SearchFilters, TaskEntity } from '../types';
import { DEFAULT_SEARCH_FILTERS } from '../types';
import { useTasks } from '../hooks/useTasks';
import { isOverdue } from '../utils';
import TaskItem from './TaskItem';
import SearchFilterBar from './SearchFilterBar';
import styles from './TaskList.module.css';

export default function TaskList() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get('tab') as Tab | null;
  const activeTab: Tab = tabParam === 'ACTIONABLE' || tabParam === 'SEARCH' ? tabParam : 'THEMES';

  const { getPendingRootTasks, getLeafTasks, searchTasks } = useTasks();

  const [searchQuery, setSearchQuery] = useState('');
  const [filters, setFilters] = useState<SearchFilters>(DEFAULT_SEARCH_FILTERS);

  const setTab = useCallback(
    (tab: Tab) => {
      setSearchParams({ tab });
    },
    [setSearchParams],
  );

  const themeTasks = useMemo(() => getPendingRootTasks(), [getPendingRootTasks]);
  const actionableTasks = useMemo(() => getLeafTasks(), [getLeafTasks]);
  const searchResults = useMemo(() => {
    let results = searchTasks(searchQuery);
    results = applyFilters(results, filters);
    return results;
  }, [searchTasks, searchQuery, filters]);

  return (
    <div className={styles.page}>
      <div className={styles.topBar}>
        <span className={styles.topBarTitle}>WorkPlanner</span>
        <button
          className={styles.settingsButton}
          onClick={() => navigate('/settings')}
          aria-label="Settings"
        >
          &#9881;
        </button>
      </div>

      <div className={styles.tabBar}>
        {(['THEMES', 'ACTIONABLE', 'SEARCH'] as Tab[]).map((tab) => (
          <button
            key={tab}
            className={`${styles.tab} ${activeTab === tab ? styles.tabActive : ''}`}
            onClick={() => setTab(tab)}
          >
            {tab === 'THEMES' ? 'Themes' : tab === 'ACTIONABLE' ? 'Actionable' : 'Search'}
          </button>
        ))}
      </div>

      <div className={styles.content}>
        {activeTab === 'THEMES' && (
          <div className={styles.taskList}>
            {themeTasks.length === 0 ? (
              <div className={styles.empty}>No themes yet. Create one!</div>
            ) : (
              themeTasks.map((task) => (
                <TaskItem key={task.id} task={task} showDescription />
              ))
            )}
          </div>
        )}

        {activeTab === 'ACTIONABLE' && (
          <div className={styles.taskList}>
            {actionableTasks.length === 0 ? (
              <div className={styles.empty}>No actionable tasks</div>
            ) : (
              actionableTasks.map((task) => (
                <TaskItem key={task.id} task={task} showPath />
              ))
            )}
          </div>
        )}

        {activeTab === 'SEARCH' && (
          <>
            <SearchFilterBar
              onSearchChange={setSearchQuery}
              onFiltersChange={setFilters}
            />
            <div className={styles.taskList}>
              {searchQuery && searchResults.length === 0 ? (
                <div className={styles.empty}>No matching tasks</div>
              ) : (
                searchResults.map((task) => (
                  <TaskItem key={task.id} task={task} showPath />
                ))
              )}
            </div>
          </>
        )}
      </div>

      {activeTab === 'THEMES' && (
        <button
          className={styles.fab}
          onClick={() => navigate('/tasks/new')}
          aria-label="Add task"
        >
          +
        </button>
      )}
    </div>
  );
}

function applyFilters(tasks: TaskEntity[], filters: SearchFilters): TaskEntity[] {
  return tasks.filter((task) => {
    // Status filter
    if (filters.status !== 'ALL' && task.status !== filters.status) return false;

    // Priority range filter
    if (task.priority < filters.minPriority || task.priority > filters.maxPriority) return false;

    // Due date filter
    switch (filters.dueDate) {
      case 'HAS_DUE_DATE':
        if (task.dueDate === null) return false;
        break;
      case 'OVERDUE':
        if (task.dueDate === null || !isOverdue(task.dueDate)) return false;
        break;
      case 'NO_DUE_DATE':
        if (task.dueDate !== null) return false;
        break;
    }

    return true;
  });
}
