import { PRIORITY_COLORS } from '../types';
import styles from './PriorityBadge.module.css';

interface Props {
  priority: number;
}

export default function PriorityBadge({ priority }: Props) {
  const color = PRIORITY_COLORS[priority] ?? PRIORITY_COLORS[3];
  return (
    <span className={styles.badge} style={{ backgroundColor: color }}>
      {priority}
    </span>
  );
}
