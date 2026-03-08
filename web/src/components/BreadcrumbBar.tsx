import { useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import type { TaskEntity } from '../types';
import styles from './BreadcrumbBar.module.css';

interface Props {
  breadcrumbs: TaskEntity[];
}

export default function BreadcrumbBar({ breadcrumbs }: Props) {
  const navigate = useNavigate();
  const barRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to end
  useEffect(() => {
    if (barRef.current) {
      barRef.current.scrollLeft = barRef.current.scrollWidth;
    }
  }, [breadcrumbs]);

  return (
    <div className={styles.bar} ref={barRef}>
      <button
        className={styles.crumb}
        onClick={() => navigate('/tasks?tab=THEMES')}
      >
        Root
      </button>
      {breadcrumbs.map((task, i) => {
        const isLast = i === breadcrumbs.length - 1;
        return (
          <span key={task.id} style={{ display: 'contents' }}>
            <span className={styles.separator}>&gt;</span>
            <button
              className={`${styles.crumb} ${isLast ? styles.crumbCurrent : ''}`}
              onClick={isLast ? undefined : () => navigate(`/tasks/${task.id}`)}
              disabled={isLast}
            >
              {task.title}
            </button>
          </span>
        );
      })}
    </div>
  );
}
