import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
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
  const navigate = useNavigate();
  const [rows, setRows] = useState<ScheduleRow[]>([]);
  const [people, setPeople] = useState<Person[]>([]);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [depsFor, setDepsFor] = useState<string | null>(null);
  const [deps, setDeps] = useState<planner.Dependency[]>([]);
  const [depErr, setDepErr] = useState<string | null>(null);
  const [draft, setDraft] = useState<{ parentId: string | null; title: string; estimate: string; assigneeId: string } | null>(null);

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

  // Begin an inline draft row under `parentId`, pre-filling the assignee from
  // the parent (cascade default). Nothing hits the backend until Save.
  const startDraft = (parentId: string | null) => {
    const parentRow = parentId ? rows.find((r) => r.taskId === parentId) : undefined;
    if (parentId) setCollapsed((prev) => { const n = new Set(prev); n.delete(parentId); return n; });
    setDraft({ parentId, title: '', estimate: '', assigneeId: parentRow?.assigneeId ?? '' });
  };
  const saveDraft = async () => {
    if (!draft || !draft.title.trim()) return;
    const created = await createTask({ title: draft.title.trim(), parentId: draft.parentId });
    if (draft.estimate !== '') await updateTask(created.id, { duration: Number(draft.estimate) });
    if (draft.assigneeId) await planner.updateTaskPlanner(created.id, { assigneeId: draft.assigneeId });
    setDraft(null);
    await reload();
  };
  const draftRow = (depth: number): React.ReactNode => (
    <tr key="__draft__" className={styles.draftRow}>
      <td style={{ paddingLeft: 8 + depth * 18 }}>
        <span className={styles.toggleSpacer} />
        <input autoFocus className={styles.txt} placeholder="New task title" value={draft!.title}
          onChange={(e) => setDraft({ ...draft!, title: e.target.value })}
          onKeyDown={(e) => { if (e.key === 'Enter') void saveDraft(); if (e.key === 'Escape') setDraft(null); }} />
        <button className={styles.saveBtn} onClick={() => void saveDraft()}>Save</button>
        <button className={styles.addBtn} onClick={() => setDraft(null)}>Cancel</button>
      </td>
      <td><input className={styles.numIn} type="number" min="0" placeholder="h" value={draft!.estimate}
        onChange={(e) => setDraft({ ...draft!, estimate: e.target.value })} /></td>
      <td>
        <select className={styles.sel} value={draft!.assigneeId} onChange={(e) => setDraft({ ...draft!, assigneeId: e.target.value })}>
          <option value="">— unassigned —</option>
          {people.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </td>
      <td colSpan={3} />
    </tr>
  );
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

  const titleOf = (id: string) => rows.find((r) => r.taskId === id)?.title ?? id.slice(0, 8);
  const openDeps = async (taskId: string) => {
    setDepsFor(taskId);
    setDepErr(null);
    setDeps(await planner.listDependencies(taskId));
  };
  const addDep = async (blockerId: string) => {
    if (!depsFor || !blockerId) return;
    try {
      await planner.createDependency(depsFor, blockerId);
      setDeps(await planner.listDependencies(depsFor));
      setDepErr(null);
      await reload();
    } catch {
      setDepErr('Could not add — that would create a cycle.');
    }
  };
  const removeDep = async (id: string) => {
    await planner.deleteDependency(id);
    if (depsFor) setDeps(await planner.listDependencies(depsFor));
    await reload();
  };

  const renderRows = (parentId: string | null, depth: number): React.ReactNode[] => {
    const kids = byParent.get(parentId) || [];
    const out: React.ReactNode[] = kids.flatMap((r) => {
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
            <span className={styles.taskLink} onClick={() => navigate(`/tasks/${r.taskId}`)}>{r.title}</span>
            <button className={styles.addBtn} title="Add subtask" onClick={() => startDraft(r.taskId)}>+sub</button>
            <button className={styles.addBtn} title="Add sibling" onClick={() => startDraft(r.parentId)}>+sib</button>
            <button className={styles.addBtn} title="Dependencies" onClick={() => openDeps(r.taskId)}>&#9741; deps</button>
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
    if (draft && draft.parentId === parentId) out.push(draftRow(depth));
    return out;
  };

  if (loading) return <p className={styles.muted}>Loading…</p>;

  const start = rootId ?? null;
  const topKids = byParent.get(start) || [];
  return (
    <div>
      <button className={styles.primary} onClick={() => startDraft(start)}>
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

      {depsFor && (
        <div className={styles.overlay} onClick={() => setDepsFor(null)}>
          <div className={styles.popup} onClick={(e) => e.stopPropagation()}>
            <h3>Blocked by — {titleOf(depsFor)}</h3>
            {deps.length === 0 && <p className={styles.muted}>No dependencies yet.</p>}
            {deps.map((d) => (
              <div key={d.id} className={styles.depRow}>
                <span>{titleOf(d.dependsOnId)}</span>
                <button className={styles.danger} onClick={() => removeDep(d.id)}>&times;</button>
              </div>
            ))}
            <div className={styles.formRow}>
              <select className={styles.sel} value="" onChange={(e) => { void addDep(e.target.value); }}>
                <option value="">+ add blocker…</option>
                {rows
                  .filter((r) => r.taskId !== depsFor && !deps.some((d) => d.dependsOnId === r.taskId))
                  .map((r) => <option key={r.taskId} value={r.taskId}>{r.title}</option>)}
              </select>
            </div>
            {depErr && <p className={styles.error}>{depErr}</p>}
            <button className={styles.primary} onClick={() => setDepsFor(null)}>Done</button>
          </div>
        </div>
      )}
    </div>
  );
}
