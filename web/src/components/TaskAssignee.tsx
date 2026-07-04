import { useState, useEffect } from 'react';
import * as planner from '../api/planner';
import type { Person } from '../api/planner';
import styles from './Planner.module.css';

/** Set a task's assignee directly from its detail page. */
export default function TaskAssignee({ taskId }: { taskId: string }) {
  const [people, setPeople] = useState<Person[]>([]);
  const [assigneeId, setAssigneeId] = useState<string>('');

  useEffect(() => {
    let cancelled = false;
    Promise.all([planner.listPeople(), planner.getSchedule()]).then(([p, s]) => {
      if (cancelled) return;
      setPeople(p);
      const row = s.find((r) => r.taskId === taskId);
      setAssigneeId(row?.assigneeId ?? '');
    });
    return () => { cancelled = true; };
  }, [taskId]);

  const onChange = async (a: string) => {
    setAssigneeId(a);
    await planner.updateTaskPlanner(taskId, { assigneeId: a });
  };

  return (
    <div className={styles.formRow}>
      <span className={styles.muted}>Assignee</span>
      <select className={styles.sel} value={assigneeId} onChange={(e) => onChange(e.target.value)}>
        <option value="">— unassigned —</option>
        {people.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
      </select>
    </div>
  );
}
