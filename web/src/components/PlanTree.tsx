import { useState, useEffect, useCallback } from 'react';
import { createTask, updateTask } from '../api/tasks';
import * as planner from '../api/planner';
import type { Person, ScheduleRow } from '../api/planner';
import styles from './Planner.module.css';

/**
 * Editable WBS tree-table. A "project" is just a task, so the same tree renders
 * the whole workspace (rootId undefined → forest of root tasks) or a single
 * task's subtree (rootId set → that task's descendants, e.g. on the task page).
 */
export default function PlanTree({ rootId }: { rootId?: string }) {
  const [rows, setRows] = useState<ScheduleRow[]>([]);
  const [people, setPeople] = useState<Person[]>([]);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    const [s, p] = await Promise.all([planner.getSchedule(), planner.listPeople()]);
    setRows(s);
    setPeople(p);
    setLoading(false);
  }, []);
  useEffect(() => { void reload(); }, [reload]);

  const byParent = new Map<string | null, ScheduleRow[]>();
  for (const r of rows) {
    const k = r.parentId;
    if (!byParent.has(k)) byParent.set(k, []);
    byParent.get(k)!.push(r);
  }

  const addTask = async (parentId: string | null) => {
    const title = window.prompt('Task title');
    if (!title) return;
    await createTask({ title, parentId });
    await reload();
  };
  const setEstimate = async (id: string, v: string) => {
    await updateTask(id, { duration: v === '' ? null : Number(v) });
    await reload();
  };
  const setAssignee = async (id: string, a: string) => {
    await planner.updateTaskPlanner(id, { assigneeId: a });
    await reload();
  };
  const toggle = (id: string) =>
    setCollapsed((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });

  const renderRows = (parentId: string | null, depth: number): React.ReactNode[] => {
    const kids = byParent.get(parentId) || [];
    return kids.flatMap((r) => {
      const hasChildren = (byParent.get(r.taskId) || []).length > 0;
      const isCollapsed = collapsed.has(r.taskId);
      const row = (
        <tr key={r.taskId} className={r.onCriticalPath ? styles.critical : undefined}>
          <td style={{ paddingLeft: 8 + depth * 18 }}>
            {hasChildren ? (
              <button className={styles.toggle} onClick={() => toggle(r.taskId)}>{isCollapsed ? '▸' : '▾'}</button>
            ) : (
              <span className={styles.toggleSpacer} />
            )}
            {r.title}
            <button className={styles.addBtn} title="Add subtask" onClick={() => addTask(r.taskId)}>+sub</button>
            <button className={styles.addBtn} title="Add sibling" onClick={() => addTask(r.parentId)}>+sib</button>
          </td>
          <td>
            {hasChildren ? (
              <span className={styles.muted}>{r.estimateHours ?? '—'}</span>
            ) : (
              <input className={styles.numIn} type="number" min="0" defaultValue={r.estimateHours ?? ''}
                onBlur={(e) => setEstimate(r.taskId, e.target.value)} />
            )}
          </td>
          <td>
            <select className={styles.sel} value={r.assigneeId ?? ''} onChange={(e) => setAssignee(r.taskId, e.target.value)}>
              <option value="">— unassigned —</option>
              {people.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </td>
          <td className={styles.date}>{r.start || '—'}</td>
          <td className={styles.date}>{r.end || '—'}</td>
          <td className={styles.cp}>{r.onCriticalPath ? '★' : ''}</td>
        </tr>
      );
      return hasChildren && !isCollapsed ? [row, ...renderRows(r.taskId, depth + 1)] : [row];
    });
  };

  if (loading) return <p className={styles.muted}>Loading…</p>;

  const start = rootId ?? null;
  const topKids = byParent.get(start) || [];
  return (
    <div>
      <button className={styles.primary} onClick={() => addTask(start)}>
        + {rootId ? 'Subtask' : 'Project'}
      </button>
      <table className={styles.table}>
        <thead>
          <tr><th>Task</th><th>Est (h)</th><th>Assignee</th><th>Start</th><th>End</th><th>CP</th></tr>
        </thead>
        <tbody>{renderRows(start, 0)}</tbody>
      </table>
      {topKids.length === 0 && (
        <p className={styles.muted}>{rootId ? 'No subtasks yet.' : 'No tasks yet. Add a project to begin.'}</p>
      )}
    </div>
  );
}
