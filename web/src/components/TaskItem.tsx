import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import type { TaskEntity } from '../types';
import { useTasks } from '../hooks/useTasks';
import PriorityBadge from './PriorityBadge';
import { formatDate, isOverdue } from '../utils';
import styles from './TaskItem.module.css';

interface Props {
  task: TaskEntity;
  showPath?: boolean;
  showDescription?: boolean;
}

export default function TaskItem({ task, showPath, showDescription }: Props) {
  const navigate = useNavigate();
  const { getBreadcrumbs } = useTasks();
  const [path, setPath] = useState<string | null>(null);

  useEffect(() => {
    if (!showPath) return;
    let cancelled = false;
    getBreadcrumbs(task.id).then((crumbs) => {
      if (!cancelled) {
        setPath(
          crumbs
            .slice(0, -1)
            .map((t) => t.title)
            .join(' > '),
        );
      }
    });
    return () => { cancelled = true; };
  }, [showPath, task.id, getBreadcrumbs]);

  return (
    <div className={styles.card} onClick={() => navigate(`/tasks/${task.id}`)}>
      <div className={styles.content}>
        <div
          className={`${styles.title} ${task.status === 'CLOSED' ? styles.titleClosed : ''}`}
        >
          {task.title}
        </div>
        {showDescription && task.description && (
          <div className={styles.description}>{task.description}</div>
        )}
        {showPath && path && <div className={styles.path}>{path}</div>}
        <div className={styles.meta}>
          {task.dueDate != null && (
            <span
              className={`${styles.dueDate} ${isOverdue(task.dueDate) && task.status === 'PENDING' ? styles.dueDateOverdue : ''}`}
            >
              {formatDate(task.dueDate)}
            </span>
          )}
        </div>
      </div>
      <PriorityBadge priority={task.priority} />
      <span
        className={`${styles.statusDot} ${task.status === 'PENDING' ? styles.statusPending : styles.statusClosed}`}
      />
    </div>
  );
}
