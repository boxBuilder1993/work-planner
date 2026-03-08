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

  const path = showPath
    ? getBreadcrumbs(task.id)
        .slice(0, -1) // exclude self
        .map((t) => t.title)
        .join(' > ')
    : null;

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
